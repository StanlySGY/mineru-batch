"""Content service — business logic for task content operations."""
import io
import os
import zipfile

import aiofiles
from fastapi import HTTPException
from models import FileTask, TaskStatus, add_log
from sqlalchemy.orm import Session


async def preview_result_impl(db: Session, task_id: int, safe_path_fn) -> dict:
    """Get preview of completed task result."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    safe = safe_path_fn(task.output_path)
    if not os.path.exists(safe):
        raise HTTPException(404, "Output file missing on disk")
    async with aiofiles.open(safe, encoding="utf-8") as f:
        content = await f.read()
    return {"content": content, "filename": os.path.basename(safe), "format": task.output_format.value}


async def update_task_content_impl(db: Session, task_id: int, body: dict, safe_path_fn) -> dict:
    """Update task content and save to disk."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.output_path:
        raise HTTPException(400, "Output path is not set")

    content = body.get("content")
    if content is None:
        raise HTTPException(400, "Content is required")

    safe_path = safe_path_fn(task.output_path)
    if not os.path.exists(safe_path):
        raise HTTPException(404, "Output file missing on disk")

    if os.path.isdir(safe_path):
        target_file = None
        for ext in (task.output_format.value, "md", "txt"):
            cand = os.path.join(safe_path, f"output.{ext}")
            if os.path.exists(cand):
                target_file = cand
                break
        if not target_file:
            for root, _, files in os.walk(safe_path):
                for fn in files:
                    if fn.endswith((".md", ".txt", ".html")):
                        target_file = os.path.join(root, fn)
                        break
                if target_file:
                    break
        if not target_file:
            raise HTTPException(404, "Target content file not found inside bundle")
        safe_file_path = safe_path_fn(target_file)
    else:
        safe_file_path = safe_path

    async with aiofiles.open(safe_file_path, "w", encoding="utf-8") as f:
        await f.write(content)

    add_log("用户在线编辑并保存了解析内容", task_id=task.id)
    return {"detail": "saved"}


def download_result_impl(db: Session, task_id: int, safe_path_fn, sanitize_filename_fn) -> io.BytesIO | tuple:
    """Download task result as file or ZIP bundle."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    safe = safe_path_fn(task.output_path)
    if not os.path.exists(safe):
        raise HTTPException(404, "Output file missing on disk")
    if os.path.isdir(safe):
        stem = sanitize_filename_fn(task.original_filename)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(safe):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.join(stem, os.path.relpath(fp, safe))
                    zf.write(fp, arc)
        buf.seek(0)
        return buf, "zip", f"{stem}_bundle.zip"
    return safe, task.output_format.value, os.path.basename(safe)
