# 锐艺视频处理工具 · SharpArt Video Toolkit

> 锐利画质，精湛工艺 —— 让每一帧都值得留存

依据《锐艺视频处理工具 产品功能规格说明书 v1.0》实现的 Windows 桌面视频处理软件。
界面采用 Windows 11 风格三明治布局，字体统一使用**更纱黑体 SC**，
底层调用本机 FFmpeg 完成压缩、转换、批处理与信息解析。

**主题一致性**：配色由 QSS + Fusion 风格 + QPalette 三层共同保证，深色主题下不会出现浅
色板块，浅色主题下也不会出现深色板块；窗口采用自绘圆角柔和渐变模拟云母质感，并在
Windows 11 下通过 `DWMWA_WINDOW_CORNER_PREFERENCE` 请求系统级圆角。未启用 DWM Mica，
以避免桌面壁纸色调透出后与软件主题产生混色。

- 中文名：锐艺视频处理工具
- 英文名：SharpArt Video Toolkit（缩写 SAVT）
- 可执行文件：`SharpArtVideo.exe`
- 命名空间：`SharpArt.Video.Toolkit`

---

## 一、功能一览

### 智能文件信息识别（拖入即显）
把视频拖入窗口任意位置，右侧信息面板即刻刷新：

| 分类 | 展示字段 |
| --- | --- |
| 基础元数据 | 文件名、文件大小、文件路径 |
| 视频流 | 编码格式、分辨率、帧率、码率、色深（8/10bit）、色彩空间（YUV 4:2:0 / 4:2:2 / 4:4:4） |
| 音频流 | 音频编码、声道数（立体声 / 5.1 / 7.1）、采样率、音频码率 |
| 辅助信息 | 视频时长、字幕轨、章节标记、HDR 类型（HDR10 / Dolby Vision / HLG）、透明通道 |

- 内置视频预览（不可播放时自动降级为首帧抽帧）
- `复制全部信息（Ctrl+C）`：一键复制完整参数文本
- `提取音频`：导出 MP3 / AAC / FLAC / WAV

### 智能视频压缩
- **CPU 典藏模式**：x264 / x265 软件编码，CRF 恒定质量（默认 20，范围 16–32），画质优先
- **GPU 极速模式**：NVIDIA NVENC / AMD AMF / Intel QuickSync 硬件加速
  - 启动时后台实测硬件编码器可用性，不可用时自动回退 CPU 并在界面提示
  - 处理中实时显示 GPU 占用率与显存占用（NVIDIA 精确采样，其它平台自动隐藏）

### 精准控盘压缩
- **绝对值模式**：直接指定目标大小（MB / GB）
- **百分比模式**：压到原体积的 N%
- **CRF 模式**：按恒定画质输出
- 算法：目标总码率 = 目标大小 ÷ 时长 → 目标视频码率 = 目标总码率 − 音频码率 − 容器开销
- 自动启用两遍编码（2-Pass）；完成后若与目标偏差超过 ±3%，自动按实测比例校准重编一次
- 目标视频码率低于 500 kbps 时，状态栏给出建议值提醒
- 实时预估：`N 个文件总输出 ≈ X MB（A ~ B）　原始 Y GB　节省 Z%`

### 万能格式转换
- 通用格式：MP4 / MOV / MKV / AVI / WMV / FLV / 3GP / WebM（不支持的封装格式自动置灰）
- 专业格式：ProRes（Proxy / LT / Standard / HQ）、DNxHR（LB / SQ / HQ / HQX）、MOV + Alpha 透明通道
- 设备预设：iPhone 16 Pro、Samsung S30、Xbox Series X、抖音 / 快手竖屏
- 10bit 与 HDR（HDR10 / HLG）元信息保留

### 批处理
- 多文件拖入自动切换为列表视图：序号、文件名、原始大小、时长、分辨率、目标压缩大小、处理状态
- 状态：⏳ 等待处理 / 🔄 处理中（带百分比与遍数）/ ✅ 已完成 / ❌ 失败（悬停显示原因）
- 顶部摘要：总文件数、总大小、总时长、4K 数量、1080p 数量、MOV 数量、MP4 数量
- **统一设置模式**：参数改动同步到所有文件
- **独立设置模式**：只调整当前选中行，每行可单独设定目标与格式
- 批量操作：全部开始、全部取消、清空已完成、按格式筛选、按分辨率筛选
- **并发控制**：默认顺序处理；可切换并发 2 / 3 个（开启时提示可能影响系统流畅度）
- **失败重试**：失败自动跳过继续；结束弹出汇总报告，可勾选失败项一键重试
- 完成后可自动关机（60 秒倒计时，可随时取消）、导出任务清单（CSV）、导出处理报告（TXT）

---

## 二、环境要求

| 依赖 | 说明 |
| --- | --- |
| Windows 11 | Mica 云母效果需 Windows 11 22H2 及以上；低版本自动降级为渐变背景 |
| Python 3.13 | 运行源码所需（打包后不再需要） |
| PySide6 ≥ 6.6 | `pip install -r requirements.txt` |
| FFmpeg / FFprobe | 已实测 9.0.1；须包含 libx264、libx265，建议含 prores_ks、dnxhd、qtrle、libmp3lame |

FFmpeg 未安装或缺失编码器时，软件会给出明确提示，并自动置灰不可用的编码器与封装格式，
不会生成必然失败的命令。

---

## 三、运行方式

```powershell
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

首次启动若提示找不到 FFmpeg，请在 `⚙ 设置` 中指定 `ffmpeg.exe` 与 `ffprobe.exe` 的路径，
或把其所在目录加入系统 PATH。设置保存在用户配置（INI）中，下次启动自动沿用。

---

## 四、目录结构

```
main.py                 程序入口
app/                    应用层
  config.py             全局常量（产品标识、默认 CRF、500kbps 阈值、容差等）
  settings.py           偏好持久化（QSettings / INI）
  theme.py              更纱黑体 SC 字体装配、Mica 窗口效果、深浅色 QSS
  app.py                应用初始化与启动
core/                   核心层（不依赖 UI）
  models.py             VideoInfo / EncodeParams / TaskItem / TaskStatus
  capabilities.py       ffmpeg / ffprobe 定位与能力探测（含硬件编码器实测）
  probe.py              ffprobe 元数据解析（含 HDR 判定）
  profiles.py           编码器 / 容器 / 专业格式 / 设备预设表
  planner.py            码率计算、2-Pass 决策、命令构建、体积预估
  runner.py             子进程执行器：进度解析、取消、错误摘要
  queue.py              任务队列：顺序 / 并发调度、跳过失败、体积校准、重试
  audio.py              音轨提取
  report.py             汇总报告与任务清单导出
  gpu.py                GPU 占用率与显存采样
  power.py              自动关机（可取消）
  utils.py              格式化与路径工具
ui/                     表现层
  main_window.py        三明治布局主窗口与业务流程编排
  title_bar             自定义无边框标题栏（窗口内）
  toolbar.py            顶部工具栏与筛选器
  drop_area.py          拖放区
  file_list.py          批处理表格、状态委托、摘要统计条
  info_panel.py         右侧信息面板
  preview.py            视频预览（含降级抽帧）
  settings_panel.py     压缩设置区与实时预估
  dialogs.py            设置 / 报告 / 音频提取 / 关机倒计时 / 关于
  widgets.py            卡片、胶囊标签、键值行等通用控件
```

---

## 五、打包为 SharpArtVideo.exe

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name SharpArtVideo --clean main.py
```

产物位于 `dist\SharpArtVideo.exe`。若需图标，追加 `--icon app.ico`。
打包环境需与运行环境一致（Windows）；分发时目标机器仍需 FFmpeg（可放在程序目录并在设置中指定路径）。

---

## 六、优化记录（BUG及优化V1）

依据《BUG及优化V1.docx》的 15 项问题完成修复（按工作量从小到大分批实施）：

| 项 | 问题 | 修复 |
| --- | --- | --- |
| 启动 | 启动时弹窗，需点 OK 才能进入 | 改为非阻塞：状态栏醒目提示 + 「配置 ffmpeg」入口；并增强 ffmpeg 多路径探测（程序目录 / bin / AppData / Program Files / PATH），从源头避免探测失败 |
| 1 | 选「目标大小」后无法同时选中 CPU/GPU | 5 个单选按钮原同挂 SettingsPanel 下，Qt 默认同父自动互斥；改用两个 `QButtonGroup`（编码器组 / 尺寸模式组）分别托管 |
| 2 | 预览框圆弧边角叠加直角底色、空状态为黑色 | 新增 `RoundVideoWidget`（遮罩圆角）+ 主题色容器；空状态改浅色底 + 灰边框 + 提示文字 |
| 3 | 下拉框圆弧上叠加直角框 | QSS 补齐 `QComboBox::frame`、`::drop-down` 圆角，并统一输入类控件内部 frame 去边框 |
| 4 | 软件下方显示分层 | 底部操作栏与状态栏合并为连续区块（`#bottomBar`），设置面板阴影减弱 |
| 5 | 预览左右黑边 | 新增 `AspectFrame`（`hasHeightForWidth`），按视频真实宽高比分配高度，画面填满无黑边 |
| 7 | 文件信息需滚动查看 | 信息面板去滚动区，四组信息改 2×2 网格紧凑布局，一屏完整展示（超长值省略号 + tooltip） |
| 8 | 输出格式/音频/输出路径与控件距离远、文字太细 | 三组改紧凑横向排列，标签与控件间距 6px，字段名改 13px/600 |
| 9 | CRF 缺少数值说明 | 滑块后增加动态说明（16 接近无损 → 28 低画质） |
| 10 | 找不到格式转换入口 | 新增「仅转格式（不重编码）」模式（流复制，无损极速），输出格式下拉补充说明 |
| 11 | 批处理缺少移除功能 | 底部操作栏新增「移除选中」，仅从列表移除，源文件不做任何改动 |
| 12 | 顶部信息重复 | 标题栏仅显示产品名 + 英文名，版本号改为更小更淡、无底色 |
| 13 | 版本信息冗余 | 删除工具栏独立版本按钮，「关于」入口迁入设置对话框 |
| 14 | 窗口控制按钮间距大、hover 底色不全 | 按钮改 46×32、间距 2px，hover 底色完整填充按钮区域 |
| 15 | 只有 GPU 硬件信息 | 新增 CPU 型号与占用率采样（psutil → 性能计数器 → wmic 回退链），状态栏同时显示 CPU 与 GPU |

附带修复：

- 自绘单选/复选按钮的文字改用手动 `QPainter.drawText` 绘制。原先使用的 `drawItemText` 会在 `State_On` 状态自动套用调色板的 `HighlightedText`（浅色主题下为白色），导致选中按钮变成「白字压在浅色卡片背景上」而几乎不可见；现统一使用主题的 `text` 色，并在选中时加粗以提升可读性。
- 窗口关闭后后台 GPU 探测回调访问已销毁控件导致的 `RuntimeError`（可能弹出未处理异常对话框）。

## 七、已知限制

- GPU 编码（NVENC / AMF / QSV）采用单遍码率控制，体积误差大于 CPU 2-Pass；追求精准控盘建议使用 CPU 模式
- 极端低码率目标（视频码率低于编码器可达下限）时无法完全达标，软件会在完成后标注实际偏差
- AMD / Intel 平台缺少命令行 GPU 采样工具时，GPU 占用率区域自动隐藏，不影响编码
- ProRes / DNxHR 属于专业母版格式，输出体积远大于原压缩文件，预估面板会提示「体积将增加」
