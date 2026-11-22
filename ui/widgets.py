"""通用控件：卡片、胶囊标签、键值行、按钮等。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from app.theme import DARK, LIGHT, current_palette, font_of, solid_color
from ui.tooltip import RoundedToolTip


# ------------------------------------------------------------------ 自绘选择控件
class _ThemedIndicatorMixin:
    """提供主题调色板同步能力。

    默认跟随 app.theme 的当前调色板，父级也可显式 set_palette 覆盖。
    """

    _palette = None

    def set_palette(self, palette) -> None:
        self._palette = palette
        self.update()

    def _colors(self):
        return self._palette or current_palette()


class SavtRadioButton(QRadioButton, _ThemedIndicatorMixin):
    """自绘单选按钮：外圈细边 + 选中时中心 accent 实心圆点。

    说明：Qt6 Fusion 不绘制 ::indicator:checked 的中心圆点，
    QSS 也无法通过 image / background-image 为子控件叠加图形，因此改为自绘。
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._palette = LIGHT
        # 关闭键盘焦点，避免原生蓝色焦点框
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        p = self._colors()

        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.style().subElementRect(QStyle.SE_RadioButtonIndicator, option, self)
        # 额外 0.5px 安全边距：把抗锯齿半透明边缘收进指示器内部，避免溢出到边界外
        box = QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5)

        checked = bool(option.state & QStyle.State_On)
        if checked:
            fill = solid_color(p.accent)
            border = solid_color(p.accent)
        else:
            fill = solid_color(p.card_solid)
            border = solid_color(p.border_strong)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(box)

        if checked:
            # 选中态：白色实心圆点融在蓝色底上，彻底消除白底上的浅蓝光晕
            inset = box.width() * 0.30
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(solid_color(p.on_accent)))
            painter.drawEllipse(box.adjusted(inset, inset, -inset, -inset))

        text_rect = self.style().subElementRect(QStyle.SE_RadioButtonContents, option, self)
        # manual text render: avoid drawItemText HighlightedText (white) on State_On
        text_color = solid_color(p.text) if self.isEnabled() else solid_color(p.text_disabled)
        font = self.font()
        font.setWeight(QFont.DemiBold if checked else QFont.Normal)
        painter.setPen(text_color)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, self.text())

class SavtCheckBox(QCheckBox, _ThemedIndicatorMixin):
    """自绘复选框：圆角方块 + 勾选时 accent 底色与白色勾号。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._palette = LIGHT
        # 关闭键盘焦点，避免原生蓝色焦点框
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        p = self._colors()

        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        # 额外 0.5px 安全边距：把抗锯齿半透明边缘收进指示器内部，避免溢出到边界外
        box = QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5)

        checked = option.state & QStyle.State_On
        enabled = self.isEnabled()

        fill = p.accent if checked else p.card_solid
        border_color = p.accent if checked else p.border_strong
        if not enabled:
            fill = p.track
            border_color = p.border

        painter.setPen(QPen(solid_color(border_color), 1.0))
        painter.setBrush(QBrush(solid_color(fill)))
        painter.drawRoundedRect(box, 5, 5)

        if checked:
            pen = QPen(solid_color(p.on_accent))
            pen.setWidthF(max(2.0, box.width() / 8))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            x, y, w, h = box.x(), box.y(), box.width(), box.height()
            painter.drawLine(
                QPointF(x + w * 0.24, y + h * 0.52),
                QPointF(x + w * 0.44, y + h * 0.72),
            )
            painter.drawLine(
                QPointF(x + w * 0.44, y + h * 0.72),
                QPointF(x + w * 0.78, y + h * 0.30),
            )

        text_rect = self.style().subElementRect(QStyle.SE_CheckBoxContents, option, self)
        # 同 SavtRadioButton：手动用主题色绘制文字 + 选中时加粗，避开 drawItemText 的 HighlightedText 并提升可读性
        text_color = solid_color(p.text) if enabled else solid_color(p.text_disabled)
        font = self.font()
        font.setWeight(QFont.DemiBold if checked else QFont.Normal)
        painter.setPen(text_color)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, self.text())


# ------------------------------------------------------------------ 卡片
class Card(QFrame):
    """圆角分层卡片，带柔和阴影。"""

    def __init__(self, parent=None, hover: bool = False, shadowy: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        if hover:
            self.setProperty("hover", "true")
        if shadowy:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(8)
            effect.setOffset(0, 1)
            effect.setColor(QColor(15, 23, 42, 36))
            self.setGraphicsEffect(effect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.graphicsEffect() is not None:
            radius = 12
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class Divider(QFrame):
    def __init__(self, parent=None, vertical: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("divider")
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


# ------------------------------------------------------------------ 文本
def subheading(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("subheading")
    return label


def caption(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("caption")
    return label


def muted(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("muted")
    return label


def field_label(text: str, parent=None) -> QLabel:
    """表单字段名：13px 半粗，比 caption 更醒目（用于「输出格式 / 音频 / 输出路径」等）。"""
    label = QLabel(text, parent)
    label.setObjectName("fieldLabel")
    return label


def badge(text: str, parent=None, neutral: bool = False) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("badgeNeutral" if neutral else "badge")
    return label


# ------------------------------------------------------------------ 按钮
def button(text: str, variant: str = "", parent=None, width: int = 0) -> QPushButton:
    btn = QPushButton(text, parent)
    if variant:
        btn.setProperty("variant", variant)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
    btn.setCursor(Qt.PointingHandCursor)
    if width:
        btn.setFixedWidth(width)
    return btn


# ------------------------------------------------------------------ 键值行
class InfoRow(QWidget):
    """信息面板中的「键：值」行。

    compact=True 时行高更小、字号更小，且超长值以省略号截断（完整内容保留在 tooltip），
    用于信息面板一页展示全部字段（#7）。
    """

    def __init__(self, key: str, value: str = "", key_width: int = 84, parent=None) -> None:
        super().__init__(parent)
        self._compact = False
        self._full_text = value or "—"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(10)

        self._key = muted(key, self)
        self._key.setFixedWidth(key_width)
        self._key.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._value = QLabel(self._full_text, self)
        self._value.setObjectName("mono")
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._value.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._value.setToolTip("")  # 使用自定义圆角 tooltip
        self._value.setMinimumWidth(80)  # 防止首次 layout 前宽度被压缩到 0/极小
        self._value.installEventFilter(self)

        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.timeout.connect(self._show_tooltip)

        layout.addWidget(self._key)
        layout.addWidget(self._value, 1)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.layout().setContentsMargins(0, 1, 0, 1)
        self.layout().setSpacing(6 if compact else 10)
        # 紧凑模式用略小的字号让值在 ~240px 卡片里能完整显示；
        # 正文走 Regular(400)：字号 12 兼顾可读性与一屏展示
        size = 12 if compact else 13
        self._key.setFont(font_of(size, 400))
        self._value.setFont(font_of(size, 400))
        self._value.setWordWrap(not compact)
        self._apply_elide()

    def _apply_elide(self) -> None:
        if not self._compact:
            if self._value.text() != self._full_text:
                self._value.setText(self._full_text)
            return
        # 始终以 value 当前实际宽度计算省略，避免窗口/卡片尚未 layout 时
        # 用估算宽度误截断；宽度无效时跳过，等 Resize 事件再校准。
        width = self._value.width()
        if width <= 0:
            return
        metrics = self._value.fontMetrics()
        elided = metrics.elidedText(self._full_text, Qt.ElideMiddle, width)
        if self._value.text() != elided:
            self._value.setText(elided)

    def set_value(self, text: str) -> None:
        self._full_text = text or "—"
        self._value.setToolTip("")
        self._apply_elide()
        # 通知布局系统 sizeHint 已变化，避免卡片/网格被旧的、过小的 sizeHint 锁死
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()
        # 首次导入常在 layout 稳定前触发，延迟再校准一次
        QTimer.singleShot(0, self._apply_elide)

    def value(self) -> str:
        return self._full_text

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._compact:
            self._apply_elide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._value:
            # value 宽度一旦变化（layout 完成 / 窗口缩放）立即重算省略，
            # 这是解决「首次导入文字被截断、挪动窗口才正常」的关键时机
            if event.type() == QEvent.Resize and self._compact:
                self._apply_elide()
            elif event.type() == QEvent.Enter:
                self._tip_timer.start(350)
            elif event.type() in (QEvent.Leave, QEvent.MouseButtonPress):
                self._tip_timer.stop()
                RoundedToolTip.hide_now()
        return super().eventFilter(obj, event)

    def _show_tooltip(self) -> None:
        RoundedToolTip.show_for(self._value, self._full_text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._compact:
            self._apply_elide()

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        if self._compact:
            hint.setHeight(max(hint.height(), 18))
        return hint


class GroupCard(Card):
    """带标题的信息分组卡片。

    compact=True 时使用更小的内边距、标题字号与行高，用于信息面板一页展示（#7）。
    expand=True 时垂直策略为 Expanding，并在每行之间插入弹性空白，
    使卡片填满父容器高度后各行均匀分布，2×2 网格中不再有"挤在顶部"的拥挤感。
    """

    def __init__(self, title: str, parent=None, compact: bool = False, expand: bool = False) -> None:
        super().__init__(parent)
        self._compact = compact
        self._expand = expand
        self._first_row = True
        self._layout = QVBoxLayout(self)
        if compact:
            self._layout.setContentsMargins(10, 7, 10, 6)
            self._layout.setSpacing(0)
        else:
            self._layout.setContentsMargins(14, 12, 14, 12)
            self._layout.setSpacing(2)

        if expand:
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        title_label = subheading(title, self)
        if compact:
            title_label.setFont(font_of(12, 500))
        self._layout.addWidget(title_label)
        self._layout.addSpacing(3 if compact else 4)

    def add_row(self, key: str, value: str = "", key_width: int = 84) -> InfoRow:
        row = InfoRow(key, value, key_width, self)
        self._first_row = False
        if self._compact:
            row.set_compact(True)
        self._layout.addWidget(row)
        return row

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


# ------------------------------------------------------------------ 分段控制器
class SegmentedControl(QWidget):
    """胶囊样式分段控制器：一组互斥按钮，选中项以主题 accent 高亮。

    用于「统一设置 / 独立设置」这类二选一模式切换，比两个独立按钮更直观。
    """

    modeChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        self._options: "list[tuple[str, str]]" = []  # (mode_key, label)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonToggled.connect(self.update)
        self._group.buttonClicked.connect(self._on_clicked)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(5, 5, 5, 5)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        # 父级绘制选中 pill：子按钮只负责文字，避免子控件背景溢出圆角框
        checked = self._group.checkedButton()
        if checked is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = current_palette()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(solid_color(p.accent)))
        painter.drawRoundedRect(QRectF(checked.geometry()), 3, 3)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 圆角裁剪：作为兜底，防止 hover 背景等子控件绘制溢出容器圆角
        radius = 8
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def add_option(self, mode: str, label: str) -> None:
        btn = QPushButton(label, self)
        btn.setObjectName("segBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setCheckable(True)
        # 关闭默认按钮指示器与键盘焦点，避免选中/点击时弹出 Windows 原生蓝色焦点框
        btn.setAutoDefault(False)
        btn.setDefault(False)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setProperty("segMode", mode)
        self._group.addButton(btn)
        # 在结尾的 stretch 之前插入，保证按钮居中
        self._layout.insertWidget(self._layout.count() - 1, btn)
        self._options.append((mode, label))

    def _on_clicked(self, btn: QPushButton) -> None:
        mode = btn.property("segMode")
        if mode is not None:
            self.modeChanged.emit(mode)

    def set_mode(self, mode: str) -> None:
        for btn in self._group.buttons():
            if btn.property("segMode") == mode:
                btn.setChecked(True)
                break

    def mode(self) -> str:
        checked = self._group.checkedButton()
        return checked.property("segMode") if checked is not None else ""
