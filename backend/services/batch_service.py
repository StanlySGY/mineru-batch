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


def _find_markdown_output(output_path: str) -> str | None:
    if os.path.isfile(output_path) and output_path.lower().endswith(".md"):
        return output_path
    if not os.path.isdir(output_path):
        return None
    preferred = os.path.join(output_path, "output.md")
    if os.path.exists(preferred):
        return preferred
    for root, _, files in os.walk(output_path):
        for fn in sorted(files):
            if fn.lower().endswith(".md"):
                return os.path.join(root, fn)
    return None


def _archive_markdown_name(task: FileTask) -> str:
    raw = (task.original_filename or f"task_{task.id}.pdf").replace("\\", "/")
    parts = [p for p in raw.split("/") if p and p not in (".", "..")]
    if not parts:
        parts = [f"task_{task.id}.pdf"]
    dirs = [_sanitize_filename(p) for p in parts[:-1]]
    stem = _sanitize_filename(parts[-1])
    return "/".join([*dirs, f"{stem}.md"]) if dirs else f"{stem}.md"


def _unique_archive_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    root, ext = os.path.splitext(name)
    counter = 2
    while f"{root}_{counter}{ext}" in used:
        counter += 1
    unique = f"{root}_{counter}{ext}"
    used.add(unique)
    return unique


def _take_utf8_prefix(text: str, limit: int) -> tuple[str, str]:
    total = 0
    for idx, ch in enumerate(text):
        size = len(ch.encode("utf-8"))
        if total + size > limit:
            return text[:idx], text[idx:]
        total += size
    return text, ""


def _split_markdown(content: str, max_bytes: int) -> list[str]:
    if len(content.encode("utf-8")) <= max_bytes:
        return [content]
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0

    def flush() -> None:
        nonlocal current, current_bytes
        if current:
            chunks.append("".join(current))
            current = []
            current_bytes = 0

    for line in content.splitlines(keepends=True):
        rest = line
        while rest:
            available = max_bytes - current_bytes
            if available <= 0:
                flush()
                available = max_bytes
            if len(rest.encode("utf-8")) <= available:
                current.append(rest)
                current_bytes += len(rest.encode("utf-8"))
                break
            segment, rest = _take_utf8_prefix(rest, available)
            if segment:
                current.append(segment)
                current_bytes += len(segment.encode("utf-8"))
            flush()
    flush()
    return chunks


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


async def batch_retry_tasks_impl(db: Session, ids: str, safe_remove_fn, enqueue_fn) -> dict:
    """Retry multiple failed or completed tasks."""
    id_list = _parse_id_list(ids)
    if not id_list:
        return {"detail": "batch retried", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list), FileTask.status.in_((TaskStatus.FAILED, TaskStatus.COMPLETED))).all()
    for task in tasks:
        await asyncio.to_thread(safe_remove_fn, task.output_path)
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


def batch_download_markdown_tasks_impl(db: Session, ids: str, max_part_mb: int = 45) -> io.BytesIO:
    id_list = _parse_id_list(ids)
    if not id_list:
        raise HTTPException(400, "No valid task IDs")
    max_part_mb = max(1, min(max_part_mb, 50))
    max_bytes = max_part_mb * 1024 * 1024
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list), FileTask.status == TaskStatus.COMPLETED).all()
    if not tasks:
        raise HTTPException(400, "No completed tasks found")

    entries: list[tuple[FileTask, str]] = []
    for task in tasks:
        if task.output_path and os.path.exists(task.output_path):
            md_path = _find_markdown_output(task.output_path)
            if md_path:
                entries.append((task, md_path))
    if not entries:
        raise HTTPException(404, "No Markdown outputs found on disk")

    used: set[str] = set()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for task, md_path in entries:
            with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            arc_name = _unique_archive_name(_archive_markdown_name(task), used)
            parts = _split_markdown(content, max_bytes)
            if len(parts) == 1:
                zf.writestr(arc_name, parts[0])
                continue
            root, ext = os.path.splitext(arc_name)
            for idx, part in enumerate(parts, start=1):
                zf.writestr(f"{root}.part{idx:02d}{ext}", part)
    buf.seek(0)
    return buf
