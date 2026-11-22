"""ffmpeg 子进程执行器：进度解析、取消、错误摘要。"""

from __future__ import annotations

import os
import re
from typing import List, Optional

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from app.config import TWO_PASS_SPLIT

_DEBUG_LOG = os.path.join(os.getcwd(), "ffmpeg_debug.log")


def _debug(msg: str) -> None:
    """把 ffmpeg 命令与完整报错同时输出到终端和 ffmpeg_debug.log，便于排查失败原因。"""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass

ERROR_HINTS = [
    (r"no space left on device", "磁盘空间不足"),
    (r"permission denied", "没有写入权限（目标目录被占用或只读）"),
    (r"invalid data found when processing input", "文件已损坏或格式不受支持"),
    (r"codec not currently supported|unknown encoder", "当前 ffmpeg 不支持该编码器"),
    (r"error while opening encoder|could not open encoder", "编码器初始化失败（可能被占用或缺少驱动）"),
    (r"too many packets buffered", "输出流缓冲溢出（素材异常）"),
    (r"unable to find a suitable output format", "目标格式不可用"),
    (r"incorrect codec parameters", "编码参数不受目标容器支持"),
    (r"device creation failed|failed to initialise|no device", "硬件编码器不可用，请改用 CPU 编码"),
    (r"moov atom not found", "文件索引损坏（可能是未完整下载的视频）"),
    (r"invalid argument", "参数不受支持（编码器版本较旧）"),
]


def summarize_error(stderr: str, exit_code: int) -> str:
    """从 ffmpeg 输出尾部提取可读错误原因。"""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    if not lines:
        return f"ffmpeg 退出码 {exit_code}"
    tail = lines[-6:]
    for pattern, hint in ERROR_HINTS:
        for line in tail:
            if re.search(pattern, line, re.IGNORECASE):
                return f"{hint}（{line[:90]}）"
    for line in reversed(tail):
        if re.search(r"error|invalid|failed|not supported|unable", line, re.IGNORECASE):
            return line[:160]
    return f"{tail[-1][:160]}（退出码 {exit_code}）"


class FFmpegRunner(QObject):
    """顺序执行 1~2 遍编码，实时上报进度。"""

    progress = Signal(float, int, int)     # 0~1, 当前遍(1-based), 总遍数
    finished = Signal(bool, str)           # 成功, 错误摘要

    def __init__(self, ffmpeg_path: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._ffmpeg = ffmpeg_path
        self._process: Optional[QProcess] = None
        self._watchdog: Optional[QTimer] = None
        self._passes: List[List[str]] = []
        self._duration = 0.0
        self._index = 0
        self._buffer = b""
        self._stderr_tail = ""
        self._stderr_full = ""
        self._canceled = False
        self._passlogfile = ""
        self._last_percent = 0.0
        self._done = False

    # ------------------------------------------------------------ 控制
    def start(self, passes: List[List[str]], duration: float, passlogfile: str = "") -> None:
        self._passes = passes or []
        self._duration = max(duration, 0.0)
        self._index = 0
        self._buffer = b""
        self._stderr_tail = ""
        self._canceled = False
        self._passlogfile = passlogfile
        self._last_percent = 0.0
        self._stderr_full = ""
        self._start_pass()

    def cancel(self) -> None:
        self._canceled = True
        self._stop_watchdog()
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()

    @property
    def canceled(self) -> bool:
        return self._canceled

    # ------------------------------------------------------------ 内部
    def _start_pass(self) -> None:
        if self._canceled or self._index >= len(self._passes):
            self._emit_finished(False, "已取消" if self._canceled else "未知错误")
            return

        args = ["-nostats", "-progress", "pipe:1"] + self._passes[self._index]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        # 携带进程引用：遍次切换后，上一遍进程经 Qt 事件队列迟到的 finished 信号
        # 可凭身份被忽略，避免重复启动同一遍次进程（双 ffmpeg 互踩临时文件的竞态）
        process.finished.connect(
            lambda code, _status, p=process: self._on_finished(code, p)
        )
        self._process = process
        self._done = False
        process.start(self._ffmpeg, args)
        _debug("【FFMPEG 命令 #%d】%s %s"
               % (self._index + 1, self._ffmpeg, " ".join(args)))
        self.progress.emit(
            self._map_progress(0.0), self._index + 1, max(len(self._passes), 1)
        )
        # 看门狗：纯主线程计时器，替代原跨线程 waitForFinished（后者会因
        # QWinEventNotifier 跨线程而崩溃）。超时则强制终止并报错，避免卡死。
        self._start_watchdog(process)

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput())
        if not chunk:
            return
        self._buffer += chunk
        while b"\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition(b"\n")
            self._parse_progress(line.decode("utf-8", "ignore").strip())

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", "ignore")
        if text:
            self._stderr_tail = (self._stderr_tail + text)[-8192:]
            self._stderr_full = (self._stderr_full + text)[-8192:]

    def _parse_progress(self, line: str) -> None:
        if "=" not in line:
            return
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "out_time_us":
            try:
                seconds = int(value) / 1_000_000.0
            except ValueError:
                return
            if self._duration <= 0:
                return
            ratio = min(max(seconds / self._duration, 0.0), 1.0)
            self._emit_progress(ratio)
        elif key == "progress" and value == "end":
            self._emit_progress(1.0)

    def _emit_progress(self, ratio: float) -> None:
        if ratio < self._last_percent and ratio < 0.99:
            return  # 防止进度回跳导致 UI 抖动
        self._last_percent = ratio
        self.progress.emit(self._map_progress(ratio), self._index + 1, max(len(self._passes), 1))

    def _map_progress(self, ratio: float) -> float:
        total = max(len(self._passes), 1)
        if total == 1:
            return ratio
        split = TWO_PASS_SPLIT
        if self._index == 0:
            return ratio * split
        return split + ratio * (1 - split)

    # ------------------------------------------------------------ 看门狗
    def _start_watchdog(self, process: QProcess) -> None:
        """主线程单发计时器，防止个别环境下 finished 信号不触发导致卡死。"""
        self._stop_watchdog()
        # 每遍预留：时长×2 + 3 分钟缓冲（二遍编码更慢、启动有开销）
        timeout_ms = int(self._duration * 2000) + 180_000
        tw = QTimer(self)
        tw.setSingleShot(True)
        tw.timeout.connect(lambda p=process: self._on_watchdog(p))
        tw.start(timeout_ms)
        self._watchdog = tw

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog.deleteLater()
            self._watchdog = None

    def _on_watchdog(self, process: QProcess) -> None:
        if self._done or process is not self._process:
            return
        if process.state() != QProcess.NotRunning:
            _debug("【FFMPEG 超时】进程无响应，强制终止")
            # 先标记完成并停掉看门狗，否则被 kill 的进程随后触发的 finished
            # 信号会进入 _on_finished（_done 仍为 False）再次发射 finished，
            # 导致队列收到重复完成回调、重复启动下一个任务。
            self._done = True
            self._stop_watchdog()
            process.kill()
            if self._process is process:
                self._process = None
            self._emit_finished(False, "编码超时（进程无响应，已强制终止）")

    def _on_finished(self, exit_code: int, process=None) -> None:
        # 身份校验：忽略上一遍进程经 Qt 事件队列迟到的 finished 信号
        if process is not None and process is not self._process:
            return
        if self._done:
            return  # 防止 finished 信号重复触发
        self._done = True
        self._stop_watchdog()
        if self._process is not None:
            tail = bytes(self._process.readAllStandardError()).decode("utf-8", "ignore")
            if tail:
                self._stderr_tail = (self._stderr_tail + tail)[-8192:]
            self._process.deleteLater()
            self._process = None

        if self._canceled:
            self._emit_finished(False, "已取消")
            return
        # FailedToStart 时 exitCode() 仍为 0，会被误判为成功，必须显式拦截
        if process is not None and process.error() == QProcess.FailedToStart:
            _debug("【FFMPEG 启动失败】%s" % self._ffmpeg)
            self._emit_finished(
                False, "ffmpeg 启动失败：找不到可执行文件或被安全软件拦截"
            )
            return
        if exit_code != 0:
            _debug("【FFMPEG 失败 #%d】退出码 %d" % (self._index + 1, exit_code))
            _debug("【FFMPEG 完整 stderr】\n" + self._stderr_full)
            self._emit_finished(False, summarize_error(self._stderr_tail, exit_code))
            return

        self._index += 1
        if self._index < len(self._passes):
            self._last_percent = 0.0
            self._start_pass()
        else:
            self._emit_finished(True, "")

    def _emit_finished(self, ok: bool, error: str) -> None:
        if ok:
            # 成功路径也留痕：记录临时产物体积与 stderr 尾部，便于日后诊断
            _debug("【FFMPEG 完成 #%d】退出码 0" % (self._index + 1))
            if self._stderr_full.strip():
                _debug("【FFMPEG 成功 stderr 尾部】\n" + self._stderr_full[-2048:])
        self._cleanup_passlog()
        self.finished.emit(ok, error)

    def _cleanup_passlog(self) -> None:
        if not self._passlogfile:
            return
        directory = os.path.dirname(self._passlogfile) or "."
        stem = os.path.basename(self._passlogfile)
        try:
            for name in os.listdir(directory):
                if name.startswith(stem):
                    os.remove(os.path.join(directory, name))
        except Exception:
            pass
