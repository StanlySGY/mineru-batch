"""Query service — business logic for task query operations."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import FileTask


def get_tasks_since_impl(db: Session, since: str) -> dict:
    """Get tasks updated since a given timestamp."""
    try:
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format")
    tasks = db.query(FileTask).filter(FileTask.updated_at >= cutoff).all()
    return {"items": [t.to_dict() for t in tasks]}


def list_tasks_impl(
    db: Session,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 20,
    batch_id: str | None = None,
) -> dict:
    """List tasks with filtering and pagination."""
    q = db.query(FileTask)
    if status:
        q = q.filter(FileTask.status == status)
    if search:
        q = q.filter(FileTask.original_filename.ilike(f"%{search}%"))
    if batch_id:
        q = q.filter(FileTask.batch_id == batch_id)
    total = q.count()
    items = q.order_by(FileTask.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [t.to_dict() for t in items]}


def get_task_impl(db: Session, task_id: int) -> dict:
    """Get a single task by ID."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    return task.to_dict()
