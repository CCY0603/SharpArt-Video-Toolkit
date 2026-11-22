"""偏好设置持久化（QSettings / INI）。"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from app.config import APP_NAME, ORG_NAME


class AppSettings:
    """轻量偏好存储：读取带默认值，写入立即落盘。"""

    DEFAULTS = {
        "ffmpeg/path": "",
        "ffmpeg/probe_path": "",
        "output/dir": "",
        "output/dir_migrated_to_default": False,  # 旧版硬编码默认输出目录 → 留空（源文件同目录）的一次性迁移标记
        "output/container": "mp4",
        "encode/mode": "cpu",                 # cpu | gpu
        "encode/encoder": "libx264",
        "encode/migrated_h264_default": False,  # 旧默认 H.265 → H.264 的一次性迁移标记
        "encode/size_mode": "absolute",       # absolute | percent | crf
        "encode/target_value": 0.0,           # 0 表示未设置（占位符「未设置」）
        "encode/target_unit": "MB",           # MB | GB
        "encode/percent": 60,
        "encode/crf": 20,
        "encode/audio_mode": "copy",          # copy | aac | flac | mp3 | wav（格式转换卡）
        "encode/audio_mode_compress": "copy", # 视频压缩卡独立的音频设置，与转换卡隔离
        "encode/keep_subtitles": False,
        "encode/resolution": "origin",         # origin | 1080p | 720p | 480p
        "encode/preset_name": "",             # 专业格式/设备预设
        "encode/keep_hdr": True,
        "queue/concurrency": 1,
        "queue/batch_mode": "unified",        # unified | independent
        "ui/theme": "system",                 # system | light | dark
        "after/shutdown": False,
        "after/report": True,
        "paths/last_input_dir": "",
    }

    def __init__(self) -> None:
        self._qs = QSettings(QSettings.IniFormat, QSettings.UserScope, ORG_NAME, APP_NAME)

    # ------------------------------------------------------------ 基础读写
    def get(self, key: str):
        default = self.DEFAULTS.get(key)
        value = self._qs.value(key, default)
        # INI 会把布尔读成字符串
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        return value

    def set(self, key: str, value) -> None:
        self._qs.setValue(key, value)

    def sync(self) -> None:
        self._qs.sync()

    # ------------------------------------------------------------ 便捷属性
    @property
    def ffmpeg_path(self) -> str:
        return self.get("ffmpeg/path")

    @ffmpeg_path.setter
    def ffmpeg_path(self, value: str) -> None:
        self.set("ffmpeg/path", value)

    @property
    def probe_path(self) -> str:
        return self.get("ffmpeg/probe_path")

    @probe_path.setter
    def probe_path(self, value: str) -> None:
        self.set("ffmpeg/probe_path", value)

    @property
    def output_dir(self) -> str:
        return self.get("output/dir")

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self.set("output/dir", value)

    @property
    def output_dir_migrated_to_default(self) -> bool:
        """旧版默认输出目录 → 留空（输出到源文件同目录）的一次性迁移标记。"""
        return bool(self.get("output/dir_migrated_to_default"))

    @output_dir_migrated_to_default.setter
    def output_dir_migrated_to_default(self, value: bool) -> None:
        self.set("output/dir_migrated_to_default", value)

    @property
    def container(self) -> str:
        return self.get("output/container")

    @container.setter
    def container(self, value: str) -> None:
        self.set("output/container", value)

    @property
    def encoder_mode(self) -> str:
        return self.get("encode/mode")

    @encoder_mode.setter
    def encoder_mode(self, value: str) -> None:
        self.set("encode/mode", value)

    @property
    def encoder(self) -> str:
        return self.get("encode/encoder")

    @encoder.setter
    def encoder(self, value: str) -> None:
        self.set("encode/encoder", value)

    @property
    def migrated_h264_default(self) -> bool:
        """旧版默认编码器为 H.265，现统一改为 H.264；用于只迁移一次。"""
        return bool(self.get("encode/migrated_h264_default"))

    @migrated_h264_default.setter
    def migrated_h264_default(self, value: bool) -> None:
        self.set("encode/migrated_h264_default", value)

    @property
    def size_mode(self) -> str:
        return self.get("encode/size_mode")

    @size_mode.setter
    def size_mode(self, value: str) -> None:
        self.set("encode/size_mode", value)

    @property
    def target_value(self) -> float:
        return self.get("encode/target_value")

    @target_value.setter
    def target_value(self, value: float) -> None:
        self.set("encode/target_value", value)

    @property
    def target_unit(self) -> str:
        return self.get("encode/target_unit")

    @target_unit.setter
    def target_unit(self, value: str) -> None:
        self.set("encode/target_unit", value)

    @property
    def percent(self) -> int:
        return self.get("encode/percent")

    @percent.setter
    def percent(self, value: int) -> None:
        self.set("encode/percent", value)

    @property
    def crf(self) -> int:
        return self.get("encode/crf")

    @crf.setter
    def crf(self, value: int) -> None:
        self.set("encode/crf", value)

    @property
    def audio_mode(self) -> str:
        return self.get("encode/audio_mode")

    @audio_mode.setter
    def audio_mode(self, value: str) -> None:
        self.set("encode/audio_mode", value)

    @property
    def audio_mode_compress(self) -> str:
        return self.get("encode/audio_mode_compress")

    @audio_mode_compress.setter
    def audio_mode_compress(self, value: str) -> None:
        self.set("encode/audio_mode_compress", value)

    @property
    def keep_subtitles(self) -> bool:
        return self.get("encode/keep_subtitles")

    @keep_subtitles.setter
    def keep_subtitles(self, value: bool) -> None:
        self.set("encode/keep_subtitles", value)

    @property
    def resolution(self) -> str:
        return self.get("encode/resolution")

    @resolution.setter
    def resolution(self, value: str) -> None:
        self.set("encode/resolution", value)

    @property
    def preset_name(self) -> str:
        return self.get("encode/preset_name")

    @preset_name.setter
    def preset_name(self, value: str) -> None:
        self.set("encode/preset_name", value)

    @property
    def keep_hdr(self) -> bool:
        return self.get("encode/keep_hdr")

    @keep_hdr.setter
    def keep_hdr(self, value: bool) -> None:
        self.set("encode/keep_hdr", value)

    @property
    def concurrency(self) -> int:
        return self.get("queue/concurrency")

    @concurrency.setter
    def concurrency(self, value: int) -> None:
        self.set("queue/concurrency", value)

    @property
    def batch_mode(self) -> str:
        return self.get("queue/batch_mode")

    @batch_mode.setter
    def batch_mode(self, value: str) -> None:
        self.set("queue/batch_mode", value)

    @property
    def theme(self) -> str:
        return self.get("ui/theme")

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("ui/theme", value)

    @property
    def shutdown_after(self) -> bool:
        return self.get("after/shutdown")

    @shutdown_after.setter
    def shutdown_after(self, value: bool) -> None:
        self.set("after/shutdown", value)

    @property
    def generate_report(self) -> bool:
        return self.get("after/report")

    @generate_report.setter
    def generate_report(self, value: bool) -> None:
        self.set("after/report", value)

    @property
    def last_input_dir(self) -> str:
        return self.get("paths/last_input_dir")

    @last_input_dir.setter
    def last_input_dir(self, value: str) -> None:
        self.set("paths/last_input_dir", value)
