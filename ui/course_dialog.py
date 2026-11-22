"""课程压缩对话框：参数可调的批量课程视频压缩入口。

视频编码固定 H.264/AVC、扫描方式固定逐行、音频编码固定 AAC；
最低视频码率、分辨率、帧率、音频采样率、音频码率可调。
"""

from __future__ import annotations

from app.theme import RoundedCombo
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.models import CourseParams
from ui.widgets import caption, subheading


class CourseCompressDialog(QDialog):
    """弹出对话框，调节课程压缩参数后点击「应用」返回 CourseParams。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("课程压缩")
        self.setMinimumWidth(460)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(subheading("课程压缩", self))
        hint = caption(
            "面向网课/教学视频的可调压缩：H.264 + AAC，按最低码率保证画质损失最小。"
            "参数将应用到所有已添加的视频。",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        group = QGroupBox("编码参数", self)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)

        # 固定项：以弱化标签展示
        form.addRow("视频编码", caption("H.264/AVC（固定）", self))
        form.addRow("扫描方式", caption("逐行（固定）", self))
        form.addRow("音频编码", caption("AAC（固定）", self))

        # 最低视频码率
        self._vbr = QSpinBox(self)
        self._vbr.setRange(1024, 20000)
        self._vbr.setSingleStep(64)
        self._vbr.setValue(1024)
        self._vbr.setSuffix(" Kbps")
        self._vbr.setToolTip("动态码率下限，简单场景不浪费、复杂场景靠上限兜底")
        form.addRow("最低视频码率", self._vbr)

        # 分辨率（宽 × 高）
        res_row = QHBoxLayout()
        self._width = QSpinBox(self)
        self._width.setRange(1, 7680)
        self._width.setValue(1280)
        self._width.setFixedWidth(90)
        self._height = QSpinBox(self)
        self._height.setRange(1, 7680)
        self._height.setValue(720)
        self._height.setFixedWidth(90)
        sep = QLabel("×", self)
        res_row.addWidget(self._width)
        res_row.addWidget(sep)
        res_row.addWidget(self._height)
        res_row.addStretch(1)
        form.addRow("分辨率", self._wrap(res_row))

        # 帧率
        self._fps = QSpinBox(self)
        self._fps.setRange(1, 120)
        self._fps.setValue(25)
        self._fps.setSuffix(" fps")
        form.addRow("帧率", self._fps)

        # 音频采样率
        self._sample = RoundedCombo(self)
        self._sample.addItems(["48000 Hz", "44100 Hz", "32000 Hz"])
        self._sample.setCurrentIndex(0)
        self._sample.setFixedWidth(150)
        form.addRow("音频采样率", self._sample)

        # 音频码率
        self._abr = QSpinBox(self)
        self._abr.setRange(32, 320)
        self._abr.setSingleStep(16)
        self._abr.setValue(128)
        self._abr.setSuffix(" Kbps")
        self._abr.setToolTip("恒定码率（CBR）")
        form.addRow("音频码率", self._abr)

        layout.addWidget(group)
        layout.addStretch(1)

        box = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self
        )
        box.button(QDialogButtonBox.Cancel).setProperty("variant", "ghost")
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.setProperty("variant", "primary")
        ok_btn.setText("应用")
        ok_btn.clicked.connect(self.accept)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    # ------------------------------------------------------------ 辅助
    def _wrap(self, inner: QWidget) -> QWidget:
        """把横向布局包成 QWidget 以便放进 QFormLayout。"""
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addLayout(inner)
        row.addStretch(1)
        return holder

    # ------------------------------------------------------------ 取值
    def params(self) -> CourseParams:
        sample_text = self._sample.currentText()
        sample_rate = int(sample_text.split()[0])
        return CourseParams(
            video_bitrate_kbps=self._vbr.value(),
            width=self._width.value(),
            height=self._height.value(),
            fps=self._fps.value(),
            audio_sample_rate=sample_rate,
            audio_bitrate_kbps=self._abr.value(),
        )
