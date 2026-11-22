"""一次性脚本：把 MiSans woff2 转为 ttf 放到 fonts/ 目录。"""
import os
from fontTools.ttLib import TTFont

SRC = r"C:\B-下载\MiSans\MiSans\woff2"
DST = os.path.join(os.path.dirname(__file__), "fonts")
os.makedirs(DST, exist_ok=True)

FILES = {
    "MiSans-Normal.woff2": "MiSans-Regular.ttf",
    "MiSans-Medium.woff2": "MiSans-Medium.ttf",
    "MiSans-Semibold.woff2": "MiSans-Semibold.ttf",
}

for src_name, dst_name in FILES.items():
    src = os.path.join(SRC, src_name)
    dst = os.path.join(DST, dst_name)
    if not os.path.exists(src):
        print("MISSING", src)
        continue
    font = TTFont(src)
    font.flavor = None  # 去掉 woff2 封装
    font.save(dst)
    print("CONVERTED", src_name, "->", dst_name)
