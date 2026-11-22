"""音轨提取。"""

from __future__ import annotations

import os

from core.models import VideoInfo
from core.profiles import EXTRACT_FORMATS
from core.utils import safe_filename, unique_path


def extract_format_info(key: str):
    for item in EXTRACT_FORMATS:
        if item[0] == key:
            return item
    return EXTRACT_FORMATS[0]


def build_output_path(info: VideoInfo, key: str, output_dir: str) -> str:
    _, _, _, ext = extract_format_info(key)
    base = os.path.splitext(os.path.basename(info.path))[0]
    directory = output_dir or os.path.dirname(info.path)
    os.makedirs(directory, exist_ok=True)
    return unique_path(os.path.join(directory, safe_filename(f"{base}_音频{ext}")))


def build_extract_args(info: VideoInfo, key: str, output: str) -> list[str]:
    """构建提取音轨的 ffmpeg 参数（单遍，带进度）。"""
    _, _, encoder, _ = extract_format_info(key)
    args = [
        "-hide_banner", "-loglevel", "error", "-y",
        "-i", info.path,
        "-vn", "-map", "0:a:0",
        "-c:a", encoder,
    ]
    if key in ("mp3", "aac"):
        bitrate = 320000 if key == "mp3" else 256000
        if info.a_bitrate and info.a_bitrate < bitrate:
            bitrate = max(info.a_bitrate, 96000)
        args += ["-b:a", str(bitrate)]
    if key == "aac":
        args += ["-movflags", "+faststart"]
    args += [output]
    return args
