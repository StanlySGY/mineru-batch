"""Task management service — business logic for task update and deletion."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import FileTask, OutputFormat, add_log


async def delete_task_impl(db: Session, task_id: int, safe_remove_fn) -> dict:
    """Delete a single task and its associated files."""
    import asyncio
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    await asyncio.to_thread(safe_remove_fn, task.file_path)
    await asyncio.to_thread(safe_remove_fn, task.output_path)
    await asyncio.to_thread(safe_remove_fn, task.pdf_path)
    db.delete(task)
    db.commit()
    return {"detail": "deleted"}


def update_task_impl(
    db: Session,
    task_id: int,
    backend: str | None = None,
    mineru_api: str | None = None,
    server_url: str | None = None,
    parse_method: str | None = None,
    lang_list: str | None = None,
    output_format: str | None = None,
    timeout: str | None = None,
    validate_url_fn=None,
    allow_private: bool = False,
) -> dict:
    """Update task configuration."""
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if backend:
        task.backend = backend
    if mineru_api:
        task.mineru_api = validate_url_fn(mineru_api, "mineru_api", allow_private=allow_private) if validate_url_fn else mineru_api
    if server_url:
        task.server_url = validate_url_fn(server_url, "server_url", allow_private=allow_private) if validate_url_fn else server_url
    if parse_method:
        task.parse_method = parse_method
    if lang_list:
        task.lang_list = lang_list
    if output_format and output_format in ("md", "txt", "html"):
        task.output_format = OutputFormat(output_format)
    if timeout:
        try:
            t = int(timeout)
            task.timeout = max(60, min(t, 3600))
        except (ValueError, TypeError):
            raise HTTPException(400, "timeout must be 60-3600")
    db.commit()
    db.refresh(task)
    return task.to_dict()
