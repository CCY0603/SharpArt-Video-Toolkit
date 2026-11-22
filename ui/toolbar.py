"""顶部工具栏：文件操作、批量模式与并发菜单。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from ui.widgets import Divider, SegmentedControl, button, caption
from ui.icons import IconText, recolor_buttons, set_button_icon


class Toolbar(QWidget):
    addFilesRequested = Signal()
    settingsRequested = Signal()
    batchModeChanged = Signal(str)
    concurrencyChanged = Signal(int)
    gpuInfoRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 2, 14, 2)
        layout.setSpacing(8)

        self._add_btn = button("添加文件", "primary", self)
        set_button_icon(self._add_btn, "plus")
        self._add_btn.clicked.connect(self.addFilesRequested.emit)

        self._queue_btn = button("任务队列", "tool", self)
        set_button_icon(self._queue_btn, "list")
        self._queue_menu = QMenu(self)
        self._concurrency_group = []
        for value, text in ((1, "顺序处理（默认）"), (2, "并发 2 个"), (3, "并发 3 个")):
            action = self._queue_menu.addAction(text)
            action.setCheckable(True)
            action.setData(value)
            action.triggered.connect(lambda _checked=False, v=value: self._on_concurrency(v))
            self._concurrency_group.append(action)
        self._concurrency_group[0].setChecked(True)
        self._queue_btn.setMenu(self._queue_menu)

        self._settings_btn = button("设置", "tool", self)
        set_button_icon(self._settings_btn, "settings")
        self._settings_btn.clicked.connect(self.settingsRequested.emit)

        layout.addWidget(self._add_btn)
        layout.addWidget(self._queue_btn)
        layout.addWidget(self._settings_btn)
        layout.addWidget(Divider(self, vertical=True))
        layout.addSpacing(6)

        mode_label = caption("批量模式：", self)
        layout.addWidget(mode_label)
        self._mode_seg = SegmentedControl(self)
        self._mode_seg.add_option("unified", "统一设置")
        self._mode_seg.add_option("independent", "独立设置")
        self._mode_seg.set_mode("unified")
        self._mode_seg.modeChanged.connect(self._set_mode)
        layout.addWidget(self._mode_seg)

        layout.addStretch(1)

        self._gpu_label = caption("", self)
        layout.addWidget(self._gpu_label)
        # #13：删除工具栏独立的版本号按钮（版本信息统一在标题栏淡化显示）

    # ------------------------------------------------------------ 状态
    def _set_mode(self, mode: str) -> None:
        self._mode_seg.set_mode(mode)
        self.batchModeChanged.emit(mode)

    def set_mode(self, mode: str) -> None:
        self._set_mode(mode)

    def batch_mode(self) -> str:
        return self._mode_seg.mode()

    def _on_concurrency(self, value: int) -> None:
        for action in self._concurrency_group:
            action.setChecked(action.data() == value)
        self.concurrencyChanged.emit(value)

    def set_concurrency(self, value: int) -> None:
        self._on_concurrency(value)

    def set_gpu_text(self, text: str) -> None:
        self._gpu_label.setText(text)
        self._gpu_label.setVisible(bool(text))

    def set_palette(self, palette) -> None:
        recolor_buttons(self)
