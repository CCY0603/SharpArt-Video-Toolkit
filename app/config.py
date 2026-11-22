"""全局常量与默认参数。"""

from __future__ import annotations

# ---------------------------------------------------------------- 产品标识
APP_NAME = "SharpArt Video Toolkit"
APP_NAME_CN = "锐艺视频处理工具"
APP_ABBR = "SAVT"
APP_VERSION = "2.0"
ORG_NAME = "SharpArt"
APP_ID = "SharpArt.Video.Toolkit"
EXE_NAME = "SharpArtVideo"
SLOGAN = "锐利画质，精湛工艺 —— 让每一帧都值得留存"

# ---------------------------------------------------------------- 字体
FONT_FAMILY = "Microsoft YaHei UI"
FONT_FAMILY_CN = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei UI"
FONT_WEIGHTS = {
    "extralight": 200,
    "light": 300,
    "regular": 400,
    "semibold": 600,
    "bold": 700,
}

# ---------------------------------------------------------------- 编码默认值
DEFAULT_CRF = 20
CRF_MIN, CRF_MAX = 16, 32
MIN_VIDEO_BITRATE = 500_000  # 低于该值弹出建议提示（bps）
CONTAINER_OVERHEAD = 0.01  # 容器/字幕等额外开销预留比例
SIZE_TOLERANCE = 0.03       # 目标大小容差，超出则自动校准重编（±3%）
TWO_PASS_SPLIT = 0.45  # 2-Pass 时第一遍占总进度的比例
MAX_CONCURRENCY = 3
PROBE_MAX_THREADS = 4

DEFAULT_TARGET_MB = 50
DEFAULT_PERCENT = 60
DEFAULT_AUDIO_BITRATE = 192_000

TEMP_SUFFIX = ".savt_tmp"
NULL_DEVICE = "NUL"

# ---------------------------------------------------------------- 支持的文件
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".3gp",
    ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob", ".rmvb",
    ".rm", ".asf", ".f4v", ".ogv", ".divx", ".mxf", ".prores",
}

FORMAT_FILTER = (
    "视频文件 (*.mp4 *.mov *.mkv *.avi *.wmv *.flv *.webm *.3gp *.m4v "
    "*.mpg *.mpeg *.ts *.m2ts *.vob *.rmvb *.asf *.f4v *.ogv *.mxf);;"
    "所有文件 (*.*)"
)

# ---------------------------------------------------------------- 分辨率标签
RES_LABELS = [
    ("8K", lambda h: h >= 4320),
    ("4K", lambda h: 2160 <= h < 4320),
    ("1440p", lambda h: 1440 <= h < 2160),
    ("1080p", lambda h: 1080 <= h < 1440),
    ("720p", lambda h: 720 <= h < 1080),
    ("480p", lambda h: 480 <= h < 720),
]
