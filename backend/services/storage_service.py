"""Storage service — business logic for storage operations."""
import asyncio
import os
import shutil

from models import FileTask, TaskStatus
from sqlalchemy.orm import Session


async def clean_directory(dir_path: str, skip_dotfiles: bool = False) -> int:
    """Clean all files and subdirectories in a directory, return count of cleaned items."""
    if not os.path.exists(dir_path):
        return 0
    n = 0
    for f in os.listdir(dir_path):
        if skip_dotfiles and f.startswith("."):
            continue
        fp = os.path.join(dir_path, f)
        try:
            if os.path.isfile(fp):
                await asyncio.to_thread(os.remove, fp)
                n += 1
            elif os.path.isdir(fp):
                await asyncio.to_thread(shutil.rmtree, fp)
                n += 1
        except OSError:
            pass
    return n


async def clean_storage_impl(targets: list, output_dir: str, convert_dir: str, db: Session) -> dict:
    """Clean storage targets. Returns dict with cleanup counts."""
    cleaned = {}
    if "outputs" in targets:
        cleaned["outputs"] = await clean_directory(output_dir)
        db.query(FileTask).filter(FileTask.output_path.isnot(None)).update({"output_path": None})
        db.commit()
    if "converted" in targets:
        cleaned["converted"] = await clean_directory(convert_dir, skip_dotfiles=True)
    return cleaned


async def clean_completed_sources_impl(db: Session) -> dict:
    """Clean source files for completed tasks. Returns dict with count and freed bytes."""
    tasks = db.query(FileTask).filter(
        FileTask.status == TaskStatus.COMPLETED,
        FileTask.file_path.isnot(None),
    ).all()
    count = 0
    freed = 0
    for task in tasks:
        if task.file_path and os.path.exists(task.file_path):
            try:
                freed += os.path.getsize(task.file_path)
                await asyncio.to_thread(os.remove, task.file_path)
                task.file_path = None
                count += 1
            except OSError:
                pass
    db.commit()
    return {"count": count, "freed_bytes": freed}
