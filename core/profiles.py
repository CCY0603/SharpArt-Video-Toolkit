"""编码器、容器、专业格式与设备预设表。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class EncoderSpec:
    key: str
    label: str
    mode: str                 # cpu | gpu
    vendor: str = ""          # nvidia / amd / intel
    codec: str = "h264"       # h264 | hevc
    supports_two_pass: bool = True
    supports_10bit: bool = False
    note: str = ""


ENCODERS: List[EncoderSpec] = [
    EncoderSpec("libx265", "H.265 / HEVC（x265）", "cpu", codec="hevc",
                supports_10bit=True, note="同画质体积更小，适合归档"),
    EncoderSpec("libx264", "H.264 / AVC（x264）", "cpu", codec="h264",
                supports_10bit=True, note="兼容性最好，适合分享"),
    EncoderSpec("hevc_nvenc", "H.265 / HEVC（NVIDIA NVENC）", "gpu", "nvidia", "hevc",
                supports_two_pass=False, supports_10bit=True, note="极速，大小误差略增"),
    EncoderSpec("h264_nvenc", "H.264 / AVC（NVIDIA NVENC）", "gpu", "nvidia", "h264",
                supports_two_pass=False, note="极速，兼容性好"),
    EncoderSpec("hevc_amf", "H.265 / HEVC（AMD AMF）", "gpu", "amd", "hevc",
                supports_two_pass=False, note="AMD 显卡硬件加速"),
    EncoderSpec("h264_amf", "H.264 / AVC（AMD AMF）", "gpu", "amd", "h264",
                supports_two_pass=False, note="AMD 显卡硬件加速"),
    EncoderSpec("hevc_qsv", "H.265 / HEVC（Intel QSV）", "gpu", "intel", "hevc",
                supports_two_pass=False, supports_10bit=True, note="Intel 核显硬件加速"),
    EncoderSpec("h264_qsv", "H.264 / AVC（Intel QSV）", "gpu", "intel", "h264",
                supports_two_pass=False, note="Intel 核显硬件加速"),
]

ENCODER_MAP: Dict[str, EncoderSpec] = {e.key: e for e in ENCODERS}


def encoders_for_mode(mode: str) -> List[EncoderSpec]:
    return [e for e in ENCODERS if e.mode == mode]


def encoders_for_vendor(vendor: str) -> List[EncoderSpec]:
    """返回指定 GPU 厂商的硬件编码器，H.264 优先。

    只列本机显卡对应的厂商：NVIDIA 仅 NVENC、AMD 仅 AMF、Intel 仅 QSV，
    避免下拉里出现本机根本用不了的其它厂商编码器。
    """
    if not vendor:
        return []
    matched = [e for e in ENCODERS if e.mode == "gpu" and e.vendor == vendor]
    return sorted(matched, key=lambda e: (e.codec != "h264", e.label))


def default_encoder(mode: str, vendor: str = "") -> str:
    """默认编码器：统一优先 H.264（兼容性最好、速度最快）。

    CPU → libx264；GPU → 本机显卡厂商对应的 H.264 硬件编码器。
    """
    if mode == "gpu":
        for spec in ENCODERS:
            if spec.mode == "gpu" and spec.codec == "h264" and spec.vendor == vendor:
                return spec.key
        return "h264_nvenc"
    return "libx264"


# ------------------------------------------------------------------ 容器
@dataclass
class ContainerSpec:
    key: str
    label: str
    ext: str
    muxer: str
    audio_codecs: List[str] = field(default_factory=list)
    subtitles: bool = False
    chapters: bool = False
    faststart: bool = False


CONTAINERS: List[ContainerSpec] = [
    ContainerSpec("mp4", "MP4", ".mp4", "mp4", ["aac", "mp3", "copy"], False, False, True),
    ContainerSpec("mov", "MOV", ".mov", "mov", ["aac", "flac", "wav", "mp3", "copy"], True, True, True),
    ContainerSpec("mkv", "MKV", ".mkv", "matroska", ["aac", "flac", "wav", "mp3", "copy"], True, True, False),
    ContainerSpec("webm", "WebM", ".webm", "webm", ["copy"], True, True, False),
    ContainerSpec("avi", "AVI", ".avi", "avi", ["mp3", "wav", "copy"], False, False, False),
    ContainerSpec("wmv", "WMV", ".wmv", "asf", ["copy"], False, False, False),
    ContainerSpec("flv", "FLV", ".flv", "flv", ["aac", "mp3", "copy"], False, False, False),
    ContainerSpec("3gp", "3GP", ".3gp", "3gp", ["aac", "copy"], False, False, False),
]

CONTAINER_MAP: Dict[str, ContainerSpec] = {c.key: c for c in CONTAINERS}


def container_for_extension(path: str) -> str:
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    for spec in CONTAINERS:
        if spec.ext.lstrip(".") == ext:
            return spec.key
    return "mp4"


# ------------------------------------------------------------------ 专业格式
@dataclass
class ProPreset:
    key: str
    label: str
    kind: str                 # prores | dnxhr | alpha
    container: str
    encoder: str
    profile: str = ""
    pix_fmt: str = ""
    extra: List[str] = field(default_factory=list)
    note: str = ""


PROFESSIONAL_PRESETS: List[ProPreset] = [
    ProPreset("prores_proxy", "ProRes Proxy", "prores", "mov", "prores_ks", "0",
              "yuv422p10le", note="代理剪辑，体积最小"),
    ProPreset("prores_lt", "ProRes LT", "prores", "mov", "prores_ks", "1",
              "yuv422p10le", note="轻量，适合预览与移动端剪辑"),
    ProPreset("prores_standard", "ProRes Standard", "prores", "mov", "prores_ks", "2",
              "yuv422p10le", note="标准画质，通用交付"),
    ProPreset("prores_hq", "ProRes HQ", "prores", "mov", "prores_ks", "3",
              "yuv422p10le", note="高画质母版，接近无损"),
    ProPreset("dnxhr_lb", "DNxHR LB", "dnxhr", "mov", "dnxhd", "dnxhr_lb",
              "yuv422p", note="低带宽代理"),
    ProPreset("dnxhr_sq", "DNxHR SQ", "dnxhr", "mov", "dnxhd", "dnxhr_sq",
              "yuv422p", note="标准质量，剪辑常用"),
    ProPreset("dnxhr_hq", "DNxHR HQ", "dnxhr", "mov", "dnxhd", "dnxhr_hq",
              "yuv422p", note="高质量交付"),
    ProPreset("dnxhr_hqx", "DNxHR HQX", "dnxhr", "mov", "dnxhd", "dnxhr_hqx",
              "yuv422p10le", note="10bit 高质量"),
    ProPreset("alpha_qtrle", "MOV + Alpha 透明通道", "alpha", "mov", "qtrle", "",
              "argb", note="保留透明背景，用于合成"),
    ProPreset("alpha_prores4444", "ProRes 4444 + Alpha", "alpha", "mov", "prores_ks", "4",
              "yuva444p10le", ["-alpha_bits", "8"], note="带透明通道的专业母版"),
]

PRO_PRESET_MAP: Dict[str, ProPreset] = {p.key: p for p in PROFESSIONAL_PRESETS}


# ------------------------------------------------------------------ 设备预设
@dataclass
class DevicePreset:
    key: str
    label: str
    container: str
    encoder_mode: str
    encoder: str
    max_width: int = 0
    max_height: int = 0
    fps_cap: float = 0
    audio_mode: str = "aac"
    audio_bitrate: int = 192000
    note: str = ""


DEVICE_PRESETS: List[DevicePreset] = [
    DevicePreset("iphone16pro", "iPhone 16 Pro", "mov", "cpu", "libx265",
                 3840, 2160, 60, "aac", 256000, note="最高 4K60，HEVC 高效播放"),
    DevicePreset("samsung_s30", "Samsung S30", "mp4", "cpu", "libx265",
                 3840, 2160, 60, "aac", 192000, note="安卓旗舰通用预设"),
    DevicePreset("xbox_series_x", "Xbox Series X", "mp4", "cpu", "libx265",
                 3840, 2160, 60, "aac", 192000, note="主机播放，HEVC 优先"),
    DevicePreset("douyin_vertical", "抖音 / 快手竖屏", "mp4", "cpu", "libx264",
                 1080, 1920, 60, "aac", 192000, note="竖屏 1080×1920，H.264 兼容最佳"),
]

DEVICE_PRESET_MAP: Dict[str, DevicePreset] = {d.key: d for d in DEVICE_PRESETS}


# ------------------------------------------------------------------ 音频
AUDIO_MODES = [
    ("copy", "复制原音轨（最快）"),
    ("aac", "AAC（通用）"),
    ("mp3", "MP3（兼容）"),
    ("flac", "FLAC（无损）"),
    ("wav", "WAV（PCM）"),
    ("follow", "跟随压缩（动态）"),
]

AUDIO_ENCODERS = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "flac": "flac",
    "wav": "pcm_s16le",
    "follow": "aac",  # 跟随压缩实际用 AAC 动态码率，由 planner 计算具体 -b:a
}


# ------------------------------------------------------------------ 分辨率档位
# 下拉框可选的目标分辨率；width/height 为上限基准，实际输出在 _scale_filter 中
# 按 force_original_aspect_ratio=decrease 保持原宽高比并强制偶数对齐。
# origin 表示保留源分辨率（或设备预设的 max_width/max_height）。
RESOLUTIONS = [
    ("origin", "原分辨率", 0, 0),
    ("1080p", "1080p", 1920, 1080),
    ("720p", "720p", 1280, 720),
    ("480p", "480p", 854, 480),
]

RESOLUTION_MAP: Dict[str, "tuple[int, int]"] = {key: (w, h) for key, _, w, h in RESOLUTIONS}

EXTRACT_FORMATS = [
    ("mp3", "MP3", "libmp3lame", ".mp3"),
    ("aac", "AAC (M4A)", "aac", ".m4a"),
    ("flac", "FLAC", "flac", ".flac"),
    ("wav", "WAV", "pcm_s16le", ".wav"),
]


