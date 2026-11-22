"""格式化与路径工具。"""

from __future__ import annotations

import math
import os
import re

from app.config import RES_LABELS


# ------------------------------------------------------------------ 大小
def format_size(num_bytes: float, precision: int = 2) -> str:
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = min(int(math.floor(math.log(num_bytes, 1024))), len(units) - 1)
    value = num_bytes / (1024 ** idx)
    if idx == 0:
        return f"{int(value)} B"
    return f"{value:.{precision}f} {units[idx]}"


_SIZE_FACTORS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
}


def size_to_bytes(value: float, unit: str) -> int:
    return int(value * _SIZE_FACTORS.get(unit.upper(), 1024 ** 2))


def bytes_to_unit(num_bytes: float, unit: str) -> float:
    return num_bytes / _SIZE_FACTORS.get(unit.upper(), 1024 ** 2)


# ------------------------------------------------------------------ 时长
def format_duration(seconds: float, show_ms: bool = False) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration_cn(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "0 秒"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分")
    if secs or not parts:
        parts.append(f"{secs}秒")
    return "".join(parts)


_TC_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,6}))?")


def parse_ffmpeg_time(text: str) -> float:
    """解析 HH:MM:SS.mmm / N.NNN 形式的时间戳为秒。"""
    if not text:
        return 0.0
    text = text.strip().strip(",")
    if text in ("N/A", "nan", "-0.000000"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    m = _TC_RE.match(text)
    if not m:
        return 0.0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    frac = m.group(4) or "0"
    return hours * 3600 + minutes * 60 + seconds + float("0." + frac)


# ------------------------------------------------------------------ 码率
def format_bitrate(bps: float) -> str:
    if not bps or bps <= 0:
        return "—"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    return f"{bps / 1000:.0f} kbps"


def format_sample_rate(rate: int) -> str:
    if not rate:
        return "—"
    return f"{rate / 1000:.1f} kHz"


def channel_label(channels: int) -> str:
    return {1: "单声道", 2: "立体声", 4: "4.0", 6: "5.1", 8: "7.1"}.get(channels, f"{channels} 声道")


# ------------------------------------------------------------------ 像素格式
def pix_fmt_chroma(pix_fmt: str) -> str:
    pf = (pix_fmt or "").lower()
    if "440" in pf:
        base = "YUV 4:4:0"
    elif "444" in pf:
        base = "YUV 4:4:4"
    elif "422" in pf:
        base = "YUV 4:2:2"
    elif "420" in pf:
        base = "YUV 4:2:0"
    elif "410" in pf:
        base = "YUV 4:1:0"
    elif "411" in pf:
        base = "YUV 4:1:1"
    elif any(k in pf for k in ("rgb", "bgr", "gbr", "gray", "mono")):
        return "RGB / 灰度"
    else:
        return pix_fmt or "未知"
    if "p10" in pf or "10le" in pf or "10be" in pf:
        base += " 10bit"
    elif "p12" in pf or "12le" in pf or "12be" in pf:
        base += " 12bit"
    return base


def pix_fmt_bit_depth(pix_fmt: str) -> int:
    pf = (pix_fmt or "").lower()
    for depth in (16, 14, 12, 10, 9, 8):
        if f"p{depth}" in pf or f"{depth}le" in pf or f"{depth}be" in pf:
            return depth
    return 8


def pix_fmt_has_alpha(pix_fmt: str) -> bool:
    pf = (pix_fmt or "").lower()
    return bool(re.search(r"(^|[^a-z])(yuva|rgba|bgra|argb|abgr|gbrap|ya\d+)", pf))


# ------------------------------------------------------------------ 分辨率
def resolution_label(height: int) -> str:
    for label, test in RES_LABELS:
        if test(height):
            return label
    return f"{height}p"


def resolution_text(width: int, height: int) -> str:
    return f"{width}×{height}"


# ------------------------------------------------------------------ 路径
INVALID_CHARS = r'<>:"/\|?*'


def safe_filename(name: str) -> str:
    cleaned = "".join("_" if c in INVALID_CHARS else c for c in name).strip().rstrip(".")
    return cleaned or "output"


def unique_path(path: str) -> str:
    """避免覆盖同名文件：name.mp4 → name (1).mp4"""
    if not os.path.exists(path):
        return path
    directory = os.path.dirname(path)
    base, ext = os.path.splitext(os.path.basename(path))
    index = 1
    while True:
        candidate = os.path.join(directory, f"{base} ({index}){ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def codec_display(codec: str) -> str:
    table = {
        "h264": "H.264 / AVC",
        "hevc": "H.265 / HEVC",
        "av1": "AV1",
        "vp9": "VP9",
        "vp8": "VP8",
        "mpeg4": "MPEG-4",
        "mpeg2video": "MPEG-2",
        "prores": "Apple ProRes",
        "dnxhd": "DNxHR / DNxHD",
        "aac": "AAC",
        "mp3": "MP3",
        "flac": "FLAC",
        "opus": "Opus",
        "vorbis": "Vorbis",
        "ac3": "Dolby AC-3",
        "eac3": "Dolby Digital Plus",
        "wmav2": "Windows Media Audio",
        "pcm_s16le": "PCM 16bit",
        "pcm_s24le": "PCM 24bit",
        "truehd": "Dolby TrueHD",
        "dts": "DTS",
    }
    return table.get((codec or "").lower(), codec or "未知")
