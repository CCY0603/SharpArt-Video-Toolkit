"""对话框：设置、汇总报告、音频提取、关机倒计时、关于。"""

from __future__ import annotations

from typing import List, Optional

from app.theme import RoundedCombo
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    APP_ABBR,
    APP_NAME,
    APP_NAME_CN,
    APP_VERSION,
    EXE_NAME,
    SLOGAN,
)
from core.capabilities import Capabilities
from core.models import TaskItem
from core.profiles import EXTRACT_FORMATS
from core.report import build_report_text
from ui.widgets import Card, SavtRadioButton, caption, subheading
from ui.icons import icon
from app.theme import current_palette, solid_color


# ------------------------------------------------------------------ 设置
class SettingsDialog(QDialog):
    settingsSaved = Signal()

    def __init__(self, settings, caps: Optional[Capabilities], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self._settings = settings
        self._caps = caps

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        ffmpeg_group = QGroupBox("ffmpeg 位置", self)
        form = QFormLayout(ffmpeg_group)
        form.setLabelAlignment(Qt.AlignRight)
        self._ffmpeg_edit = QLineEdit(self._settings.ffmpeg_path, self)
        self._ffmpeg_edit.setPlaceholderText("留空则自动使用系统 PATH 中的 ffmpeg")
        self._ffmpeg_btn = QPushButton("浏览…", self)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self._ffmpeg_edit, 1)
        ffmpeg_row.addWidget(self._ffmpeg_btn)
        form.addRow("ffmpeg.exe：", self._wrap(ffmpeg_row))

        self._probe_edit = QLineEdit(self._settings.probe_path, self)
        self._probe_edit.setPlaceholderText("留空则自动使用系统 PATH 中的 ffprobe")
        self._probe_btn = QPushButton("浏览…", self)
        probe_row = QHBoxLayout()
        probe_row.addWidget(self._probe_edit, 1)
        probe_row.addWidget(self._probe_btn)
        form.addRow("ffprobe.exe：", self._wrap(probe_row))
        layout.addWidget(ffmpeg_group)

        if caps is not None and caps.ok:
            info = Card(self)
            info_layout = QVBoxLayout(info)
            info_layout.setSpacing(2)
            info_layout.addWidget(subheading("已就绪", info))
            info_layout.addWidget(caption(f"版本：{caps.version}", info))
            info_layout.addWidget(QLabel(f"路径：{caps.ffmpeg}", info))
            info_layout.addWidget(caption(f"编码器 {len(caps.encoders)} 个 · 封装格式 {len(caps.muxers)} 个", info))
            layout.addWidget(info)

        general_group = QGroupBox("常规", self)
        general_form = QFormLayout(general_group)
        general_form.setLabelAlignment(Qt.AlignRight)

        self._output_edit = QLineEdit(self._settings.output_dir, self)
        self._output_edit.setPlaceholderText("留空则输出到源文件所在目录")
        self._output_btn = QPushButton("浏览…", self)
        output_row = QHBoxLayout()
        output_row.addWidget(self._output_edit, 1)
        output_row.addWidget(self._output_btn)
        general_form.addRow("默认输出目录：", self._wrap(output_row))

        self._concurrency_spin = QSpinBox(self)
        self._concurrency_spin.setRange(1, 3)
        self._concurrency_spin.setValue(self._settings.concurrency)
        self._concurrency_spin.setSuffix(" 个同时处理")
        general_form.addRow("并发处理：", self._concurrency_spin)

        theme_row = QHBoxLayout()
        self._theme_system = SavtRadioButton("跟随系统", self)
        self._theme_light = SavtRadioButton("浅色", self)
        self._theme_dark = SavtRadioButton("深色", self)
        current = self._settings.theme
        {"system": self._theme_system, "light": self._theme_light, "dark": self._theme_dark}.get(
            current, self._theme_system
        ).setChecked(True)
        theme_row.addWidget(self._theme_system)
        theme_row.addWidget(self._theme_light)
        theme_row.addWidget(self._theme_dark)
        theme_row.addStretch(1)
        general_form.addRow("主题：", self._wrap(theme_row))
        layout.addWidget(general_group)

        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        # 工具栏版本按钮移除后，「关于」入口迁入设置对话框
        self._about_btn = buttons.addButton("关于", QDialogButtonBox.ResetRole)
        self._about_btn.clicked.connect(self._show_about)
        layout.addWidget(buttons)

        self._ffmpeg_btn.clicked.connect(lambda: self._pick_file(self._ffmpeg_edit, "ffmpeg.exe"))
        self._probe_btn.clicked.connect(lambda: self._pick_file(self._probe_edit, "ffprobe.exe"))
        self._output_btn.clicked.connect(self._pick_dir)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    @staticmethod
    def _wrap(layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _pick_file(self, target: QLineEdit, name: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"选择 {name}", "", "可执行文件 (*.exe);;所有文件 (*.*)")
        if path:
            target.setText(path)

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择默认输出目录", self._output_edit.text())
        if path:
            self._output_edit.setText(path)

    def _save(self) -> None:
        self._settings.ffmpeg_path = self._ffmpeg_edit.text().strip()
        self._settings.probe_path = self._probe_edit.text().strip()
        self._settings.output_dir = self._output_edit.text().strip()
        self._settings.concurrency = self._concurrency_spin.value()
        theme = "system"
        if self._theme_light.isChecked():
            theme = "light"
        elif self._theme_dark.isChecked():
            theme = "dark"
        self._settings.theme = theme
        self._settings.sync()
        self.settingsSaved.emit()
        self.accept()


# ------------------------------------------------------------------ 汇总报告
class ReportDialog(QDialog):
    retryRequested = Signal(list)
    exportReportRequested = Signal(str)
    exportListRequested = Signal(str)

    def __init__(self, tasks: List[TaskItem], elapsed: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("处理报告")
        self.resize(620, 520)
        self._tasks = tasks
        self._failed = [t for t in tasks if t.status == "failed"]

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setPlainText(build_report_text(tasks, elapsed))
        layout.addWidget(self._text, 1)

        if self._failed:
            layout.addWidget(subheading("失败文件（勾选后可一键重试）", self))
            self._list = QListWidget(self)
            for task in self._failed:
                item = QListWidgetItem(f"{task.name}　{task.error or '未知原因'}")
                item.setIcon(icon("x", solid_color(current_palette().danger), 14))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, id(task))
                self._list.addItem(item)
            layout.addWidget(self._list)
        else:
            self._list = None

        row = QHBoxLayout()
        self._retry_btn = QPushButton("↻ 重试选中", self)
        self._retry_btn.setProperty("variant", "primary")
        self._retry_btn.setEnabled(bool(self._failed))
        self._retry_btn.clicked.connect(self._on_retry)
        self._export_report_btn = QPushButton("导出报告", self)
        self._export_report_btn.clicked.connect(self._on_export_report)
        self._export_list_btn = QPushButton("导出任务清单", self)
        self._export_list_btn.clicked.connect(self._on_export_list)
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        row.addWidget(self._retry_btn)
        row.addStretch(1)
        row.addWidget(self._export_report_btn)
        row.addWidget(self._export_list_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _on_retry(self) -> None:
        if self._list is None:
            return
        chosen = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.Checked:
                task_id = item.data(Qt.UserRole)
                for task in self._failed:
                    if id(task) == task_id:
                        chosen.append(task)
        if chosen:
            self.retryRequested.emit(chosen)
            self.accept()

    def _on_export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出报告", "SAVT_处理报告.txt", "文本文件 (*.txt)")
        if path:
            self.exportReportRequested.emit(path)

    def _on_export_list(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出任务清单", "SAVT_任务清单.csv", "CSV 文件 (*.csv)")
        if path:
            self.exportListRequested.emit(path)


# ------------------------------------------------------------------ 音频提取
class ExtractAudioDialog(QDialog):
    def __init__(self, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("提取音频")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(caption(f"源文件：{source_name}", self))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self._format_combo = RoundedCombo(self)
        for key, label, _encoder, _ext in EXTRACT_FORMATS:
            self._format_combo.addItem(label, key)
        form.addRow("导出格式：", self._format_combo)

        self._dir_edit = QLineEdit(self)
        self._dir_edit.setPlaceholderText("留空则输出到源文件所在目录")
        self._dir_btn = QPushButton("浏览…", self)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._dir_edit, 1)
        dir_row.addWidget(self._dir_btn)
        dir_widget = QWidget(self)
        dir_widget.setLayout(dir_row)
        form.addRow("输出目录：", dir_widget)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._dir_btn.clicked.connect(self._pick_dir)

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self._dir_edit.text())
        if path:
            self._dir_edit.setText(path)

    def format_key(self) -> str:
        return self._format_combo.currentData()

    def output_dir(self) -> str:
        return self._dir_edit.text().strip()


# ------------------------------------------------------------------ 关机倒计时
class ShutdownCountdown(QDialog):
    def __init__(self, seconds: int = 60, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("即将关机")
        self.setModal(True)
        self._remaining = seconds
        self._canceled = False

        layout = QVBoxLayout(self)
        self._label = QLabel(f"系统将在 {seconds} 秒后关机", self)
        self._label.setObjectName("heading")
        self._bar = QProgressBar(self)
        self._bar.setRange(0, seconds)
        self._bar.setValue(seconds)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        layout.addWidget(caption("关闭本窗口或点击「取消关机」即可中止。", self))

        self._cancel_btn = QPushButton("取消关机", self)
        self._cancel_btn.setProperty("variant", "primary")
        self._cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self._cancel_btn)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._remaining -= 1
        self._label.setText(f"系统将在 {max(self._remaining, 0)} 秒后关机")
        self._bar.setValue(max(self._remaining, 0))
        if self._remaining <= 0:
            self._timer.stop()
            self.accept()

    def _cancel(self) -> None:
        self._canceled = True
        self._timer.stop()
        self.reject()

    @property
    def canceled(self) -> bool:
        return self._canceled


# ------------------------------------------------------------------ 关于
class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        title = QLabel(APP_NAME_CN, self)
        title.setObjectName("heading")
        layout.addWidget(title)
        layout.addWidget(caption(f"{APP_NAME}　{APP_ABBR} v{APP_VERSION}", self))
        layout.addWidget(caption(SLOGAN, self))
        layout.addSpacing(8)

        info = QPlainTextEdit(self)
        info.setReadOnly(True)
        info.setPlainText(
            "功能概览\n"
            "· 智能视频压缩：CPU（x264 / x265，CRF 恒定质量）与 GPU（NVENC / AMF / QuickSync）双通道\n"
            "· 精准控盘：直接指定目标大小或百分比，自动两遍编码，误差 ±3%\n"
            "· 万能转换：MP4 / MOV / MKV / AVI / WMV / FLV / 3GP / WebM，及 ProRes、DNxHR、Alpha\n"
            "· 批处理：统一 / 独立设置、顺序或并发、失败跳过与一键重试\n"
            "· 信息处理：拖入即显完整音视频参数，支持预览与音频提取\n\n"
            f"可执行文件：{EXE_NAME}.exe\n"
            "界面字体：更纱黑体 SC（Sarasa Gothic SC）\n"
            "底层引擎：FFmpeg"
        )
        layout.addWidget(info, 1)

        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
