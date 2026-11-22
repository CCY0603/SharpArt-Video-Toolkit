"""汇总报告与任务清单导出。"""

from __future__ import annotations

import csv
import os
from typing import List

from core.models import TaskItem, TaskStatus
from core.utils import format_duration, format_size


def split_results(tasks: List[TaskItem]):
    success = [t for t in tasks if t.status == TaskStatus.DONE]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]
    canceled = [t for t in tasks if t.status == TaskStatus.CANCELED]
    return success, failed, canceled


def build_report_text(tasks: List[TaskItem], elapsed: float) -> str:
    success, failed, canceled = split_results(tasks)
    original = sum(t.info.size_bytes for t in tasks if t.info)
    output = sum(t.output_bytes for t in success)
    saved = 1 - (output / original) if original else 0.0

    lines = [
        "锐艺视频处理工具 — 处理报告",
        f"任务队列：{len(tasks)} 个文件",
        f"处理完成：{len(success)} 成功，{len(failed)} 失败"
        + (f"，{len(canceled)} 已取消" if canceled else ""),
        f"总耗时：{format_duration(elapsed)}",
        f"原始总计：{format_size(original)}",
        f"输出总计：{format_size(output)}",
        f"节省空间：{saved * 100:.1f}%",
        "",
    ]
    if success:
        lines.append("【成功文件】")
        for task in success:
            ratio = ""
            if task.info and task.info.size_bytes and task.output_bytes:
                ratio = f"（压缩至 {task.output_bytes / task.info.size_bytes * 100:.1f}%）"
            lines.append(
                f"  [OK] {task.name}　{format_size(task.info.size_bytes)} → "
                f"{format_size(task.output_bytes)}　{ratio}"
            )
        lines.append("")
    if failed:
        lines.append("【失败文件】")
        for task in failed:
            lines.append(f"  [X] {task.name}（原因：{task.error or '未知'}）")
        lines.append("")
    if canceled:
        lines.append("【已取消】")
        for task in canceled:
            lines.append(f"  [-] {task.name}")
    return "\n".join(lines)


def export_task_list_csv(tasks: List[TaskItem], path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "序号", "文件名", "原始大小(字节)", "时长(秒)", "分辨率",
                "目标", "状态", "输出路径", "输出大小(字节)", "说明",
            ])
            for index, task in enumerate(tasks, start=1):
                info = task.info
                writer.writerow([
                    index,
                    task.name,
                    info.size_bytes if info else 0,
                    f"{info.duration:.2f}" if info else "0",
                    info.resolution_text if info else "",
                    task.target_text,
                    TaskStatus.LABELS.get(task.status, task.status),
                    task.output_path,
                    task.output_bytes,
                    task.error,
                ])
        return True
    except Exception:
        return False


def export_text(text: str, path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return True
    except Exception:
        return False
