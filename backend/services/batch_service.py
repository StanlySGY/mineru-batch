"""Batch service — business logic for batch task operations."""
import os
import io
import zipfile
import asyncio

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import FileTask, TaskStatus, add_log


def _parse_id_list(ids: str) -> list[int]:
    """Parse comma-separated ID string into list of integers."""
    return [int(i) for i in ids.split(",") if i.strip().isdigit()]


def _sanitize_filename(name: str) -> str:
    """Sanitize filename for safe use in archives."""
    import re
    name = os.path.splitext(name)[0]
    name = re.sub(r'[\s\\/:*?"<>|]', '_', name)
    name = re.sub(r'[^\w\-.一-鿿]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or 'output'


async def batch_delete_tasks_impl(db: Session, ids: str, safe_remove_fn) -> dict:
    """Delete multiple tasks and their associated files."""
    id_list = _parse_id_list(ids)
    if not id_list:
        return {"detail": "batch deleted", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list)).all()
    for task in tasks:
        await asyncio.to_thread(safe_remove_fn, task.file_path)
        await asyncio.to_thread(safe_remove_fn, task.output_path)
        await asyncio.to_thread(safe_remove_fn, task.pdf_path)
        db.delete(task)
    db.commit()
    return {"detail": "batch deleted", "count": len(tasks)}


async def batch_retry_tasks_impl(db: Session, ids: str, enqueue_fn) -> dict:
    """Retry multiple failed or completed tasks."""
    id_list = _parse_id_list(ids)
    if not id_list:
        return {"detail": "batch retried", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list), FileTask.status.in_((TaskStatus.FAILED, TaskStatus.COMPLETED))).all()
    for task in tasks:
        if task.output_path and os.path.exists(task.output_path):
            os.remove(task.output_path)
        task.output_path = None
        task.status = TaskStatus.PENDING
        task.error_message = None
        add_log(f"批量重试", task_id=task.id)
        enqueue_fn(task.id)
    db.commit()
    return {"detail": "batch retried", "count": len(tasks)}


async def batch_convert_tasks_impl(db: Session, ids: str, is_doc_file_fn, convert_to_pdf_fn, enqueue_fn) -> dict:
    """Convert multiple document files to PDF and enqueue for processing."""
    id_list = _parse_id_list(ids)
    if not id_list:
        return {"detail": "batch converted", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list)).all()
    converted = 0
    for task in tasks:
        if is_doc_file_fn(task.original_filename) and not task.pdf_path:
            try:
                pdf_path = await convert_to_pdf_fn(task.file_path, task.id)
                task.pdf_path = pdf_path
                task.auto_convert_doc = True
                db.commit()
                add_log(f"批量转换完成，开始解析", task_id=task.id)
                enqueue_fn(task.id)
                converted += 1
            except Exception as e:
                add_log(f"批量转换失败: {e}", task_id=task.id, level="error")
    return {"detail": "batch converted", "count": converted}


def batch_download_tasks_impl(db: Session, ids: str) -> io.BytesIO:
    """Download results from multiple completed tasks as a ZIP file."""
    id_list = _parse_id_list(ids)
    if not id_list:
        raise HTTPException(400, "No valid task IDs")
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list), FileTask.status == TaskStatus.COMPLETED).all()
    if not tasks:
        raise HTTPException(400, "No completed tasks found")
    valid = [t for t in tasks if t.output_path and os.path.exists(t.output_path)]
    if not valid:
        raise HTTPException(404, "No output files found on disk")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for t in valid:
            stem = _sanitize_filename(t.original_filename)
            if os.path.isdir(t.output_path):
                for root, _, files in os.walk(t.output_path):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        arc = os.path.join(stem, os.path.relpath(fp, t.output_path))
                        zf.write(fp, arc)
            else:
                ext = os.path.splitext(t.output_path)[1] or ".md"
                arc_name = f"{stem}_{t.id}{ext}"
                zf.write(t.output_path, arc_name)
    buf.seek(0)
    return buf
