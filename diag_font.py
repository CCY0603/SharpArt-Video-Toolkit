"""字体诊断：打印生效字体族名与关键控件字号/字重，便于核对 MiSans 三档映射。

运行：python diag_font.py  （offscreen 平台，仅打印参数，不改运行行为）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.theme import ensure_font, font_of
from ui.widgets import InfoRow, subheading, button


def show(label: str, f) -> None:
    style = f.styleStrategy()
    aa = "Antialias" if style & QFont.PreferAntialias else "default"
    print(
        f"  {label:<22} family={f.family()!r:<14} size={f.pointSize()} "
        f"weight={f.weight()} hint={f.hintingPreference()} AA={aa}"
    )


def main() -> None:
    app = QApplication(sys.argv)
    fam = ensure_font()
    print("[font] 生效族名:", fam)
    print("[font] 全局字体:")
    show("QApplication.font", app.font())

    print("[font] 三档字重入口:")
    show("Regular(400)", font_of(13, 400))
    show("Medium(500)", font_of(13, 500))
    show("Semibold(600)", font_of(13, 600))

    print("[font] InfoRow 紧凑模式(正文档):")
    row = InfoRow("文件名", "example_2160p_hevc.mov", 56)
    row.set_compact(True)
    show("key(muted)", row._key.font())
    show("value(mono)", row._value.font())
    row.set_compact(False)
    show("value(non-compact)", row._value.font())

    print("[font] 标题/按钮(Medium 档):")
    show("subheading", subheading("文件信息").font())
    show("button(默认)", button("复制全部信息").font())

    print("[font] 重点数据(Semibold 档):")
    show("estimate_label", font_of(13, 600))


if __name__ == "__main__":
    main()
