"""Batch service — business logic for batch task operations."""
import os
import io
import json
import zipfile
import asyncio

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import FileTask, TaskStatus, add_log, _iso


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
            return (ch, text[idx + 1:]) if idx == 0 else (text[:idx], text[idx:])
        total += size
    return text, ""


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _split_oversized_block(text: str, max_bytes: int) -> list[str]:
    parts: list[str] = []
    rest = text
    while rest:
        segment, rest = _take_utf8_prefix(rest, max_bytes)
        if segment:
            parts.append(segment)
    return parts


def _split_markdown(content: str, max_bytes: int) -> list[str]:
    if _byte_len(content) <= max_bytes:
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

    def append_block(block: str) -> None:
        nonlocal current_bytes
        block_bytes = _byte_len(block)
        if block_bytes > max_bytes:
            flush()
            chunks.extend(_split_oversized_block(block, max_bytes))
            return
        if current and current_bytes + block_bytes > max_bytes:
            flush()
        current.append(block)
        current_bytes += block_bytes

    block: list[str] = []
    for line in content.splitlines(keepends=True):
        if line.startswith("#") and block:
            append_block("".join(block))
            block = []
        block.append(line)
        if not line.strip():
            append_block("".join(block))
            block = []
    if block:
        append_block("".join(block))
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


async def batch_retry_tasks_impl(db: Session, ids: str | None, batch_id: str | None, failed_only: bool, safe_remove_fn, enqueue_fn) -> dict:
    """Retry multiple failed or completed tasks."""
    statuses = (TaskStatus.FAILED,) if failed_only else (TaskStatus.FAILED, TaskStatus.COMPLETED)
    if batch_id:
        tasks = db.query(FileTask).filter(FileTask.batch_id == batch_id, FileTask.status.in_(statuses)).all()
    else:
        id_list = _parse_id_list(ids or "")
        if not id_list:
            return {"detail": "batch retried", "count": 0}
        tasks = db.query(FileTask).filter(FileTask.id.in_(id_list), FileTask.status.in_(statuses)).all()
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


def _build_markdown_export_plan_for_tasks(tasks: list[FileTask], selected_count: int, max_part_mb: int = 45) -> dict:
    if not tasks:
        raise HTTPException(400, "No completed tasks found")
    max_part_mb = max(1, min(max_part_mb, 50))
    max_bytes = max_part_mb * 1024 * 1024

    used: set[str] = set()
    files: list[dict] = []
    zip_files: list[dict] = []
    skipped = 0
    for task in tasks:
        if not task.output_path or not os.path.exists(task.output_path):
            skipped += 1
            continue
        md_path = _find_markdown_output(task.output_path)
        if not md_path:
            skipped += 1
            continue
        with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        arc_name = _unique_archive_name(_archive_markdown_name(task), used)
        parts = _split_markdown(content, max_bytes)
        root, ext = os.path.splitext(arc_name)
        archive_files: list[str] = []
        markdown_bytes = 0
        for idx, part in enumerate(parts, start=1):
            part_name = arc_name if len(parts) == 1 else f"{root}.part{idx:02d}{ext}"
            part_bytes = _byte_len(part)
            archive_files.append(part_name)
            markdown_bytes += part_bytes
            zip_files.append({"path": part_name, "content": part})
        files.append({
            "task_id": task.id,
            "original_filename": task.original_filename,
            "archive_files": archive_files,
            "markdown_bytes": markdown_bytes,
            "parts": len(parts),
            "split": len(parts) > 1,
            "completed_at": _iso(task.completed_at),
        })
    if not files:
        raise HTTPException(404, "No Markdown outputs found on disk")

    total_parts = sum(item["parts"] for item in files)
    total_bytes = sum(item["markdown_bytes"] for item in files)
    return {
        "selected_tasks": selected_count,
        "completed_tasks": len(tasks),
        "exported_tasks": len(files),
        "skipped_tasks": skipped,
        "max_part_mb": max_part_mb,
        "max_part_bytes": max_bytes,
        "total_markdown_bytes": total_bytes,
        "total_parts": total_parts,
        "manifest_name": "manifest.json",
        "files": files,
        "_zip_files": zip_files,
    }


def _build_markdown_export_plan(db: Session, ids: str | None, batch_id: str | None, max_part_mb: int = 45) -> dict:
    if batch_id:
        tasks = db.query(FileTask).filter(
            FileTask.batch_id == batch_id,
            FileTask.status == TaskStatus.COMPLETED,
        ).order_by(FileTask.id.asc()).all()
        return _build_markdown_export_plan_for_tasks(tasks, len(tasks), max_part_mb)

    id_list = _parse_id_list(ids or "")
    if not id_list:
        raise HTTPException(400, "No valid task IDs or batch ID")
    tasks = db.query(FileTask).filter(
        FileTask.id.in_(id_list),
        FileTask.status == TaskStatus.COMPLETED,
    ).order_by(FileTask.id.asc()).all()
    return _build_markdown_export_plan_for_tasks(tasks, len(id_list), max_part_mb)


def batch_download_markdown_tasks_impl(db: Session, ids: str | None = None, batch_id: str | None = None, max_part_mb: int = 45, include_manifest: bool = False) -> io.BytesIO:
    plan = _build_markdown_export_plan(db, ids, batch_id, max_part_mb)
    manifest = {k: v for k, v in plan.items() if not k.startswith("_")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_manifest:
            zf.writestr(plan["manifest_name"], json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in plan["_zip_files"]:
            zf.writestr(item["path"], item["content"])
    buf.seek(0)
    return buf
