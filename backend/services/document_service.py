"""Document service — business logic for document conversion operations."""
import os

from fastapi import HTTPException
from models import FileTask, add_log
from sqlalchemy.orm import Session


async def convert_doc_to_pdf_impl(
    db: Session,
    task_id: int,
    is_doc_file_fn,
    convert_to_pdf_fn,
    enqueue_fn,
) -> dict:
    """Convert a document file to PDF."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not is_doc_file_fn(task.original_filename):
        raise HTTPException(400, "Not a convertible document file")
    if task.pdf_path and os.path.exists(task.pdf_path):
        return {"detail": "already converted", "pdf_path": task.pdf_path}

    try:
        pdf_path = await convert_to_pdf_fn(task.file_path, task_id)
        task.pdf_path = pdf_path
        task.auto_convert_doc = True
        db.commit()
        add_log("手动转换完成，开始解析", task_id=task_id)
        enqueue_fn(task.id)
        return {"detail": "converted", "pdf_path": pdf_path}
    except Exception as e:
        raise HTTPException(500, f"Conversion failed: {e}") from e
