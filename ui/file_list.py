"""批处理列表：表格模型、状态委托与顶部摘要统计。"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QModelIndex, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.theme import LIGHT, font_of, solid_color

from core.models import TaskItem, TaskStatus
from ui.icons import paint_icon
from ui.widgets import badge, button

COL_INDEX, COL_NAME, COL_SIZE, COL_DURATION, COL_RESOLUTION, COL_TARGET, COL_STATUS, COL_ACTION = range(8)
HEADERS = ["#", "文件名", "原始大小", "时长", "分辨率", "目标压缩大小", "处理状态", "操作"]

STATUS_COLORS = {
    TaskStatus.PENDING: "secondary",
    TaskStatus.PROBING: "accent",
    TaskStatus.RUNNING: "accent",
    TaskStatus.DONE: "success",
    TaskStatus.FAILED: "danger",
    TaskStatus.CANCELED: "secondary",
}


# ------------------------------------------------------------------ 委托
class NameDelegate(QStyledItemDelegate):
    """文件名（主行）+ 路径（次行）。"""

    def __init__(self, table: "FileTable") -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        task = self._table.task_at(index.row())
        if task is None or task.info is None:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._table.palette_ref()

        margin = 10
        name_rect = QRectF(option.rect.adjusted(margin, 4, -margin, -option.rect.height() / 2))
        path_rect = QRectF(
            option.rect.adjusted(margin, option.rect.height() / 2 - 4, -margin, -4)
        )
        selected = bool(option.state & QStyle.State_Selected)
        # 选中行是柔和半透明高亮，文字保持常规色即可读；选中仅加粗强调
        painter.setPen(solid_color(p.text))
        painter.setFont(font_of(13, 600 if selected else 400))
        elided = painter.fontMetrics().elidedText(task.name, Qt.ElideMiddle, int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        painter.setPen(solid_color(p.text_secondary))
        painter.setFont(font_of(11, 400))
        elided_path = painter.fontMetrics().elidedText(
            task.info.path, Qt.ElideMiddle, int(path_rect.width())
        )
        painter.drawText(path_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_path)
        painter.restore()

    def sizeHint(self, option, index) -> object:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(50)
        return size


class StatusDelegate(QStyledItemDelegate):
    """状态图标 + 文字 + 行内进度条。"""

    def __init__(self, table: "FileTable") -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        task = self._table.task_at(index.row())
        if task is None:
            super().paint(painter, option, index)
            return
        p = self._table.palette_ref()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        color_key = STATUS_COLORS.get(task.status, "secondary")
        color = solid_color({
            "secondary": p.text_secondary,
            "accent": p.accent,
            "success": p.success,
            "danger": p.danger,
        }[color_key])

        if task.status == TaskStatus.RUNNING:
            label = f"{task.progress * 100:.0f}%"
            if task.total_passes > 1:
                label += f"（第 {task.pass_index}/{task.total_passes} 遍）"
            if task.error:
                label += "　校准中"
        elif task.status == TaskStatus.DONE and task.error:
            label = "已完成"
        else:
            label = TaskStatus.LABELS.get(task.status, "")

        icon_name = TaskStatus.ICONS.get(task.status)
        icon_size = 14
        gap = 6
        painter.setPen(color)  # color 已是 QColor，不能再过 solid_color（其只接受字符串）
        painter.setFont(font_of(12, 600 if task.status == TaskStatus.RUNNING else 400))
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(label)

        # 计算「图标 + 间距 + 文字（+告警图标）」整体宽度，使其在单元格内水平居中
        has_alert = task.status == TaskStatus.DONE and task.error
        icon_w = icon_size if icon_name else 0
        icon_gap = gap if icon_name else 0
        alert_w = icon_size if has_alert else 0
        alert_gap = gap if has_alert else 0
        block_w = icon_w + icon_gap + text_width + alert_gap + alert_w
        start_x = option.rect.left() + max(0.0, (option.rect.width() - block_w) / 2.0)
        vcenter = option.rect.top() + option.rect.height() / 2.0

        # 图标与文字均按单元格垂直中心对齐，保证同一水平线、基线一致
        # 直接绘制 SVG 到目标矩形，避免 QPixmap 缩放导致的模糊/锯齿
        # 图标颜色与文字一致（随状态色变化），强化等待/处理中/完成/失败的颜色区分
        if icon_name:
            paint_icon(
                painter,
                icon_name,
                color,
                QRectF(start_x, vcenter - icon_size / 2.0, icon_size, icon_size),
            )
        text_x = start_x + icon_w + icon_gap
        text_rect = QRectF(text_x, option.rect.top(), text_width, option.rect.height())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

        # 已完成但存在错误时，在文字后补充告警图标
        if has_alert:
            alert_x = text_x + text_width + gap
            paint_icon(
                painter,
                "alert-triangle",
                solid_color(p.danger),
                QRectF(alert_x, vcenter - icon_size / 2.0, icon_size, icon_size),
            )

        # 进度条
        if task.status in (TaskStatus.RUNNING, TaskStatus.DONE):
            bar_rect = QRectF(
                option.rect.left() + 10,
                option.rect.bottom() - 9,
                option.rect.width() - 20,
                4,
            )
            track = QPainterPath()
            track.addRoundedRect(bar_rect, 2, 2)
            painter.fillPath(track, solid_color(p.track))
            ratio = 1.0 if task.status == TaskStatus.DONE else min(max(task.progress, 0.02), 1.0)
            chunk_rect = QRectF(bar_rect)
            chunk_rect.setWidth(bar_rect.width() * ratio)
            chunk = QPainterPath()
            chunk.addRoundedRect(chunk_rect, 2, 2)
            painter.fillPath(chunk, color)
        painter.restore()

    def sizeHint(self, option, index) -> object:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(50)
        return size


class ActionDelegate(QStyledItemDelegate):
    """操作列：居中绘制删除（trash）图标，点击由表格 cellPressed 处理。"""

    def __init__(self, table: "FileTable") -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        task = self._table.task_at(index.row())
        if task is None:
            return
        p = self._table.palette_ref()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        icon_size = 16
        # 选中/悬停行用强调色提示可点击，普通行用主文字色。
        # 选中行是柔和半透明高亮，on_accent（白）在浅底上不可见，故用 accent。
        if selected or hover:
            color = p.accent
        else:
            color = p.text
        rect = QRectF(
            option.rect.left() + (option.rect.width() - icon_size) / 2.0,
            option.rect.top() + (option.rect.height() - icon_size) / 2.0,
            icon_size,
            icon_size,
        )
        paint_icon(painter, "trash", solid_color(color), rect)
        painter.restore()

    def sizeHint(self, option, index) -> object:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(50)
        return size


# ------------------------------------------------------------------ 表格

def _parse_target_size(text: str) -> Optional[float]:
    text = text.strip().upper().replace(",", "").replace(" ", "")
    if not text:
        return None
    for unit, factor in (("TB", 1024 ** 4), ("GB", 1024 ** 3),
                         ("MB", 1024 ** 2), ("KB", 1024), ("B", 1)):
        if text.endswith(unit):
            body = text[: -len(unit)]
            if body:
                try:
                    return float(body) * factor
                except ValueError:
                    return None
            return None
    # 无单位后缀时按 MB 解释：与设置区默认单位一致，符合"输入 50 = 50MB"的直觉
    try:
        return float(text) * 1024 ** 2
    except ValueError:
        return None


class TargetDelegate(QStyledItemDelegate):

    def __init__(self, table: "FileTable") -> None:
        super().__init__(table)
        self._table = table

    def setModelData(self, editor, model, index) -> None:
        text = editor.text().strip()
        task = self._table.task_at(index.row())
        if task is None or task.params is None:
            return
        if not text:
            return
        num = _parse_target_size(text)
        if num is None or num <= 0:
            return
        task.params.size_mode = "absolute"
        # 下限 1MB：避免误输入得到荒谬的小目标
        task.params.target_bytes = max(int(num), 1024 ** 2)
        # 标记为已单独调整，避免被智能目标覆盖
        task.custom_params = True
        self._table.update_task(task)
        self._table.targetEdited.emit(task)


class FileTable(QTableWidget):
    """批处理任务表。"""

    removeRequested = Signal()
    resetRequested = Signal()
    targetEdited = Signal(object)
    taskDeleteRequested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(HEADERS), parent)
        self._tasks: List[TaskItem] = []
        self._palette = LIGHT

        self.setHorizontalHeaderLabels(HEADERS)
        self._apply_header_alignment()
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        # 关闭 viewport 自动填充：否则深色主题下整片表格会显示不透明的浅色底块
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background-color: transparent;")

        # 选中行由 paintEvent 统一绘制圆角高亮，禁用所有默认直角选择背景；
        # 不强制 selection-color，文字色由 delegate 按主题绘制
        self.setStyleSheet(
            "QTableWidget { selection-background-color: transparent; }\n"
            "QTableWidget::item:selected { background-color: transparent; }\n"
            "QTableWidget::item { background-color: transparent; }"
        )

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.setColumnWidth(COL_INDEX, 46)
        self.setColumnWidth(COL_NAME, 300)
        self.setColumnWidth(COL_SIZE, 88)
        self.setColumnWidth(COL_DURATION, 74)
        self.setColumnWidth(COL_RESOLUTION, 110)
        self.setColumnWidth(COL_TARGET, 108)
        self.setColumnWidth(COL_STATUS, 148)
        self.setColumnWidth(COL_ACTION, 52)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        # 压缩左侧最小宽度，给右侧「文件信息 / 格式转换」留出更多空间，
        # 同时仍能保证表格主要列可见；文件名列会自动拉伸并显示省略号。
        self.setMinimumWidth(760)

        self.setItemDelegateForColumn(COL_NAME, NameDelegate(self))
        self.setItemDelegateForColumn(COL_STATUS, StatusDelegate(self))
        self.setItemDelegateForColumn(COL_TARGET, TargetDelegate(self))
        self.setItemDelegateForColumn(COL_ACTION, ActionDelegate(self))
        # 统一固定行高，避免单行/双行内容行高忽高忽低造成列错位
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(50)
        # 操作列点击删除：点击「操作」列单元格即请求移除该行
        self.cellPressed.connect(self._on_cell_pressed)

    # ------------------------------------------------------------ 外观
    def set_palette(self, palette) -> None:
        self._palette = palette
        self.viewport().update()

    def restore_layout(self) -> None:
        """表格从隐藏状态显示后，重新同步表头与列宽，避免错位。"""
        header = self.horizontalHeader()
        # 先强制固定宽度，避免表头自动压缩；设置完成后再恢复可拖动
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setStretchLastSection(False)
        self.setColumnWidth(COL_INDEX, 46)
        self.setColumnWidth(COL_NAME, 300)
        self.setColumnWidth(COL_SIZE, 88)
        self.setColumnWidth(COL_DURATION, 74)
        self.setColumnWidth(COL_RESOLUTION, 110)
        self.setColumnWidth(COL_TARGET, 108)
        self.setColumnWidth(COL_STATUS, 148)
        self.setColumnWidth(COL_ACTION, 52)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        self._apply_header_alignment()
        self.horizontalScrollBar().setValue(0)
        self.updateGeometry()
        self.viewport().update()

    def _apply_header_alignment(self) -> None:
        """使表头文字对齐与数据单元格一致，消除表头/数据错位。"""
        mapping = {
            COL_INDEX: Qt.AlignCenter,
            COL_NAME: Qt.AlignLeft | Qt.AlignVCenter,
            COL_SIZE: Qt.AlignCenter | Qt.AlignVCenter,
            COL_DURATION: Qt.AlignCenter | Qt.AlignVCenter,
            COL_RESOLUTION: Qt.AlignCenter | Qt.AlignVCenter,
            COL_TARGET: Qt.AlignCenter | Qt.AlignVCenter,
            COL_STATUS: Qt.AlignCenter | Qt.AlignVCenter,
            COL_ACTION: Qt.AlignCenter | Qt.AlignVCenter,
        }
        for col, align in mapping.items():
            item = self.horizontalHeaderItem(col)
            if item is not None:
                item.setTextAlignment(align)

    def palette_ref(self):
        return self._palette

    def paintEvent(self, event) -> None:
        """绘制斑马线 + 统一圆角选中高亮，替代默认直角选择背景。"""
        if self._palette:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            viewport_rect = self.viewport().rect()
            radius = 8
            margin = 2

            # 斑马线：隔行浅底色，增强长列表可读性（偶数行留白、奇数行浅底）
            zebra = solid_color(self._palette.zebra)
            for row in range(self.rowCount()):
                y = self.rowViewportPosition(row)
                h = self.rowHeight(row)
                if y + h <= viewport_rect.top() or y >= viewport_rect.bottom():
                    continue
                if row % 2 == 1:
                    row_rect = QRectF(
                        viewport_rect.left() + 1,
                        y + 1,
                        viewport_rect.width() - 2,
                        h - 2,
                    )
                    painter.fillRect(row_rect, zebra)

            # 选中行：圆角强高亮（画在斑马线之上）
            selected_rows = sorted(
                r for r in range(self.rowCount())
                if self.selectionModel().isRowSelected(r, QModelIndex())
            )
            groups: List[List[int]] = []
            for row in selected_rows:
                if groups and row == groups[-1][-1] + 1:
                    groups[-1].append(row)
                else:
                    groups.append([row])

            for group in groups:
                y = self.rowViewportPosition(group[0])
                h = sum(self.rowHeight(r) for r in group)
                if y + h <= viewport_rect.top() or y >= viewport_rect.bottom():
                    continue
                row_rect = QRectF(
                    viewport_rect.left() + margin,
                    y + margin,
                    viewport_rect.width() - margin * 2,
                    h - margin * 2,
                )
                path = QPainterPath()
                path.addRoundedRect(row_rect, radius, radius)
                painter.fillPath(path, solid_color(self._palette.selection))
            painter.end()
        super().paintEvent(event)

    # ------------------------------------------------------------ 数据
    def tasks(self) -> List[TaskItem]:
        return list(self._tasks)

    def task_at(self, row: int) -> Optional[TaskItem]:
        if 0 <= row < len(self._tasks):
            return self._tasks[row]
        return None

    def _on_cell_pressed(self, row: int, column: int) -> None:
        """操作列（最右侧）被点击时，请求移除该行对应的任务。"""
        if column != COL_ACTION:
            return
        task = self.task_at(row)
        if task is not None:
            self.taskDeleteRequested.emit(task)

    def row_of(self, task: TaskItem) -> int:
        try:
            return self._tasks.index(task)
        except ValueError:
            return -1

    def add_task(self, task: TaskItem) -> None:
        self._tasks.append(task)
        row = len(self._tasks) - 1
        self.insertRow(row)
        for column in range(len(HEADERS)):
            self.setItem(row, column, QTableWidgetItem(""))
        self._fill_row(row, task)

    def _fill_row(self, row: int, task: TaskItem) -> None:
        info = task.info
        values = {
            COL_INDEX: str(row + 1),
            COL_NAME: task.name,
            COL_SIZE: info.size_text if info else "—",
            COL_DURATION: info.duration_text if info else "—",
            # 仅显示分辨率数值（如 3840×2160），不再额外显示 4K/1080p tooltip
            COL_RESOLUTION: f"{info.resolution_text}" if info and info.width else "—",
            COL_TARGET: task.target_text,
            COL_STATUS: "",
        }
        # 每列水平对齐：文件名左对齐；其余居中（编号/原始大小/时长/分辨率/目标/状态/操作）
        h_align = {
            COL_NAME: Qt.AlignLeft,
            COL_INDEX: Qt.AlignCenter,
            COL_SIZE: Qt.AlignCenter,
            COL_DURATION: Qt.AlignCenter,
            COL_RESOLUTION: Qt.AlignCenter,
            COL_TARGET: Qt.AlignCenter,
            COL_STATUS: Qt.AlignCenter,
            COL_ACTION: Qt.AlignCenter,
        }
        for column, text in values.items():
            item = self.item(row, column)
            if item is None:
                item = QTableWidgetItem(text)
                self.setItem(row, column, item)
            else:
                item.setText(text)
            if column == COL_TARGET:
                item.setFlags(item.flags() | Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            # 强制所有列垂直居中，消除窄行在高行内的视觉错位
            item.setTextAlignment(h_align.get(column, Qt.AlignLeft) | Qt.AlignVCenter)
        # 操作列：不可编辑、居中、提示可移除（图标由 ActionDelegate 绘制）
        action_item = self.item(row, COL_ACTION)
        if action_item is not None:
            action_item.setFlags(action_item.flags() & ~Qt.ItemIsEditable)
            action_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            action_item.setToolTip("从列表移除")
        status_item = self.item(row, COL_STATUS)
        if status_item is not None:
            status_item.setToolTip(task.error or "")

    def update_task(self, task: TaskItem) -> None:
        row = self.row_of(task)
        if row < 0:
            return
        self._fill_row(row, task)
        self.viewport().update()

    def refresh_all(self) -> None:
        for row, task in enumerate(self._tasks):
            self._fill_row(row, task)
        self.viewport().update()

    def remove_task(self, task: TaskItem) -> None:
        row = self.row_of(task)
        if row < 0:
            return
        self._tasks.pop(row)
        self.removeRow(row)
        self.refresh_all()

    def clear_completed(self) -> int:
        remaining: List[TaskItem] = []
        removed = 0
        for task in self._tasks:
            if task.status == TaskStatus.DONE:
                removed += 1
            else:
                remaining.append(task)
        if removed:
            self.setRowCount(0)
            self._tasks = []
            for task in remaining:
                self.add_task(task)
        return removed

    def remove_selected(self) -> int:
        """移除当前选中的行（仅从列表移除，不改动源文件）。"""
        tasks = self.selected_tasks()
        for task in tasks:
            self.remove_task(task)
        return len(tasks)

    def contextMenuEvent(self, event) -> None:
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        if not self.selectedIndexes():
            self.selectRow(index.row())
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        # 改为不透明背景，避免右键菜单半透明难以看清
        remove_action = menu.addAction("移除选中")
        remove_action.triggered.connect(self.removeRequested.emit)
        reset_action = menu.addAction("重置状态")
        reset_action.triggered.connect(self.resetRequested.emit)
        menu.exec(event.globalPos())

    def clear_all(self) -> None:
        self.setRowCount(0)
        self._tasks = []

    def selected_tasks(self) -> List[TaskItem]:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        return [self._tasks[r] for r in rows if 0 <= r < len(self._tasks)]

    def select_tasks(self, tasks: List[TaskItem]) -> None:
        self.clearSelection()
        for task in tasks:
            row = self.row_of(task)
            if row >= 0:
                self.selectRow(row)


# ------------------------------------------------------------------ 摘要条
class SummaryBar(QWidget):
    """顶部摘要：文件数、总大小、总时长与格式/分辨率胶囊。"""

    clearRequested = Signal()
    removeSelectedRequested = Signal()
    resetStatusRequested = Signal()
    courseCompressRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._palette = LIGHT
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(8)

        self._count_label = QLabel("尚未添加文件", self)
        self._count_label.setFont(font_of(13, 500))
        layout.addWidget(self._count_label)
        layout.addSpacing(6)

        self._chips_layout = QHBoxLayout()
        self._chips_layout.setSpacing(6)
        layout.addLayout(self._chips_layout, 1)

        layout.addStretch(1)
        self._course_btn = QPushButton("课程压缩", self)
        self._course_btn.setProperty("variant", "ghost")
        self._course_btn.setCursor(Qt.PointingHandCursor)
        self._course_btn.setToolTip("按可调参数批量压缩课程视频（H.264 + AAC，画质优先）")
        self._course_btn.clicked.connect(self.courseCompressRequested.emit)
        layout.addWidget(self._course_btn)

        self._remove_btn = QPushButton("移除选中", self)
        self._remove_btn.setProperty("variant", "ghost")
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.setToolTip("从处理列表中移除选中的文件，源文件不受影响")
        self._remove_btn.clicked.connect(self.removeSelectedRequested.emit)
        layout.addWidget(self._remove_btn)

        self._reset_btn = QPushButton("重置状态", self)
        self._reset_btn.setProperty("variant", "ghost")
        self._reset_btn.setCursor(Qt.PointingHandCursor)
        self._reset_btn.setToolTip("将已完成/失败/取消的选中文件重置为待处理，可重新加入队列")
        self._reset_btn.clicked.connect(self.resetStatusRequested.emit)
        layout.addWidget(self._reset_btn)

        self._clear_btn = button("全部清空", "ghost", self)
        self._clear_btn.clicked.connect(self.clearRequested.emit)
        layout.addWidget(self._clear_btn)

    def set_palette(self, palette) -> None:
        self._palette = palette

    def update_stats(self, tasks: List[TaskItem]) -> None:
        from core.utils import format_duration_cn, format_size

        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not tasks:
            self._count_label.setText("尚未添加文件")
            self._clear_btn.setVisible(False)
            self._course_btn.setVisible(False)
            self._remove_btn.setVisible(False)
            self._reset_btn.setVisible(False)
            return

        self._clear_btn.setVisible(True)
        self._course_btn.setVisible(True)
        self._remove_btn.setVisible(True)
        self._reset_btn.setVisible(True)
        total_size = 0
        total_duration = 0.0
        count_4k = count_1080p = count_mov = count_mp4 = 0
        for task in tasks:
            info = task.info
            if info is None:
                continue
            total_size += info.size_bytes
            total_duration += info.duration
            if info.height >= 2160:
                count_4k += 1
            elif info.height >= 1080:
                count_1080p += 1
            ext = info.path.lower().rsplit(".", 1)[-1] if "." in info.path else ""
            if ext == "mov":
                count_mov += 1
            elif ext == "mp4":
                count_mp4 += 1

        self._count_label.setText(
            f"已添加 {len(tasks)} 个文件　总计 {format_size(total_size)}　"
            f"总时长 {format_duration_cn(total_duration)}"
        )

        chips = [
            (f"4K · {count_4k}", count_4k),
            (f"1080p · {count_1080p}", count_1080p),
            (f"MOV · {count_mov}", count_mov),
            (f"MP4 · {count_mp4}", count_mp4),
        ]
        for text, value in chips:
            if value > 0:
                self._chips_layout.addWidget(badge(text, self, neutral=True))
        self._chips_layout.addStretch(1)
