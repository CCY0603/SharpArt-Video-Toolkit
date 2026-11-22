"""任务队列：顺序/并发调度、失败跳过、取消与重试。"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from app.config import SIZE_TOLERANCE, TEMP_SUFFIX, MAX_CONCURRENCY
from core.capabilities import Capabilities
from core.models import EncodeParams, TaskItem, TaskStatus
from core.planner import (
    build_ffmpeg_args,
    build_output_path,
    compute_bitrate_plan,
    release_output_path,
)
from core.runner import FFmpegRunner
from core.utils import format_size


class TaskQueue(QObject):
    """批处理调度器（全在主线程，依赖 QProcess 异步，不阻塞 UI）。"""

    taskUpdated = Signal(object)          # TaskItem
    taskStarted = Signal(object)
    queueStateChanged = Signal()
    queueFinished = Signal(dict)          # 汇总统计
    message = Signal(str)

    def __init__(self, settings, caps: Capabilities, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._caps = caps
        self._pending: List[TaskItem] = []
        self._running: Dict[int, Dict] = {}
        self._active = False
        self._started_at = 0.0
        self._output_dir = ""

    # ------------------------------------------------------------ 属性
    @property
    def active(self) -> bool:
        return self._active

    @property
    def concurrency(self) -> int:
        value = int(self._settings.concurrency or 1)
        return max(1, min(value, MAX_CONCURRENCY))

    def set_concurrency(self, value: int) -> None:
        self._settings.concurrency = max(1, min(int(value), MAX_CONCURRENCY))

    def set_caps(self, caps: Capabilities) -> None:
        self._caps = caps

    # ------------------------------------------------------------ 调度
    def start(self, tasks: List[TaskItem], output_dir: str) -> None:
        if self._active:
            return
        if not self._caps or not self._caps.ok:
            self.message.emit(self._caps.error if self._caps else "ffmpeg 未就绪")
            return
        # 只接受已探测完成的任务：占位 VideoInfo（duration=0）会导致码率与进度全错
        todo = [t for t in tasks if t.is_runnable()]
        if not todo:
            self.message.emit("没有待处理的文件")
            return
        self._pending = todo
        self._active = True
        self._started_at = time.time()
        self._output_dir = output_dir
        for task in todo:
            task.status = TaskStatus.PENDING
            task.progress = 0.0
            task.error = ""
            task.pass_index = 0
        self.queueStateChanged.emit()
        self._pump()

    def cancel_all(self) -> None:
        for entry in list(self._running.values()):
            # 打标记：让收尾回调把它归为「已取消」而非「失败」
            entry["canceled"] = True
            runner: FFmpegRunner = entry["runner"]
            runner.cancel()
        # 尚未启动的任务也要置为已取消，否则会永远停在「等待处理」且不再被调度
        for task in self._pending:
            task.status = TaskStatus.CANCELED
            task.error = "已取消"
            self.taskUpdated.emit(task)
        self._pending = []
        self._active = False
        self.queueStateChanged.emit()

    # ------------------------------------------------------------ 内部
    def _pump(self) -> None:
        if not self._active:
            return
        while self._pending and len(self._running) < self.concurrency:
            task = self._pending.pop(0)
            self._launch(task, self._output_dir)
        if not self._pending and not self._running:
            self._finish()

    def _launch(self, task: TaskItem, output_dir: str) -> None:
        info = task.info
        params: EncodeParams = task.params

        final_path = build_output_path(info, params, output_dir, self._caps)
        base, ext = os.path.splitext(final_path)
        tmp_path = f"{base}{TEMP_SUFFIX}{ext}"  # 保留扩展名，确保 ffmpeg 能识别封装格式

        task.status = TaskStatus.RUNNING
        task.progress = 0.0
        task.output_path = final_path
        self.taskStarted.emit(task)
        self.taskUpdated.emit(task)

        entry = {
            "task": task,
            "tmp": tmp_path,
            "final": final_path,
            "start": time.time(),
            "adjust": 0,
            "plan": None,
            "params": params,
            "runner": None,
        }
        self._running[task.id] = entry
        self._run_passes(task, params, entry)

    def _run_passes(self, task: TaskItem, params: EncodeParams, entry: Dict) -> None:
        info = task.info
        plan = compute_bitrate_plan(info, params, self._caps)
        entry["plan"] = plan
        entry["params"] = params

        tmp_path: str = entry["tmp"]
        # passlog 放到 ASCII 临时目录，规避 x265 内部 fopen 对非 ASCII 路径的兼容问题
        passlogfile = os.path.join(
            tempfile.gettempdir(), f"savt_{task.id}.passlog"
        )

        if plan.two_pass and plan.total_passes == 2:
            passes = [
                build_ffmpeg_args(info, params, tmp_path, pass_no=1,
                                  passlogfile=passlogfile, caps=self._caps),
                build_ffmpeg_args(info, params, tmp_path, pass_no=2,
                                  passlogfile=passlogfile, caps=self._caps),
            ]
        else:
            passes = [
                build_ffmpeg_args(info, params, tmp_path, pass_no=0,
                                  passlogfile=passlogfile, caps=self._caps)
            ]

        task.total_passes = len(passes)
        task.pass_index = 1

        runner = FFmpegRunner(self._caps.ffmpeg, self)
        entry["runner"] = runner

        def on_progress(value: float, current_pass: int, total_passes: int) -> None:
            task.progress = value
            task.pass_index = current_pass
            task.total_passes = total_passes
            if entry["adjust"]:
                task.error = "体积校准中"
            self.taskUpdated.emit(task)

        def on_finished(ok: bool, error: str) -> None:
            self._on_task_finished(task, ok, error, entry)

        runner.progress.connect(on_progress)
        runner.finished.connect(on_finished)
        runner.start(passes, info.duration, passlogfile)

    def _needs_adjust(self, task: TaskItem, entry: Dict) -> bool:
        plan = entry.get("plan")
        params: EncodeParams = entry.get("params")
        if plan is None or params is None:
            return False
        if params.size_mode == "crf" or plan.target_bytes <= 0:
            return False
        if entry.get("adjust", 0) >= 1:
            return False
        actual = task.output_bytes
        if actual <= 0:
            return False
        return abs(actual - plan.target_bytes) / plan.target_bytes > SIZE_TOLERANCE

    @staticmethod
    def _adjust_params(params: EncodeParams, actual: int, target: int) -> Optional[EncodeParams]:
        """按实际输出与目标的比例修正码率基准，用于一次校准重编。"""
        if actual <= 0 or target <= 0:
            return None
        scale = target / actual
        scale = max(min(scale, 2.0), 0.4)
        new_params = params.copy()
        if params.size_mode == "absolute":
            new_params.target_bytes = int(params.target_bytes * scale)
        elif params.size_mode == "percent":
            new_params.percent = int(max(1, min(params.percent * scale, 300)))
        else:
            return None
        return new_params

    def _on_task_finished(self, task: TaskItem, ok: bool, error: str, entry: Dict) -> None:
        from core.runner import _debug
        runner: FFmpegRunner = entry["runner"]
        runner.deleteLater()
        self._running.pop(task.id, None)

        tmp_path: str = entry["tmp"]
        final_path: str = entry["final"]
        task.elapsed = time.time() - entry["start"]

        _debug("【任务结束】%s ok=%s error=%r 耗时 %.1fs"
               % (task.name, ok, error, task.elapsed))

        if ok:
            try:
                # 校验临时产物：ffmpeg 偶发"退出码 0 却未写入数据"，
                # 直接 rename 会丢 WinError 2；此处给出明确报错而非崩溃
                if not os.path.exists(tmp_path):
                    raise FileNotFoundError(
                        f"ffmpeg 报告成功，但输出文件不存在：{tmp_path}"
                    )
                if os.path.getsize(tmp_path) == 0:
                    try:
                        tail = (error or "").strip()
                    except Exception:
                        tail = ""
                    raise OSError(
                        f"输出文件为 0 字节（编码器未写入数据），ffmpeg 尾部：{tail[:300]}"
                    )
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.replace(tmp_path, final_path)
                task.output_bytes = os.path.getsize(final_path)
                task.error = ""
                if self._needs_adjust(task, entry):
                    plan = entry["plan"]
                    new_params = self._adjust_params(entry["params"], task.output_bytes, plan.target_bytes)
                    if new_params is not None:
                        entry["adjust"] = entry.get("adjust", 0) + 1
                        task.status = TaskStatus.RUNNING
                        task.progress = 0.0
                        task.error = "体积校准中"
                        # 重新登记回调度表：否则校准期间任务不在 _running 内，
                        # 会导致并发计数偏小、队列提前 _finish、cancel_all 杀不掉该进程
                        self._running[task.id] = entry
                        self.taskUpdated.emit(task)
                        self._run_passes(task, new_params, entry)
                        return
                plan = entry.get("plan")
                if plan is not None and plan.target_bytes > 0 and task.output_bytes:
                    deviation = abs(task.output_bytes - plan.target_bytes) / plan.target_bytes
                    if deviation > SIZE_TOLERANCE:
                        task.error = (
                            f"实际输出 {format_size(task.output_bytes)}，与目标 "
                            f"{format_size(plan.target_bytes)} 偏差 {deviation * 100:.0f}%："
                            f"受素材内容或编码器码率下限限制，已尽力贴近目标"
                        )
                task.status = TaskStatus.DONE
                task.progress = 1.0
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = f"输出文件写入失败：{exc}"
                _debug("【输出写入失败】%s -> %s : %r" % (tmp_path, final_path, exc))
        else:
            # 用户主动取消应归为「已取消」，而不是混进「失败」统计
            if entry.get("canceled"):
                task.status = TaskStatus.CANCELED
                task.error = "已取消"
            else:
                task.status = TaskStatus.FAILED
                task.error = error or "编码失败"
                _debug("【编码失败】%s : %s" % (task.name, error or "编码失败"))
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        # 任务到达终态（成功 / 失败 / 取消），释放输出路径预约。
        # 注意：上面的校准重编分支已 return，此时仍占用同一路径，不能释放。
        release_output_path(final_path)
        self.taskUpdated.emit(task)
        self.queueStateChanged.emit()
        self._pump()

    def _finish(self) -> None:
        self._active = False
        elapsed = time.time() - self._started_at if self._started_at else 0.0
        summary = {
            "elapsed": elapsed,
            "tasks": [],
        }
        self.queueStateChanged.emit()
        self.queueFinished.emit(summary)
