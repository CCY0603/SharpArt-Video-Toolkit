"""应用初始化与启动。"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import APP_ID, APP_NAME, APP_NAME_CN, APP_VERSION
from app.settings import AppSettings
from app.theme import ThemeManager, ensure_font, font_of


def _app_icon() -> QIcon:
    """载入 assets/icon.png 作为应用图标（窗口 / 任务栏 / 快捷方式）。

    源码与打包两种运行形态都兼容；文件缺失时回退到内置矢量图标。
    """
    import os

    candidates = []
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(base, "assets", "icon.png"))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", "icon.png"))
    for path in candidates:
        if os.path.exists(path):
            return QIcon(path)
    return _fallback_icon()


def _fallback_icon() -> QIcon:
    """内置矢量图标（不依赖外部资源文件）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    from PySide6.QtGui import QPainter, QPainterPath, QColor

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(4, 4, 56, 56, 16, 16)
    painter.fillPath(path, QColor("#0078D4"))
    painter.setPen(Qt.white)
    f = font_of(28, 600)
    painter.setFont(f)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "S")
    painter.end()
    return QIcon(pixmap)


def _excepthook(cls, exc, tb) -> None:
    text = "".join(traceback.format_exception(cls, exc, tb))
    print(text, file=sys.stderr)
    try:
        QMessageBox.critical(
            None,
            f"{APP_NAME_CN} — 未处理异常",
            f"{cls.__name__}: {exc}\n\n{text[-1200:]}",
        )
    except Exception:
        pass


def main() -> int:
    # 进程级「每显示器 DPI 感知 V2」：跨屏到不同 DPI 屏幕时由 Windows 通知 Qt
    # 按新屏 DPI 重排重绘，避免整窗位图拉伸导致的发虚、缩放与文字大小不一致。
    # 必须在创建 QApplication 前设置；清单已在打包时内嵌，这里为源码运行兜底。
    if sys.platform == "win32":
        try:
            from PySide6.QtWin import QtWin
            QtWin.setProcessDpiAwareness(QtWin.PerMonitorV2DpiAware)
        except Exception:
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwarenessContext(-4)
            except Exception:
                pass

    # 高分屏缩放（Qt6 默认开启，显式声明更稳妥）；PassThrough 适配 150%/125% 等分数缩放
    QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME_CN} — {APP_NAME}")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("SharpArt")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(_app_icon())
    ensure_font()
    app.setFont(font_of(13, 400))

    settings = AppSettings()
    theme = ThemeManager(settings)

    sys.excepthook = _excepthook

    from ui.main_window import MainWindow

    window = MainWindow(settings, theme)
    theme.apply(app, window)
    window.show()

    return app.exec()
