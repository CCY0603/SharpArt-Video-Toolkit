"""自定义圆角 tooltip，替代系统直角 tooltip。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.theme import current_palette, font_of, solid_color


class RoundedToolTip(QWidget):
    """圆角、无边框、单例 tooltip。"""

    _instance: RoundedToolTip | None = None
    _margin = 8
    _radius = 8

    def __init__(self, parent=None) -> None:
        flags = (
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    @classmethod
    def _ensure(cls) -> RoundedToolTip:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def show_for(cls, widget: QWidget, text: str, duration_ms: int = 5000) -> None:
        if not text:
            cls.hide_now()
            return
        tip = cls._ensure()
        tip._prepare(text)
        pos = widget.mapToGlobal(QPoint(0, widget.height() + 4))

        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()

        if pos.x() + tip.width() > screen_geo.right():
            pos.setX(screen_geo.right() - tip.width() - 8)
        if pos.y() + tip.height() > screen_geo.bottom():
            pos = widget.mapToGlobal(QPoint(0, -tip.height() - 4))
        if pos.x() < screen_geo.left():
            pos.setX(screen_geo.left() + 4)
        if pos.y() < screen_geo.top():
            pos.setY(screen_geo.top() + 4)

        tip.move(pos)
        tip.show()
        tip.raise_()
        tip._hide_timer.start(duration_ms)

    @classmethod
    def hide_now(cls) -> None:
        if cls._instance is not None:
            cls._instance._hide_timer.stop()
            cls._instance.hide()

    def _prepare(self, text: str) -> None:
        p = current_palette()
        self._label.setFont(font_of(12, 400))
        self._label.setStyleSheet(
            f"color: {p.text}; background: transparent; border: none;"
        )
        self._label.setText(text)
        self._label.adjustSize()
        self.resize(
            self._label.width() + self._margin * 2,
            self._label.height() + self._margin * 2,
        )
        self._label.move(self._margin, self._margin)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            self.rect().adjusted(1, 1, -1, -1), self._radius, self._radius
        )
        painter.fillPath(path, solid_color(p.card_solid))
        painter.setPen(QColor(0, 0, 0, 30))
        painter.drawPath(path)
