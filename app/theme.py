"""主题：字体装配（微软雅黑 UI）、Mica 窗口效果、深浅色 QSS。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QBuffer, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPalette, QPen, QRegion
from PySide6.QtWidgets import QApplication, QComboBox, QStyleFactory

from app.config import FONT_FALLBACK, FONT_FAMILY, FONT_FAMILY_CN

# 程序内自带字体目录（历史 MiSans ttf；当前 UI 字体统一使用微软雅黑 UI，见 config.FONT_FAMILY）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.normpath(os.path.join(_THIS_DIR, os.pardir, "fonts"))
# MiSans 三档字重文件（Regular=正文 / Medium=按钮标题 / Semibold=重点数据）
_FONT_FILES = (
    "MiSans-Regular.ttf",
    "MiSans-Medium.ttf",
    "MiSans-Semibold.ttf",
)


# ------------------------------------------------------------------ 字体
def _normalize(name: str) -> str:
    return name.replace(" ", "").replace("-", "").lower()


def install_fonts() -> str:
    """确保 UI 字体（微软雅黑 UI）可用，返回实际使用的字体家族名。

    优先使用系统已注册的微软雅黑 UI；未找到时回退到 FONT_FALLBACK。
    """
    # 1) 程序内自带字体优先（三档字重 ttf）
    for name in _FONT_FILES:
        path = os.path.join(_FONT_DIR, name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)

    # 2) 已注册的 MiSans 直接返回
    families = QFontDatabase.families()
    for fam in families:
        if _normalize(fam) in (_normalize(FONT_FAMILY), _normalize(FONT_FAMILY_CN)):
            print(f"[font] MiSans 已就绪：{fam}")
            return fam

    # 3) 系统字体目录兜底（用户可能已安装 MiSans ttf）
    dirs = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    dirs.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    for directory in dirs:
        for name in ("MiSans-Regular.ttf", "MiSans-Medium.ttf", "MiSans-Semibold.ttf"):
            path = os.path.join(directory, name)
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)

    families = QFontDatabase.families()
    for fam in families:
        if _normalize(fam) in (_normalize(FONT_FAMILY), _normalize(FONT_FAMILY_CN)):
            print(f"[font] MiSans 已就绪：{fam}")
            return fam

    # 4) 回退到系统字体
    print(f"[font] 未找到 MiSans，回退到：{FONT_FALLBACK}")
    return FONT_FALLBACK


# 注意：QFontDatabase 必须在 QApplication 创建之后才能访问，
# 因此这里只放占位值，真正解析推迟到 ensure_font()（由应用启动流程调用）。
FONT = FONT_FAMILY
_FONT_READY = False

# 当前生效的调色板：自绘控件（Radio / Check 等）在未显式设置时读取此值，
# 保证新创建的控件（如对话框）也能自动跟随深浅色主题。
_CURRENT_PALETTE = None  # 惰性：模块加载时 LIGHT 尚未定义


def set_current_palette(palette) -> None:
    global _CURRENT_PALETTE
    _CURRENT_PALETTE = palette


def current_palette():
    return _CURRENT_PALETTE or LIGHT


def ensure_font() -> str:
    """确保 UI 字体（微软雅黑 UI）已注册，返回实际使用的家族名。"""
    global FONT, _FONT_READY
    if not _FONT_READY:
        FONT = install_fonts()
        _FONT_READY = True
    return FONT


def font_of(size: int = 13, weight: int = 400) -> QFont:
    """按字重令牌构造字体。

    字重约定：正文 400(Regular) / 按钮标题 500(Medium) / 重点数据 600(Semibold)。
    渲染策略：垂直 hinting + 质量优先，避免 full hinting 把低 DPI 小字压成一团、发虚。
    """
    f = QFont(ensure_font(), size)
    f.setWeight(QFont.Weight(weight))
    f.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
    f.setHintingPreference(QFont.PreferVerticalHinting)
    return f


# ------------------------------------------------------------------ 调色板
@dataclass
class Palette:
    name: str
    window_bg: str
    window_bg_mica: str
    card: str
    card_alt: str
    card_hover: str
    text: str
    text_secondary: str
    text_disabled: str
    border: str
    border_strong: str
    hover: str
    pressed: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    on_accent: str
    success: str
    success_soft: str
    warning: str
    danger: str
    track: str
    selection: str
    selection_strong: str
    zebra: str
    shadow: str
    gradient_top: str = field(default="")
    gradient_bottom: str = field(default="")
    # 不透明版本：用于 QPalette（半透明色作为 Window/Base 角色会导致渲染异常）
    window_solid: str = field(default="#F3F5F9")
    card_solid: str = field(default="#FFFFFF")


LIGHT = Palette(
    name="light",
    window_bg="rgba(243, 245, 249, 0.96)",
    window_bg_mica="rgba(243, 245, 249, 0.28)",
    card="rgba(255, 255, 255, 0.86)",
    card_alt="rgba(255, 255, 255, 0.62)",
    card_hover="rgba(255, 255, 255, 0.95)",
    text="#1A1A1A",
    text_secondary="#616161",
    text_disabled="#9E9E9E",
    border="rgba(15, 23, 42, 0.09)",
    border_strong="rgba(15, 23, 42, 0.18)",
    hover="rgba(15, 23, 42, 0.045)",
    pressed="rgba(15, 23, 42, 0.085)",
    accent="#0078D4",
    accent_hover="#1A9BF5",
    accent_pressed="#0067C0",
    accent_soft="rgba(0, 120, 212, 0.12)",
    on_accent="#FFFFFF",
    success="#0F7B0F",
    success_soft="rgba(15, 123, 15, 0.12)",
    warning="#9D5D00",
    danger="#C42B1C",
    track="rgba(15, 23, 42, 0.10)",
    selection="rgba(0, 120, 212, 0.16)",
    selection_strong="rgba(0, 120, 212, 0.88)",
    zebra="rgba(15, 23, 42, 0.035)",
    shadow="rgba(15, 23, 42, 0.14)",
    gradient_top="#F7F9FC",
    gradient_bottom="#E8EDF5",
    window_solid="#F3F5F9",
    card_solid="#FFFFFF",
)

DARK = Palette(
    name="dark",
    window_bg="rgba(28, 28, 30, 0.96)",
    window_bg_mica="rgba(28, 28, 30, 0.42)",
    card="rgba(43, 43, 46, 0.82)",
    card_alt="rgba(52, 52, 56, 0.60)",
    card_hover="rgba(58, 58, 62, 0.86)",
    text="#EAEAEA",
    text_secondary="#A8A8AE",
    text_disabled="#6E6E74",
    border="rgba(255, 255, 255, 0.10)",
    border_strong="rgba(255, 255, 255, 0.20)",
    hover="rgba(255, 255, 255, 0.06)",
    pressed="rgba(255, 255, 255, 0.11)",
    accent="#4CC2FF",
    accent_hover="#6ECEFF",
    accent_pressed="#2FA5E8",
    accent_soft="rgba(76, 194, 255, 0.16)",
    on_accent="#0A1A24",
    success="#5FCA5F",
    success_soft="rgba(95, 202, 95, 0.16)",
    warning="#FFC83D",
    danger="#FF6B5B",
    track="rgba(255, 255, 255, 0.12)",
    selection="rgba(76, 194, 255, 0.22)",
    selection_strong="rgba(76, 194, 255, 0.40)",
    zebra="rgba(255, 255, 255, 0.04)",
    shadow="rgba(0, 0, 0, 0.5)",
    gradient_top="#252528",
    gradient_bottom="#1B1B1E",
    window_solid="#1C1C1E",
    card_solid="#2B2B2E",
)


# ------------------------------------------------------------------ QSS
def build_stylesheet(p: Palette, mica: bool = False) -> str:
    family = ensure_font()
    arrow = p.text_secondary
    radio_dot = radio_dot_url(p.accent)
    check_mark = check_mark_url(p.on_accent)
    return f"""
* {{
    font-family: "{family}";
    font-size: 13px;
    font-weight: 400;
    outline: none;
}}

QWidget#root, QWidget#centralRoot {{
    background: transparent;
    color: {p.text};
}}

QFrame#card {{
    background: {p.card_solid};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QFrame#card[hover="true"]:hover {{
    background: {p.card_solid};
    border: 1px solid {p.border_strong};
}}
QFrame#panel {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QFrame#divider {{
    background: {p.border};
}}

QLabel {{
    color: {p.text};
    background: transparent;
}}
QLabel#heading {{
    font-size: 20px;
    font-weight: 500;
    letter-spacing: 0.4px;
}}
QLabel#subheading {{
    font-size: 14px;
    font-weight: 500;
}}
QLabel#caption {{
    color: {p.text_secondary};
    font-size: 12px;
    font-weight: 400;
}}
/* #8：表单字段名用 Medium（标题档）更醒目（13px / 500） */
QLabel#fieldLabel {{
    color: {p.text};
    font-size: 13px;
    font-weight: 500;
    background: transparent;
}}
QLabel#fieldHint {{
    color: {p.text_secondary};
    font-size: 11px;
    font-weight: 400;
    background: transparent;
}}
/* 启动提示（ffmpeg 缺失等非阻塞告警），Medium 标题档 */
QLabel#statusWarning {{
    color: {p.danger};
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}}
QLabel#muted {{
    color: {p.text_secondary};
}}
QLabel#accent {{
    color: {p.accent};
    font-weight: 600;
}}
QLabel#mono {{
    font-weight: 400;
    letter-spacing: 0.2px;
}}
QLabel#statValue {{
    font-size: 16px;
    font-weight: 600;
    color: {p.text};
}}
QLabel#heroValue {{
    font-size: 24px;
    font-weight: 400;
    color: {p.accent};
}}
QLabel#badge {{
    background: {p.accent_soft};
    color: {p.accent};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}}
QLabel#badgeNeutral {{
    background: {p.track};
    color: {p.text_secondary};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 400;
}}
/* 预估栏「节省 X%」专用绿色徽章 */
QLabel#badgeSuccess {{
    background: {p.success_soft};
    color: {p.success};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton {{
    background: {p.card_alt};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    outline: none;
}}
QPushButton:hover {{ background: {p.hover}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background: {p.pressed}; }}
QPushButton:disabled {{ color: {p.text_disabled}; background: {p.track}; border-color: transparent; }}
QPushButton[variant="primary"] {{
    background: {p.accent};
    color: {p.on_accent};
    border: 1px solid {p.accent};
    font-weight: 500;
}}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {p.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{ background: {p.track}; color: {p.text_disabled}; border-color: transparent; }}
QPushButton[variant="danger"] {{
    color: {p.text_secondary};
    border-color: {p.border};
    font-weight: 500;
}}
QPushButton[variant="danger"]:hover {{ background: {p.danger}; color: {p.on_accent}; border-color: {p.danger}; }}
QPushButton[variant="danger"]:disabled {{ color: {p.text_disabled}; background: {p.track}; border-color: transparent; }}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid {p.border};
    border-radius: 6px;
    color: {p.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{ background: {p.hover}; color: {p.text}; }}
QPushButton[variant="tool"] {{
    background: transparent;
    border: 1px solid transparent;
    padding: 5px 10px;
    font-weight: 500;
}}
QPushButton[variant="tool"]:hover {{ background: {p.hover}; }}
QPushButton[variant="tool"]:checked {{ background: {p.accent_soft}; color: {p.accent}; font-weight: 500; }}
QPushButton#titleButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0;
}}
QPushButton#titleButton:hover {{ background: {p.hover}; }}
QPushButton#titleButton:pressed {{ background: {p.pressed}; }}
QPushButton#titleButton[role="close"]:hover {{ background: #C42B1C; color: #FFFFFF; }}

/* -------------------------------------------------- 胶囊分段控制器（#6） */
QWidget#segmented {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QPushButton#segBtn {{
    background: transparent;
    color: {p.text_secondary};
    border: none;
    border-radius: 3px;
    margin: 0 1px;
    padding: 5px 14px;
    font-weight: 500;
    outline: none;
}}
QPushButton#segBtn:hover {{ background: {p.hover}; color: {p.text}; }}
QPushButton#segBtn:checked {{
    color: {p.on_accent};
    font-weight: 500;
}}
QPushButton#segBtn:checked:hover {{ color: {p.on_accent}; }}
QPushButton#segBtn:focus {{ outline: none; border: none; }}

/* #12：标题栏主文本（纯黑/主文本色）与淡化版本号 */
QLabel#titleMain {{
    font-size: 13px;
    font-weight: 400;
    color: {p.text};
    background: transparent;
}}
QLabel#titleVersion {{
    font-size: 11px;
    font-weight: 400;
    color: {p.text_secondary};
    background: transparent;
    border: none;
    padding: 0;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.card_alt};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p.border_strong};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    color: {p.text_disabled};
    background: {p.track};
}}
/* #3：消除下拉框「圆弧框上叠加直角框」——内部 frame 与下拉按钮都跟随外框圆角 */
QComboBox::frame {{
    border: none;
    background: transparent;
    border-radius: 6px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
    background: transparent;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QComboBox::drop-down:hover {{ background: {p.hover}; }}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {arrow};
    margin-right: 6px;
}}
/* 下拉视图：独立的圆角卡片；qcombobox-popup:0 后它会直接以 QSS 渲染 */
QComboBox QAbstractItemView {{
    background: {p.card_solid};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
/* 原生弹出容器（QFrame，Qt 内置 objectName，从构造起就匹配，无 polish 时机问题）：
   透明无边框，只让内层 view 的 8px 圆角卡片可见；配合 RoundedCombo 构造时的
   WA_TranslucentBackground 让 Windows 原生窗口透出圆角 */
QFrame#qt_combobox_popup {{
    background: transparent;
    border: none;
    margin: 0;
    padding: 0;
}}
/* 下拉内滚动条：缩进并贴圆角内侧，避免溢出方形边角 */
QComboBox QAbstractItemView QScrollBar:vertical {{
    width: 8px;
    margin: 6px 4px 6px 2px;
    background: transparent;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0; height: 0; border: none; background: transparent;
}}

QCheckBox, QRadioButton {{ spacing: 8px; color: {p.text}; background: transparent; outline: none; }}
QCheckBox:focus, QRadioButton:focus {{ outline: none; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {p.border_strong};
    background: {p.card_solid};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    image: url("{check_mark}");
}}
QCheckBox::indicator:disabled {{ background: {p.track}; border-color: {p.border}; }}
QRadioButton::indicator {{
    width: 18px; height: 18px; border-radius: 9px;
    border: 1px solid {p.border_strong};
    background: {p.card_solid};
}}
QRadioButton::indicator:checked {{
    border: 1px solid {p.accent};
    /* Qt6 Fusion 不绘制 ::indicator:checked 的中心圆点，SVG data URL 又依赖 SVG 插件，
       改用运行时生成的 PNG data URL（Qt 内置 PNG 解码器，颜色随主题） */
    background-color: {p.card_solid};
    image: url("{radio_dot}");
}}

QTableWidget, QTableView {{
    background: transparent;
    alternate-background-color: {p.track};
    gridline-color: transparent;
    border: none;
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QTableWidget::item:selected, QTableView::item:selected {{ background: {p.selection}; color: {p.text}; }}
QHeaderView::section {{
    background: transparent;
    color: {p.text_secondary};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 6px 8px;
    font-weight: 500;
    font-size: 12px;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

QProgressBar {{
    background: {p.track};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QProgressBar#rowProgress {{ height: 4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {p.border_strong}; border-radius: 5px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {p.accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    background: {p.card_solid};
    color: {p.text};
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}}
QMenu {{
    background: {p.card_solid};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p.accent_soft}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}

/* #4：底部操作栏与状态栏合并为连续区块，消除分层割裂感 */
QWidget#bottomBar {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: transparent; color: {p.text_secondary}; }}
QTextEdit, QPlainTextEdit {{
    background: {p.card_alt};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px;
}}

/* -------------------------------------------------- 对话框与分组容器 */
QDialog, QMessageBox, QInputDialog {{
    background: {p.window_solid};
    color: {p.text};
}}
QDialog QLabel, QMessageBox QLabel {{ background: transparent; }}
QGroupBox {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    margin-top: 16px;
    padding: 14px 12px 10px 12px;
    font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {p.text};
    font-weight: 500;
}}
QListWidget, QTreeWidget, QListView, QTreeView {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 4px;
    color: {p.text};
}}
QListWidget::item, QTreeWidget::item {{
    padding: 6px 8px;
    border-radius: 6px;
    color: {p.text};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {p.selection};
    color: {p.text};
}}
QListWidget::item:hover {{ background: {p.hover}; }}

/* -------------------------------------------------- 滚动区域与视口 */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QAbstractScrollArea {{ background: transparent; border: none; }}
QAbstractScrollArea#qt_scrollarea_viewport {{ background: transparent; }}
QScrollArea QScrollBar, QAbstractScrollArea QScrollBar {{
    background: transparent;
}}
/* #3：输入类控件的内部 frame 统一去边框，避免直角与圆角重叠 */
QLineEdit::frame, QTextEdit::frame, QPlainTextEdit::frame,
QSpinBox::frame, QDoubleSpinBox::frame, QComboBox::frame {{
    border: none;
    background: transparent;
}}
QFrame {{ border: none; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {p.border};
}}

/* -------------------------------------------------- 滑块 */
QSlider::groove:horizontal {{
    height: 4px;
    background: {p.track};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {p.accent};
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    background: {p.track};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {p.accent};
    border: 2px solid {p.card_solid};
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hover}; }}
QSlider::groove:vertical {{ width: 4px; background: {p.track}; border-radius: 2px; }}
QSlider::handle:vertical {{
    height: 14px;
    margin: 0 -5px;
    border-radius: 7px;
    background: {p.accent};
    border: 2px solid {p.card_solid};
}}

/* -------------------------------------------------- 其它通用控件 */
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    color: {p.text};
}}
QToolButton:hover {{ background: {p.hover}; }}
QToolButton[popupMode="1"] {{ padding-right: 14px; }}
QTabWidget::pane {{
    background: {p.card_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.text_secondary};
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 400;
}}
QTabBar::tab:selected {{ color: {p.text}; background: {p.card_alt}; font-weight: 500; }}
QTabBar::tab:hover {{ background: {p.hover}; }}
QMenuBar {{ background: transparent; color: {p.text}; }}
QMenuBar::item:selected {{ background: {p.hover}; border-radius: 5px; }}
QToolBar {{ background: transparent; border: none; spacing: 4px; }}
QDockWidget {{ background: {p.window_solid}; color: {p.text}; }}
QDockWidget::title {{
    background: {p.card_alt};
    border-radius: 8px 8px 0 0;
    padding: 6px 10px;
}}

/* -------------------------------------------------- 视频预览容器（#2） */
QFrame#videoFrame {{
    background: {p.card_solid};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QLabel#videoPoster {{
    background: {p.card_solid};
    border: 1px solid {p.border};
    border-radius: 8px;
    color: {p.text_secondary};
    padding: 8px;
}}
/* 显示首帧画面时改用黑底，避免浅色边框包裹画面 */
QLabel#videoPoster[state="frame"] {{
    background: #000000;
    color: #FFFFFF;
    border: 1px solid {p.border};
}}
"""


def build_qpalette(p: Palette) -> QPalette:
    """构造与主题一致的 QPalette：让未被 QSS 覆盖的控件也跟随深浅色。"""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(p.window_solid))
    palette.setColor(QPalette.WindowText, QColor(p.text))
    palette.setColor(QPalette.Base, QColor(p.card_solid))
    palette.setColor(QPalette.AlternateBase, QColor(p.window_solid))
    palette.setColor(QPalette.Text, QColor(p.text))
    palette.setColor(QPalette.Button, QColor(p.card_solid))
    palette.setColor(QPalette.ButtonText, QColor(p.text))
    palette.setColor(QPalette.Highlight, QColor(p.accent))
    palette.setColor(QPalette.HighlightedText, QColor(p.on_accent))
    palette.setColor(QPalette.ToolTipBase, QColor(p.card_solid))
    palette.setColor(QPalette.ToolTipText, QColor(p.text))
    palette.setColor(QPalette.Link, QColor(p.accent))
    palette.setColor(QPalette.PlaceholderText, QColor(p.text_secondary))
    palette.setColor(QPalette.BrightText, QColor(p.danger))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(p.text_disabled))
    return palette


# ------------------------------------------------------------------ 系统效果
def _png_data_url(size: int, painter_fn) -> str:
    """把 QPainter 绘制结果转成 data URL（Qt 内置 PNG 解码器，无需 SVG 插件）。"""
    import base64

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter_fn(painter, size)
    painter.end()

    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    payload = base64.b64encode(bytes(buffer.data())).decode("ascii")
    buffer.close()
    return f"data:image/png;base64,{payload}"


def radio_dot_url(color: str) -> str:
    """单选按钮选中态的中心实心圆点。"""

    def draw(painter: QPainter, size: int) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        inset = size * 0.22
        painter.drawEllipse(
            int(inset), int(inset), int(size - 2 * inset), int(size - 2 * inset)
        )

    return _png_data_url(16, draw)


def check_mark_url(color: str) -> str:
    """复选按钮勾选态的白色勾号。"""

    def draw(painter: QPainter, size: int) -> None:
        pen = QPen(QColor(color))
        pen.setWidth(max(2, int(size * 0.16)))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(int(size * 0.22), int(size * 0.52),
                         int(size * 0.42), int(size * 0.72))
        painter.drawLine(int(size * 0.42), int(size * 0.72),
                         int(size * 0.78), int(size * 0.30))

    return _png_data_url(16, draw)


def solid_color(text: str) -> QColor:
    """把 CSS 颜色（含 rgba/rgb 函数）解析为 QColor。

    PySide6 的 QColor 构造函数不支持 rgba(...) 函数语法（默认返回黑色），但 QSS 支持。
    自绘代码（paintEvent、QColor 直接构造）必须先经过此函数解析，否则在浅色主题下会渲染成黑色块。
    """
    text = text.strip()
    if text.startswith(("rgba(", "rgb(")):
        try:
            inside = text[text.index("(") + 1: text.index(")")]
            nums = [float(x.strip()) for x in inside.split(",")]
            r = max(0, min(255, int(nums[0])))
            g = max(0, min(255, int(nums[1])))
            b = max(0, min(255, int(nums[2])))
            a = max(0, min(255, int(nums[3] * 255) if len(nums) > 3 else 255))
            return QColor(r, g, b, a)
        except Exception:
            return QColor()
    return QColor(text)


def system_prefers_dark() -> bool:
    """读取 Windows 个人化设置判断系统主题。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return int(value) == 0
    except Exception:
        return False


def apply_window_effect(window) -> None:
    """为无边框窗口请求 Windows 11 系统圆角偏好。

    不再启用 Mica：Mica 会把桌面壁纸色调透进窗口，与软件自身深浅色主题产生混色，
    统一改为自绘圆角渐变来模拟云母质感，保证两个主题下配色完全一致。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window.winId())
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        corner = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
    except Exception:
        pass


def apply_dark_titlebar(window, dark: bool) -> None:
    """无边框窗口下同步标题栏深浅色，避免与系统主题冲突。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(int(window.winId())),
            ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


class RoundedCombo(QComboBox):
    """QComboBox 子类：下拉弹出框圆角方案（三层保险）。

    - 构造时：弹出容器设 `Qt.Popup | FramelessWindowHint | NoDropShadowWindowHint`
      + `WA_TranslucentBackground`，并在 polish 前显式 `objectName="qt_combobox_popup"`
      （命中样式表的容器透明规则）
    - showPopup：弹窗尺寸算好后施加 8px 圆角蒙版（几何裁剪保底——Qt6 的
      QComboBoxPrivateContainer 自绘方形底会绕过 QSS，蒙版直接把方角裁掉）
    - 不改 QPalette（之前“样式崩溃”是 Base 调色板透明所致，已废弃）
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 弹出容器在 QComboBox 构造时已存在；在其原生窗口创建前设置标志/属性，
        # 让 Windows 原生 Popup 窗口透出圆角（仅此一次，无运行时 hack）。
        popup = self.view().window()
        if popup is not None:
            # 显式设置 Qt 内置 objectName，确保样式表 `QFrame#qt_combobox_popup`
            # 在 polish 阶段即可匹配（部分平台下内置 objectName 延迟赋值）。
            popup.setObjectName("qt_combobox_popup")
            popup.setWindowFlags(
                Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
            )
            popup.setAttribute(Qt.WA_TranslucentBackground, True)

    def showPopup(self) -> None:  # noqa: N802 (Qt 命名)
        # 先由 Qt 完成弹出与尺寸计算，再对弹出窗口施加圆角蒙版。
        # Qt6 的 QComboBoxPrivateContainer 会用 PE_PanelItemView 自绘一层方形底，
        # 绕过 QSS；几何蒙版直接把方形边缘从窗口像素上裁掉，保底保证圆角。
        super().showPopup()
        popup = self.view().window()
        if popup is not None:
            lay = popup.layout()
            if lay is not None:
                lay.setContentsMargins(0, 0, 0, 0)
            r = popup.rect()
            path = QPainterPath()
            path.addRoundedRect(0, 0, r.width(), r.height(), 8, 8)
            popup.setMask(QRegion(path.toFillPolygon().toPolygon()))


class ThemeManager:
    """主题状态管理：系统跟随 / 浅色 / 深色。"""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._mica = False
        self.palette = LIGHT

    @property
    def mica(self) -> bool:
        return self._mica

    def is_dark(self) -> bool:
        mode = self._settings.theme
        if mode == "dark":
            return True
        if mode == "light":
            return False
        return system_prefers_dark()

    def set_mode(self, mode: str) -> None:
        self._settings.theme = mode

    def apply(self, app: QApplication, window=None) -> None:
        dark = self.is_dark()
        self.palette = DARK if dark else LIGHT
        set_current_palette(self.palette)
        if window is not None:
            # 禁用 Mica，避免桌面壁纸透出与软件主题冲突；统一自绘圆角渐变背景
            apply_window_effect(window)
            apply_dark_titlebar(window, dark)
            self._mica = False
            window.setAttribute(Qt.WA_TranslucentBackground, False)
        # Fusion 风格保证 QSS 100% 生效，避免 windows11 原生样式混入系统浅色
        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            app.setStyle(fusion)
        # 先设调色板再设样式表：两者结合可覆盖全部控件，避免深浅色混杂
        app.setPalette(build_qpalette(self.palette))
        app.setStyleSheet(build_stylesheet(self.palette, self._mica))
        app.setFont(font_of(13, 400))

    def refresh(self, app: QApplication, window=None) -> None:
        self.apply(app, window)
        if window is not None:
            window.update()
            window.repaint()
