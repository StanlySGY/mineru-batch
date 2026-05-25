"""Queue service — business logic for queue status reporting."""
from sqlalchemy.orm import Session

from models import FileTask, TaskStatus


def get_queue_status_impl(db: Session, concurrency: int, queue_size: int, waiting_limit: int = 5) -> dict:
    pending = db.query(FileTask).filter(FileTask.status == TaskStatus.PENDING).count()
    processing = db.query(FileTask).filter(FileTask.status == TaskStatus.PROCESSING).count()
    waiting_tasks = (
        db.query(FileTask)
        .filter(FileTask.status == TaskStatus.PENDING)
        .order_by(FileTask.priority.desc(), FileTask.created_at.asc())
        .limit(waiting_limit)
        .all()
    )
    return {
        "concurrency": concurrency,
        "queue_size": queue_size,
        "pending": pending,
        "processing": processing,
        "available_slots": max(concurrency - processing, 0),
        "waiting_tasks": [
            {
                "id": task.id,
                "filename": task.original_filename,
                "priority": task.priority or 0,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            }
            for task in waiting_tasks
        ],
    }
