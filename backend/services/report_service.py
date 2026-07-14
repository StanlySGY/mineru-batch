"""Report service — business logic for statistics and report operations."""
from models import FileTask, TaskStatus, _iso
from sqlalchemy import func
from sqlalchemy.orm import Session


def classify_failure_reason(message: str | None) -> str:
    text = (message or "").lower()
    if any(k in text for k in ("timeout", "timed out", "超时")):
        return "timeout"
    if any(k in text for k in ("connect", "connection", "network", "连接")):
        return "network"
    if any(k in text for k in ("convert", "libreoffice", "转换")):
        return "conversion"
    if any(k in text for k in ("mineru", "file_parse", "api")):
        return "mineru_api"
    return "other"


def get_failure_categories_impl(db: Session) -> dict:
    failed = db.query(FileTask.error_message).filter(FileTask.status == TaskStatus.FAILED).all()
    counts: dict[str, int] = {}
    for (message,) in failed:
        category = classify_failure_reason(message)
        counts[category] = counts.get(category, 0) + 1
    return {
        "total": sum(counts.values()),
        "items": [{"category": key, "count": value} for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)],
    }


def get_stats_impl(db: Session) -> dict:
    """Get overall task statistics."""
    total = db.query(func.count(FileTask.id)).scalar()
    by_status = (
        db.query(FileTask.status, func.count(FileTask.id))
        .group_by(FileTask.status)
        .all()
    )
    status_map = {s.value: c for s, c in by_status}
    completed_tasks = db.query(FileTask.started_at, FileTask.completed_at).filter(
        FileTask.status == TaskStatus.COMPLETED,
        FileTask.started_at.isnot(None),
        FileTask.completed_at.isnot(None),
    ).all()
    durations = [(c - s).total_seconds() * 1000 for s, c in completed_tasks if c and s]
    avg_duration_ms = sum(durations) / len(durations) if durations else 0
    return {
        "total": total,
        "pending": status_map.get("pending", 0),
        "processing": status_map.get("processing", 0),
        "completed": status_map.get("completed", 0),
        "failed": status_map.get("failed", 0),
        "avg_duration_ms": avg_duration_ms,
    }


def get_quality_report_impl(db: Session, stats: dict) -> dict:
    """Get quality report with recent failures."""
    done = stats["completed"] + stats["failed"]
    recent_failed = (
        db.query(FileTask)
        .filter(FileTask.status == TaskStatus.FAILED)
        .order_by(FileTask.id.desc())
        .limit(5)
        .all()
    )
    return {
        "total": stats["total"],
        "completed": stats["completed"],
        "failed": stats["failed"],
        "processing": stats["processing"],
        "pending": stats["pending"],
        "success_rate": round(stats["completed"] / done * 100, 1) if done else 0,
        "avg_duration_ms": stats["avg_duration_ms"],
        "recent_failures": [
            {
                "id": t.id,
                "filename": t.original_filename,
                "error_message": t.error_message,
                "created_at": _iso(t.created_at),
                "completed_at": _iso(t.completed_at),
            }
            for t in recent_failed
        ],
    }
