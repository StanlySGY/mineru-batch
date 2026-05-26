"""Batch report service."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import FileTask


def get_batch_progress_impl(db: Session, limit: int = 20, batch_id: str | None = None) -> dict:
    query = db.query(FileTask.batch_id, FileTask.batch_name, FileTask.status, func.count(FileTask.id), func.max(FileTask.created_at)).filter(FileTask.batch_id.isnot(None))
    if batch_id:
        query = query.filter(FileTask.batch_id == batch_id)
    rows = query.group_by(FileTask.batch_id, FileTask.batch_name, FileTask.status).all()
    batches: dict[str, dict] = {}
    for batch_id, batch_name, status, count, latest in rows:
        item = batches.setdefault(batch_id, {
            "batch_id": batch_id,
            "batch_name": batch_name,
            "total": 0,
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "latest_at": latest.isoformat() if latest else None,
        })
        key = status.value if status else "pending"
        item[key] = count
        item["total"] += count
        if latest and (not item["latest_at"] or latest.isoformat() > item["latest_at"]):
            item["latest_at"] = latest.isoformat()
    items = list(batches.values())
    for item in items:
        item["progress"] = round(item["completed"] / item["total"] * 100, 1) if item["total"] else 0
    items.sort(key=lambda x: x.get("latest_at") or "", reverse=True)
    return {"total": len(items), "items": items[:limit]}
