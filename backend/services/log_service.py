"""Log service — business logic for log operations."""
import os
from pathlib import Path

from models import FileTask, ProcessLog, _iso
from sqlalchemy.orm import Session

PROJECT_DIR = Path(__file__).resolve().parents[2]


def get_app_log_file(create_parent: bool = False) -> Path:
    configured = os.environ.get("APP_LOG_FILE", "").strip()
    log_file = Path(configured).expanduser() if configured else Path("/app/app.log")
    if not configured and (not log_file.parent.exists() or not os.access(log_file.parent, os.W_OK)):
        log_file = PROJECT_DIR / "app.log"
    if create_parent:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    return log_file


def list_logs_impl(
    db: Session,
    task_id: int | None = None,
    level: str | None = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """List logs with optional filtering and pagination."""
    q = db.query(ProcessLog)
    if task_id:
        q = q.filter(ProcessLog.task_id == task_id)
    if level:
        q = q.filter(ProcessLog.level == level)
    total = q.count()
    items = q.order_by(ProcessLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [log.to_dict() for log in items]}


def clear_logs_impl(db: Session) -> int:
    """Clear all logs. Returns count of deleted logs."""
    count = db.query(ProcessLog).delete()
    db.commit()
    return count


def get_grouped_logs_impl(
    db: Session,
    page: int = 1,
    size: int = 20,
    level: str | None = None,
) -> dict:
    """Get logs grouped by task with pagination. Returns dict with total and items."""
    total = db.query(ProcessLog).count()
    all_ids = [r[0] for r in db.query(FileTask.id).order_by(FileTask.id.desc()).all()]

    paged_ids = all_ids[(page - 1) * size: page * size]

    tasks_map = {}
    if paged_ids:
        for t in db.query(FileTask).filter(FileTask.id.in_(paged_ids)).all():
            tasks_map[t.id] = t

    logs_q = db.query(ProcessLog).filter(ProcessLog.task_id.in_(paged_ids))
    if level:
        logs_q = logs_q.filter(ProcessLog.level == level)
    logs_by_task: dict = {}
    for log in logs_q.order_by(ProcessLog.id.asc()).all():
        logs_by_task.setdefault(log.task_id, []).append(log)

    groups = []
    for tid in paged_ids:
        task = tasks_map.get(tid)
        groups.append({
            "task_id": tid,
            "filename": task.original_filename if task else f"Task#{tid}",
            "status": task.status.value if task else "unknown",
            "created_at": _iso(task.created_at) if task else None,
            "logs": [log.to_dict() for log in logs_by_task.get(tid, [])],
        })
    return {"total": total, "items": groups}
