"""Stats service — business logic for statistics operations."""
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from models import FileTask, TaskStatus


def get_stats_trend_impl(db: Session, days: int = 7) -> list:
    """Get task completion trend over days. Returns list of daily stats."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    tasks = db.query(FileTask.created_at, FileTask.status).filter(
        FileTask.created_at >= cutoff
    ).all()
    daily: dict[str, dict[str, int]] = {}
    for created_at, status in tasks:
        d = created_at.strftime("%Y-%m-%d") if created_at else "unknown"
        if d not in daily:
            daily[d] = {"completed": 0, "failed": 0}
        if status == TaskStatus.COMPLETED:
            daily[d]["completed"] += 1
        elif status == TaskStatus.FAILED:
            daily[d]["failed"] += 1
    return [{"date": d, "completed": v["completed"], "failed": v["failed"]} for d, v in sorted(daily.items())]


def get_filetype_stats_impl(db: Session) -> list:
    """Get file type distribution. Returns list of file type stats."""
    tasks = db.query(FileTask.original_filename).all()
    ext_count: dict[str, int] = {}
    for (filename,) in tasks:
        ext = os.path.splitext(filename)[1].lower() or '.unknown'
        ext_count[ext] = ext_count.get(ext, 0) + 1
    return [{"type": ext, "count": cnt} for ext, cnt in sorted(ext_count.items(), key=lambda x: -x[1])]
