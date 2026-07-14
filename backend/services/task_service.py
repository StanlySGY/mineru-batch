"""Task service — business logic for task operations."""
import os
import threading
from datetime import UTC, datetime

from fastapi import HTTPException
from models import FileTask, TaskStatus, add_log
from sqlalchemy.orm import Session

_cancelled_tasks: set[int] = set()
_cancel_lock = threading.Lock()


def mark_task_cancelled(task_id: int):
    """Mark a task as cancelled in the tracking set."""
    with _cancel_lock:
        _cancelled_tasks.add(task_id)


def is_task_cancelled(task_id: int) -> bool:
    """Check if a task is marked as cancelled."""
    with _cancel_lock:
        return task_id in _cancelled_tasks


def unmark_task_cancelled(task_id: int):
    """Remove a task from the cancelled set."""
    with _cancel_lock:
        _cancelled_tasks.discard(task_id)


def check_and_mark_cancelled(task: FileTask, db: Session, cleanup_path: str = None) -> bool:
    """Check if task is cancelled. If so, mark it FAILED and return True. Cleanup file if provided."""
    if not is_task_cancelled(task.id):
        return False
    if cleanup_path and os.path.exists(cleanup_path):
        os.remove(cleanup_path)
    task.status = TaskStatus.FAILED
    task.error_message = "任务已取消"
    task.completed_at = datetime.now(UTC)
    db.commit()
    return True


def cancel_task_impl(task_id: int, db: Session) -> dict:
    """Cancel a task. Returns task dict."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(400, "只能取消等待中或处理中的任务")

    mark_task_cancelled(task_id)
    task.status = TaskStatus.FAILED
    task.error_message = "用户取消"
    task.completed_at = datetime.now(UTC)
    db.commit()
    add_log("任务已取消", task_id=task_id, level="warn")
    return task.to_dict()


def retry_task_impl(
    task_id: int,
    mineru_api: str | None,
    server_url: str | None,
    db: Session,
    validate_external_url_fn,
    allow_private: bool,
    enqueue_fn=None,
) -> dict:
    """Retry a task. Returns task dict."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.output_path and os.path.exists(task.output_path):
        try:
            os.remove(task.output_path)
        except OSError:
            pass

    task.output_path = None
    task.status = TaskStatus.PENDING
    task.error_message = None

    if mineru_api:
        task.mineru_api = validate_external_url_fn(mineru_api, "mineru_api", allow_private=allow_private)
    if server_url:
        task.server_url = validate_external_url_fn(server_url, "server_url", allow_private=allow_private)

    db.commit()
    add_log("任务重新提交", task_id=task_id)

    if enqueue_fn:
        enqueue_fn(task.id)

    return task.to_dict()
