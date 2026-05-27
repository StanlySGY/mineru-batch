"""Batch report service."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Batch, FileTask


def _fallback_batch_names(db: Session, batch_ids: list[str]) -> dict[str, str]:
    names = {}
    if not batch_ids:
        return names
    rows = db.query(FileTask.batch_id, FileTask.batch_name, FileTask.id).filter(
        FileTask.batch_id.in_(batch_ids),
        FileTask.batch_name.isnot(None),
        FileTask.batch_name != "",
    ).order_by(FileTask.id.asc()).all()
    for batch_id, batch_name, _ in rows:
        names.setdefault(batch_id, batch_name)
    return names


def get_batch_progress_impl(db: Session, limit: int = 20, batch_id: str | None = None, include_archived: bool = False) -> dict:
    query = db.query(FileTask.batch_id, FileTask.status, func.count(FileTask.id), func.max(FileTask.created_at)).filter(FileTask.batch_id.isnot(None))
    if batch_id:
        query = query.filter(FileTask.batch_id == batch_id)
    rows = query.group_by(FileTask.batch_id, FileTask.status).all()
    batch_ids = list({row[0] for row in rows if row[0]})
    batch_rows = db.query(Batch).filter(Batch.batch_id.in_(batch_ids)).all() if batch_ids else []
    canonical_names = {batch.batch_id: batch.name for batch in batch_rows}
    archived_map = {batch.batch_id: bool(batch.archived) for batch in batch_rows}
    fallback_names = _fallback_batch_names(db, batch_ids)
    batches: dict[str, dict] = {}
    for batch_id, status, count, latest in rows:
        item = batches.setdefault(batch_id, {
            "batch_id": batch_id,
            "batch_name": canonical_names.get(batch_id) or fallback_names.get(batch_id),
            "archived": archived_map.get(batch_id, False),
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
    items = [item for item in batches.values() if include_archived or not item.get("archived")]
    for item in items:
        item["progress"] = round(item["completed"] / item["total"] * 100, 1) if item["total"] else 0
    items.sort(key=lambda x: x.get("latest_at") or "", reverse=True)
    return {"total": len(items), "items": items[:limit]}
