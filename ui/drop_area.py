"""文件拖放区（已迁移为表格卡片内的提示横幅 DropPrompt）。"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame

from app.config import VIDEO_EXTENSIONS
from app.theme import LIGHT, font_of, solid_color


def extract_video_paths(event) -> List[str]:
    """从拖放事件中提取视频文件路径，供窗口全局拖放与 DropPrompt 复用。"""
    import os

    result = []
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if not path:
            continue
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in files:
                    full = os.path.join(root, name)
                    if os.path.splitext(full)[1].lower() in VIDEO_EXTENSIONS:
                        result.append(full)
        elif os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS:
            result.append(path)
    return result


class DropPrompt(QFrame):
    """表格卡片顶部的拖放提示横幅。

    原「拖入视频文件」独立卡片已合并到批处理队列卡片内，仅保留文字提醒。
    """

    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dropPrompt")
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setMinimumHeight(84)
        self._active = False
        self._expanded = False
        self._palette = LIGHT

    def set_palette(self, palette) -> None:
        self._palette = palette
        self.update()

    def set_expanded(self, expanded: bool) -> None:
        """空队列时切换为紧凑的扩展态虚线框，避免撑出过大空白。"""
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.setMinimumHeight(64 if expanded else 84)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)

        fill = solid_color(p.accent_soft if self._active else p.card_alt)
        painter.fillPath(path, fill)

        pen = QPen(solid_color(p.accent if self._active else p.border_strong))
        pen.setWidth(2 if self._active else 1)
        pen.setStyle(Qt.SolidLine if self._active else Qt.DashLine)
        if not self._active:
            pen.setDashPattern([6, 5])
        painter.setPen(pen)
        painter.drawPath(path)

        # 图标 + 文字整体按左侧固定边距排布；图标中心与主标题垂直中心对齐
        margin = 24
        center_x = margin + 16
        text_left = center_x + 16 + 12
        text_right_margin = 12

        if self._active:
            title = "松开鼠标即可加入队列"
            title_font = font_of(14, 500)
            subtitle = ""
        elif self._expanded:
            title = "拖拽视频文件到此处"
            subtitle = "支持 MP4 / MOV / MKV / AVI / WebM 等全部常见格式，可一次拖入多个文件进行批处理"
            title_font = font_of(16, 600)
        else:
            title = "拖入视频文件，或点击此处添加"
            subtitle = "支持 MP4 / MOV / MKV / AVI / WebM 等全部常见格式，可一次拖入多个文件进行批处理"
            title_font = font_of(14, 500)

        # 计算标题 / 副标题矩形，使文字块在控件内垂直居中
        title_h = 24
        subtitle_h = 20
        gap = 2
        if subtitle:
            block_h = title_h + gap + subtitle_h
        else:
            block_h = title_h
        block_top = (self.height() - block_h) / 2.0

        painter.setPen(QColor(p.text))
        painter.setFont(title_font)
        title_rect = QRectF(
            text_left,
            block_top,
            self.width() - text_left - text_right_margin,
            title_h,
        )
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        subtitle_rect = QRectF()
        if subtitle:
            painter.setPen(QColor(p.text_secondary))
            painter.setFont(font_of(12, 400))
            subtitle_rect = QRectF(
                text_left,
                block_top + title_h + gap,
                self.width() - text_left - text_right_margin,
                subtitle_h,
            )
            painter.drawText(subtitle_rect, Qt.AlignLeft | Qt.AlignVCenter, subtitle)

        # 图标中心对齐到主标题的垂直中心，保证图标与第一行文字在一条水平线上
        icon_center_y = block_top + title_h / 2.0
        radius = 16 if self._active else 14
        painter.setPen(Qt.NoPen)
        painter.setBrush(solid_color(p.accent))
        painter.drawEllipse(
            QRectF(
                center_x - radius,
                icon_center_y - radius,
                radius * 2,
                radius * 2,
            )
        )
        painter.setPen(QPen(solid_color(p.on_accent), 2.0))
        cross_len = radius * 0.45
        painter.drawLine(center_x - cross_len, icon_center_y, center_x + cross_len, icon_center_y)
        painter.drawLine(center_x, icon_center_y - cross_len, center_x, icon_center_y + cross_len)

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._active = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._active = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._active = False
        self.update()
        paths = extract_video_paths(event)
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()
