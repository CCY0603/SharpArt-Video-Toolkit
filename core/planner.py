"""编码规划：码率计算、ffmpeg 参数生成、输出路径与体积预估。"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.config import CONTAINER_OVERHEAD, MIN_VIDEO_BITRATE, NULL_DEVICE, CRF_MIN, CRF_MAX
from core.capabilities import Capabilities
from core.models import CourseParams, EncodeParams, TaskItem, VideoInfo
from core.profiles import (
    CONTAINER_MAP,
    ENCODER_MAP,
    PRO_PRESET_MAP,
    RESOLUTION_MAP,
    container_for_extension,
)
from core.utils import safe_filename, unique_path

# CRF → 每像素比特数（经验值，用于体积预估）
CRF_BPP = [(16, 0.155), (18, 0.115), (20, 0.082), (22, 0.061),
           (24, 0.046), (26, 0.035), (28, 0.026), (32, 0.016)]

# 课程压缩专用预设标记：写入 params.preset_name 以区别于专业/设备预设，
# 并触发 planner 的 -minrate 码率下限逻辑
COURSE_PRESET_NAME = "__course__"


def _bpp_for_crf(crf: int) -> float:
    if crf <= CRF_BPP[0][0]:
        return CRF_BPP[0][1]
    for (c1, b1), (c2, b2) in zip(CRF_BPP, CRF_BPP[1:]):
        if c1 <= crf <= c2:
            ratio = (crf - c1) / (c2 - c1)
            return b1 + (b2 - b1) * ratio
    return CRF_BPP[-1][1]


# ------------------------------------------------------------------ 推荐 CRF
def suggest_crf_for(info: VideoInfo) -> int:
    """按分辨率、HDR、帧率推荐一个「肉眼难辨」的 CRF/CQ 值（数值越小画质越高）。

    经验档位（仅软件/硬件 H.264/H.265 通用基线）：
      4K(≥2160) → 22，2K/1440p → 21，1080p → 20，720p → 23，<720p → 24
    HDR 或帧率 > 30 时各 +1，避免运动/高动态细节丢失；最终夹在合法范围 [CRF_MIN, CRF_MAX]。
    """
    height = max(info.height, 360)
    if height >= 2160:
        crf = 22
    elif height >= 1440:
        crf = 21
    elif height >= 1080:
        crf = 20
    elif height >= 720:
        crf = 23
    else:
        crf = 24
    if info.hdr_type != "SDR":
        crf += 1
    if (info.fps or 0.0) > 30:
        crf += 1
    return max(min(crf, CRF_MAX), CRF_MIN)


def _follow_audio_kbps(video_bps: int) -> int:
    """跟随压缩：按视频目标码率动态选择音频码率（kbps）。

    视频目标码率 < 500 kbps 时用 64 kbps（避免音频喧宾夺主、整体体积被拉高），
    否则用 128 kbps（兼顾清晰度）。返回值单位为 kbps。
    """
    return 64 if video_bps < 500_000 else 128


@dataclass
class BitratePlan:
    mode: str = "absolute"
    target_bytes: int = 0
    target_total_bps: int = 0
    audio_bps: int = 0
    video_bps: int = 0
    two_pass: bool = False
    total_passes: int = 1
    warning: str = ""
    min_bytes: int = 0
    max_bytes: int = 0
    ratio: float = 0.0
    encoder: str = ""
    note: str = ""


# ------------------------------------------------------------------ 音频码率
def planned_audio_bps(info: VideoInfo, params: EncodeParams) -> int:
    if not info.has_audio:
        return 0
    mode = params.audio_mode
    if mode == "copy":
        return info.a_bitrate or 128_000
    if mode == "flac":
        # 无损压缩约为 PCM 的 55%
        return int((info.a_sample_rate or 48000) * 16 * (info.a_channels or 2) * 0.55)
    if mode == "wav":
        return int((info.a_sample_rate or 48000) * 16 * (info.a_channels or 2))
    return params.audio_bitrate or 192_000


def estimate_crf_bitrate(info: VideoInfo, encoder: str, crf: int) -> int:
    """按分辨率、帧率与 CRF 估算视频码率。"""
    if not info.width or not info.height:
        return 2_000_000
    fps = info.fps or 25.0
    bpp = _bpp_for_crf(crf)
    if "264" in encoder or "h264" in encoder:
        bpp *= 1.32
    bitrate = info.width * info.height * fps * bpp
    # 高帧率轻微折扣，低帧率略增
    if fps > 30:
        bitrate *= (fps / 30.0) ** 0.35
    return max(int(bitrate), 200_000)


# ------------------------------------------------------------------ 目标字节
def target_bytes_for(info: VideoInfo, params: EncodeParams) -> int:
    if params.size_mode == "absolute":
        return max(int(params.target_bytes), 0)
    if params.size_mode == "percent":
        return int(info.size_bytes * max(min(params.percent, 300), 1) / 100.0)
    return 0


def compute_bitrate_plan(info: VideoInfo, params: EncodeParams, caps: Optional[Capabilities] = None) -> BitratePlan:
    """计算目标码率、是否两遍编码，并给出低码率警告与预估区间。"""
    plan = BitratePlan(mode=params.size_mode)
    duration = max(info.duration, 0.1)
    preset = PRO_PRESET_MAP.get(params.preset_name)

    if params.size_mode == "streamcopy":
        # #10：仅转换封装格式，不重新编码 —— 无损且极快，体积基本不变
        plan.video_bps = 0
        plan.two_pass = False
        plan.total_passes = 1
        plan.min_bytes = info.size_bytes
        plan.max_bytes = info.size_bytes
        plan.ratio = 1.0
        plan.note = "仅转换封装：不重新编码，画质无损，速度最快"
        return plan

    audio_bps = planned_audio_bps(info, params)
    plan.audio_bps = audio_bps
    plan.encoder = params.encoder

    if preset is not None:
        # 专业格式为质量优先，不做体积控制
        plan.video_bps = 0
        plan.two_pass = False
        plan.total_passes = 1
        plan.min_bytes = int(info.size_bytes * 1.5)
        plan.max_bytes = int(info.size_bytes * 6)
        plan.ratio = plan.min_bytes / info.size_bytes if info.size_bytes else 0
        plan.note = f"{preset.label}：画质优先，体积随素材而定"
        return plan

    if params.size_mode == "crf":
        video_bps = estimate_crf_bitrate(info, params.encoder, params.crf)
        estimated_total = (video_bps + audio_bps) * duration / 8.0
        plan.target_bytes = int(estimated_total)
        plan.target_total_bps = int((video_bps + audio_bps))
        plan.video_bps = video_bps
        if params.audio_mode == "follow":
            plan.audio_bps = _follow_audio_kbps(video_bps) * 1000
        plan.two_pass = False
        plan.total_passes = 1
        plan.min_bytes = int(estimated_total * 0.75)
        plan.max_bytes = int(estimated_total * 1.35)
        plan.ratio = estimated_total / info.size_bytes if info.size_bytes else 0
        return plan

    target_bytes = target_bytes_for(info, params)
    plan.target_bytes = target_bytes
    target_total_bps = int(target_bytes * 8 / duration * (1 - CONTAINER_OVERHEAD))
    plan.target_total_bps = max(target_total_bps, 0)
    video_bps = plan.target_total_bps - audio_bps
    plan.video_bps = video_bps
    if params.audio_mode == "follow":
        plan.audio_bps = _follow_audio_kbps(video_bps) * 1000

    spec = ENCODER_MAP.get(params.encoder)
    two_pass = bool(
        params.two_pass
        and spec is not None
        and spec.supports_two_pass
        and video_bps > 0
    )
    plan.two_pass = two_pass
    plan.total_passes = 2 if two_pass else 1

    if video_bps < MIN_VIDEO_BITRATE:
        suggested = suggested_min_bytes(info, audio_bps)
        plan.warning = (
            f"目标过小：按当前设置视频码率仅 {video_bps // 1000} kbps（低于 500 kbps），"
            f"画质将明显下降。建议目标不小于 {format_size_text(suggested)}。"
        )
        plan.video_bps = max(video_bps, 120_000)

    plan.min_bytes = int(target_bytes * 0.97)
    plan.max_bytes = int(target_bytes * 1.03)
    if video_bps < MIN_VIDEO_BITRATE:
        plan.min_bytes = int(target_bytes * 0.9)
        plan.max_bytes = int(target_bytes * 1.12)
    plan.ratio = target_bytes / info.size_bytes if info.size_bytes else 0
    return plan


def format_size_text(num_bytes: float) -> str:
    from core.utils import format_size
    return format_size(num_bytes)


def suggested_min_bytes(info: VideoInfo, audio_bps: int) -> int:
    """视频码率 500 kbps 时对应的最小可行目标体积。"""
    duration = max(info.duration, 0.1)
    total_bps = (MIN_VIDEO_BITRATE + audio_bps) / (1 - CONTAINER_OVERHEAD)
    return int(total_bps * duration / 8.0)


# ------------------------------------------------------------------ 命令构建
def _resolution_target(params: EncodeParams) -> "tuple[int, int]":
    """解析目标分辨率上限 (w, h)。

    - resolution != "origin"：优先用分辨率表（UI 下拉框选择，如 1080p→1920x1080）
    - origin：沿用 max_width/max_height（设备预设等场景）
    返回 (0, 0) 表示保持原分辨率。
    """
    if params.resolution and params.resolution != "origin":
        return RESOLUTION_MAP.get(params.resolution, (0, 0))
    return (params.max_width, params.max_height)


def _scale_filter(info: VideoInfo, params: EncodeParams) -> List[str]:
    """按目标分辨率上限缩放，保持原宽高比并强制偶数对齐（防止 HEVC/NVENC 因奇数维度报错）。

    - force_original_aspect_ratio=decrease：在目标框内等比缩小，不拉伸变形
    - trunc(iw/2)*2:trunc(ih/2)*2：等价于 scale=W:-2 的偶数对齐作用，确保宽高均为偶数
    仅当源尺寸大于目标时才缩放，绝不放大（如 720p 源选 1080p 保持原样）。
    """
    filters: List[str] = []
    width, height = info.width, info.height
    if not width or not height:
        return filters
    target_w, target_h = _resolution_target(params)
    if target_w and target_h and (width > target_w or height > target_h):
        filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease")
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    return filters


def _target_pix_fmt(info: VideoInfo, params: EncodeParams, encoder: str) -> str:
    preset = PRO_PRESET_MAP.get(params.preset_name)
    if preset is not None and preset.pix_fmt:
        return preset.pix_fmt
    spec = ENCODER_MAP.get(encoder)
    ten_bit = (info.bit_depth >= 10 or info.hdr_type != "SDR") and spec is not None and spec.supports_10bit
    if info.has_alpha and params.preset_name.startswith("alpha"):
        return "yuva444p10le" if ten_bit else "yuva420p"
    if params.keep_hdr and info.hdr_type != "SDR" and spec is not None and spec.supports_10bit:
        return "yuv420p10le"
    return "yuv420p10le" if ten_bit else "yuv420p"


def _rate_control_args(info: VideoInfo, params: EncodeParams, plan: BitratePlan, encoder: str) -> List[str]:
    args: List[str] = []
    spec = ENCODER_MAP.get(encoder)
    is_gpu = spec is not None and spec.mode == "gpu"

    if params.size_mode == "crf":
        if is_gpu:
            if "nvenc" in encoder:
                args += ["-rc", "constqp", "-cq", str(params.crf)]
            elif "amf" in encoder:
                args += ["-rc", "cqp", "-qp_p", str(params.crf), "-qp_i", str(params.crf)]
            else:  # qsv
                args += ["-global_quality", str(params.crf)]
        else:
            args += ["-crf", str(params.crf)]
        if not is_gpu:
            args += ["-preset", "medium"]
        return args

    # 目标大小 / 百分比：码率控制
    video_bps = max(plan.video_bps, 100_000)
    if is_gpu:
        if "nvenc" in encoder:
            args += ["-preset", "p4", "-rc", "vbr", "-b:v", str(video_bps),
                     "-maxrate", str(int(video_bps * 1.6)), "-bufsize", str(int(video_bps * 2))]
        elif "amf" in encoder:
            args += ["-usage", "transcoding", "-quality", "balanced", "-rc", "vbr_peak",
                     "-b:v", str(video_bps), "-maxrate", str(int(video_bps * 1.6))]
        else:  # qsv
            args += ["-preset", "medium", "-b:v", str(video_bps),
                     "-maxrate", str(int(video_bps * 1.6)), "-bufsize", str(int(video_bps * 2))]
        return args

    # 课程压缩（单遍 + 课程预设）：先把目标码率抬到用户设定下限并预留 1% 余量，
    # 再统一写入 -b:v / -minrate / -maxrate，保证三者一致。否则 -b:v 用的是
    # 未抬高的旧值，而 -minrate/-maxrate 用抬高后的新值，出现 minrate > b:v，
    # 与 x264 严格 CBR（nal-hrd=cbr）的预期矛盾。
    is_course = (not plan.two_pass) and params.preset_name == COURSE_PRESET_NAME
    if is_course:
        video_bps = max(video_bps, params.min_video_bitrate or video_bps)
        video_bps = int(video_bps * 1.01)

    args += ["-preset", "medium", "-b:v", str(video_bps)]
    if not plan.two_pass:
        if is_course:
            # 严格 CBR：强制 libx264 填充 filler，确保平均码率不随画面复杂度 undershoot。
            args += ["-minrate:v", str(video_bps),
                     "-maxrate:v", str(video_bps),
                     "-bufsize:v", str(int(video_bps)),
                     "-x264-params", "nal-hrd=cbr:filler=1"]
        else:
            args += ["-maxrate", str(int(video_bps * 1.5)), "-bufsize", str(int(video_bps * 2))]
    return args


def _video_args(info: VideoInfo, params: EncodeParams, plan: BitratePlan, encoder: str, caps) -> List[str]:
    if params.size_mode == "streamcopy":
        # 仅转封装：视频流直接复制，且不能附加任何编码参数（copy 模式下会报错）
        return ["-c:v", "copy"]

    preset = PRO_PRESET_MAP.get(params.preset_name)
    args: List[str] = ["-c:v", encoder]

    if preset is not None:
        if preset.kind == "prores":
            args += ["-profile:v", preset.profile]
        elif preset.kind == "dnxhr":
            args += ["-profile:v", preset.profile]
        if preset.pix_fmt:
            args += ["-pix_fmt", preset.pix_fmt]
        args += list(preset.extra)
        if preset.kind == "prores":
            args += ["-vendor", "apl0"]
        return args

    args += _rate_control_args(info, params, plan, encoder)
    args += ["-pix_fmt", _target_pix_fmt(info, params, encoder)]

    spec = ENCODER_MAP.get(encoder)
    if spec is not None and spec.codec == "hevc" and params.container in ("mp4", "mov"):
        args += ["-tag:v", "hvc1"]

    if params.keep_hdr and info.hdr_type != "SDR" and spec is not None and spec.codec == "hevc":
        transfer = "arib-std-b67" if info.hdr_type == "HLG" else "smpte2084"
        args += ["-color_primaries", "bt2020", "-color_trc", transfer, "-colorspace", "bt2020nc"]
    return args


def _audio_args(info: VideoInfo, params: EncodeParams, plan: "Optional[BitratePlan]" = None, caps=None) -> List[str]:
    container = CONTAINER_MAP.get(params.container)
    supported = container.audio_codecs if container else ["aac", "copy"]
    if not info.has_audio:
        return ["-an"]

    mode = params.audio_mode
    if mode == "follow":
        # 跟随压缩：按视频目标码率动态选 64k/128k（<500k→64k，否则 128k）。
        # 必须在通用兼容重映射之前处理，否则 mode 会被改成 "aac" 而丢失 follow 语义。
        # 仅转格式（streamcopy）时视频不重编码，音频也直接复制；容器不支持 aac 时降级 copy。
        if params.size_mode == "streamcopy" or "aac" not in supported:
            return ["-c:a", "copy"]
        if caps is not None and not caps.has_encoder("aac"):
            return ["-c:a", "copy"]
        k = _follow_audio_kbps(plan.video_bps if plan is not None else 0)
        args = ["-c:a", "aac", "-b:a", f"{k * 1000}"]
        if params.audio_sample_rate:
            args += ["-ar", str(params.audio_sample_rate)]
        return args

    if mode == "copy" and "copy" not in supported:
        mode = "aac"
    if mode != "copy" and mode not in supported:
        mode = "aac" if "aac" in supported else "copy"

    if mode == "copy":
        # 源音轨编码不被容器支持时降级重编
        source_codec = (info.a_codec or "").lower()
        incompatible = (
            (params.container in ("mp4", "mov") and source_codec in ("flac", "vorbis", "opus", "wmav2"))
            or (params.container == "webm" and source_codec not in ("opus", "vorbis"))
            or (params.container in ("avi", "flv") and source_codec not in ("mp3", "aac"))
        )
        if incompatible:
            mode = "aac" if "aac" in supported else "copy"
    if mode == "copy":
        return ["-c:a", "copy"]

    from core.profiles import AUDIO_ENCODERS
    encoder = AUDIO_ENCODERS.get(mode, "aac")
    if caps is not None and not caps.has_encoder(encoder):
        return ["-c:a", "copy"]
    if mode in ("aac", "mp3"):
        ab = params.audio_bitrate or 192_000
        args = ["-c:a", encoder, "-b:a", str(ab)]
        if params.audio_sample_rate:
            args += ["-ar", str(params.audio_sample_rate)]
        return args
    return ["-c:a", encoder]


def build_ffmpeg_args(
    info: VideoInfo,
    params: EncodeParams,
    output: str,
    pass_no: int = 0,
    passlogfile: str = "",
    caps: Optional[Capabilities] = None,
) -> List[str]:
    """构建完整 ffmpeg 参数（不含可执行文件路径）。"""
    plan = compute_bitrate_plan(info, params, caps)
    encoder = resolve_encoder(params, caps)

    args: List[str] = ["-hide_banner", "-loglevel", "error", "-y", "-i", info.path]

    # 流映射
    args += ["-map", "0:v:0"]
    if info.has_audio:
        args += ["-map", "0:a?"]
    if params.keep_subtitles and info.subtitle_tracks and params.container in ("mkv", "mov", "mp4"):
        args += ["-map", "0:s?"]
        args += ["-c:s", "mov_text" if params.container in ("mp4", "mov") else "copy"]
    if params.container in ("mkv", "mov", "mp4"):
        args += ["-map_metadata", "0", "-map_chapters", "0"]

    if params.size_mode != "streamcopy":
        # 仅转封装（-c:v copy）时不能附带 -vf / -r，否则 ffmpeg 报错
        # "Filtering and streamcopy cannot be used together"。
        # 触发场景：压缩卡选了 720p/1080p 后切到「仅转格式」页（分辨率下拉值共享），
        # 任务变成 streamcopy 却仍带缩放/限速滤镜，导致整批失败。
        filters = _scale_filter(info, params)
        if filters:
            args += ["-vf", ",".join(filters)]
        if params.fps_cap and info.fps and info.fps > params.fps_cap:
            args += ["-r", f"{params.fps_cap:g}"]

    args += _video_args(info, params, plan, encoder, caps)
    args += _audio_args(info, params, plan, caps)

    container = CONTAINER_MAP.get(params.container)
    if container is not None:
        if container.faststart:
            args += ["-movflags", "+faststart"]
        # 显式指定封装器：临时文件名带中间后缀时仍能正确识别格式
        args += ["-f", container.muxer]

    if pass_no == 1:
        args += ["-pass", "1", "-passlogfile", passlogfile, "-f", "null", NULL_DEVICE]
    elif pass_no == 2:
        args += ["-pass", "2", "-passlogfile", passlogfile]
        args += [output]
    else:
        args += [output]
    return args


def resolve_encoder(params: EncodeParams, caps: Optional[Capabilities]) -> str:
    """按能力表选择实际可用编码器，不可用时回退。"""
    preset = PRO_PRESET_MAP.get(params.preset_name)
    if preset is not None:
        if caps is None or caps.has_encoder(preset.encoder):
            return preset.encoder
        return "libx264" if caps.has_encoder("libx264") else ""

    candidate = params.encoder
    if caps is None:
        return candidate
    if caps.has_encoder(candidate):
        spec = ENCODER_MAP.get(candidate)
        # 硬件编码器可能被列出但实际不可用（无对应显卡/驱动）。
        # 启动时已后台实测并缓存结果，这里直接用缓存判断是否回退 CPU。
        if spec is not None and spec.mode == "gpu" and not caps.verify_encoder(candidate):
            for fallback in ("libx264", "libx265"):
                if caps.has_encoder(fallback):
                    return fallback
        return candidate
    for fallback in ("libx264", "libx265", "h264_nvenc", "mpeg4"):
        if caps.has_encoder(fallback):
            return fallback
    return candidate


# ------------------------------------------------------------------ 智能目标大小
# 按分辨率、帧率、原编码格式推荐的“肉眼难辨”输出码率（bps）。
# 以 H.264 为基准；GPU/已压缩源适当提高，避免画质劣化。
_SUGGEST_BITRATES = [
    (0,     1_500_000),   # 低于 720p
    (720,   4_000_000),   # 720p
    (1080,  8_000_000),   # 1080p
    (1440, 15_000_000),   # 2K / 1440p
    (2160, 30_000_000),   # 4K
    (4320, 80_000_000),   # 8K
]


def _source_codec_penalty(info: VideoInfo) -> float:
    """原视频已经高度压缩时，再压空间更小，目标应接近原大小。"""
    codec = (info.v_codec or "").lower()
    if any(c in codec for c in ("hevc", "h265", "265", "vp9", "av1")):
        return 1.35
    return 1.0


def _encoder_penalty(params: EncodeParams, caps: Optional[Capabilities] = None) -> float:
    """GPU 硬件编码效率低于 CPU，目标码率稍高一些。

    按 resolve_encoder 的实际结果判定：GPU 不可用回退 CPU 时不再施加惩罚，
    避免"实际 CPU 编码却按 GPU 标准抬高码率"导致体积无谓偏大。
    """
    return 1.15 if encoder_mode_tag(params, caps) == "GPU" else 1.0


def suggest_target_bytes(
    info: VideoInfo,
    params: EncodeParams,
    caps: Optional[Capabilities] = None,
) -> int:
    """根据视频画质、时长、原大小，推荐一个肉眼难辨的最小目标体积。"""
    if not info.duration or info.size_bytes <= 0:
        return params.target_bytes or int(50 * 1024 * 1024)

    height = max(info.height, 360)
    base_bps = _SUGGEST_BITRATES[0][1]
    for h, bps in _SUGGEST_BITRATES:
        if height >= h:
            base_bps = bps

    # 帧率修正：高帧率保留更多码率
    fps = max(info.fps or 30.0, 1.0)
    if fps > 30:
        base_bps *= (fps / 30.0) ** 0.5

    base_bps *= _source_codec_penalty(info) * _encoder_penalty(params, caps)

    # 按时长计算目标体积
    target = int(base_bps * info.duration / 8)

    # 边界：不小于原体积 5%、不大于原体积 85%；最低 3 MB。
    # 上限随编码惩罚（GPU/已压缩源）同比例放大，否则 GPU 的 1.15 倍惩罚会被
    # 固定 85% 上限完全吃掉，导致 CPU/GPU 切换后目标大小不变。
    penalty = _source_codec_penalty(info) * _encoder_penalty(params, caps)
    min_bytes = max(int(info.size_bytes * 0.05), 3 * 1024 * 1024)
    max_bytes = int(info.size_bytes * 0.85 * penalty)
    if max_bytes < min_bytes:
        max_bytes = min_bytes

    target = max(min(target, max_bytes), min_bytes)

    # 取整到 MB，方便显示
    target = round(target / (1024 * 1024)) * (1024 * 1024)
    return max(target, 3 * 1024 * 1024)


# ------------------------------------------------------------------ 输出路径
def encoder_mode_tag(params: EncodeParams, caps: Optional[Capabilities] = None) -> str:
    """实际使用的编码方式标签：GPU / CPU / 空串（仅转封装不重编码）。

    以 resolve_encoder 的最终结果为准，因此 GPU 不可用回退 CPU 时会正确标为 CPU。
    """
    if params.size_mode == "streamcopy":
        return ""
    encoder = resolve_encoder(params, caps)
    spec = ENCODER_MAP.get(encoder)
    if spec is not None and spec.mode == "gpu":
        return "GPU"
    return "CPU"


# 已预约但尚未落盘的输出路径。并发时多个任务会在任何文件被创建之前就完成路径
# 分配，仅靠 os.path.exists 会让不同目录下的同名源文件抢到同一个输出路径，
# 导致先完成的成品被后完成的任务删除。队列全在主线程，无需加锁。
_RESERVED_OUTPUTS: set = set()


def reserve_output_path(path: str) -> None:
    _RESERVED_OUTPUTS.add(os.path.normcase(os.path.abspath(path)))


def release_output_path(path: str) -> None:
    _RESERVED_OUTPUTS.discard(os.path.normcase(os.path.abspath(path)))


def build_output_path(
    info: VideoInfo,
    params: EncodeParams,
    output_dir: str,
    caps: Optional[Capabilities] = None,
) -> str:
    container = CONTAINER_MAP.get(params.container) or CONTAINER_MAP["mp4"]
    base = os.path.splitext(os.path.basename(info.path))[0]
    directory = output_dir or os.path.dirname(info.path)
    os.makedirs(directory, exist_ok=True)
    tag = encoder_mode_tag(params, caps)
    suffix = f"_SAVT_{tag}" if tag else "_SAVT"
    filename = safe_filename(f"{base}{suffix}{container.ext}")

    # 同时避开磁盘上已存在的文件与本次已预约（尚未落盘）的路径
    candidate = os.path.join(directory, filename)
    candidate = unique_path(candidate)
    key = os.path.normcase(os.path.abspath(candidate))
    index = 1
    while key in _RESERVED_OUTPUTS:
        stem, ext = os.path.splitext(candidate)
        # 去掉上一轮可能追加的 " (n)"，避免叠加成 " (1) (2)"
        stem = _strip_index_suffix(stem)
        candidate = os.path.join(directory, f"{stem} ({index}){ext}")
        candidate = unique_path(candidate)
        key = os.path.normcase(os.path.abspath(candidate))
        index += 1
    reserve_output_path(candidate)
    return candidate


def _strip_index_suffix(stem: str) -> str:
    """去掉 'name (1)' 形式里的序号后缀，便于重新编号。"""
    if stem.endswith(")") and " (" in stem:
        head, _, tail = stem.rpartition(" (")
        if tail[:-1].isdigit():
            return head
    return stem


# ------------------------------------------------------------------ 预估汇总
def estimate_output(info: VideoInfo, params: EncodeParams, caps: Optional[Capabilities] = None) -> Tuple[int, int, float]:
    plan = compute_bitrate_plan(info, params, caps)
    return plan.min_bytes, plan.max_bytes, plan.ratio


def estimate_total(tasks: List[TaskItem], caps: Optional[Capabilities] = None) -> Tuple[int, int, int, float]:
    """返回 (原始总字节, 预估最小, 预估最大, 节省比例)。"""
    original = 0
    min_total = 0
    max_total = 0
    for task in tasks:
        if task.info is None:
            continue
        original += task.info.size_bytes
        low, high, _ = estimate_output(task.info, task.params, caps)
        min_total += low
        max_total += high
    saved = 1 - (min_total / original) if original else 0.0
    return original, min_total, max_total, saved


def apply_preset_to_params(params: EncodeParams, preset_name: str) -> EncodeParams:
    """把专业格式 / 设备预设写入参数。"""
    from core.profiles import DEVICE_PRESET_MAP

    device = DEVICE_PRESET_MAP.get(preset_name)
    if device is not None:
        params.container = device.container
        params.encoder_mode = device.encoder_mode
        params.encoder = device.encoder
        params.max_width = device.max_width
        params.max_height = device.max_height
        params.fps_cap = device.fps_cap
        params.audio_mode = device.audio_mode
        params.audio_bitrate = device.audio_bitrate
        params.preset_name = device.key
        return params

    pro = PRO_PRESET_MAP.get(preset_name)
    if pro is not None:
        params.container = pro.container
        params.encoder = pro.encoder
        params.preset_name = pro.key
        params.max_width = 0
        params.max_height = 0
        params.fps_cap = 0.0
        if pro.kind == "alpha" and params.audio_mode == "flac":
            params.audio_mode = "copy"
        return params

    params.preset_name = ""
    params.max_width = 0
    params.max_height = 0
    params.fps_cap = 0.0
    return params


def apply_course_preset(params: EncodeParams, course: CourseParams) -> EncodeParams:
    """写入课程压缩参数：CPU 软件编码 H.264（libx264），画质优先、强制码率下限。

    目标体积由调用方按 (最低视频码率 + 音频码率) × 时长 计算，故这里只设编码与
    缩放/限速等静态参数，并把 min_video_bitrate 记下供探测完成后补全目标。
    """
    params.encoder_mode = "cpu"
    params.encoder = "libx264"
    params.container = "mp4"
    params.size_mode = "absolute"
    params.audio_mode = "aac"
    params.audio_bitrate = course.audio_bitrate_kbps * 1000
    params.audio_sample_rate = course.audio_sample_rate
    params.max_width = course.width
    params.max_height = course.height
    params.fps_cap = float(course.fps)
    params.two_pass = False
    params.preset_name = COURSE_PRESET_NAME
    params.min_video_bitrate = course.video_bitrate_kbps * 1000
    return params


def course_target_bytes(info: VideoInfo, params: EncodeParams) -> int:
    """按课程压缩最低码率折算目标体积，保证平均视频码率不低于下限。

    需抵消 compute_bitrate_plan 在总码率上预留的容器开销（CONTAINER_OVERHEAD），
    否则落到视频的码率会被该比例压低、跌破用户设定的最低视频码率。
    """
    if not info.duration or info.size_bytes <= 0:
        return params.target_bytes or int(50 * 1024 * 1024)
    video_bps = params.min_video_bitrate or 1024 * 1000
    audio_bps = planned_audio_bps(info, params)
    target = math.ceil(
        (video_bps + audio_bps) * info.duration / (8 * (1 - CONTAINER_OVERHEAD))
    )
    # 边界：不低于原体积 5%，最低 3MB
    min_bytes = max(int(info.size_bytes * 0.05), 3 * 1024 * 1024)
    return max(target, min_bytes)


def default_container_for(info: VideoInfo) -> str:
    return container_for_extension(info.path)
