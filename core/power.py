"""完成后自动关机（可取消）。"""

from __future__ import annotations

import subprocess

from core.capabilities import CREATE_NO_WINDOW


def schedule_shutdown(delay_seconds: int = 60) -> bool:
    try:
        result = subprocess.run(
            ["shutdown", "/s", "/t", str(max(delay_seconds, 10))],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def cancel_shutdown() -> bool:
    try:
        result = subprocess.run(
            ["shutdown", "/a"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False
