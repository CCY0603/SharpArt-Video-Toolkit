"""ffprobe 元数据解析。"""

from __future__ import annotations

import json
import os
import subprocess

from core.capabilities import CREATE_NO_WINDOW, Capabilities
from core.models import VideoInfo
from core.utils import (
    codec_display,
    pix_fmt_bit_depth,
    pix_fmt_chroma,
    pix_fmt_has_alpha,
)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_rate(rate: str) -> float:
    """解析 30000/1001 或 25 形式的帧率。"""
    if not rate:
        return 0.0
    if "/" in rate:
        num, _, den = rate.partition("/")
        num_f, den_f = _to_float(num), _to_float(den, 1.0)
        return num_f / den_f if den_f else 0.0
    return _to_float(rate)


def _detect_hdr(stream: dict) -> str:
    for side in stream.get("side_data_list") or []:
        side_type = (side.get("side_data_type") or "").lower()
        if "dovi" in side_type or "dolby vision" in side_type:
            return "Dolby Vision"
    transfer = (stream.get("color_transfer") or "").lower()
    primaries = (stream.get("color_primaries") or "").lower()
    if transfer in ("smpte2084", "pq") or "bt2020" in primaries and transfer == "smpte2084":
        return "HDR10"
    if transfer in ("arib-std-b67", "hlg"):
        return "HLG"
    if (stream.get("color_space") or "").startswith("bt2020"):
        return "HDR10"
    return "SDR"


def probe_file(path: str, caps: Capabilities) -> VideoInfo:
    """探测单个文件，解析出全部展示字段。"""
    cmd = [
        caps.ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", "-show_chapters", path,
    ]
    info = VideoInfo(path=path, name=os.path.basename(path))
    try:
        raw = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="ignore",
        ).stdout
        data = json.loads(raw or "{}")
    except Exception as exc:  # 解析失败也返回基础信息，避免整行不可用
        info.v_codec_display = f"无法识别（{exc.__class__.__name__}）"
        return info

    fmt = data.get("format") or {}
    info.size_bytes = _to_int(fmt.get("size") or os.path.getsize(path) if os.path.exists(path) else fmt.get("size"))
    info.duration = _to_float(fmt.get("duration"))
    info.format_name = fmt.get("format_name") or ""
    info.chapters = len(data.get("chapters") or [])

    total_bitrate = _to_int(fmt.get("bit_rate"))
    audio_bitrate = 0

    for stream in data.get("streams") or []:
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            # 跳过封面图（mjpeg / png attached_pic）
            disposition = stream.get("disposition") or {}
            if disposition.get("attached_pic"):
                continue
            if info.v_codec:
                continue
            info.v_codec = stream.get("codec_name") or ""
            info.v_codec_display = codec_display(info.v_codec)
            info.v_profile = stream.get("profile") or ""
            info.width = _to_int(stream.get("width"))
            info.height = _to_int(stream.get("height"))
            info.fps = _parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
            info.v_bitrate = _to_int(stream.get("bit_rate"))
            info.pix_fmt = stream.get("pix_fmt") or ""
            info.bit_depth = _to_int(stream.get("bits_per_raw_sample")) or pix_fmt_bit_depth(info.pix_fmt)
            info.color_space = pix_fmt_chroma(info.pix_fmt)
            info.has_alpha = pix_fmt_has_alpha(info.pix_fmt)
            info.hdr_type = _detect_hdr(stream)
            if not info.duration:
                info.duration = _to_float(stream.get("duration"))
            nb = stream.get("nb_frames")
            if nb and not info.duration and info.fps:
                info.duration = _to_float(nb) / info.fps
        elif codec_type == "audio":
            if info.has_audio:
                continue
            info.has_audio = True
            info.a_codec = stream.get("codec_name") or ""
            info.a_codec_display = codec_display(info.a_codec)
            info.a_channels = _to_int(stream.get("channels"))
            info.a_sample_rate = _to_int(stream.get("sample_rate"))
            info.a_bitrate = _to_int(stream.get("bit_rate"))
            audio_bitrate += info.a_bitrate
        elif codec_type == "subtitle":
            info.subtitle_tracks += 1

    if not info.v_bitrate and info.duration > 0:
        estimated = int(info.size_bytes * 8 / info.duration) - audio_bitrate
        info.v_bitrate = max(estimated, 0)
    if not info.a_bitrate and total_bitrate and info.v_bitrate:
        info.a_bitrate = max(total_bitrate - info.v_bitrate, 0)

    return info
