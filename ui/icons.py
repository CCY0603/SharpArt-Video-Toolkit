"""Lucide 风格单色 SVG 图标：渲染、缓存与控件辅助。

图标源文件（stroke="currentColor" 的线性描边）位于 ``assets/icons/``，
渲染时用当前主题色替换 ``currentColor``，得到跨平台一致、跟随深浅色的单色图标。
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.theme import current_palette, solid_color

_ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")

# 缓存键：(name, color_hex, size, dpr*2) -> QPixmap
# 有界 LRU：主题/调色板切换会产生大量 (name,color,size,dpr) 组合，
# 不限制会让 QPixmap 常驻显存/内存无限增长。
_MAX_PIXMAP_CACHE = 256
_cache: "OrderedDict[Tuple[str, str, int, int], QPixmap]" = OrderedDict()

# SVG 源文件缓存：name -> svg_text（避免每次读取磁盘）
_SVG_TEXT_CACHE: Dict[str, Optional[str]] = {}

# SVG 渲染器缓存：(name, color_hex) -> QSvgRenderer，用于直接绘制到目标矩形
# 同样有界，避免主题切换时无限增长。
_MAX_RENDERER_CACHE = 128
_RENDERER_CACHE: "OrderedDict[Tuple[str, str], QSvgRenderer]" = OrderedDict()


def _dpr() -> float:
    app = QApplication.instance()
    if app is None:
        return 1.0
    screen = app.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def icon(name: str, color: QColor, size: int) -> QPixmap:
    """渲染指定名称的线性 SVG 图标为单色 ``QPixmap``（含高分屏与缓存）。"""
    dpr = _dpr()
    key = (name, color.name(), size, int(dpr * 2))
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached

    path = os.path.join(_ICONS_DIR, f"{name}.svg")
    px = max(1, int(size * dpr))

    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            svg = fh.read().replace("currentColor", color.name())
        renderer = QSvgRenderer()
        if renderer.load(svg.encode("utf-8")):
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter, pm.rect().toRectF())
            painter.end()

    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    if len(_cache) > _MAX_PIXMAP_CACHE:
        _cache.popitem(last=False)
    return pm


def _svg_text(name: str) -> Optional[str]:
    """读取并缓存 SVG 源文本，图标不存在时返回 None。"""
    if name not in _SVG_TEXT_CACHE:
        path = os.path.join(_ICONS_DIR, f"{name}.svg")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                _SVG_TEXT_CACHE[name] = fh.read()
        else:
            _SVG_TEXT_CACHE[name] = None
    return _SVG_TEXT_CACHE[name]


def _renderer(name: str, color: QColor) -> Optional[QSvgRenderer]:
    """获取已按指定颜色渲染好的 QSvgRenderer（缓存复用，有界 LRU）。"""
    key = (name, color.name())
    renderer = _RENDERER_CACHE.get(key)
    if renderer is not None:
        _RENDERER_CACHE.move_to_end(key)
        return renderer
    svg = _svg_text(name)
    if svg is None:
        return None
    renderer = QSvgRenderer()
    if renderer.load(svg.replace("currentColor", color.name()).encode("utf-8")):
        _RENDERER_CACHE[key] = renderer
        if len(_RENDERER_CACHE) > _MAX_RENDERER_CACHE:
            _RENDERER_CACHE.popitem(last=False)
        return renderer
    return None


def paint_icon(painter: QPainter, name: str, color: QColor, rect: QRectF) -> None:
    """将 SVG 图标直接绘制到指定矩形（设备独立像素），避免 QPixmap 缩放造成的模糊/锯齿。

    适合在自定义 ``paint`` 中使用；按钮等控件仍用 ``icon()`` 返回的 ``QPixmap``。
    """
    renderer = _renderer(name, color)
    if renderer is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, rect)
    painter.restore()


def clear_cache() -> None:
    """主题切换后清空缓存，强制用新颜色重新渲染。"""
    _cache.clear()
    _SVG_TEXT_CACHE.clear()
    _RENDERER_CACHE.clear()


# ------------------------------------------------------------------ 控件辅助
def set_button_icon(btn: QPushButton, name: str, size: int = 16) -> None:
    """为按钮设置 SVG 图标（图标 + 文字），并自动跟随启用/禁用态与主题色。"""
    btn.setProperty("iconName", name)
    btn.setProperty("iconSizeHint", size)
    if btn.property("_icon_updater") is None:
        updater = _ButtonIconUpdater(name, size, btn)
        btn.setProperty("_icon_updater", updater)
        btn.installEventFilter(updater)
    _apply_button_icon(btn)


def _button_icon_color(btn: QPushButton) -> QColor:
    """根据按钮 variant 与状态返回应使用的图标颜色。"""
    p = current_palette()
    if not btn.isEnabled():
        return solid_color(p.text_disabled)
    variant = btn.property("variant") or ""
    if variant == "primary":
        # primary 按钮背景为强调色，文字为 on_accent（白色），图标同步为白色
        return solid_color(p.on_accent)
    if variant == "danger":
        # danger 默认红字，hover/pressed 时白字
        if btn.underMouse() or btn.isDown():
            return solid_color(p.on_accent)
        return solid_color(p.danger)
    if variant == "tool" and btn.isChecked():
        # tool 按钮选中态为强调色文字
        return solid_color(p.accent)
    return solid_color(p.text)


def _apply_button_icon(btn: QPushButton) -> None:
    name = btn.property("iconName")
    if not name:
        return
    size = int(btn.property("iconSizeHint") or 16)
    pm = icon(name, _button_icon_color(btn), size)
    btn.setIcon(pm)
    btn.setIconSize(QSize(size, size))


def recolor_buttons(parent: QWidget) -> None:
    """主题切换时，重绘父控件下所有已设置 SVG 图标的按钮。"""
    for btn in parent.findChildren(QPushButton):
        if btn.property("iconName"):
            _apply_button_icon(btn)


class _ButtonIconUpdater(QObject):
    """监听按钮状态/样式变化并刷新图标颜色的事件过滤器。"""

    def __init__(self, name: str, size: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        if isinstance(parent, QPushButton) and parent.isCheckable():
            parent.toggled.connect(lambda _checked, b=parent: _apply_button_icon(b))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (
            QEvent.EnabledChange,
            QEvent.HoverEnter,
            QEvent.HoverLeave,
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.StyleChange,
            QEvent.DynamicPropertyChange,
        ):
            _apply_button_icon(watched)
        return super().eventFilter(watched, event)


class IconText(QWidget):
    """图标 + 文字的组合控件（用于状态计数等需要图标前缀的标签）。"""

    def __init__(
        self,
        name: str = "",
        text: str = "",
        size: int = 14,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        self._palette = current_palette()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self._icon = QLabel(self)
        self._icon.setFixedSize(size, size)
        self._text = QLabel(text, self)
        self._text.setObjectName("caption")
        layout.addWidget(self._icon)
        layout.addWidget(self._text)
        self._refresh()

    def set_text(self, text: str) -> None:
        self._text.setText(text)

    def set_icon(self, name: str) -> None:
        self._name = name
        self._refresh()

    def set_icon_visible(self, visible: bool) -> None:
        self._icon.setVisible(visible)

    def set_text_style(self, name: str) -> None:
        """切换文字标签的 QSS objectName（如 caption / statusWarning）。"""
        self._text.setObjectName(name)
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)

    def set_palette(self, palette) -> None:
        self._palette = palette
        self._refresh()

    def _refresh(self) -> None:
        if self._name:
            color = solid_color(self._palette.text_secondary)
            self._icon.setPixmap(icon(self._name, color, self._size))
            self._icon.setFixedSize(self._size, self._size)
            self._icon.setVisible(True)
        else:
            self._icon.clear()
            self._icon.setVisible(False)
