"""ffmpeg / ffprobe 定位与能力探测。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, Set

from app.config import NULL_DEVICE

CREATE_NO_WINDOW = 0x08000000


@dataclass
class Capabilities:
    ffmpeg: str = ""
    ffprobe: str = ""
    version: str = ""
    encoders: Set[str] = field(default_factory=set)
    muxers: Set[str] = field(default_factory=set)
    demuxers: Set[str] = field(default_factory=set)
    error: str = ""
    _verified: Dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe and not self.error)

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def has_muxer(self, name: str) -> bool:
        return name in self.muxers

    def verify_encoder(self, name: str) -> bool:
        """实际编码一帧，确认编码器在本机可用（GPU 编码器可能列出但不可用）。"""
        if not name or not self.ffmpeg:
            return False
        if name in self._verified:
            return self._verified[name]

        extra = []
        if name.endswith("_qsv"):
            extra = ["-vf", "format=nv12,hwupload=extra_hw_frames=64"]
        # 320x240：NVENC / QSV 对最小帧尺寸有要求（128x128 会因
        # "Frame Dimension less than the minimum supported value" 被拒绝），
        # 尺寸过小会导致硬件编码器被误判为不可用
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.04:r=25",
            "-an", "-frames:v", "1",
        ] + extra + ["-c:v", name, "-f", "null", NULL_DEVICE]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
            ok = result.returncode == 0
        except Exception:
            ok = False
        self._verified[name] = ok
        return ok

    def gpu_vendor(self) -> str:
        """按实际可用情况返回 GPU 编码器厂商。"""
        for encoder, vendor in (
            ("h264_nvenc", "nvidia"),
            ("h264_amf", "amd"),
            ("h264_qsv", "intel"),
        ):
            if self.has_encoder(encoder) and self.verify_encoder(encoder):
                return vendor
        return ""


def _search_roots() -> list[str]:
    """候选搜索根目录：程序自身目录 → 用户目录 → 常见安装位置。"""
    roots: list[str] = []

    # 程序自身目录（打包后为 exe 所在目录；源码运行时为项目根），支持随包携带的便携版 ffmpeg
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for sub in ("", "bin", "ffmpeg", os.path.join("ffmpeg", "bin"), "tools",
                "_internal", os.path.join("_internal", "bin")):
        roots.append(os.path.join(base, sub) if sub else base)

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        roots.extend([
            os.path.join(local, "ffmpeg", "bin"),
            os.path.join(local, "Programs", "ffmpeg", "bin"),
        ])
    for env_key in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(env_key, "")
        if root:
            roots.append(os.path.join(root, "ffmpeg", "bin"))
    roots.extend([r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"])
    return roots


def _expand_dirs(roots: list[str], max_depth: int = 2) -> list[str]:
    """展开根目录及其有限深度的子目录（覆盖 winget 等带版本号的安装路径）。"""
    result: list[str] = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        result.append(root)
        try:
            for entry in os.listdir(root):
                sub = os.path.join(root, entry)
                if os.path.isdir(sub):
                    result.append(sub)
                    result.append(os.path.join(sub, "bin"))
        except Exception:
            continue
    return result


def resolve_executable(name: str, configured: str = "") -> str:
    """定位可执行文件：配置路径 → PATH → 程序目录 → 常见安装目录。

    多路径回退可避免打包 exe 或特定环境下因 PATH 差异找不到 ffmpeg，
    从而消除启动时「未找到 ffmpeg」的阻塞弹窗。
    """
    suffix = ".exe" if os.name == "nt" else ""
    if configured:
        if os.path.isfile(configured):
            return configured
        combined = os.path.join(configured, name + suffix)
        if os.path.isfile(combined):
            return combined

    found = shutil.which(name)
    if found:
        return found

    for directory in _expand_dirs(_search_roots()):
        candidate = os.path.join(directory, name + suffix)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        # 必须同时指定 encoding：否则 errors 参数会被忽略，非 GBK 字节会抛出 UnicodeDecodeError
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="ignore",
        )
        return result.stdout or ""
    except Exception:
        return ""


def _parse_names(output: str, name_index: int, header_marker: str = " --") -> Set[str]:
    names: Set[str] = set()
    started = False
    for line in output.splitlines():
        if line.startswith(header_marker):
            started = True
            continue
        if not started:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, name_index + 1)
        if len(parts) <= name_index:
            continue
        raw = parts[name_index]
        for item in raw.split(","):
            item = item.strip()
            if item:
                names.add(item)
    return names


def detect(ffmpeg_path: str = "", ffprobe_path: str = "") -> Capabilities:
    ffmpeg = resolve_executable("ffmpeg", ffmpeg_path)
    ffprobe = resolve_executable("ffprobe", ffprobe_path)

    if not ffmpeg or not ffprobe:
        return Capabilities(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            error="未找到 ffmpeg / ffprobe，请在「设置」中指定路径。",
        )

    version_output = _run([ffmpeg, "-hide_banner", "-version"])
    version = ""
    for line in version_output.splitlines():
        if line.startswith("ffmpeg version"):
            version = line.split(" ", 2)[-1].strip()
            break

    encoders = _parse_names(_run([ffmpeg, "-hide_banner", "-encoders"]), 1)
    muxers = _parse_names(_run([ffmpeg, "-hide_banner", "-muxers"]), 1)
    demuxers = _parse_names(_run([ffmpeg, "-hide_banner", "-demuxers"]), 1)

    if not encoders:
        return Capabilities(ffmpeg=ffmpeg, ffprobe=ffprobe, version=version,
                            error="无法读取 ffmpeg 编码器列表，请检查程序是否完整。")

    return Capabilities(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        version=version,
        encoders=encoders,
        muxers=muxers,
        demuxers=demuxers,
    )
