"""跨层数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from core.utils import (
    channel_label,
    format_bitrate,
    format_duration,
    format_sample_rate,
    format_size,
    resolution_label,
    resolution_text,
)


@dataclass
class CourseParams:
    """课程压缩的可调参数（码率单位 Kbps，采样率单位 Hz）。"""

    video_bitrate_kbps: int = 1024
    width: int = 1280
    height: int = 720
    fps: int = 25
    audio_sample_rate: int = 48000
    audio_bitrate_kbps: int = 128


class TaskStatus:
    PENDING = "pending"
    PROBING = "probing"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"

    ICONS = {
        PENDING: "clock",
        PROBING: "search",
        RUNNING: "loader",
        DONE: "check",
        FAILED: "x",
        CANCELED: "square",
    }

    LABELS = {
        PENDING: "等待处理",
        PROBING: "识别中",
        RUNNING: "处理中",
        DONE: "已完成",
        FAILED: "失败",
        CANCELED: "已取消",
    }


@dataclass
class VideoInfo:
    """ffprobe 解析得到的媒体信息。"""

    path: str = ""
    name: str = ""
    size_bytes: int = 0
    duration: float = 0.0
    format_name: str = ""

    # 视频流
    v_codec: str = ""
    v_codec_display: str = ""
    v_profile: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    v_bitrate: int = 0
    pix_fmt: str = ""
    bit_depth: int = 8
    color_space: str = ""
    hdr_type: str = "SDR"
    has_alpha: bool = False

    # 音频流
    a_codec: str = ""
    a_codec_display: str = ""
    a_channels: int = 0
    a_sample_rate: int = 0
    a_bitrate: int = 0
    has_audio: bool = False

    # 辅助
    subtitle_tracks: int = 0
    chapters: int = 0

    # -------------------------------------------------------------- 展示
    @property
    def size_text(self) -> str:
        return format_size(self.size_bytes)

    @property
    def duration_text(self) -> str:
        return format_duration(self.duration)

    @property
    def resolution_text(self) -> str:
        if not self.width:
            return "—"
        return resolution_text(self.width, self.height)

    @property
    def resolution_label(self) -> str:
        return resolution_label(self.height) if self.height else "—"

    @property
    def fps_text(self) -> str:
        return f"{self.fps:.2f} fps" if self.fps else "—"

    @property
    def v_bitrate_text(self) -> str:
        return format_bitrate(self.v_bitrate)

    @property
    def a_bitrate_text(self) -> str:
        return format_bitrate(self.a_bitrate)

    @property
    def channels_text(self) -> str:
        return channel_label(self.a_channels) if self.has_audio else "无音轨"

    @property
    def sample_rate_text(self) -> str:
        return format_sample_rate(self.a_sample_rate) if self.has_audio else "—"

    @property
    def bit_depth_text(self) -> str:
        return f"{self.bit_depth} bit"

    def summary_text(self) -> str:
        """一键复制用的完整信息文本。"""
        lines = [
            "【基础元数据】",
            f"文件名：{self.name}",
            f"文件大小：{self.size_text}",
            f"文件路径：{self.path}",
            "",
            "【视频流信息】",
            f"编码格式：{self.v_codec_display}（{self.v_codec}）",
            f"分辨率：{self.resolution_text}（{self.resolution_label}）",
            f"帧率：{self.fps_text}",
            f"码率：{self.v_bitrate_text}",
            f"色深：{self.bit_depth_text}",
            f"色彩空间：{self.color_space}（{self.pix_fmt}）",
            "",
            "【音频流信息】",
            f"音频编码：{self.a_codec_display if self.has_audio else '无'}",
            f"声道数：{self.channels_text}",
            f"采样率：{self.sample_rate_text}",
            f"音频码率：{self.a_bitrate_text}",
            "",
            "【辅助信息】",
            f"视频时长：{self.duration_text}",
            f"字幕轨：{self.subtitle_tracks} 条",
            f"章节标记：{self.chapters} 个",
            f"HDR 类型：{self.hdr_type}",
            f"透明通道：{'支持' if self.has_alpha else '无'}",
        ]
        return "\n".join(lines)


@dataclass
class EncodeParams:
    """一次编码任务的参数。"""

    encoder_mode: str = "cpu"      # cpu | gpu
    encoder: str = "libx264"
    size_mode: str = "absolute"    # absolute | percent | crf | streamcopy（仅转换封装，不重编码）
    target_bytes: int = 0
    percent: int = 60
    crf: int = 20
    container: str = "mp4"
    audio_mode: str = "copy"       # copy | aac | flac | mp3 | wav
    audio_bitrate: int = 192000
    preset_name: str = ""          # 专业格式 / 设备预设名
    keep_hdr: bool = True
    keep_subtitles: bool = False
    two_pass: bool = True
    max_width: int = 0             # 设备预设缩放上限（0 表示保持原尺寸）
    max_height: int = 0
    resolution: str = "origin"     # 目标分辨率档位：origin | 1080p | 720p | 480p
                                  # 仅重编码模式生效；origin 时沿用 max_width/max_height（设备预设），
                                  # 否则覆盖为分辨率表对应尺寸（仍保持原宽高比）
    fps_cap: float = 0.0
    audio_sample_rate: int = 0     # Hz，0 表示沿用源/默认采样率
    min_video_bitrate: int = 0     # bps；课程压缩最低视频码率下限，>0 表示课程模式

    def copy(self) -> "EncodeParams":
        return replace(self)

    def describe(self) -> str:
        if self.size_mode == "absolute":
            target = f"{format_size(self.target_bytes)}"
        elif self.size_mode == "percent":
            target = f"{self.percent}%"
        else:
            target = f"CRF {self.crf}"
        return target


@dataclass
class TaskItem:
    """列表中的一行任务。"""

    id: int = 0
    info: Optional[VideoInfo] = None
    params: EncodeParams = field(default_factory=EncodeParams)
    custom_params: bool = False     # 独立设置模式下是否被单独调整
    status: str = TaskStatus.PENDING
    progress: float = 0.0
    pass_index: int = 0
    total_passes: int = 1
    error: str = ""
    output_path: str = ""
    output_bytes: int = 0
    elapsed: float = 0.0

    @property
    def name(self) -> str:
        return self.info.name if self.info else ""

    @property
    def status_text(self) -> str:
        if self.status == TaskStatus.RUNNING:
            return f"{self.progress * 100:.0f}%"
        return TaskStatus.LABELS.get(self.status, "")

    @property
    def status_icon(self) -> str:
        return TaskStatus.ICONS.get(self.status, "")

    @property
    def target_text(self) -> str:
        if not self.params:
            return "—"
        if self.params.size_mode == "crf":
            return f"CRF {self.params.crf}"
        if self.params.size_mode == "percent":
            return f"{self.params.percent}%"
        return format_size(self.params.target_bytes)

    def is_finished(self) -> bool:
        return self.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELED)

    @property
    def probed(self) -> bool:
        """探测是否已完成。

        添加文件时先塞入占位 VideoInfo（duration / size_bytes 均为 0）并置 PROBING，
        ffprobe 返回后才填充真实信息。用 duration>0 判断是否已探测完成，
        避免把占位任务送进编码（会导致码率按 0.1 秒计算、进度恒为 0、丢失音轨）。
        """
        return self.info is not None and self.info.duration > 0

    def is_runnable(self) -> bool:
        """是否可以被送进编码队列。"""
        return (
            self.probed
            and self.status in (TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.CANCELED)
        )
