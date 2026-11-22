"""主窗口：Win11 风格三明治布局与全部业务流程编排。"""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QPainter, QShortcut, QKeySequence
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_ABBR, APP_NAME_CN, APP_VERSION
from app.theme import ThemeManager

from core.audio import build_extract_args, build_output_path as audio_output_path
from core.capabilities import Capabilities, detect
from core.gpu import HardwareMonitor
from core.models import EncodeParams, TaskItem, TaskStatus, VideoInfo
from core.planner import (
    COURSE_PRESET_NAME,
    apply_course_preset,
    compute_bitrate_plan,
    course_target_bytes,
    default_container_for,
    suggest_target_bytes,
)
from core.power import cancel_shutdown, schedule_shutdown
from core.profiles import PRO_PRESET_MAP, DEVICE_PRESET_MAP
from core.probe import probe_file
from core.queue import TaskQueue
from core.report import export_task_list_csv, export_text
from core.runner import FFmpegRunner
from core.utils import format_duration_cn, format_size

from ui.dialogs import (
    AboutDialog,
    ExtractAudioDialog,
    ReportDialog,
    SettingsDialog,
    ShutdownCountdown,
)
from ui.drop_area import DropPrompt, extract_video_paths
from ui.file_list import FileTable, SummaryBar
from ui.course_dialog import CourseCompressDialog
from ui.info_panel import InfoPanel
from ui.settings_panel import SettingsPanel
from ui.toolbar import Toolbar
from ui.widgets import Card, caption, subheading
from ui.icons import IconText, recolor_buttons, set_button_icon


# ------------------------------------------------------------------ 探测线程
class _ProbeSignals(QObject):
    done = Signal(object, object)
    failed = Signal(object, str)


class _ProbeTask(QRunnable):
    def __init__(self, caps: Capabilities, task: TaskItem) -> None:
        super().__init__()
        self._caps = caps
        self._task = task
        self.signals = _ProbeSignals()

    def run(self) -> None:
        try:
            info = probe_file(self._task.info.path, self._caps)
            self.signals.done.emit(self._task, info)
        except Exception as exc:  # 探测异常不应中断整批
            self.signals.failed.emit(self._task, str(exc))


class _TitleBar(QWidget):
    """自定义无边框标题栏。"""

    def __init__(self, window: QWidget, palette_getter) -> None:
        super().__init__(window)
        self._window = window
        self._palette_getter = palette_getter
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(8)

        # #12：标题栏仅显示产品名与英文名（纯黑主文本），版本号更小更淡且无底色
        self._title = QLabel(f"{APP_NAME_CN}  —  SharpArt Video Toolkit", self)
        self._title.setObjectName("titleMain")
        self._version = QLabel(f"{APP_ABBR} v{APP_VERSION}", self)
        self._version.setObjectName("titleVersion")

        layout.addWidget(self._title)
        layout.addWidget(self._version)
        layout.addStretch(1)

        # #14：窗口控制按钮 46×32，按钮间距 2px，右侧边距 4px
        self._min_btn = QPushButton("—", self)
        self._max_btn = QPushButton("□", self)
        self._close_btn = QPushButton("✕", self)
        for btn, role in ((self._min_btn, "min"), (self._max_btn, "max"), (self._close_btn, "close")):
            btn.setObjectName("titleButton")
            btn.setProperty("role", role)
            btn.setFixedSize(46, 32)
            btn.setCursor(Qt.PointingHandCursor)
        self._min_btn.clicked.connect(self._window.showMinimized)
        self._max_btn.clicked.connect(self._toggle_max)
        self._close_btn.clicked.connect(self._window.close)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(2)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self._min_btn)
        button_layout.addWidget(self._max_btn)
        button_layout.addWidget(self._close_btn)
        layout.addLayout(button_layout)

    def _toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def refresh_style(self) -> None:
        for btn in (self._min_btn, self._max_btn, self._close_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._window.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)


# ------------------------------------------------------------------ 主窗口
def _resolve_compress_container(params: EncodeParams, info: VideoInfo) -> str:
    """压缩任务输出容器：沿用源文件格式；专业/设备预设强制容器时保留预设值。

    格式转换（仅转格式）任务不调用此函数，仍使用下拉所选格式。
    """
    if params.preset_name in PRO_PRESET_MAP or params.preset_name in DEVICE_PRESET_MAP:
        return params.container
    return default_container_for(info) or params.container or "mp4"


class MainWindow(QWidget):
    def __init__(self, settings, theme: ThemeManager) -> None:
        super().__init__()
        self._settings = settings
        self._theme = theme
        self._caps: Capabilities = detect(settings.ffmpeg_path, settings.probe_path)
        self._tasks: List[TaskItem] = []
        self._next_id = 1
        self._batch_mode = settings.batch_mode
        self._shutdown_dialog: Optional[ShutdownCountdown] = None
        self._audio_runner: Optional[FFmpegRunner] = None

        self.setWindowTitle(f"{APP_NAME_CN} — SharpArt Video Toolkit")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        # 透明背景属性由 ThemeManager.apply 根据 Mica 状态控制，
        # 此处不显式开启以避免浅色主题下窗口变为全透明
        # 设置区改为左右两张卡片后需要更宽的最小宽度，
        # 保证上方 splitter（批处理队列 / 文件信息）与下方设置行（压缩 / 转换）
        # 在最小窗口下也能保持 3:2 严格对齐
        self.setMinimumSize(1280, 720)
        self.resize(1300, 880)
        self.setAcceptDrops(True)
        self.installEventFilter(self)

        self._build_ui()
        self._build_queue()
        self._connect_signals()
        self._apply_palette()
        self._sync_drop_prompt()

        self._hardware = HardwareMonitor(self)
        self._hardware.statsUpdated.connect(self._on_hardware_stats)

        QTimer.singleShot(60, self._startup_check)  # 非阻塞：缺失时仅在状态栏提示
        QTimer.singleShot(400, self._probe_gpu_availability)

    # ------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(0)

        self._title_bar = _TitleBar(self, lambda: self._theme.palette)
        root.addWidget(self._title_bar)

        self._toolbar = Toolbar(self)
        root.addWidget(self._toolbar)

        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setContentsMargins(14, 6, 14, 6)
        self._splitter.setHandleWidth(12)

        left = QWidget(self._splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        table_card = Card(left)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 4, 8, 4)
        table_layout.setSpacing(2)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        self._table_title = subheading("批处理队列", table_card)
        self._table_title.setMaximumHeight(24)
        header_row.addWidget(self._table_title)
        header_row.addStretch(1)
        self._table_hint = caption("单个文件时显示详情，多个文件自动切换为列表", table_card)
        self._table_hint.setMaximumHeight(24)
        header_row.addWidget(self._table_hint)
        table_layout.addLayout(header_row)
        # 摘要条移入批处理队列卡片内部，使整张卡片填满左侧分栏，
        # 与右侧「文件信息」卡片高度严格一致（均为 477px）
        self._summary_bar = SummaryBar(table_card)
        table_layout.addWidget(self._summary_bar)
        # 原独立「拖入视频文件」卡片已合并到此处：提示横幅在表格上方
        self._drop_prompt = DropPrompt(table_card)
        table_layout.addWidget(self._drop_prompt)
        self._table = FileTable(table_card)
        table_layout.addWidget(self._table, 1)
        # 空队列时左侧卡片按内容高度紧凑排列，避免为对齐右侧而强行撑出大片空白
        table_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_layout.addWidget(table_card, 0)

        # 「文件信息」卡片：与下方「格式转换设置」卡片同列同宽（默认约 1.74:1）
        self._file_info_card = Card()
        file_info_layout = QVBoxLayout(self._file_info_card)
        # 卡片内部留出 10px 内边距，避免预览、2×2 网格、按钮贴边甚至重叠
        file_info_layout.setContentsMargins(10, 10, 10, 10)
        file_info_layout.setSpacing(0)
        self._info_panel = InfoPanel(self._caps, self._file_info_card)
        self._info_panel.setMinimumWidth(380)
        self._info_panel.setMaximumWidth(900)
        file_info_layout.addWidget(self._info_panel)
        # 卡片整体宽度跟随内部 InfoPanel 的 900px 上限，避免右侧被撑得过大后与下方格式转换卡片错位
        self._file_info_card.setMaximumWidth(920)

        self._splitter.addWidget(left)
        self._splitter.addWidget(self._file_info_card)
        # 默认比例给右侧信息/转换区更多空间，左右初始约 800 / 460
        self._splitter.setSizes([800, 460])
        root.addWidget(self._splitter, 1)

        self._settings_panel = SettingsPanel(self._settings, self._caps, self)

        # 压缩设置卡片与上方 splitter 保持相同左右边距，避免左右突出/缩进（与拖放区、队列卡片对齐）
        self._settings_wrapper = QWidget(self)
        settings_wrapper_layout = QHBoxLayout(self._settings_wrapper)
        settings_wrapper_layout.setContentsMargins(14, 0, 14, 10)
        settings_wrapper_layout.setSpacing(0)
        settings_wrapper_layout.addWidget(self._settings_panel)
        root.addWidget(self._settings_wrapper)

        # #4：底部操作栏与状态栏合并为连续区块，消除分层割裂感
        bottom = QWidget(self)
        bottom.setObjectName("bottomBar")
        bottom_layout = QVBoxLayout(bottom)
        # 上下留出 6px 内边距，让两行文字整体向中部靠拢，不再贴卡片上下边缘
        bottom_layout.setContentsMargins(0, 6, 0, 6)
        bottom_layout.setSpacing(0)
        bottom_layout.addLayout(self._build_bottom_bar())
        bottom_layout.addWidget(self._build_status_bar())

        # 底部栏整体与上方压缩设置卡片左右边界对齐，背景不再贴边
        bottom_wrapper = QWidget(self)
        bottom_wrapper_layout = QHBoxLayout(bottom_wrapper)
        bottom_wrapper_layout.setContentsMargins(14, 0, 14, 0)
        bottom_wrapper_layout.setSpacing(0)
        bottom_wrapper_layout.addWidget(bottom)
        root.addWidget(bottom_wrapper)

    def _build_bottom_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(16, 2, 16, 2)
        row.setSpacing(10)

        # 队列计数紧跟统计信息（已完成/待处理/失败），便于一眼看清整体进度
        self._queue_label = QLabel("任务队列：0/0", self)
        self._queue_label.setObjectName("muted")
        row.addWidget(self._queue_label)

        self._status_done = IconText("check", "已完成：0", 14, self)
        self._status_pending = IconText("clock", "待处理：0", 14, self)
        self._status_failed = IconText("x", "失败：0", 14, self)
        for label in (self._status_done, self._status_pending, self._status_failed):
            row.addWidget(label)

        row.addStretch(1)
        return row

    def _build_status_bar(self) -> QWidget:
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.setSpacing(12)

        self._status_left = caption("就绪　锐利画质，精湛工艺 —— 让每一帧都值得留存", bar)
        layout.addWidget(self._status_left)

        # ffmpeg 缺失时的非阻塞提示入口（替代原来的启动弹窗）
        self._ffmpeg_warn_btn = QPushButton("配置 ffmpeg", bar)
        set_button_icon(self._ffmpeg_warn_btn, "alert-triangle")
        self._ffmpeg_warn_btn.setProperty("variant", "ghost")
        self._ffmpeg_warn_btn.setCursor(Qt.PointingHandCursor)
        self._ffmpeg_warn_btn.setToolTip("打开设置，指定 ffmpeg.exe 与 ffprobe.exe 的位置")
        self._ffmpeg_warn_btn.setVisible(False)
        self._ffmpeg_warn_btn.clicked.connect(self._open_settings)
        layout.addWidget(self._ffmpeg_warn_btn)
        layout.addStretch(1)

        # #15：CPU 与 GPU 硬件信息
        self._status_cpu = caption("", bar)
        self._status_gpu = caption("", bar)
        layout.addWidget(self._status_cpu)
        layout.addWidget(self._status_gpu)

        # 操作按钮从上方下移到底部状态栏右侧
        self._start_btn = QPushButton("全部开始", self)
        set_button_icon(self._start_btn, "play")
        self._start_btn.setProperty("variant", "primary")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setMinimumWidth(120)
        self._cancel_btn = QPushButton("全部取消", self)
        set_button_icon(self._cancel_btn, "square")
        self._cancel_btn.setProperty("variant", "danger")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setEnabled(False)
        self._export_btn = QPushButton("导出任务清单", self)
        set_button_icon(self._export_btn, "upload")
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn = QPushButton("清空已完成", self)
        set_button_icon(self._clear_btn, "trash")
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        # 将「导出任务清单」放到左侧、「全部开始」放到右侧，避免误触主按钮
        for btn in (self._export_btn, self._cancel_btn,
                    self._clear_btn, self._start_btn):
            layout.addWidget(btn)
        return bar

    def _build_queue(self) -> None:
        self._queue = TaskQueue(self._settings, self._caps, self)
        self._queue.taskUpdated.connect(self._on_task_updated)
        self._queue.queueStateChanged.connect(self._update_stats)
        self._queue.queueFinished.connect(self._on_queue_finished)
        self._queue.message.connect(self._set_status_text)

    def _connect_signals(self) -> None:
        self._drop_prompt.filesDropped.connect(self._add_files)
        self._drop_prompt.clicked.connect(self._choose_files)
        self._toolbar.addFilesRequested.connect(self._choose_files)
        self._toolbar.settingsRequested.connect(self._open_settings)
        self._toolbar.batchModeChanged.connect(self._on_batch_mode)
        self._toolbar.concurrencyChanged.connect(self._on_concurrency)
        self._toolbar.set_concurrency(self._settings.concurrency)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.removeRequested.connect(self._remove_selected)
        self._table.taskDeleteRequested.connect(self._remove_task)
        self._table.resetRequested.connect(self._reset_status)
        self._table.targetEdited.connect(self._on_target_edited)
        self._summary_bar.clearRequested.connect(self._clear_all)
        self._summary_bar.removeSelectedRequested.connect(self._remove_selected)
        self._summary_bar.resetStatusRequested.connect(self._reset_status)
        self._summary_bar.courseCompressRequested.connect(self._on_course_compress)

        self._settings_panel.paramsChanged.connect(self._on_params_changed)
        self._info_panel.copyRequested.connect(self._copy_info)
        self._info_panel.extractRequested.connect(self._extract_audio)

        self._start_btn.clicked.connect(self._start_all)
        self._cancel_btn.clicked.connect(self._cancel_all)
        self._export_btn.clicked.connect(self._export_list)
        self._clear_btn.clicked.connect(self._clear_completed)

        shortcut = QShortcut(QKeySequence.Copy, self)
        shortcut.activated.connect(self._copy_info)

    # ------------------------------------------------------------ 外观
    def _apply_palette(self) -> None:
        palette = self._theme.palette
        self._drop_prompt.set_palette(palette)
        self._summary_bar.set_palette(palette)
        self._table.set_palette(palette)
        self._info_panel.set_palette(palette)
        self._settings_panel.set_palette(palette)
        self._toolbar.set_palette(palette)
        recolor_buttons(self)
        for w in self.findChildren(IconText):
            w.set_palette(palette)
        self._title_bar.refresh_style()

    def refresh_theme(self) -> None:
        self._theme.apply(QApplication.instance(), self)
        self._apply_palette()
        self._table.refresh_all()

    def paintEvent(self, event) -> None:  # noqa: N802
        """窗口背景：Mica 生效时近透明由 DWM 绘制，否则自绘圆角柔和渐变。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._theme.palette
        radius = 0 if self.isMaximized() else 10
        if self._theme.mica:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        else:
            from PySide6.QtGui import QLinearGradient, QPainterPath

            gradient = QLinearGradient(0, 0, 0, self.height())
            gradient.setColorAt(0, QColor(p.gradient_top))
            gradient.setColorAt(1, QColor(p.gradient_bottom))
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), radius, radius)
            painter.fillPath(path, gradient)
        super().paintEvent(event)

    # ------------------------------------------------------------ 启动检查
    def _startup_check(self) -> None:
        self._refresh_ffmpeg_state()
        self._update_stats()

    def _refresh_ffmpeg_state(self) -> None:
        """ffmpeg 状态提示（非阻塞）。

        ffmpeg 缺失时只在状态栏给出醒目提示 + 「配置 ffmpeg」入口，
        不再弹出必须点击 OK 才能进入软件的对话框。
        """
        missing = not self._caps.ok
        self._status_left.setObjectName("statusWarning" if missing else "caption")
        self._status_left.style().unpolish(self._status_left)
        self._status_left.style().polish(self._status_left)
        self._ffmpeg_warn_btn.setVisible(missing)
        if missing:
            self._set_status_text(
                f"{self._caps.error or '未找到 ffmpeg / ffprobe'}　"
                f"点击右侧「配置 ffmpeg」指定路径后可直接使用"
            )
        else:
            self._set_status_text(
                f"ffmpeg {self._caps.version.split()[0]} 已就绪，拖入文件即可开始"
            )

    def _probe_gpu_availability(self) -> None:
        """后台探测硬件编码器，避免阻塞启动。"""
        if not self._caps.ok:
            return

        panel = self._settings_panel

        class _Task(QRunnable):
            def __init__(self, caps: Capabilities) -> None:
                super().__init__()
                self._caps = caps

            def run(self) -> None:
                for name in ("h264_nvenc", "h264_amf", "h264_qsv"):
                    if self._caps.has_encoder(name):
                        self._caps.verify_encoder(name)
                # 探测耗时较长，期间窗口可能已关闭：回调前先确认 C++ 对象仍然有效，
                # 否则访问已销毁的控件会抛出 RuntimeError 并弹出未处理异常对话框
                try:
                    from shiboken6 import isValid

                    if not isValid(panel) or not isValid(panel._encoder_combo):
                        return
                except Exception:
                    return
                panel.refresh_gpu_availability()

        QThreadPool.globalInstance().start(_Task(self._caps))

    # ------------------------------------------------------------ 文件
    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加视频文件", self._settings.last_input_dir,
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.wmv *.flv *.webm *.3gp *.m4v *.mpg *.mpeg "
            "*.ts *.m2ts *.vob *.rmvb *.asf *.f4v *.ogv *.mxf);;所有文件 (*.*)",
        )
        if paths:
            self._settings.last_input_dir = os.path.dirname(paths[0])
            self._add_files(paths)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = extract_video_paths(event)
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: List[str]) -> None:
        if not self._caps.ok:
            QMessageBox.warning(self, "无法添加", self._caps.error or "ffmpeg 未就绪")
            return
        existing = {task.info.path for task in self._tasks if task.info}
        added = 0
        for path in paths:
            if path in existing:
                continue
            task = TaskItem(
                id=self._next_id,
                info=VideoInfo(path=path, name=os.path.basename(path)),
                params=self._default_params(path),
            )
            task.status = TaskStatus.PROBING
            self._next_id += 1
            self._tasks.append(task)
            self._table.add_task(task)
            existing.add(path)
            added += 1

            worker = _ProbeTask(self._caps, task)
            worker.signals.done.connect(self._on_probe_done)
            worker.signals.failed.connect(self._on_probe_failed)
            QThreadPool.globalInstance().start(worker)

        if added:
            self._set_status_text(f"正在识别 {added} 个文件…")
        self._update_stats()
        self._sync_drop_prompt()

    def _default_params(self, path: str) -> EncodeParams:
        params = self._settings_panel.params()
        if params.size_mode == "streamcopy":
            # 格式转换 / 仅转格式：沿用下拉所选输出格式（可为用户未选时的源格式兜底）
            params.container = params.container or default_container_for(VideoInfo(path=path))
        else:
            # 视频压缩：输出容器跟随源文件格式，不再误用格式转换的下拉值
            params.container = _resolve_compress_container(params, VideoInfo(path=path))
        return params

    @Slot(object, object)
    def _on_probe_done(self, task: TaskItem, info: VideoInfo) -> None:
        # 探测回调可能晚于用户点击「开始」。此时任务已在编码或已完成，
        # 不能再覆盖 status / info / 目标大小，否则队列内部持有的旧 info
        # 会与界面彻底脱节（进度、目标、音轨都会错乱）。
        if task.status not in (TaskStatus.PROBING, TaskStatus.PENDING):
            self._table.update_task(task)
            self._update_stats()
            return
        task.info = info
        task.status = TaskStatus.PENDING
        if task.params.size_mode == "streamcopy":
            # 格式转换：沿用下拉所选输出格式
            task.params.container = task.params.container or default_container_for(info)
        else:
            # 视频压缩：输出容器跟随源文件格式（命中专业/设备预设时保留预设容器）
            task.params.container = _resolve_compress_container(task.params, info)
        # 仅当用户未单独调整过该任务时才应用智能目标大小
        if not task.custom_params and task.params.size_mode == "absolute":
            task.params.target_bytes = suggest_target_bytes(info, task.params, self._caps)
        elif task.params.preset_name == COURSE_PRESET_NAME:
            # 课程压缩：用真实时长按最低码率补全目标体积（探测前 duration=0 不算）
            task.params.target_bytes = course_target_bytes(info, task.params)
        self._table.update_task(task)
        self._update_stats()
        self._refresh_estimate()
        self._sync_settings_target_from_tasks()
        selected = self._table.selected_tasks()
        if not selected and len(self._tasks) == 1:
            self._table.selectRow(0)
            self._info_panel.set_info(info)
        elif selected and selected[0] is task:
            self._info_panel.set_info(info)
        if not self._queue.active:
            self._set_status_text(f"ffmpeg 已就绪　共 {len(self._tasks)} 个文件")

    @Slot(object, str)
    def _on_probe_failed(self, task: TaskItem, message: str) -> None:
        task.status = TaskStatus.FAILED
        task.error = f"识别失败：{message}"
        self._table.update_task(task)
        self._update_stats()

    # ------------------------------------------------------------ 参数
    def _on_params_changed(self) -> None:
        params = self._settings_panel.params()
        # 面板 target_bytes == 0 表示"未设置"占位符，不应覆盖任务已有的智能目标值
        is_placeholder = params.target_bytes == 0
        # 同页才同步：转换页改动只影响「仅转格式」任务，压缩页改动只影响重编码任务，
        # 两张卡片的参数互不覆盖
        sync_convert = params.size_mode == "streamcopy"
        if self._batch_mode == "unified":
            # 统一模式以当前页面为准：整队列跟随当前页（压缩页=全部重编码，转换页=全部仅转格式）。
            # 不再做同类过滤——切换页面时所有任务一起改类型，与「点开始」时所在页一致。
            for task in self._tasks:
                # 非目标大小模式、或面板显示占位符时，保留任务原有 target_bytes
                if params.size_mode != "absolute" or is_placeholder:
                    old_target = task.params.target_bytes
                    task.params = params.copy()
                    task.params.target_bytes = old_target
                else:
                    task.params = params.copy()
                task.custom_params = False
                # 压缩任务容器始终跟随源文件格式（转换卡下拉不改压缩输出），逐任务重解析
                if params.size_mode != "streamcopy" and task.info is not None:
                    task.params.container = _resolve_compress_container(task.params, task.info)
                # 编码模式（CPU/GPU）切换后，未手动改过目标的任务需按新模式重新计算智能目标，
                # 避免 GPU 惩罚 / 源编码惩罚等系数变化后目标仍停留在旧值、或被面板平均值统一覆盖。
                if (params.size_mode == "absolute"
                        and not task.custom_params
                        and task.info is not None
                        and task.info.duration):
                    task.params.target_bytes = suggest_target_bytes(
                        task.info, task.params, self._caps
                    )
            self._table.refresh_all()
            self._refresh_estimate()
            # 目标大小同步只属于压缩页语义；转换页无 absolute 任务，自动 no-op，不会抢模式
            if not sync_convert:
                self._sync_settings_target_from_tasks()
        else:
            for task in self._table.selected_tasks():
                if sync_convert != (task.params.size_mode == "streamcopy"):
                    continue
                if params.size_mode != "absolute" or is_placeholder:
                    old_target = task.params.target_bytes
                    task.params = params.copy()
                    task.params.target_bytes = old_target
                else:
                    task.params = params.copy()
                task.custom_params = True
        self._table.refresh_all()
        self._refresh_estimate()
        self._warn_if_target_too_small()

    def _warn_if_target_too_small(self) -> None:
        warned = False
        for task in self._tasks:
            if task.info is None or task.info.duration <= 0:
                continue
            plan = compute_bitrate_plan(task.info, task.params, self._caps)
            if plan.warning:
                warned = True
                self._set_status_text(plan.warning)
                break
        if not warned and not self._queue.active:
            self._set_status_text(f"ffmpeg 已就绪　共 {len(self._tasks)} 个文件")

    def _on_batch_mode(self, mode: str) -> None:
        self._batch_mode = mode
        self._settings.batch_mode = mode
        if mode == "independent":
            selected = self._table.selected_tasks()
            if not selected:
                self._set_status_text("独立设置模式：请先选中要单独调整的文件行")
            else:
                self._settings_panel.set_params(selected[0].params)
                self._set_status_text(f"独立设置模式：正在调整「{selected[0].name}」")
        else:
            self._apply_params_to_all()
            self._set_status_text("统一设置模式：参数改动将同步到所有文件")

    def _apply_params_to_all(self) -> None:
        params = self._settings_panel.params()
        is_placeholder = params.target_bytes == 0
        # 统一模式以当前页面为准：把当前页参数套到所有任务（压缩页=全部重编码，转换页=全部仅转格式），
        # 不再做同类过滤——点「开始」前一刻所在页即决定全部任务做什么。
        for task in self._tasks:
            if params.size_mode != "absolute" or is_placeholder:
                old_target = task.params.target_bytes
                task.params = params.copy()
                task.params.target_bytes = old_target
            else:
                task.params = params.copy()
            task.custom_params = False
            # 压缩任务容器始终跟随源文件格式（转换卡下拉不再影响压缩输出），
            # 逐任务重解析，避免“先转 MKV 再压缩”时压缩输出也变成 MKV
            if params.size_mode != "streamcopy" and task.info is not None:
                task.params.container = _resolve_compress_container(task.params, task.info)
            # 参数变更（如 CPU↔GPU 切换）后重新计算智能目标，避免所有任务被面板同一值覆盖
            if (params.size_mode == "absolute"
                    and not task.custom_params
                    and task.info is not None
                    and task.info.duration):
                task.params.target_bytes = suggest_target_bytes(
                    task.info, task.params, self._caps
                )
        self._table.refresh_all()
        self._refresh_estimate()
        # 重算后同步面板目标大小显示为新的平均值（转换页无 absolute 任务，自动 no-op）
        self._sync_settings_target_from_tasks()

    def _sync_settings_target_from_tasks(self) -> None:
        """把设置面板目标大小同步为当前任务智能目标的平均值（仅在统一设置模式 + 有选中项时）。"""
        if self._batch_mode != "unified":
            return
        # 无选中项时不写入面板，由 _on_selection_changed 驱动显示"未设置"或单任务目标
        if not self._table.selected_tasks():
            return
        targets = [
            t.params.target_bytes
            for t in self._tasks
            if t.info is not None and t.params.size_mode == "absolute"
        ]
        if not targets:
            return
        avg = sum(targets) / len(targets)
        self._settings_panel.set_target_value(avg)

    def _on_concurrency(self, value: int) -> None:
        self._queue.set_concurrency(value)
        self._settings.concurrency = value
        if value > 1:
            QMessageBox.information(
                self,
                "并发处理",
                f"已开启并发 {value} 个文件。\n\n并发可能影响系统流畅度，"
                "在配置较低的设备上建议保持「顺序处理」。",
            )

    # ------------------------------------------------------------ 选择
    def _on_selection_changed(self) -> None:
        selected = self._table.selected_tasks()
        if selected:
            task = selected[0]
            # 把选中视频的媒体信息交给设置面板，用于 CRF 智能推荐提示
            self._settings_panel.set_video_info(task.info)
            if task.info:
                self._info_panel.set_info(task.info)
                # 选中视频时，目标大小默认填入该视频的目标压缩大小（表格"目标缩小大"列）
                self._settings_panel.set_target_from_video(task.params.target_bytes)
            else:
                self._settings_panel.set_target_from_video(0)
            if self._batch_mode == "independent":
                self._settings_panel.set_params(task.params)
        else:
            # 无选中时清空：目标大小为占位符，CRF 提示回落
            self._settings_panel.set_video_info(None)
            self._settings_panel.set_target_from_video(0)

    # ------------------------------------------------------------ 执行
    def _start_all(self) -> None:
        if self._queue.active:
            return
        # 只取已探测完成的任务，避免把占位（duration=0）任务送进编码
        tasks = [t for t in self._tasks if t.is_runnable()]
        if not tasks:
            if any(t.status == TaskStatus.PROBING for t in self._tasks):
                QMessageBox.information(self, "正在识别文件", "文件信息还在识别中，请稍候再试。")
                return
            QMessageBox.information(self, "没有待处理文件", "请先添加视频文件。")
            return
        if not self._caps.ok:
            QMessageBox.warning(self, "无法开始", self._caps.error or "ffmpeg 未就绪")
            return

        # 统一模式：以「开始」键按下时所在页为准，把当前页参数强制套用到全部任务，
        # 避免“在压缩页加文件、切到转换页点开始”却跑了压缩的情况
        if self._batch_mode == "unified":
            self._apply_params_to_all()
        selected = self._table.selected_tasks()
        targets = selected if selected and self._batch_mode == "independent" else tasks
        self._settings_panel.set_enabled_state(False)
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._hardware.start()
        self._set_status_text(f"开始处理 {len(targets)} 个文件…")
        self._queue.start(targets, self._settings_panel.output_dir())

    def _cancel_all(self) -> None:
        self._queue.cancel_all()
        self._hardware.stop()
        self._settings_panel.set_enabled_state(True)
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._set_status_text("已取消全部任务")
        self._update_stats()

    def _clear_completed(self) -> None:
        removed = self._table.clear_completed()
        kept = []
        for task in self._tasks:
            if task.status != TaskStatus.DONE:
                kept.append(task)
        self._tasks = kept
        self._update_stats()
        self._refresh_estimate()
        self._sync_drop_prompt()
        self._set_status_text(f"已清除 {removed} 个已完成的文件")

    def _remove_selected(self) -> None:
        """#11：从处理列表移除选中文件，源文件完全不受影响。"""
        if self._queue.active:
            QMessageBox.information(self, "正在处理", "请先停止当前任务，再移除列表中的文件。")
            return
        tasks = self._table.selected_tasks()
        if not tasks:
            QMessageBox.information(self, "未选中文件", "请先在列表中选择要移除的文件（支持多选）。")
            return
        removed = self._table.remove_selected()
        for task in tasks:
            if task in self._tasks:
                self._tasks.remove(task)
        if not self._tasks:
            self._info_panel.set_info(None)
        self._update_stats()
        self._refresh_estimate()
        self._sync_drop_prompt()
        self._set_status_text(f"已从列表移除 {removed} 个文件（源文件未做任何改动）")

    def _remove_task(self, task: TaskItem) -> None:
        """操作列删除图标：从列表移除单个文件，源文件完全不受影响。"""
        if self._queue.active:
            QMessageBox.information(self, "正在处理", "请先停止当前任务，再移除列表中的文件。")
            return
        if task not in self._tasks:
            return
        self._table.remove_task(task)
        self._tasks.remove(task)
        if not self._tasks:
            self._info_panel.set_info(None)
        self._update_stats()
        self._refresh_estimate()
        self._sync_drop_prompt()
        self._set_status_text("已从列表移除 1 个文件（源文件未做任何改动）")

    def _reset_status(self) -> None:
        """将选中已完成/失败/取消的任务重置为待处理，可重新加入队列。"""
        if self._queue.active:
            QMessageBox.information(self, "正在处理", "请先停止当前任务，再重置列表中的状态。")
            return
        tasks = self._table.selected_tasks()
        if not tasks:
            QMessageBox.information(self, "未选中文件", "请先在列表中选择要重置状态的文件（支持多选）。")
            return
        count = 0
        for task in tasks:
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELED):
                task.status = TaskStatus.PENDING
                task.progress = 0.0
                task.error = ""
                task.pass_index = 0
                task.output_bytes = 0
                task.elapsed = 0.0
                count += 1
        if count == 0:
            self._set_status_text("没有需要重置的任务（已完成/失败/取消）")
            return
        self._table.refresh_all()
        self._update_stats()
        self._refresh_estimate()
        self._set_status_text(f"已重置 {count} 个任务的状态，可点击「全部开始」重新处理")

    def _on_target_edited(self, task: TaskItem) -> None:
        """表格里直接改了某行的目标压缩大小：同步设置面板并刷新预估。"""
        if self._batch_mode == "unified":
            for item in self._tasks:
                if item is not task:
                    item.params.target_bytes = task.params.target_bytes
                    item.params.size_mode = task.params.size_mode
                    item.custom_params = task.custom_params
        else:
            self._settings_panel.set_target_value(task.params.target_bytes)
        self._table.refresh_all()
        self._refresh_estimate()
        self._set_status_text(f"「{task.name}」目标大小已改为 {format_size(task.params.target_bytes)}")

    def _clear_all(self) -> None:
        if self._queue.active:
            QMessageBox.information(self, "正在处理", "请先停止当前任务再清空列表。")
            return
        self._tasks = []
        self._table.clear_all()
        self._info_panel.set_info(None)
        self._update_stats()
        self._refresh_estimate()
        self._sync_drop_prompt()
        self._set_status_text("已清空文件列表")

    def _on_course_compress(self) -> None:
        """对所有已添加的视频套用课程压缩参数（来自对话框的可调设置）。"""
        if not self._tasks:
            QMessageBox.information(self, "没有文件", "请先添加需要压缩的视频文件。")
            return
        dialog = CourseCompressDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        course = dialog.params()
        applied = 0
        for task in self._tasks:
            apply_course_preset(task.params, course)
            # 标记该任务为「已单独调整」，探测回调里跳过通用智能目标，改用课程目标体积
            task.custom_params = True
            if task.info is not None and task.info.duration > 0:
                task.params.target_bytes = course_target_bytes(task.info, task.params)
            else:
                # 尚未探测完成：先给一个按最低码率估算的占位体积（约 60 秒），
                # 探测回调 _on_probe_done 里会用真实时长补全
                task.params.target_bytes = max(
                    course.video_bitrate_kbps * 1000 // 8 * 60, 3 * 1024 * 1024
                )
            applied += 1
        self._table.refresh_all()
        self._update_stats()
        self._refresh_estimate()
        # 统一设置模式下把面板也同步为课程参数，让用户直观看到参数已生效
        if self._batch_mode == "unified" and self._tasks:
            self._settings_panel.set_params(self._tasks[0].params)
            self._sync_settings_target_from_tasks()
        self._set_status_text(
            f"已对 {applied} 个文件套用课程压缩（H.264 · {course.width}×{course.height} · "
            f"{course.fps}fps · 最低码率 {course.video_bitrate_kbps}Kbps）"
        )

    @Slot(object)
    def _on_task_updated(self, task: TaskItem) -> None:
        self._table.update_task(task)
        self._update_stats()

    @Slot(dict)
    def _on_queue_finished(self, _summary: dict) -> None:
        self._hardware.stop()
        self._settings_panel.set_enabled_state(True)
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._table.refresh_all()
        self._update_stats()

        elapsed = _summary.get("elapsed", 0.0)
        failed = [t for t in self._tasks if t.status == TaskStatus.FAILED]
        done = [t for t in self._tasks if t.status == TaskStatus.DONE]
        self._set_status_text(
            f"处理完成：{len(done)} 成功，{len(failed)} 失败　总耗时 {format_duration_cn(elapsed)}"
        )

        if self._settings_panel.report_enabled():
            dialog = ReportDialog(self._tasks, elapsed, self)
            dialog.retryRequested.connect(self._retry_tasks)
            dialog.exportReportRequested.connect(self._export_report)
            dialog.exportListRequested.connect(self._export_list_to)
            dialog.exec()

        # 用户在报告对话框里点了「重试」会调用 _retry_tasks → _queue.start，
        # 队列重新变 active。此时不应再弹出关机倒计时，否则一边编码一边关机。
        if self._settings_panel.shutdown_enabled() and not self._queue.active:
            self._offer_shutdown()

    def _retry_tasks(self, tasks: List[TaskItem]) -> None:
        for task in tasks:
            task.status = TaskStatus.PENDING
            task.progress = 0.0
            task.error = ""
        self._table.refresh_all()
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._settings_panel.set_enabled_state(False)
        self._hardware.start()
        self._queue.start(tasks, self._settings_panel.output_dir())

    # ------------------------------------------------------------ 导出
    def _export_list(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出任务清单", "SAVT_任务清单.csv", "CSV 文件 (*.csv)")
        if path:
            self._export_list_to(path)

    def _export_list_to(self, path: str) -> None:
        if export_task_list_csv(self._tasks, path):
            self._set_status_text(f"任务清单已导出：{path}")
        else:
            QMessageBox.warning(self, "导出失败", "无法写入文件，请检查目标路径权限。")

    def _export_report(self, path: str) -> None:
        from core.report import build_report_text

        text = build_report_text(self._tasks, 0.0)
        if export_text(text, path):
            self._set_status_text(f"报告已导出：{path}")
        else:
            QMessageBox.warning(self, "导出失败", "无法写入文件，请检查目标路径权限。")

    # ------------------------------------------------------------ 关机
    def _offer_shutdown(self) -> None:
        if schedule_shutdown(60):
            self._shutdown_dialog = ShutdownCountdown(60, self)
            self._shutdown_dialog.exec()
            if self._shutdown_dialog.canceled:
                cancel_shutdown()
                self._set_status_text("已取消自动关机")
        else:
            QMessageBox.warning(self, "自动关机失败", "无法执行关机命令，请检查系统权限。")

    # ------------------------------------------------------------ 信息面板操作
    def _copy_info(self) -> None:
        info = self._info_panel.current_info()
        if info is None:
            return
        QApplication.clipboard().setText(info.summary_text())
        self._set_status_text("已复制全部信息到剪贴板")

    def _extract_audio(self) -> None:
        info = self._info_panel.current_info()
        if info is None or not info.has_audio:
            return
        # 并发保护：若上一次提取仍在进行，先取消旧进程，避免 QProcess 泄漏
        # 以及旧 runner 的迟到 finished 回调覆盖新任务（把 _audio_runner 置空）。
        if self._audio_runner is not None:
            try:
                self._audio_runner.cancel()
            except Exception:
                pass
            self._audio_runner = None
            cur = self._info_panel.current_info()
            self._info_panel._extract_btn.setEnabled(cur is not None and cur.has_audio)
        dialog = ExtractAudioDialog(info.name, self)
        if dialog.exec() != ExtractAudioDialog.Accepted:
            return
        key = dialog.format_key()
        output = audio_output_path(info, key, dialog.output_dir() or self._settings.output_dir)
        args = build_extract_args(info, key, output)

        runner = FFmpegRunner(self._caps.ffmpeg, self)
        self._audio_runner = runner
        self._info_panel._extract_btn.setEnabled(False)
        runner.progress.connect(
            lambda value, _p, _t: self._set_status_text(f"正在提取音频… {value * 100:.0f}%")
        )
        runner.finished.connect(lambda ok, err: self._on_audio_done(ok, err, output, runner))
        runner.start([args], info.duration)

    def _on_audio_done(self, ok: bool, error: str, output: str, runner: FFmpegRunner) -> None:
        # 仅当前活动 runner 的回调才更新状态：被取代的旧 runner（cancel 后迟到的
        # finished）静默忽略，避免其把 _audio_runner 置空、打断新任务或弹错误框。
        current = runner is self._audio_runner
        if current:
            self._audio_runner = None
            cur = self._info_panel.current_info()
            self._info_panel._extract_btn.setEnabled(cur is not None and cur.has_audio)
        if not current:
            return
        if ok:
            self._set_status_text(f"音频已导出：{output}")
            QMessageBox.information(self, "提取完成", f"音频已导出到：\n{output}")
        else:
            QMessageBox.warning(self, "提取失败", error or "无法提取该文件的音轨。")

    # ------------------------------------------------------------ 设置
    def _open_settings(self) -> None:
        if self._queue.active:
            QMessageBox.information(self, "正在处理", "编码进行中无法修改设置，请先停止当前任务。")
            return
        dialog = SettingsDialog(self._settings, self._caps, self)
        dialog.settingsSaved.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self) -> None:
        if self._queue.active:
            # 设置已写入磁盘，但编码中途不替换能力表，避免后续任务参数漂移
            QMessageBox.information(self, "正在处理", "设置已保存，将在当前任务结束后生效。")
            return
        self._caps = detect(self._settings.ffmpeg_path, self._settings.probe_path)
        self._queue.set_caps(self._caps)
        self._settings_panel.set_caps(self._caps)
        self._info_panel.set_caps(self._caps)
        self.refresh_theme()
        self._refresh_ffmpeg_state()
        QTimer.singleShot(200, self._probe_gpu_availability)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------ 状态
    @Slot(str, str)
    def _on_hardware_stats(self, cpu: str, gpu: str) -> None:
        """#15：同时刷新 CPU 与 GPU 硬件信息（不可用时留空）。"""
        self._status_cpu.setText(cpu)
        self._status_gpu.setText(gpu)
        self._toolbar.set_gpu_text(gpu if gpu else (cpu if cpu else ""))

    def _set_status_text(self, text: str) -> None:
        self._status_left.setText(text)

    def _update_stats(self) -> None:
        self._summary_bar.update_stats(self._tasks)
        total = len(self._tasks)
        done = sum(1 for t in self._tasks if t.status == TaskStatus.DONE)
        failed = sum(1 for t in self._tasks if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in self._tasks if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING))
        self._queue_label.setText(f"任务队列：{done}/{total}")
        self._status_done.set_text(f"已完成：{done}")
        self._status_pending.set_text(f"待处理：{pending}")
        self._status_failed.set_text(f"失败：{failed}")
        self._table_hint.setText(
            "列表视图" if total > 1 else "详情视图：右侧显示完整参数"
        )
        if not self._queue.active:
            # 未开始处理：仅在有任务/已完成时启用「全部开始」「导出清单」「清空已完成」
            self._start_btn.setEnabled(total > 0)
            self._cancel_btn.setEnabled(False)
            self._clear_btn.setEnabled(done > 0)
            self._export_btn.setEnabled(total > 0)
        else:
            # 处理进行中：「全部取消」可用，其余操作禁用以免与队列冲突
            self._start_btn.setEnabled(False)
            self._clear_btn.setEnabled(False)
            self._export_btn.setEnabled(False)
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        self._settings_panel.refresh_estimate(self._tasks)

    def _sync_drop_prompt(self) -> None:
        """空队列时只显示大拖拽提示区，隐藏表格和摘要条；有文件时显示表格和摘要条。"""
        empty = len(self._tasks) == 0
        self._drop_prompt.setVisible(empty)
        self._summary_bar.setVisible(not empty)
        self._table_hint.setVisible(not empty)
        table_was_visible = self._table.isVisible()
        self._table.setVisible(not empty)
        if not empty and not table_was_visible:
            self._table.restore_layout()
        if empty:
            self._drop_prompt.set_expanded(True)

    # ------------------------------------------------------------ 窗口边缘缩放
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.MouseButtonPress and not self.isMaximized():
            position = event.position().toPoint() if hasattr(event, "position") else event.pos()
            edges = self._edges_at(position)
            if edges:
                self.windowHandle().startSystemResize(edges)
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def _edges_at(self, position) -> Qt.Edges:
        border = 6
        edges = Qt.Edges()
        if position.x() < border:
            edges |= Qt.LeftEdge
        if position.x() > self.width() - border:
            edges |= Qt.RightEdge
        if position.y() < border:
            edges |= Qt.TopEdge
        if position.y() > self.height() - border:
            edges |= Qt.BottomEdge
        return edges

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._queue.active:
            reply = QMessageBox.question(
                self,
                "正在处理任务",
                "仍有文件正在处理，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._queue.cancel_all()
        # 关闭窗口时终止可能仍在后台运行的音频提取进程，避免残留
        if self._audio_runner is not None:
            try:
                self._audio_runner.cancel()
            except Exception:
                pass
            self._audio_runner = None
        self._hardware.stop()
        self._settings.sync()
        super().closeEvent(event)
