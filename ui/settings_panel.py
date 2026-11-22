"""底部设置区：左右并排的「视频压缩设置」与「格式转换设置」两个卡片。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from app.theme import RoundedCombo
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import CRF_MAX, CRF_MIN
from app.theme import font_of

from core.capabilities import Capabilities
from core.models import EncodeParams, TaskItem
from core.planner import apply_preset_to_params, estimate_total, suggest_crf_for
from core.profiles import (
    AUDIO_MODES,
    CONTAINER_MAP,
    CONTAINERS,
    DEVICE_PRESETS,
    PRO_PRESET_MAP,
    PROFESSIONAL_PRESETS,
    RESOLUTIONS,
    default_encoder,
    encoders_for_mode,
    encoders_for_vendor,
)
from core.utils import format_size
from ui.widgets import (
    Card,
    Divider,
    SavtCheckBox,
    SavtRadioButton,
    SegmentedControl,
    badge,
    caption,
    field_label,
)
from ui.icons import IconText

UNITS = ["MB", "GB"]

# #9：CRF 数值说明（数值越小画质越高、体积越大）
CRF_HINTS = [
    (16, "接近无损，体积很大（母版归档）"),
    (18, "极高画质，体积较大"),
    (20, "高画质，体积适中（推荐）"),
    (22, "良好画质，体积较小"),
    (24, "普通画质，体积明显减小"),
    (26, "较低画质，体积很小"),
    (32, "低画质，体积最小（预览样片）"),
]


def crf_hint_text(value: int) -> str:
    for threshold, text in CRF_HINTS:
        if value <= threshold:
            return text
    return CRF_HINTS[-1][1]


class SettingsPanel(QWidget):
    paramsChanged = Signal()
    outputDirChanged = Signal(str)

    def __init__(self, settings, caps: Optional[Capabilities], parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._caps = caps
        self._updating = False
        self._crf_manual = False       # 用户是否手动调整过 CRF（决定推荐值是否可自动应用）
        self._current_info = None      # 当前选中视频的媒体信息（用于 CRF 推荐）
        # 记录上一次的单位，供单位切换时做等价换算（避免数值被放大/缩小 1024 倍）
        self._prev_unit = UNITS[0]
        # 记录上一次使用的重编码模式（目标大小/百分比/恒定画质），用于在「视频压缩设置」
        # 页被激活时把「仅转格式」模式自动恢复回来，避免误以重封装方式压缩。
        self._last_encode_mode = "absolute"

        # 「输出参数配置」：单卡片 + 分段控制器 + 堆叠页（视频压缩 / 格式转换）
        self._card = Card(self)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        self._seg = SegmentedControl(self._card)
        self._seg.add_option("compress", "视频压缩设置")
        self._seg.add_option("convert", "格式转换设置")
        self._seg.set_mode("compress")
        self._seg.modeChanged.connect(self._on_seg_mode)
        # 顶部切换器放大、左对齐，与下方内容对齐
        self._seg.setStyleSheet("QPushButton#segBtn { padding: 8px 22px; font-size: 14px; }")
        card_layout.addWidget(self._seg)

        self._stack = QStackedWidget(self._card)
        self._compression_card = QWidget(self._stack)
        self._convert_card = QWidget(self._stack)

        self._build_compression_card()
        self._build_convert_card()

        self._stack.addWidget(self._compression_card)
        self._stack.addWidget(self._convert_card)
        card_layout.addWidget(self._stack, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._card)

        # 左侧与上方批处理队列卡片对齐（表格 760 + 卡片内边距）
        self._card.setMinimumWidth(776)

        self._setup_button_groups()
        self._build_combos()
        self._connect_signals()
        self._refresh_container_availability()
        self.load_from_settings()

    # ------------------------------------------------------------ 输出路径行
    def _build_path_row(self, parent) -> Tuple[QHBoxLayout, QLabel, QPushButton]:
        """构建「输出路径」行，压缩卡片与格式转换卡片各用一份并保持同步。"""
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(field_label("输出路径", parent))
        edit = QLabel("默认输出到源文件同目录", parent)
        edit.setObjectName("mono")
        edit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn = QPushButton("选择文件夹", parent)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(btn.sizeHint().width() + 30)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        return row, edit, btn

    # ------------------------------------------------------------ 视频压缩卡片（标签页一）
    def _build_compression_card(self) -> None:
        card = self._compression_card
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._gpu_hint = IconText("", "", 14, card)
        header.addWidget(self._gpu_hint)
        header.addStretch(1)
        layout.addLayout(header)

        # 第一行：编码器模式 / 编码器型号 / 预设
        self._cpu_radio = SavtRadioButton("CPU（画质优先）", card)
        self._gpu_radio = SavtRadioButton("GPU（速度优先）", card)
        self._cpu_radio.setToolTip("x265 / x264 软件编码，CRF 恒定质量，接近无损")
        self._gpu_radio.setToolTip("NVENC / AMF / QuickSync 硬件加速，速度快，体积误差略增")

        self._encoder_combo = RoundedCombo(card)
        self._encoder_combo.setMinimumWidth(150)
        self._preset_combo = RoundedCombo(card)
        self._preset_combo.setMinimumWidth(130)

        encoder_row = QHBoxLayout()
        encoder_row.setSpacing(10)
        encoder_row.addWidget(self._cpu_radio)
        encoder_row.addWidget(self._gpu_radio)
        encoder_row.addSpacing(6)
        encoder_row.addWidget(self._encoder_combo)
        encoder_row.addSpacing(6)
        encoder_row.addWidget(self._preset_combo)
        encoder_row.addStretch(1)
        layout.addLayout(encoder_row)

        # 第二行：目标大小 / 百分比
        self._abs_radio = SavtRadioButton("目标大小", card)
        self._target_spin = QDoubleSpinBox(card)
        # 下限取 0、精度取 2 位：切到 GB 单位时 50MB≈0.05GB 才能原样往返，
        # 否则会被下限/精度截断成 0.5GB（放大 10 倍）。0 作为「未设置」占位符。
        self._target_spin.setRange(0, 99999)
        self._target_spin.setDecimals(2)
        self._target_spin.setSpecialValueText("未设置")
        self._target_spin.setFixedWidth(92)
        self._unit_combo = RoundedCombo(card)
        self._unit_combo.addItems(UNITS)
        self._unit_combo.setFixedWidth(72)

        self._pct_radio = SavtRadioButton("百分比", card)
        self._percent_spin = QSpinBox(card)
        self._percent_spin.setRange(1, 300)
        self._percent_spin.setFixedWidth(78)
        self._percent_spin.setSuffix(" %")

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        size_row.addWidget(self._abs_radio)
        size_row.addWidget(self._target_spin)
        size_row.addWidget(self._unit_combo)
        size_row.addSpacing(10)
        size_row.addWidget(self._pct_radio)
        size_row.addWidget(self._percent_spin)
        size_row.addStretch(1)
        layout.addLayout(size_row)

        # 第三行：恒定画质 CRF（独立成行，避免与上行挤压重叠）
        self._crf_radio = SavtRadioButton("恒定画质 CRF", card)
        self._crf_slider = QSlider(Qt.Horizontal, card)
        self._crf_slider.setRange(CRF_MIN, CRF_MAX)
        self._crf_slider.setFixedWidth(120)
        self._crf_label = QLabel("20", card)
        self._crf_label.setFixedWidth(26)
        self._crf_hint = QLabel(crf_hint_text(20), card)
        self._crf_hint.setObjectName("fieldHint")

        crf_row = QHBoxLayout()
        crf_row.setSpacing(8)
        crf_row.addWidget(self._crf_radio)
        crf_row.addWidget(self._crf_slider)
        crf_row.addWidget(self._crf_label)
        crf_row.addWidget(self._crf_hint)
        crf_row.addStretch(1)
        layout.addLayout(crf_row)

        # 第四行：两遍编码
        self._two_pass_check = SavtCheckBox("启用两遍编码（更贴近目标大小）", card)
        self._two_pass_check.setToolTip("2-Pass 可把最终体积误差控制在 ±3% 以内，耗时约翻倍")
        option_row = QHBoxLayout()
        option_row.addWidget(self._two_pass_check)
        option_row.addStretch(1)
        layout.addLayout(option_row)

        # 第五行：分辨率 + 音频 并排（与格式转换卡片共享音频设置，两侧下拉保持同步）
        self._res_combo = RoundedCombo(card)
        self._res_combo.setFixedWidth(130)
        self._res_combo.setToolTip("将视频缩放至所选分辨率上限，保持原宽高比，不拉伸变形")
        for key, label, _, _ in RESOLUTIONS:
            self._res_combo.addItem(label, key)

        self._audio_combo2 = RoundedCombo(card)
        self._audio_combo2.setFixedWidth(130)
        self._audio_combo2.setToolTip(
            "选择输出音频处理方式；「跟随压缩（动态）」会按视频目标码率自动选 64k/128k"
        )

        res_audio_row = QHBoxLayout()
        res_audio_row.setSpacing(10)
        res_audio_row.addWidget(field_label("分辨率", card))
        res_audio_row.addWidget(self._res_combo)
        res_audio_row.addWidget(caption("保持原比例，不拉伸"))
        res_audio_row.addSpacing(12)
        res_audio_row.addWidget(field_label("音频", card))
        res_audio_row.addWidget(self._audio_combo2)
        res_audio_row.addWidget(caption("跟随压缩：按视频码率自动选 64k/128k"))
        res_audio_row.addStretch(1)
        layout.addLayout(res_audio_row)

        # 第七行：输出路径
        (
            self._path_row,
            self._output_edit,
            self._output_btn,
        ) = self._build_path_row(card)
        layout.addLayout(self._path_row)

        layout.addWidget(Divider(card))

        # 预估结果栏：绿色徽章（节省比例）+ 富文本说明（原始删除线 → 输出体积）
        estimate_row = QHBoxLayout()
        estimate_row.setSpacing(8)
        self._estimate_badge = badge("")
        self._estimate_badge.setVisible(False)
        self._estimate_label = QLabel("添加文件后显示预估压缩结果", card)
        self._estimate_label.setFont(font_of(13, 600))
        self._estimate_label.setObjectName("accent")
        self._estimate_label.setTextFormat(Qt.RichText)
        estimate_row.addWidget(self._estimate_badge)
        estimate_row.addWidget(self._estimate_label)
        estimate_row.addStretch(1)
        layout.addLayout(estimate_row)

    # ------------------------------------------------------------ 格式转换卡片（标签页二）
    def _build_convert_card(self) -> None:
        card = self._convert_card
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        # 「仅转格式」模式开关
        self._copy_radio = SavtRadioButton("仅转格式（不重编码）", card)
        self._copy_radio.setToolTip("直接复制音视频流到新封装，画质无损、速度最快，体积基本不变")
        copy_row = QHBoxLayout()
        copy_row.addWidget(self._copy_radio)
        copy_row.addStretch(1)
        layout.addLayout(copy_row)

        # 仅转格式模式提示：明确其「快速重封装、不重编码」的语义，避免与压缩混淆
        self._copy_hint = QLabel(
            "仅按上方所选格式快速重封装，不重新编码；如要压缩请切到「视频压缩设置」页。",
            card,
        )
        self._copy_hint.setObjectName("muted")
        self._copy_hint.setWordWrap(True)
        layout.addWidget(self._copy_hint)

        # 输出格式 / 音频
        self._container_combo = RoundedCombo(card)
        self._container_combo.setFixedWidth(110)
        self._container_combo.setToolTip(
            "选择输出格式即可完成格式转换；配合「仅转格式（不重编码）」"
            "可在完全不损失画质的情况下极速转换封装"
        )
        self._audio_combo = RoundedCombo(card)
        self._audio_combo.setFixedWidth(130)

        format_row = QHBoxLayout()
        format_row.setSpacing(12)
        format_row.addWidget(field_label("输出格式", card))
        format_row.addWidget(self._container_combo)
        format_row.addSpacing(6)
        format_row.addWidget(field_label("音频", card))
        format_row.addWidget(self._audio_combo)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        # 输出路径
        (
            self._path_row2,
            self._output_edit2,
            self._output_btn2,
        ) = self._build_path_row(card)
        layout.addLayout(self._path_row2)

        layout.addStretch(1)

    # ------------------------------------------------------------ 构建
    def _setup_button_groups(self) -> None:
        """#1：把单选按钮拆成两个独立的互斥组。

        QRadioButton 默认 autoExclusive=True，同一父控件内的所有单选按钮会自动互斥。
        用 QButtonGroup 分组后，编码器组与尺寸模式组互不干扰。
        """
        self._encoder_group = QButtonGroup(self)
        self._encoder_group.addButton(self._cpu_radio, 0)
        self._encoder_group.addButton(self._gpu_radio, 1)

        self._size_group = QButtonGroup(self)
        self._size_group.addButton(self._abs_radio, 0)
        self._size_group.addButton(self._pct_radio, 1)
        self._size_group.addButton(self._crf_radio, 2)
        self._size_group.addButton(self._copy_radio, 3)

    def _on_seg_mode(self, mode: str) -> None:
        """分段控制器切换页面。

        切到「视频压缩设置」页时，若当前仍停留在「仅转格式」模式，自动恢复上一次
        的重编码模式（目标大小/百分比/恒定画质）。否则会出现「看着压缩页、实际跑的是
        仅转格式重封装」的陷阱——输出沿用格式转换所选封装，而非源文件格式。
        """
        self._stack.setCurrentIndex(0 if mode == "compress" else 1)
        if mode == "convert":
            # 进入转换页：勾选「仅转格式」以同步视觉状态（实际模式恒由页面决定）
            if not self._copy_radio.isChecked():
                self._copy_radio.setChecked(True)  # 触发 _on_changed：刷新控件 + 保存 + 通知
        elif self._copy_radio.isChecked():
            target = self._last_encode_mode or "absolute"
            radio = {
                "absolute": self._abs_radio,
                "percent": self._pct_radio,
                "crf": self._crf_radio,
            }.get(target, self._abs_radio)
            radio.setChecked(True)  # 触发 _on_changed：刷新控件 + 保存 + 通知

    def _size_mode_from_radios(self) -> str:
        if self._abs_radio.isChecked():
            return "absolute"
        if self._pct_radio.isChecked():
            return "percent"
        if self._crf_radio.isChecked():
            return "crf"
        return "streamcopy"

    def _update_mode_controls(self) -> None:
        """根据尺寸模式启用/禁用相关输入（四种模式互斥）。

        - 目标大小：启用目标大小 + 单位；禁用百分比、CRF 三项
        - 百分比：  启用百分比；禁用目标大小 + 单位、CRF 三项
        - 恒定画质：启用 CRF 滑块 / 数值 / 提示；禁用目标大小 + 单位、百分比
        - 仅转格式：全部禁用
        两遍编码仅在「目标大小 / 百分比」模式可用。
        """
        abs_mode = self._abs_radio.isChecked()
        pct_mode = self._pct_radio.isChecked()
        crf_mode = self._crf_radio.isChecked()

        self._target_spin.setEnabled(abs_mode)
        self._unit_combo.setEnabled(abs_mode)
        self._percent_spin.setEnabled(pct_mode)
        self._crf_slider.setEnabled(crf_mode)
        self._crf_label.setEnabled(crf_mode)
        # 非 CRF 模式时数值显式置灰：QSS 固定 color 使 disabled 不变色，改用 muted 样式保持一致
        self._crf_label.setObjectName("muted" if not crf_mode else "")
        self._crf_label.style().unpolish(self._crf_label)
        self._crf_label.style().polish(self._crf_label)
        self._crf_hint.setEnabled(crf_mode)

        # 分辨率缩放仅重编码模式生效；仅转格式（streamcopy）不重编码，禁用
        self._res_combo.setEnabled(abs_mode or pct_mode or crf_mode)

        # 切换模式后刷新 CRF 推荐提示（进入 CRF 时自动应用推荐值）
        self._refresh_crf_recommendation()

        two_pass_enabled = abs_mode or pct_mode
        self._two_pass_check.setEnabled(two_pass_enabled)
        # CRF / 仅转格式模式下两遍编码无意义：自动取消勾选
        if not two_pass_enabled:
            self._two_pass_check.setChecked(False)
        # GPU（速度优先）模式下不建议两遍编码：自动取消勾选并给出专用提示
        if self._gpu_radio.isChecked() and two_pass_enabled:
            self._two_pass_check.setChecked(False)
            self._two_pass_check.setToolTip("GPU编码通常不建议使用两遍编码")
        else:
            self._two_pass_check.setToolTip(
                "2-Pass 可把最终体积误差控制在 ±3% 以内，耗时约翻倍"
                if two_pass_enabled else "两遍编码仅在目标大小 / 百分比模式生效"
            )

    def _build_combos(self) -> None:
        for container in CONTAINERS:
            self._container_combo.addItem(container.label, container.key)
        for key, label in AUDIO_MODES:
            self._audio_combo.addItem(label, key)
            self._audio_combo2.addItem(label, key)

        self._preset_combo.addItem("无预设（自定义参数）", "")
        self._preset_combo.addItem("—— 设备预设 ——", "__device__")
        for device in DEVICE_PRESETS:
            self._preset_combo.addItem(device.label, device.key)
        self._preset_combo.addItem("—— 专业格式 ——", "__pro__")
        for preset in PROFESSIONAL_PRESETS:
            self._preset_combo.addItem(preset.label, preset.key)
        self._refresh_encoder_combo()

    def _connect_signals(self) -> None:
        self._cpu_radio.toggled.connect(self._on_encoder_mode)
        self._gpu_radio.toggled.connect(self._on_encoder_mode)
        self._encoder_combo.currentIndexChanged.connect(self._on_changed)
        self._preset_combo.currentIndexChanged.connect(self._on_preset)
        for radio in (self._abs_radio, self._pct_radio, self._crf_radio, self._copy_radio):
            radio.toggled.connect(self._on_changed)
        self._target_spin.valueChanged.connect(self._on_changed)
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        self._percent_spin.valueChanged.connect(self._on_changed)
        self._crf_slider.valueChanged.connect(self._on_crf)
        self._container_combo.currentIndexChanged.connect(self._on_changed)
        self._audio_combo.currentIndexChanged.connect(self._on_audio_changed)
        self._audio_combo2.currentIndexChanged.connect(self._on_audio_changed)
        self._res_combo.currentIndexChanged.connect(self._on_changed)
        self._two_pass_check.toggled.connect(self._on_changed)

        self._output_btn.clicked.connect(self._choose_output)
        self._output_btn2.clicked.connect(self._choose_output)

    # ------------------------------------------------------------ 能力
    def set_caps(self, caps: Capabilities) -> None:
        self._caps = caps
        self._refresh_encoder_combo()
        self._refresh_container_availability()
        self._update_gpu_hint()

    def set_palette(self, palette) -> None:
        """同步自绘控件（单选 / 复选按钮 / 图标文字）的调色板。"""
        for widget in self.findChildren(SavtRadioButton):
            widget.set_palette(palette)
        for widget in self.findChildren(SavtCheckBox):
            widget.set_palette(palette)
        for widget in self.findChildren(IconText):
            widget.set_palette(palette)

    def _refresh_container_availability(self) -> None:
        """当前 ffmpeg 不支持的封装格式置灰，避免生成必然失败的命令。"""
        if self._caps is None or not self._caps.ok:
            return
        model = self._container_combo.model()
        for row in range(self._container_combo.count()):
            spec = CONTAINER_MAP.get(self._container_combo.itemData(row))
            item = model.item(row)
            if spec is None or item is None:
                continue
            available = self._caps.has_muxer(spec.muxer)
            item.setEnabled(available)
            item.setToolTip("" if available else "当前 ffmpeg 未包含该封装格式")

    def _refresh_encoder_combo(self) -> None:
        try:
            current = self._encoder_combo.currentData()
        except RuntimeError:
            # 控件已随窗口销毁（如后台探测回调晚于窗口关闭），直接忽略
            return
        self._encoder_combo.blockSignals(True)
        self._encoder_combo.clear()

        mode = "gpu" if self._gpu_radio.isChecked() else "cpu"
        # GPU 模式只认本机显卡厂商：N 卡仅 NVENC、A 卡仅 AMF、Intel 仅 QSV，
        # 避免下拉里出现本机用不了的其它厂商编码器（实际可用性由启动时后台探测缓存决定）
        vendor = self._caps.gpu_vendor() if (mode == "gpu" and self._caps is not None) else ""

        available = []
        if self._caps is not None:
            if mode == "gpu" and vendor:
                available = [
                    spec for spec in encoders_for_vendor(vendor)
                    if self._caps.has_encoder(spec.key)
                ]
            if not available:
                # 未探测到可用硬件编码器时回退 CPU 列表
                available = [
                    spec for spec in encoders_for_mode("cpu")
                    if self._caps.has_encoder(spec.key)
                ]
                mode = "cpu"
                vendor = ""
            available.sort(key=lambda spec: spec.codec != "h264")

        for spec in available:
            self._encoder_combo.addItem(spec.label, spec.key)

        # 沿用当前选择；不在列表中时回落到该模式的默认编码器（统一 H.264 优先）
        index = self._encoder_combo.findData(current) if current else -1
        if index < 0:
            index = self._encoder_combo.findData(default_encoder(mode, vendor))
        if index < 0 and self._encoder_combo.count():
            index = 0
        if index >= 0:
            self._encoder_combo.setCurrentIndex(index)
        self._encoder_combo.blockSignals(False)

    def _update_gpu_hint(self) -> None:
        if self._caps is None or not self._caps.ok:
            self._gpu_hint.set_icon("")
            self._gpu_hint.set_text("")
            self._gpu_hint.setToolTip("")
            self._set_hint_style(warning=False)
            return
        vendor = self._caps.gpu_vendor()
        names = {"nvidia": "NVIDIA NVENC", "amd": "AMD AMF", "intel": "Intel QuickSync"}
        if vendor:
            self._gpu_hint.set_icon("")
            self._gpu_hint.set_text(f"检测到硬件编码器：{names.get(vendor, vendor)}")
            self._gpu_hint.setToolTip("已启用硬件加速，编码速度更快")
            self._set_hint_style(warning=False)
        elif self._gpu_radio.isChecked():
            # 切换到 GPU 但 ffmpeg 不可用 NVENC/AMF/QuickSync 时给出醒目告警，避免静默回退造成困惑
            self._gpu_hint.set_icon("alert-triangle")
            self._gpu_hint.set_text("未检测到可用的硬件编码器，将自动使用 CPU 编码")
            self._gpu_hint.setToolTip(
                "当前 ffmpeg 未包含 NVIDIA NVENC / AMD AMF / Intel QuickSync 等硬件加速器，\n"
                "已选择 GPU 模式时会自动回退到 CPU（x265 / x264）。\n"
                "如需使用硬件编码，请安装支持硬件加速的 ffmpeg 版本。"
            )
            self._set_hint_style(warning=True)
        else:
            self._gpu_hint.set_icon("")
            self._gpu_hint.set_text("")
            self._gpu_hint.setToolTip("")
            self._set_hint_style(warning=False)

    def _set_hint_style(self, warning: bool) -> None:
        """切换 GPU 提示的样式：告警用红色，正常用次要色。"""
        self._gpu_hint.set_text_style("statusWarning" if warning else "caption")

    def _update_encoder_mode_availability(self) -> None:
        """专业格式（ProRes / DNxHR / Alpha）只有 CPU 实现，
        此时 CPU/GPU 单选不生效，置灰并给出说明，避免误导。"""
        key = self._preset_combo.currentData()
        locked = key in PRO_PRESET_MAP
        tip = "当前专业格式仅支持 CPU 编码，该选项不生效" if locked else ""
        for radio in (self._cpu_radio, self._gpu_radio):
            radio.setEnabled(not locked)
            radio.setToolTip(tip or (
                "x265 / x264 软件编码，CRF 恒定质量，接近无损"
                if radio is self._cpu_radio else
                "NVENC / AMF / QuickSync 硬件加速，速度快，体积误差略增"
            ))
        self._encoder_combo.setEnabled(not locked)

    def refresh_gpu_availability(self) -> None:
        """在后台完成硬件编码器探测后刷新下拉与提示。"""
        self._refresh_encoder_combo()
        self._update_gpu_hint()

    # ------------------------------------------------------------ 参数
    def params(self) -> EncodeParams:
        params = EncodeParams()
        params.encoder_mode = "gpu" if self._gpu_radio.isChecked() else "cpu"
        params.encoder = self._encoder_combo.currentData() or (
            "h264_nvenc" if params.encoder_mode == "gpu" else "libx264"
        )
        page = self._seg.mode()
        if page == "convert":
            # 格式转换 / 仅转格式：与视频压缩设置完全隔离，仅读取本页控件
            params.size_mode = "streamcopy"
            params.container = self._container_combo.currentData() or "mp4"
            params.audio_mode = self._audio_combo.currentData() or "copy"
            params.resolution = self._res_combo.currentData() or "origin"
            params.two_pass = self._two_pass_check.isChecked()
            params.keep_subtitles = bool(self._settings.keep_subtitles)
            params.keep_hdr = bool(self._settings.keep_hdr)
            params.preset_name = ""  # 预设是压缩特性，转换页不生效，避免污染输出格式/音频
            return params
        # 视频压缩页：仅读取本页控件，绝不取转换页的「仅转格式」
        mode = self._size_mode_from_radios()
        if mode == "streamcopy":
            mode = self._last_encode_mode or "absolute"
        params.size_mode = mode
        from core.utils import size_to_bytes
        params.target_bytes = size_to_bytes(self._target_spin.value(), self._unit_combo.currentText())
        params.percent = self._percent_spin.value()
        params.crf = self._crf_slider.value()
        # 压缩输出容器由 _resolve_compress_container 按源文件格式决定，
        # 不读转换卡的下拉（避免“先转 MKV 再压缩，压缩输出也变 MKV”）
        params.container = ""
        params.audio_mode = self._audio_combo2.currentData() or "copy"
        params.resolution = self._res_combo.currentData() or "origin"
        params.two_pass = self._two_pass_check.isChecked()
        params.keep_subtitles = bool(self._settings.keep_subtitles)
        params.keep_hdr = bool(self._settings.keep_hdr)
        params.preset_name = self._preset_combo.currentData() or ""
        if params.preset_name in ("__device__", "__pro__"):
            params.preset_name = ""
        if params.preset_name:
            apply_preset_to_params(params, params.preset_name)
        return params

    def set_target_value(self, target_bytes: int) -> None:
        """仅更新目标大小输入框的显示值（不触发保存 / 参数同步）。"""
        from core.utils import bytes_to_unit
        self._updating = True
        # 转换页 / 已选「仅转格式」时不抢模式：强制切「目标大小」会因单选互斥把
        # 「仅转格式」顶掉，造成它刚点上就被弹回、看似无法选中的问题
        if self._seg.mode() != "convert" and not self._copy_radio.isChecked():
            self._abs_radio.setChecked(True)
        # 下限用控件自身的 minimum：原先写死 0.5 会把 GB 单位下的智能目标（约 0.05GB）
        # 抬到 0.5GB（放大 10 倍）
        self._target_spin.setValue(
            max(bytes_to_unit(target_bytes, self._unit_combo.currentText()),
                self._target_spin.minimum())
        )
        self._updating = False

    def set_target_from_video(self, size_bytes: int) -> None:
        """根据选中视频的目标压缩大小更新目标大小输入框（不触发保存 / 参数同步 / 不切换模式）。

        - size_bytes > 0：将目标大小填入该值，单位自动适配。
        - size_bytes == 0（无视频 / 未探测）：清空为「未设置」占位符。

        注意：不改变当前压缩模式（目标大小/百分比/CRF/仅转格式），由用户自行选择。
        """
        from core.utils import bytes_to_unit
        self._updating = True
        if size_bytes > 0:
            self._target_spin.setValue(
                max(bytes_to_unit(size_bytes, self._unit_combo.currentText()),
                    self._target_spin.minimum())
            )
        else:
            self._target_spin.setValue(0)  # 触发 specialValueText("未设置")
        self._updating = False

    def set_video_info(self, info) -> None:
        """记录当前选中视频的媒体信息，并刷新 CRF 推荐提示。

        切换选中视频时重置 _crf_manual，使未手动改过 CRF 的用户重新获得按新视频
        分辨率推荐的 CRF 值；已手动调整过的则保持用户选择。

        若在 CRF 模式下应用了推荐值，统一模式下同步保存并发射 paramsChanged，
        使所有任务套用新 CRF 并刷新预估；独立模式不发射（其后 set_params 会恢复单文件值）。
        """
        self._current_info = info
        self._crf_manual = False
        applied = self._refresh_crf_recommendation()
        if applied and self._settings.batch_mode == "unified":
            self.save_to_settings()
            self.paramsChanged.emit()

    def _refresh_crf_recommendation(self) -> bool:
        """CRF 模式下根据选中视频显示推荐 CRF 提示，并在满足条件时自动把滑块设为推荐值。

        自动应用条件（同时满足）：
          1. 当前为 CRF 模式（_crf_radio 勾选）
          2. 已选中带分辨率的视频（_current_info 有效）
          3. 用户未手动调整过 CRF（_crf_manual 为 False）
          4. 推荐值与当前滑块值不同（避免无意义的重复刷新）
        应用后把 _crf_manual 置 True，使其在该视频内不被重复覆盖；切换视频时
        set_video_info 会把它重置为 False，从而对新视频再次推荐。

        返回是否实际应用了推荐值（供 set_video_info 决定是否持久化 / 刷新预估）。
        """
        if not self._crf_radio.isChecked():
            # 非 CRF 模式：提示恢复为当前 CRF 的基础描述（控件置灰，仅占位）
            self._crf_hint.setText(crf_hint_text(self._crf_slider.value()))
            return False
        info = self._current_info
        if info is None or not info.width:
            self._crf_hint.setText(crf_hint_text(self._crf_slider.value()))
            return False
        rec = suggest_crf_for(info)
        self._crf_hint.setText(f"推荐 CRF {rec}（{info.resolution_label}·高画质·体积适中）")
        if self._crf_manual or self._crf_slider.value() == rec:
            return False
        # blockSignals 防止 valueChanged → _on_crf 副作用（重复置 _crf_manual 并触发冗余信号）
        self._crf_slider.blockSignals(True)
        self._crf_slider.setValue(rec)
        self._crf_label.setText(str(rec))
        self._crf_slider.blockSignals(False)
        self._crf_manual = True
        return True

    def set_params(self, params: EncodeParams) -> None:
        self._updating = True
        self._cpu_radio.setChecked(params.encoder_mode != "gpu")
        self._gpu_radio.setChecked(params.encoder_mode == "gpu")
        self._refresh_encoder_combo()
        index = self._encoder_combo.findData(params.encoder)
        if index >= 0:
            self._encoder_combo.setCurrentIndex(index)
        index = self._preset_combo.findData(params.preset_name)
        self._preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self._update_encoder_mode_availability()

        self._abs_radio.setChecked(params.size_mode == "absolute")
        self._pct_radio.setChecked(params.size_mode == "percent")
        self._crf_radio.setChecked(params.size_mode == "crf")
        self._copy_radio.setChecked(params.size_mode == "streamcopy")
        # 记住加载时的重编码模式，供切回压缩页时恢复（仅转格式不记录）
        if params.size_mode != "streamcopy":
            self._last_encode_mode = params.size_mode
        from core.utils import bytes_to_unit
        self._target_spin.setValue(
            max(bytes_to_unit(params.target_bytes, self._unit_combo.currentText()),
                self._target_spin.minimum())
        )
        self._percent_spin.setValue(params.percent)
        self._crf_slider.setValue(params.crf)
        self._crf_label.setText(str(params.crf))
        self._crf_hint.setText(crf_hint_text(params.crf))
        # 显式载入参数：视为已确定的取值，不再被推荐值自动覆盖
        self._crf_manual = True

        # 容器：仅格式转换任务回填「格式转换」卡的下拉；压缩任务容器由源格式/预设决定
        if params.size_mode == "streamcopy":
            index = self._container_combo.findData(params.container)
            if index >= 0:
                self._container_combo.setCurrentIndex(index)
        # 音频：按任务类型回填对应卡片的下拉，两卡不再互相同步
        target_audio = self._audio_combo if params.size_mode == "streamcopy" else self._audio_combo2
        index = target_audio.findData(params.audio_mode)
        if index >= 0:
            target_audio.setCurrentIndex(index)
        index = self._res_combo.findData(params.resolution)
        if index >= 0:
            self._res_combo.setCurrentIndex(index)
        self._two_pass_check.setChecked(params.two_pass)
        # 应用参数后再次同步 GPU 与两遍编码状态，确保 GPU 模式不保留 two_pass
        self._update_mode_controls()
        self._updating = False

    def load_from_settings(self) -> None:
        self._migrate_default_encoder()
        self._migrate_output_dir_to_default()
        params = EncodeParams()
        params.encoder_mode = self._settings.encoder_mode
        params.encoder = self._settings.encoder
        params.size_mode = self._settings.size_mode
        from core.utils import size_to_bytes
        params.target_bytes = size_to_bytes(self._settings.target_value, self._settings.target_unit)
        params.percent = self._settings.percent
        params.crf = self._settings.crf
        params.container = self._settings.container
        params.audio_mode = self._settings.audio_mode
        params.keep_subtitles = self._settings.keep_subtitles
        params.preset_name = self._settings.preset_name
        params.keep_hdr = self._settings.keep_hdr
        # 单位必须先于 set_params 设置：否则 set_params 会用旧的（默认 MB）单位
        # 去换算 target_bytes，把 1GB 填成 1024，再切到 GB 就变成 1024GB。
        self._prev_unit = self._settings.target_unit or UNITS[0]
        self._unit_combo.setCurrentText(self._prev_unit)
        self.set_params(params)

        # 压缩卡音频独立加载（与转换卡 settings.audio_mode 隔离），覆盖 set_params 的回填
        idx = self._audio_combo2.findData(self._settings.audio_mode_compress)
        if idx >= 0:
            self._audio_combo2.setCurrentIndex(idx)

        # 启动默认停留在「视频压缩设置」页；若上次关闭时停留在「仅转格式」，
        # 立刻恢复上一次重编码模式，避免一启动就处于"看着压缩页、实为重封装"的状态。
        if self._seg.mode() == "compress" and self._copy_radio.isChecked():
            target = self._last_encode_mode or "absolute"
            radio = {
                "absolute": self._abs_radio,
                "percent": self._pct_radio,
                "crf": self._crf_radio,
            }.get(target, self._abs_radio)
            radio.setChecked(True)

        self._update_output_label()

    def _migrate_default_encoder(self) -> None:
        """把旧版默认的 H.265 迁移为 H.264（只执行一次，之后尊重用户选择）。"""
        if self._settings.migrated_h264_default:
            return
        if self._settings.encoder == "libx265":
            self._settings.encoder = "libx264"
        self._settings.migrated_h264_default = True
        self._settings.sync()

    def _migrate_output_dir_to_default(self) -> None:
        """把旧版硬编码的默认输出目录清空，统一改为「留空 = 输出到源文件同目录」（只迁移一次）。"""
        if self._settings.output_dir_migrated_to_default:
            return
        if self._settings.output_dir:
            self._settings.output_dir = ""
        self._settings.output_dir_migrated_to_default = True
        self._settings.sync()

    def save_to_settings(self) -> None:
        params = self.params()
        self._settings.encoder_mode = params.encoder_mode
        self._settings.encoder = params.encoder
        # 仅在压缩页保存尺寸模式；转换页编辑时不把 size_mode 写成 streamcopy 覆盖压缩设置
        if self._seg.mode() == "compress":
            self._settings.size_mode = (
                params.size_mode if params.size_mode != "streamcopy"
                else (self._last_encode_mode or "absolute")
            )
        from core.utils import bytes_to_unit
        # 压缩页专属数值仅在压缩页保存；转换页编辑时 params() 给出默认目标/百分比/CRF，
        # 不可覆盖压缩页已存值（否则改一次转换设置就清掉用户的压缩目标大小）
        if self._seg.mode() == "compress":
            self._settings.target_value = bytes_to_unit(params.target_bytes, self._unit_combo.currentText())
            self._settings.target_unit = self._unit_combo.currentText()
            self._settings.percent = params.percent
            self._settings.crf = params.crf
        self._settings.container = params.container
        # 压缩卡音频独立持久化（与转换卡 settings.audio_mode 隔离）
        self._settings.audio_mode_compress = self._audio_combo2.currentData() or "copy"
        self._settings.audio_mode = params.audio_mode
        self._settings.keep_subtitles = params.keep_subtitles
        self._settings.preset_name = params.preset_name
        self._settings.keep_hdr = params.keep_hdr
        self._settings.sync()

    def shutdown_enabled(self) -> bool:
        return bool(self._settings.shutdown_after)

    def report_enabled(self) -> bool:
        return bool(self._settings.generate_report)

    def output_dir(self) -> str:
        return self._settings.output_dir

    # ------------------------------------------------------------ 槽
    def _on_encoder_mode(self, *_args) -> None:
        if self._updating:
            return
        self._refresh_encoder_combo()
        self._update_gpu_hint()
        # _on_changed -> _update_mode_controls 会统一处理 GPU 模式下的两遍编码同步
        self._on_changed()

    def _on_preset(self, *_args) -> None:
        if self._updating:
            return
        key = self._preset_combo.currentData()
        if key in ("__device__", "__pro__"):
            self._updating = True
            self._preset_combo.setCurrentIndex(0)
            self._updating = False
            return
        if key:
            params = self.params()
            apply_preset_to_params(params, key)
            self._updating = True
            # 预设仅作用于视频压缩，不再把预设的封装/音频写回「格式转换」卡的下拉，
            # 避免污染转换页设置。压缩任务的容器由 _resolve_compress_container 的预设分支决定。
            self._cpu_radio.setChecked(params.encoder_mode != "gpu")
            self._gpu_radio.setChecked(params.encoder_mode == "gpu")
            self._refresh_encoder_combo()
            index = self._encoder_combo.findData(params.encoder)
            if index >= 0:
                self._encoder_combo.setCurrentIndex(index)
            self._updating = False
        self._update_encoder_mode_availability()
        self._on_changed()

    def _on_crf(self, value: int) -> None:
        if self._updating:
            return
        # 用户手动拖动滑块：标记手动调整，后续不再被推荐值自动覆盖
        self._crf_manual = True
        self._crf_label.setText(str(value))
        self._crf_hint.setText(crf_hint_text(value))
        self._on_changed()

    def _on_audio_changed(self, *_args) -> None:
        """音频下拉（视频压缩卡片 / 格式转换卡片各一份）改动时触发参数更新。

        两个卡片的音频设置现已完全隔离，各自独立、分别持久化，不再互相同步。
        """
        self._on_changed()

    def _on_unit_changed(self, new_unit: str) -> None:
        """单位切换时保持目标体积等价：按旧单位折成字节，再按新单位折回。

        不这样做的话，50MB 切到 GB 会变成 50GB（×1024），并立刻写回配置。
        """
        old_unit = self._prev_unit
        self._prev_unit = new_unit
        if self._updating or not old_unit or old_unit == new_unit:
            self._on_changed()
            return
        from core.utils import bytes_to_unit, size_to_bytes
        current_bytes = size_to_bytes(self._target_spin.value(), old_unit)
        minimum = self._target_spin.minimum()
        self._target_spin.blockSignals(True)
        self._target_spin.setValue(max(bytes_to_unit(current_bytes, new_unit), minimum))
        self._target_spin.blockSignals(False)
        self._on_changed()

    def _on_changed(self, *_args) -> None:
        self._update_mode_controls()
        # 记录上一次使用的重编码模式（仅转格式不记录），供切回压缩页时恢复
        mode = self._size_mode_from_radios()
        if mode != "streamcopy":
            self._last_encode_mode = mode
        if self._updating:
            return
        self.save_to_settings()
        self.paramsChanged.emit()

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self._settings.output_dir or "")
        if directory:
            self._settings.output_dir = directory
            self._settings.sync()
            self._update_output_label()
            self.outputDirChanged.emit(directory)
            self.paramsChanged.emit()

    def _update_output_label(self) -> None:
        # 留空 = 默认输出到源文件同目录；用 muted 样式 + 简短提示文字告知用户
        path = self._settings.output_dir
        if path:
            for edit in (self._output_edit, self._output_edit2):
                edit.setText(path)
                edit.setToolTip(path)
                edit.setObjectName("mono")
                edit.style().unpolish(edit)
                edit.style().polish(edit)
        else:
            hint = "默认输出到源文件同目录"
            for edit in (self._output_edit, self._output_edit2):
                edit.setText(hint)
                edit.setToolTip("留空 = 输出到源文件同目录；点击「选择…」可指定其他目录")
                edit.setObjectName("muted")
                edit.style().unpolish(edit)
                edit.style().polish(edit)

    # ------------------------------------------------------------ 预估
    def refresh_estimate(self, tasks: List[TaskItem]) -> None:
        if not tasks:
            self._estimate_badge.setVisible(False)
            self._estimate_label.setText("添加文件后显示预估压缩结果")
            self._estimate_label.setToolTip("")
            return
        original, low, high, saved = estimate_total(tasks, self._caps)
        params = self.params()
        if saved >= 0:
            saved_text = f"节省 {saved * 100:.0f}%"
            badge_neutral = False
        else:
            saved_text = f"体积 +{abs(saved) * 100:.0f}%"
            badge_neutral = True
        # 节省比例做成绿色徽章；体积增加时改用中性色徽章
        self._estimate_badge.setText(saved_text)
        self._estimate_badge.setObjectName("badgeNeutral" if badge_neutral else "badgeSuccess")
        self._estimate_badge.style().unpolish(self._estimate_badge)
        self._estimate_badge.style().polish(self._estimate_badge)
        self._estimate_badge.setVisible(True)

        mid = (low + high) / 2
        out = format_size(mid)
        orig = format_size(original)
        if params.size_mode == "crf":
            text = (
                f"CRF {params.crf}：共 {len(tasks)} 个文件　"
                f"原始 <s>{orig}</s> → {out}"
                f"（预计 {format_size(low)} ~ {format_size(high)}）"
            )
        else:
            text = (
                f"共 {len(tasks)} 个文件　"
                f"原始 <s>{orig}</s> → {out}"
                f"（预计 {format_size(low)} ~ {format_size(high)}）"
            )
        self._estimate_label.setText(text)
        self._estimate_label.setToolTip("预估基于目标码率计算，2-Pass 实际误差通常在 ±3% 以内")

    def set_enabled_state(self, enabled: bool) -> None:
        for widget in (
            self._cpu_radio, self._gpu_radio, self._encoder_combo, self._preset_combo,
            self._abs_radio, self._pct_radio, self._crf_radio, self._target_spin,
            self._unit_combo, self._percent_spin,             self._crf_slider, self._container_combo,
            self._audio_combo, self._audio_combo2, self._res_combo, self._two_pass_check, self._copy_radio,
            self._output_btn, self._output_btn2,
        ):
            widget.setEnabled(enabled)
        if enabled:
            # 专业格式下 CPU/GPU 不生效，需在前一步统一启用后重新置灰
            self._update_encoder_mode_availability()
