"""硬件信息采样：CPU 型号与占用率、GPU 占用率与显存。

采样链均带优雅降级：NVIDIA GPU 走 nvidia-smi，CPU 优先 psutil，
回退 Windows 性能计数器 / 注册表，全部不可用时返回占位符，绝不抛异常。
"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QObject, QTimer, Signal

from core.capabilities import CREATE_NO_WINDOW

PLACEHOLDER = "—"


# ------------------------------------------------------------------ CPU
def cpu_model() -> str:
    """获取 CPU 型号（注册表优先，其次 platform）。"""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            name = str(value).strip()
            if name:
                return name
        except Exception:
            pass
    try:
        import platform

        name = (platform.processor() or "").strip()
        if name:
            return name
    except Exception:
        pass
    return ""


def cpu_usage() -> str:
    """获取 CPU 占用率百分比文本。"""
    # 1) psutil（最准确，若环境已安装）
    try:
        import psutil  # type: ignore

        return f"{psutil.cpu_percent(interval=None):.0f} %"
    except Exception:
        pass

    if sys.platform == "win32":
        # 2) 性能计数器（PDH 的原始计数器，读取瞬时值）
        try:
            result = subprocess.run(
                ["typeperf", r"\Processor Information(_Total)\% Processor Utility", "-sc", "1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=6,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="ignore",
            )
            lines = [line for line in (result.stdout or "").splitlines() if "," in line]
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        value = float(parts[-1].strip().strip('"'))
                        return f"{value:.0f} %"
                    except ValueError:
                        continue
        except Exception:
            pass

        # 3) wmic（旧版 Windows 可用，新版可能已移除）
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "loadpercentage"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="ignore",
            )
            for line in (result.stdout or "").splitlines():
                text = line.strip()
                if text.isdigit():
                    return f"{text} %"
        except Exception:
            pass
    return PLACEHOLDER


def cpu_text() -> str:
    """格式化 CPU 显示文本：型号（截断）+ 占用率。"""
    model = cpu_model()
    usage = cpu_usage()
    if model:
        if len(model) > 26:
            model = model[:25] + "…"
        return f"CPU {model}　{usage}"
    return f"CPU {usage}"


# ------------------------------------------------------------------ GPU
def gpu_stats() -> tuple[str, str, str]:
    """返回 (占用率, 显存文本, 显卡名)，不可用时返回占位符。"""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return PLACEHOLDER, "", ""
        lines = (result.stdout or b"").decode("utf-8", "ignore").strip().splitlines()
        if not lines:
            return PLACEHOLDER, "", ""
        parts = [p.strip() for p in lines[0].split(",")]
        if len(parts) < 4:
            return PLACEHOLDER, "", ""
        name, usage, used, total = parts[0], parts[1], parts[2], parts[3]
        try:
            used_f, total_f = float(used), float(total)
            memory = f"{used_f / 1024:.1f} / {total_f / 1024:.1f} GB"
        except ValueError:
            memory = f"{used} / {total} MB"
        return f"{usage} %", memory, name
    except Exception:
        return PLACEHOLDER, "", ""


def gpu_text() -> str:
    usage, memory, name = gpu_stats()
    if usage == PLACEHOLDER:
        return ""
    label = name or "GPU"
    if len(label) > 22:
        label = label[:21] + "…"
    return f"GPU {label}　{usage}　显存 {memory}"


# ------------------------------------------------------------------ 监控器
class HardwareMonitor(QObject):
    """统一的硬件采样器：CPU 与 GPU 一起上报（#15）。"""

    statsUpdated = Signal(str, str)  # cpu_text, gpu_text（空串表示不可用）

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.sample)
        self._last = ("", "")

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.sample()

    def stop(self) -> None:
        self._timer.stop()

    def sample(self) -> None:
        current = (cpu_text(), gpu_text())
        if current != self._last:
            self._last = current
            self.statsUpdated.emit(current[0], current[1])
