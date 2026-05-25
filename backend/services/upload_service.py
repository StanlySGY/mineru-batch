"""Upload service — business logic extracted from routes.py upload endpoint."""
import os
import uuid
import json

import aiofiles
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from models import FileTask, OutputFormat, add_log


MAX_FILE_SIZE = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
}

DOC_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


def parse_bool(val: str) -> bool:
    """Parse a form boolean string to bool."""
    return val.lower() in ("true", "1", "yes")


def is_doc_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in DOC_EXTENSIONS


def validate_upload_params(
    output_format: str,
    start_page_id: str,
    end_page_id: str,
    timeout: str,
    priority: str,
) -> tuple[int, int, int, int]:
    """Validate and parse upload form parameters. Returns (start_page, end_page, timeout, priority)."""
    if output_format not in ("md", "txt", "html"):
        raise HTTPException(400, "output_format must be md, txt or html")
    try:
        _start_page = int(start_page_id)
        _end_page = int(end_page_id)
        _timeout = int(timeout)
        _priority = max(0, min(2, int(priority)))
    except ValueError:
        raise HTTPException(400, "start_page_id, end_page_id, timeout, priority must be integers")
    if _timeout < 10 or _timeout > 7200:
        raise HTTPException(400, "timeout must be between 10 and 7200 seconds")
    if _start_page < 0:
        raise HTTPException(400, "start_page_id must be >= 0")
    return _start_page, _end_page, _timeout, _priority


def prepare_batch_info(batch_id: str | None, batch_name: str | None) -> tuple[str, str | None]:
    """Return normalized (batch_id, batch_name)."""
    upload_batch_id = (batch_id or uuid.uuid4().hex).strip()[:64]
    upload_batch_name = (batch_name or "").strip()[:256] or None
    return upload_batch_id, upload_batch_name


def parse_relative_paths(relative_paths: str | None) -> list:
    if not relative_paths:
        return []
    try:
        return json.loads(relative_paths)
    except json.JSONDecodeError:
        return []


def normalize_relative_name(name: str | None, fallback: str) -> str:
    value = (name or "").replace("\\", "/")
    parts = [p.strip() for p in value.split("/") if p.strip() and p.strip() not in (".", "..")]
    return "/".join(parts) if parts else fallback


def generate_save_path(file: UploadFile, upload_dir: str) -> tuple[str, str]:
    """Generate saved filename and full save path."""
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(upload_dir, saved_name)
    return saved_name, save_path


async def save_upload_stream(file: UploadFile, save_path: str) -> int:
    """Stream file to disk, enforce size limit. Returns file size in bytes."""
    size = 0
    async with aiofiles.open(save_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                await out.close()
                try:
                    os.remove(save_path)
                except OSError:
                    pass
                raise HTTPException(400, f"文件 {file.filename} 超过大小限制({MAX_FILE_SIZE // 1024 // 1024}MB)")
            await out.write(chunk)
    return size


def build_file_task(
    *,
    original_name: str,
    saved_name: str,
    save_path: str,
    file_size: int,
    selected_url: str,
    selected_api: str | None,
    backend: str,
    server_url: str,
    parse_method: str,
    lang_list: str,
    formula_enable: str,
    table_enable: str,
    return_md: str,
    return_middle_json: str,
    return_model_output: str,
    return_content_list: str,
    return_images: str,
    response_format_zip: str,
    replace_image_url: str,
    start_page: int,
    end_page: int,
    output_format: str,
    timeout: int,
    auto_convert: str,
    webhook_url: str | None,
    batch_id: str,
    batch_name: str | None,
    priority: int,
    endpoint: dict | None = None,
) -> FileTask:
    """Construct a FileTask ORM instance from validated params."""
    return FileTask(
        original_filename=original_name,
        saved_filename=saved_name,
        file_path=save_path,
        file_size=file_size,
        mineru_api=selected_url,
        backend=endpoint.get("backend", backend) if endpoint else backend,
        server_url=endpoint.get("serverUrl", server_url) if endpoint else server_url,
        parse_method=parse_method,
        lang_list=lang_list,
        formula_enable=parse_bool(formula_enable),
        table_enable=parse_bool(table_enable),
        return_md=parse_bool(return_md),
        return_middle_json=parse_bool(return_middle_json),
        return_model_output=parse_bool(return_model_output),
        return_content_list=parse_bool(return_content_list),
        return_images=parse_bool(return_images),
        response_format_zip=parse_bool(response_format_zip),
        replace_image_url=parse_bool(replace_image_url),
        start_page_id=start_page,
        end_page_id=end_page,
        output_format=OutputFormat(output_format),
        timeout=timeout,
        auto_convert_doc=parse_bool(auto_convert),
        api_key=selected_api,
        webhook_url=webhook_url,
        batch_id=batch_id,
        batch_name=batch_name,
        priority=priority,
    )


async def upload_files_impl(
    db: Session,
    files: list[UploadFile],
    backend: str,
    mineru_api: str,
    server_url: str,
    mineru_endpoints: str | None,
    parse_method: str,
    lang_list: str,
    formula_enable: str,
    table_enable: str,
    return_md: str,
    return_middle_json: str,
    return_model_output: str,
    return_content_list: str,
    return_images: str,
    response_format_zip: str,
    replace_image_url: str,
    start_page_id: str,
    end_page_id: str,
    output_format: str,
    timeout: str,
    auto_convert: str,
    relative_paths: str | None,
    webhook_url: str | None,
    api_key: str | None,
    batch_id: str | None,
    batch_name: str | None,
    priority: str,
    upload_dir: str,
    allow_private_endpoints: bool,
    validate_endpoint_fn,
    validate_external_url_fn,
    pick_endpoint_fn,
    get_endpoint_api_key_fn,
    notify_task_change_fn,
    enqueue_task_fn,
) -> dict:
    """Upload files and create tasks. Returns dict with tasks list."""
    _start_page, _end_page, _timeout, _priority = validate_upload_params(
        output_format, start_page_id, end_page_id, timeout, priority
    )

    upload_batch_id, upload_batch_name = prepare_batch_info(batch_id, batch_name)

    endpoints_list = None
    if mineru_endpoints:
        try:
            raw_endpoints = json.loads(mineru_endpoints)
            if isinstance(raw_endpoints, list):
                endpoints_list = [validate_endpoint_fn(ep) for ep in raw_endpoints]
        except json.JSONDecodeError:
            endpoints_list = None
    if not endpoints_list:
        mineru_api = validate_external_url_fn(mineru_api, "mineru_api", allow_private=allow_private_endpoints)
        server_url = validate_external_url_fn(server_url, "server_url", allow_private=allow_private_endpoints)
    if webhook_url:
        webhook_url = validate_external_url_fn(webhook_url, "webhook_url", allow_private=allow_private_endpoints)

    results = []
    rel_paths = parse_relative_paths(relative_paths)

    for idx, file in enumerate(files):
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型: {ext}，允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        saved_name, save_path = generate_save_path(file, upload_dir)
        file_size = await save_upload_stream(file, save_path)

        original_name = normalize_relative_name(rel_paths[idx] if idx < len(rel_paths) else None, file.filename or saved_name)

        ep = pick_endpoint_fn(endpoints_list) if endpoints_list else None
        selected_api = ep.get("apiKey") if ep else api_key
        selected_url = ep["url"] if ep else mineru_api
        selected_api = get_endpoint_api_key_fn(db, selected_url) or selected_api

        task = build_file_task(
            original_name=original_name,
            saved_name=saved_name,
            save_path=save_path,
            file_size=file_size,
            selected_url=selected_url,
            selected_api=selected_api,
            backend=ep.get("backend", backend) if ep else backend,
            server_url=ep.get("serverUrl", server_url) if ep else server_url,
            parse_method=parse_method,
            lang_list=lang_list,
            formula_enable=formula_enable,
            table_enable=table_enable,
            return_md=return_md,
            return_middle_json=return_middle_json,
            return_model_output=return_model_output,
            return_content_list=return_content_list,
            return_images=return_images,
            response_format_zip=response_format_zip,
            replace_image_url=replace_image_url,
            start_page=_start_page,
            end_page=_end_page,
            output_format=output_format,
            timeout=_timeout,
            auto_convert=auto_convert,
            webhook_url=webhook_url,
            batch_id=upload_batch_id,
            batch_name=upload_batch_name,
            priority=_priority,
            endpoint=ep,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        results.append(task.to_dict())
        add_log(f"文件上传成功: {file.filename}", task_id=task.id)
        notify_task_change_fn(task.id, "pending")

        if is_doc_file(file.filename) and not parse_bool(auto_convert):
            add_log(f"文档格式文件，等待手动转换为 PDF", task_id=task.id)

    for r in results:
        tid = r["id"]
        task = db.query(FileTask).filter(FileTask.id == tid).first()
        if is_doc_file(task.original_filename) and not task.auto_convert_doc:
            continue
        enqueue_task_fn(tid, priority=getattr(task, 'priority', 0) or 0)

    return {"tasks": results}

