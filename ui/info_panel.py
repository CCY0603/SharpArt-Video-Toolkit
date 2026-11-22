"""右侧信息面板：四组信息（一页展示）+ 快捷操作。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.models import VideoInfo
from ui.widgets import GroupCard, button, caption, subheading


class InfoPanel(QWidget):
    copyRequested = Signal()
    extractRequested = Signal()

    def __init__(self, caps, parent=None) -> None:
        super().__init__(parent)
        # 给右侧信息卡片更大基础宽度，避免文件路径、视频参数被截断
        self.setMinimumWidth(380)
        self._caps = caps
        self._info: Optional[VideoInfo] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.addWidget(subheading("文件信息", self))
        title_row.addStretch(1)
        self._tag = caption("拖入即显", self)
        title_row.addWidget(self._tag)
        outer.addLayout(title_row)

        # #7：四组信息改为 2×2 网格双列布局，去掉滚动区，一屏展示全部元数据
        # expand=True 让每张 GroupCard 撑满所在网格行，行间自动均分空白，
        # 避免 6 行卡片堆在一起显得拥挤
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self._basic = GroupCard("基础元数据", compact=True, expand=True)
        self._row_name = self._basic.add_row("文件名", key_width=56)
        self._row_size = self._basic.add_row("文件大小", key_width=56)
        self._row_path = self._basic.add_row("文件路径", key_width=56)

        self._video = GroupCard("视频流信息", compact=True, expand=True)
        self._row_vcodec = self._video.add_row("编码格式", key_width=56)
        self._row_res = self._video.add_row("分辨率", key_width=56)
        self._row_fps = self._video.add_row("帧率", key_width=56)
        self._row_vbitrate = self._video.add_row("码率", key_width=56)
        self._row_duration = self._video.add_row("视频时长", key_width=56)
        self._row_space = self._video.add_row("色彩空间", key_width=56)

        self._audio = GroupCard("音频流信息", compact=True, expand=True)
        self._row_acodec = self._audio.add_row("音频编码", key_width=56)
        self._row_channels = self._audio.add_row("声道数", key_width=56)
        self._row_sample = self._audio.add_row("采样率", key_width=56)
        self._row_abitrate = self._audio.add_row("音频码率", key_width=56)

        self._extra = GroupCard("辅助信息", compact=True, expand=True)
        self._row_subtitle = self._extra.add_row("字幕轨", key_width=56)
        self._row_chapter = self._extra.add_row("章节标记", key_width=56)
        self._row_hdr = self._extra.add_row("HDR 类型", key_width=56)
        self._row_alpha = self._extra.add_row("透明通道", key_width=56)

        grid.addWidget(self._basic, 0, 0)
        grid.addWidget(self._video, 0, 1)
        grid.addWidget(self._audio, 1, 0)
        grid.addWidget(self._extra, 1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._copy_btn = button("复制全部信息（Ctrl+C）", "primary", self)
        self._copy_btn.clicked.connect(self.copyRequested.emit)
        self._extract_btn = button("提取音频", "", self)
        self._extract_btn.clicked.connect(self.extractRequested.emit)
        actions.addWidget(self._copy_btn, 1)
        actions.addWidget(self._extract_btn)
        outer.addLayout(actions)

    # ------------------------------------------------------------ 外观
    def set_palette(self, palette) -> None:
        # 预留接口：预览窗口已移除，主题通过全局 QSS 自动套用，无需逐控件刷新
        pass

    def set_caps(self, caps) -> None:
        self._caps = caps

    # ------------------------------------------------------------ 数据
    def current_info(self) -> Optional[VideoInfo]:
        return self._info

    def set_info(self, info: Optional[VideoInfo]) -> None:
        self._info = info
        if info is None:
            self._tag.setText("拖入即显")
            self._clear_rows()
            self._copy_btn.setEnabled(False)
            self._extract_btn.setEnabled(False)
            return

        self._copy_btn.setEnabled(True)
        self._extract_btn.setEnabled(info.has_audio)
        self._tag.setText(info.resolution_label if info.width else "已识别")

        self._row_name.set_value(info.name)
        self._row_size.set_value(info.size_text)
        self._row_path.set_value(info.path)

        self._row_vcodec.set_value(
            f"{info.v_codec_display}（{info.v_codec}）" if info.v_codec else "—"
        )
        self._row_res.set_value(
            f"{info.resolution_text}　{info.resolution_label}" if info.width else "—"
        )
        self._row_fps.set_value(info.fps_text)
        self._row_vbitrate.set_value(info.v_bitrate_text)
        self._row_duration.set_value(info.duration_text)
        self._row_space.set_value(f"{info.color_space}（{info.pix_fmt}）" if info.pix_fmt else "—")

        self._row_acodec.set_value(info.a_codec_display if info.has_audio else "无音轨")
        self._row_channels.set_value(info.channels_text)
        self._row_sample.set_value(info.sample_rate_text)
        self._row_abitrate.set_value(info.a_bitrate_text)

        self._row_subtitle.set_value(f"{info.subtitle_tracks} 条" if info.subtitle_tracks else "无")
        self._row_chapter.set_value(f"{info.chapters} 个" if info.chapters else "无")
        self._row_hdr.set_value(info.hdr_type)
        self._row_alpha.set_value("支持" if info.has_alpha else "无")

    def _clear_rows(self) -> None:
        for card in (self._basic, self._video, self._audio, self._extra):
            for row in card.findChildren(type(self._row_name)):
                row.set_value("")
