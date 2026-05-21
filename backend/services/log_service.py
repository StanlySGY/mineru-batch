"""Log service — business logic for log operations."""
from sqlalchemy.orm import Session
from models import ProcessLog, FileTask, ProcessLog as ProcessLogModel


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
            "created_at": task.created_at.isoformat() if task and task.created_at else None,
            "logs": [l.to_dict() for l in logs_by_task.get(tid, [])],
        })
    return {"total": total, "items": groups}
