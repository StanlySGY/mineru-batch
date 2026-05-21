import os
import re
import uuid
import json
import io
import zipfile
import shutil
import subprocess
import threading
import traceback
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse
import aiofiles
import httpx
import html
import markdown
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query, Request, Header
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models import (
    FileTask, TaskStatus, OutputFormat, ProcessLog, LogLevel, AppSetting,
    get_db, SessionLocal, add_log,
)
from error_codes import ErrorCode, with_code
from services.upload_service import (
    parse_bool, is_doc_file, validate_upload_params, prepare_batch_info,
    parse_relative_paths, generate_save_path, save_upload_stream, build_file_task,
    ALLOWED_EXTENSIONS as _UPLOAD_ALLOWED_EXT, MAX_FILE_SIZE as _UPLOAD_MAX_SIZE,
)
from services.task_service import (
    mark_task_cancelled, is_task_cancelled, unmark_task_cancelled, cancel_task_impl, retry_task_impl,
)
from services.storage_service import clean_directory, clean_storage_impl, clean_completed_sources_impl
from services.log_service import clear_logs_impl, get_grouped_logs_impl, list_logs_impl
from services.stats_service import get_stats_trend_impl, get_filetype_stats_impl
from services.settings_service import (
    get_settings_from_db, sanitize_settings, validate_settings_payload, save_settings, get_endpoint_api_key,
)
from services.report_service import get_stats_impl, get_quality_report_impl
from services.query_service import get_tasks_since_impl, list_tasks_impl, get_task_impl
from services.batch_service import batch_delete_tasks_impl, batch_retry_tasks_impl, batch_convert_tasks_impl, batch_download_tasks_impl
from services.content_service import preview_result_impl, update_task_content_impl, download_result_impl
from services.task_management_service import delete_task_impl, update_task_impl
from services.system_service import test_connection_impl
from services.document_service import convert_doc_to_pdf_impl
from services.storage_stats_service import get_storage_stats_impl

router = APIRouter()

# 限流：上传接口 10次/分钟
from limiter import limiter as _limiter

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs"))
CONVERT_DIR = os.environ.get("CONVERT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "converted"))
ALLOW_PRIVATE_ENDPOINTS = os.environ.get("ALLOW_PRIVATE_ENDPOINTS", "true").lower() in ("1", "true", "yes")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CONVERT_DIR, exist_ok=True)

DOC_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
MAX_ZIP_ENTRIES = 1000
MAX_ZIP_UNCOMPRESSED_SIZE = 500 * 1024 * 1024
_lo_semaphore = asyncio.Semaphore(2)
_rr_counter = 0
_rr_lock = threading.Lock()
_task_semaphore = asyncio.Semaphore(5)
_max_concurrency = 5
_SAFE_DIRS = (os.path.normpath(UPLOAD_DIR), os.path.normpath(OUTPUT_DIR), os.path.normpath(CONVERT_DIR))

# 工作池：避免 create_task 风暴（优先级队列，值越小优先级越高）
_task_queue: asyncio.PriorityQueue[tuple[int, int]] = asyncio.PriorityQueue()
_workers: list[asyncio.Task] = []

BLOCKED_URL_HOSTS = {"localhost", "localhost.localdomain"}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
body{{max-width:900px;margin:40px auto;font-family:system-ui,sans-serif;line-height:1.8;color:#333;padding:0 20px}}
h1,h2,h3{{margin-top:24px}}h1{{font-size:1.6em;border-bottom:1px solid #ddd;padding-bottom:8px}}
h2{{font-size:1.3em}}h3{{font-size:1.1em}}
code{{background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:0.9em}}
pre{{background:#f4f4f4;padding:16px;border-radius:6px;overflow-x:auto}}
pre code{{background:none;padding:0}}
table{{border-collapse:collapse;margin:16px 0}}th,td{{border:1px solid #ddd;padding:8px 12px}}th{{background:#f8f8f8}}
blockquote{{border-left:4px solid #ddd;padding-left:16px;color:#666;margin:12px 0}}
img{{max-width:100%;border-radius:4px}}
</style></head><body>
{md_html}
</body></html>"""


def _find_content_in_bundle(bundle_dir: str) -> str:
    for root, _, files in os.walk(bundle_dir):
        for fn in files:
            if fn.endswith(".md") or fn.endswith(".txt"):
                with open(os.path.join(root, fn), "r", encoding="utf-8") as f:
                    return f.read()
    return ""


def _is_public_ip(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_external_url(url: str, label: str = "URL", allow_private: bool = False) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, f"{label} must be http or https URL")
    if allow_private:
        return value
    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_URL_HOSTS:
        raise HTTPException(400, f"{label} host is not allowed")
    try:
        addresses = [host] if re.fullmatch(r"[0-9a-fA-F:.]+", host) else socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = [item if isinstance(item, str) else item[4][0] for item in addresses]
        if not ips or any(not _is_public_ip(ip) for ip in ips):
            raise HTTPException(400, f"{label} host is not allowed")
    except HTTPException:
        raise
    except (OSError, ValueError):
        raise HTTPException(400, f"{label} host cannot be resolved")
    return value


def require_admin(x_admin_api_key: str | None = Header(None)):
    if not ADMIN_API_KEY:
        return
    if x_admin_api_key != ADMIN_API_KEY:
        raise HTTPException(401, "Admin authorization required")




def _safe_path(path: str) -> str:
    target = Path(path).resolve()
    for d in _SAFE_DIRS:
        if target.is_relative_to(Path(d).resolve()):
            return str(target)
    raise HTTPException(403, "Access denied")


def _safe_remove(path: str):
    """Remove file or directory, ignore errors."""
    if not path or not os.path.exists(path):
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError:
        pass


def set_concurrency(n: int):
    global _task_semaphore, _max_concurrency
    _max_concurrency = max(1, min(n, 20))
    _task_semaphore = asyncio.Semaphore(_max_concurrency)


def _enqueue_task(task_id: int, priority: int = 0):
    # 优先级反转：priority 2=紧急 → queue 值 0（最高），priority 0=普通 → queue 值 2（最低）
    _task_queue.put_nowait((2 - priority, task_id))


async def _worker_loop(worker_id: int):
    while True:
        _, task_id = await _task_queue.get()
        try:
            await _process_task(task_id)
        except Exception:
            pass
        finally:
            _task_queue.task_done()


def start_workers(n: int = 0):
    global _workers
    if _workers:
        return
    count = n or _max_concurrency
    _workers = [asyncio.create_task(_worker_loop(i), name=f"worker-{i}") for i in range(count)]


def stop_workers():
    global _workers
    for w in _workers:
        w.cancel()
    _workers = []


# SSE 事件总线
_sse_subscribers: list[asyncio.Queue] = []
_sse_lock = asyncio.Lock()


def _emit_event(event_type: str, task_id: int, data: dict = None):
    payload = json.dumps({"type": event_type, "task_id": task_id, **(data or {})}, ensure_ascii=False)
    for q in _sse_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def _notify_task_change(task_id: int, status: str, **extra):
    _emit_event("task_update", task_id, {"status": status, **extra})


def _send_webhook_sync(task: FileTask, content: str = None):
    if not task.webhook_url:
        return
    try:
        _validate_external_url(task.webhook_url, "webhook_url", allow_private=ALLOW_PRIVATE_ENDPOINTS)
        payload = {
            "task_id": task.id,
            "filename": task.original_filename,
            "status": task.status.value,
            "output_format": task.output_format.value if task.output_format else None,
            "error_message": task.error_message,
        }
        if content:
            payload["content"] = content[:50000]
        with httpx.Client(timeout=30) as client:
            resp = client.post(task.webhook_url, json=payload)
            add_log(f"Webhook 推送: HTTP {resp.status_code}", task_id=task.id,
                    level="info" if resp.status_code < 400 else "warn",
                    detail=f"url={task.webhook_url}\nstatus={resp.status_code}")
    except Exception as e:
        add_log(f"Webhook 推送失败: {e}", task_id=task.id, level="warn")


async def _send_webhook(task: FileTask, content: str = None):
    await asyncio.to_thread(_send_webhook_sync, task, content)


def _pick_endpoint(endpoints: list[dict]) -> dict:
    global _rr_counter
    enabled = [e for e in endpoints if e.get("enabled", True)]
    if not enabled:
        raise RuntimeError(with_code(ErrorCode.NO_AVAILABLE_NODE, "没有可用的 MinerU 服务节点"))
    with _rr_lock:
        idx = _rr_counter % len(enabled)
        _rr_counter += 1
    return enabled[idx]


def _sanitize_filename(name: str) -> str:
    name = os.path.splitext(name)[0]
    name = re.sub(r'[\s\\/:*?"<>|]', '_', name)
    name = re.sub(r'[^\w\-.\u4e00-\u9fff]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or 'output'


def _save_upload(file: UploadFile) -> tuple[str, str]:
    ext = os.path.splitext(file.filename)[1] or ".pdf"
    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, saved_name)
    return saved_name, save_path


def _safe_extract_zip(zip_path: str, dest_dir: str):
    dest = Path(dest_dir).resolve()
    total_size = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise RuntimeError(with_code(ErrorCode.MINERU_API_ERROR, "ZIP 文件数量超限"))
        for info in infos:
            total_size += info.file_size
            if total_size > MAX_ZIP_UNCOMPRESSED_SIZE:
                raise RuntimeError(with_code(ErrorCode.MINERU_API_ERROR, "ZIP 解压体积超限"))
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest):
                raise RuntimeError(with_code(ErrorCode.MINERU_API_ERROR, "ZIP 包含非法路径"))
        zf.extractall(dest)


async def _save_upload_stream(file: UploadFile, save_path: str) -> int:
    size = 0
    async with aiofiles.open(save_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                await out.close()
                _safe_remove(save_path)
                raise HTTPException(400, f"文件 {file.filename} 超过大小限制({MAX_FILE_SIZE // 1024 // 1024}MB)")
            await out.write(chunk)
    return size


def _is_doc_file(filename: str) -> bool:
    return is_doc_file(filename)


def _convert_to_pdf_sync(input_path: str, task_id: int) -> str:
    out_dir = CONVERT_DIR
    profile_dir = os.path.join(CONVERT_DIR, f".lo_profile_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile_dir, exist_ok=True)
    cmd = [
        "libreoffice", "--headless", "--convert-to", "pdf",
        f"-env:UserInstallation=file://{profile_dir}",
        "--outdir", out_dir, input_path,
    ]
    add_log(f"LibreOffice 转换开始", task_id=task_id,
            detail=f"cmd={' '.join(cmd)}\ninput={os.path.basename(input_path)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": "/tmp"}
        )
        if result.returncode != 0:
            raise RuntimeError(with_code(ErrorCode.DOC_CONVERT_FAIL, f"LibreOffice exit {result.returncode}: {result.stderr[:500] or result.stdout[:500]}"))
        base = os.path.splitext(os.path.basename(input_path))[0]
        pdf_path = os.path.join(out_dir, f"{base}.pdf")
        if not os.path.exists(pdf_path):
            for f in os.listdir(out_dir):
                if f.lower().endswith(".pdf"):
                    cand = os.path.join(out_dir, f)
                    if abs(os.path.getmtime(cand) - os.path.getmtime(input_path)) < 60:
                        pdf_path = cand
                        break
        if not os.path.exists(pdf_path):
            raise RuntimeError(with_code(ErrorCode.PDF_NOT_GENERATED, "PDF 文件未生成"))
        add_log(f"转换完成: {os.path.basename(pdf_path)}", task_id=task_id)
        return pdf_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(with_code(ErrorCode.DOC_CONVERT_TIMEOUT, "LibreOffice 转换超时(120s)"))
    except Exception as e:
        add_log(f"转换失败: {e}", task_id=task_id, level="error", detail=traceback.format_exc())
        raise
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


async def _convert_to_pdf(input_path: str, task_id: int) -> str:
    return await asyncio.to_thread(_convert_to_pdf_sync, input_path, task_id)


def _build_mineru_form(task: FileTask) -> dict:
    bool_fields = {
        "formula_enable": task.formula_enable,
        "table_enable": task.table_enable,
        "return_md": task.return_md,
        "return_middle_json": task.return_middle_json,
        "return_model_output": task.return_model_output,
        "return_content_list": task.return_content_list,
        "return_images": task.return_images,
        "response_format_zip": task.response_format_zip,
        "replace_image_url": task.replace_image_url,
    }
    data = {
        "backend": task.backend,
        "server_url": task.server_url,
        "parse_method": task.parse_method,
        "lang_list": task.lang_list,
        "output_dir": "./output",
        "start_page_id": str(task.start_page_id),
        "end_page_id": str(task.end_page_id),
    }
    for k, v in bool_fields.items():
        data[k] = "true" if v else "false"
    return data


def _call_mineru_sync(task: FileTask, task_id: int, file_to_parse: str) -> dict:
    api_url = _validate_external_url(task.mineru_api, "mineru_api", allow_private=ALLOW_PRIVATE_ENDPOINTS)
    _validate_external_url(task.server_url, "server_url", allow_private=ALLOW_PRIVATE_ENDPOINTS)
    timeout = task.timeout or 600
    add_log(f"开始调用 MinerU API", task_id=task_id,
            detail=f"api={api_url}\nbackend={task.backend}\nserver_url={task.server_url}\nparse_method={task.parse_method}\nfile={os.path.basename(file_to_parse)}\ntimeout={timeout}s")
    try:
        file_size = os.path.getsize(file_to_parse)
        add_log(f"文件大小 {file_size} 字节，开始流式上传", task_id=task_id)
        form_data = _build_mineru_form(task)
        add_log(f"发送参数", task_id=task_id, detail=json.dumps(form_data, ensure_ascii=False))
        headers = {}
        api_key = task.api_key if hasattr(task, 'api_key') else None
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        with httpx.Client(timeout=timeout) as client:
            with open(file_to_parse, "rb") as f:
                resp = client.post(
                    api_url,
                    files={"files": (os.path.basename(file_to_parse), f, "application/octet-stream")},
                    data=form_data,
                    headers=headers,
                )
            add_log(f"MinerU 响应: HTTP {resp.status_code}", task_id=task_id,
                    level="info" if resp.status_code == 200 else "error",
                    detail=f"status={resp.status_code}\ncontent_type={resp.headers.get('content-type','')}\nbody_preview={resp.text[:2000] if resp.headers.get('content-type','').startswith('application/json') else '(binary)'}")
            if resp.status_code != 200:
                raise RuntimeError(with_code(ErrorCode.MINERU_API_ERROR, f"MinerU API error {resp.status_code}: {resp.text[:500]}"))
            content_type = resp.headers.get("content-type", "")
            if "application/zip" in content_type or "application/octet-stream" in content_type:
                add_log(f"MinerU 返回 ZIP 流，保存中...", task_id=task_id)
                bundle_dir = os.path.join(OUTPUT_DIR, f"_bundle_{task_id}")
                os.makedirs(bundle_dir, exist_ok=True)
                zip_path = os.path.join(bundle_dir, "mineru_raw.zip")
                with open(zip_path, "wb") as zf:
                    zf.write(resp.content)
                _safe_extract_zip(zip_path, bundle_dir)
                os.remove(zip_path)
                add_log(f"ZIP 已解压到 {bundle_dir}", task_id=task_id)
                md_content = _find_content_in_bundle(bundle_dir)
                return {"_bundle_dir": bundle_dir, "results": {os.path.splitext(task.original_filename)[0]: {"md_content": md_content}}}
            return resp.json()
    except httpx.ConnectError as e:
        add_log(f"连接 MinerU 失败", task_id=task_id, level="error", detail=str(e))
        raise RuntimeError(with_code(ErrorCode.MINERU_CONNECT_FAIL, f"连接 MinerU 失败: {e}"))
    except httpx.TimeoutException as e:
        add_log(f"调用 MinerU 超时({timeout}s)", task_id=task_id, level="error", detail=str(e))
        raise RuntimeError(with_code(ErrorCode.MINERU_TIMEOUT, f"调用 MinerU 超时({timeout}s): {e}"))
    except json.JSONDecodeError as e:
        add_log(f"MinerU 响应非 JSON", task_id=task_id, level="error", detail=f"{e}\nbody_preview={resp.text[:500]}")
        raise RuntimeError(with_code(ErrorCode.MINERU_API_ERROR, f"MinerU 响应非 JSON: {e}"))
    except Exception as e:
        add_log(f"调用 MinerU 异常: {type(e).__name__}", task_id=task_id, level="error", detail=traceback.format_exc())
        raise


def _extract_md_from_result(result: dict, original_filename: str) -> str:
    results = result.get("results", {})
    stem = os.path.splitext(original_filename)[0]
    file_result = results.get(stem) or results.get(original_filename)
    if file_result and isinstance(file_result, dict):
        return file_result.get("md_content", "")
    for key, val in results.items():
        if isinstance(val, dict) and val.get("md_content"):
            return val["md_content"]
    return ""


def _is_cancelled(task_id: int) -> bool:
    return is_task_cancelled(task_id)


def _check_and_mark_cancelled(task: FileTask, db, cleanup_path: str = None) -> bool:
    """如果任务已取消则标记 FAILED 并提交，返回 True 表示调用方应立即 return"""
    if not _is_cancelled(task.id):
        return False
    if cleanup_path and os.path.exists(cleanup_path):
        os.remove(cleanup_path)
    task.status = TaskStatus.FAILED
    task.error_message = "任务已取消"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return True


def _process_task_sync(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(FileTask).filter(FileTask.id == task_id).first()
        if not task or _check_and_mark_cancelled(task, db):
            return

        file_to_parse = task.file_path

        if _is_doc_file(task.original_filename):
            if task.pdf_path and os.path.exists(task.pdf_path):
                file_to_parse = task.pdf_path
                add_log(f"使用已转换的 PDF: {os.path.basename(file_to_parse)}", task_id=task_id)
            else:
                add_log(f"检测到文档格式，先转换为 PDF", task_id=task_id)
                try:
                    pdf_path = _convert_to_pdf_sync(task.file_path, task_id)
                    task.pdf_path = pdf_path
                    file_to_parse = pdf_path
                    db.commit()
                except Exception as e:
                    raise RuntimeError(f"文档转 PDF 失败: {e}")

        if _check_and_mark_cancelled(task, db):
            return

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        db.commit()
        add_log(f"任务开始处理", task_id=task_id)
        _notify_task_change(task_id, "processing")

        if _check_and_mark_cancelled(task, db): return

        result = _call_mineru_sync(task, task_id, file_to_parse)

        md_content = _extract_md_from_result(result, task.original_filename)
        if not md_content:
            add_log(f"MinerU 返回结果中未找到 md_content", task_id=task_id, level="warn",
                    detail=f"result_keys={list(result.keys())}\nfull={json.dumps(result, ensure_ascii=False)[:2000]}")
            md_content = json.dumps(result, ensure_ascii=False, indent=2)

        original_stem = _sanitize_filename(task.original_filename)
        ext = task.output_format.value
        bundle_dir = result.get("_bundle_dir")

        output_content = md_content
        if ext == "html":
            import markdown as md_lib
            md_html = md_lib.markdown(
                md_content,
                extensions=['tables', 'fenced_code', 'codehilite', 'toc'],
            )
            escaped_title = html.escape(original_stem)
            output_content = _HTML_TEMPLATE.format(title=escaped_title, md_html=md_html)

        if bundle_dir and os.path.isdir(bundle_dir):
            final_bundle = os.path.join(OUTPUT_DIR, f"{task.id}_{original_stem}")
            if os.path.exists(final_bundle):
                shutil.rmtree(final_bundle)
            shutil.move(bundle_dir, final_bundle)
            out_path = os.path.join(final_bundle, f"output.{ext}")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            add_log(f"Bundle 已保存: {final_bundle} (含 images/json/md)", task_id=task_id)
        else:
            out_name = f"{original_stem}.{ext}"
            out_path = os.path.join(OUTPUT_DIR, out_name)
            counter = 1
            while os.path.exists(out_path):
                out_name = f"{original_stem}_{counter}.{ext}"
                out_path = os.path.join(OUTPUT_DIR, out_name)
                counter += 1
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            add_log(f"结果已保存: {out_name} ({len(md_content)} 字符)", task_id=task_id)
        if _check_and_mark_cancelled(task, db, cleanup_path=out_path): return
        task.output_path = out_path
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        _notify_task_change(task_id, "completed")
        _send_webhook_sync(task, md_content[:50000])
    except Exception as e:
        task = db.query(FileTask).filter(FileTask.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            add_log(f"任务失败: {e}", task_id=task_id, level="error", detail=traceback.format_exc())
            _notify_task_change(task_id, "failed", error_message=str(e))
            _send_webhook_sync(task)
    finally:
        unmark_task_cancelled(task_id)
        db.close()


async def _process_task(task_id: int):
    async with _task_semaphore:
        await asyncio.to_thread(_process_task_sync, task_id)


@router.get("/concurrency")
async def get_concurrency():
    return {"concurrency": _max_concurrency}


@router.put("/concurrency")
async def set_concurrency_endpoint(body: dict, _: None = Depends(require_admin)):
    n = body.get("concurrency", 5)
    if not isinstance(n, int) or n < 1 or n > 20:
        raise HTTPException(400, "concurrency must be 1-20")
    set_concurrency(n)
    return {"concurrency": _max_concurrency}


@router.post("/test-connection")
async def test_connection(body: dict = None):
    return await test_connection_impl(body, _validate_external_url, ALLOW_PRIVATE_ENDPOINTS)


@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)):
    return sanitize_settings(get_settings_from_db(db))


@router.put("/settings")
async def update_settings(body: dict, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    current = get_settings_from_db(db)
    saved = save_settings(db, validate_settings_payload(body or {}, current))
    return sanitize_settings(saved)


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    return get_stats_impl(db)


@router.get("/reports/quality")
async def get_quality_report(db: Session = Depends(get_db)):
    stats = get_stats_impl(db)
    return get_quality_report_impl(db, stats)


@router.get("/tasks/events")
async def task_events():
    async def _stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        async with _sse_lock:
            _sse_subscribers.append(q)
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            async with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)
    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/tasks/since")
async def tasks_since(since: str = Query(..., description="ISO timestamp"), db: Session = Depends(get_db)):
    return get_tasks_since_impl(db, since)


# Constants moved to services.upload_service
MAX_FILE_SIZE = _UPLOAD_MAX_SIZE
ALLOWED_EXTENSIONS = _UPLOAD_ALLOWED_EXT


@router.post("/upload")
@_limiter.limit("10/minute")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    backend: str = Form("hybrid-http-client"),
    mineru_api: str = Form("http://localhost:8086/file_parse"),
    server_url: str = Form("http://localhost:6002/v1"),
    mineru_endpoints: str = Form(None),
    parse_method: str = Form("auto"),
    lang_list: str = Form("ch"),
    formula_enable: str = Form("true"),
    table_enable: str = Form("true"),
    return_md: str = Form("true"),
    return_middle_json: str = Form("true"),
    return_model_output: str = Form("true"),
    return_content_list: str = Form("false"),
    return_images: str = Form("false"),
    response_format_zip: str = Form("false"),
    replace_image_url: str = Form("true"),
    start_page_id: str = Form("0"),
    end_page_id: str = Form("99999"),
    output_format: str = Form("md"),
    timeout: str = Form("600"),
    auto_convert: str = Form("true"),
    relative_paths: str = Form(None),
    webhook_url: str = Form(None),
    api_key: str = Form(None),
    batch_id: str = Form(None),
    batch_name: str = Form(None),
    priority: str = Form("0"),
    db: Session = Depends(get_db),
):
    if output_format not in ("md", "txt", "html"):
        raise HTTPException(400, "output_format must be md, txt or html")

    _start_page, _end_page, _timeout, _priority = validate_upload_params(
        output_format, start_page_id, end_page_id, timeout, priority
    )

    upload_batch_id, upload_batch_name = prepare_batch_info(batch_id, batch_name)

    endpoints_list = None
    if mineru_endpoints:
        try:
            raw_endpoints = json.loads(mineru_endpoints)
            if isinstance(raw_endpoints, list):
                endpoints_list = [_validate_endpoint(ep) for ep in raw_endpoints]
        except json.JSONDecodeError:
            endpoints_list = None
    if not endpoints_list:
        mineru_api = _validate_external_url(mineru_api, "mineru_api", allow_private=ALLOW_PRIVATE_ENDPOINTS)
        server_url = _validate_external_url(server_url, "server_url", allow_private=ALLOW_PRIVATE_ENDPOINTS)
    if webhook_url:
        webhook_url = _validate_external_url(webhook_url, "webhook_url", allow_private=ALLOW_PRIVATE_ENDPOINTS)

    results = []
    rel_paths = parse_relative_paths(relative_paths)

    for idx, file in enumerate(files):
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型: {ext}，允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        saved_name, save_path = generate_save_path(file, UPLOAD_DIR)
        file_size = await save_upload_stream(file, save_path)

        original_name = file.filename
        if idx < len(rel_paths) and rel_paths[idx] and "/" in rel_paths[idx]:
            original_name = rel_paths[idx].replace("/", "_")

        ep = _pick_endpoint(endpoints_list) if endpoints_list else None
        selected_api = ep.get("apiKey") if ep else api_key
        selected_url = ep["url"] if ep else mineru_api
        selected_api = get_endpoint_api_key(db, selected_url) or selected_api

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
        _notify_task_change(task.id, "pending")

        if is_doc_file(file.filename) and not parse_bool(auto_convert):
            add_log(f"文档格式文件，等待手动转换为 PDF", task_id=task.id)

    for r in results:
        tid = r["id"]
        task = db.query(FileTask).filter(FileTask.id == tid).first()
        if is_doc_file(task.original_filename) and not task.auto_convert_doc:
            continue
        _enqueue_task(tid, priority=getattr(task, 'priority', 0) or 0)

    return {"tasks": results}


@router.post("/tasks/{task_id}/convert")
async def convert_doc_to_pdf(task_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await convert_doc_to_pdf_impl(db, task_id, _is_doc_file, _convert_to_pdf, _enqueue_task)


@router.get("/tasks")
async def list_tasks(
    status: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    batch_id: str = Query(None),
    db: Session = Depends(get_db),
):
    return list_tasks_impl(db, status, search, page, size, batch_id)


@router.delete("/tasks/batch")
async def batch_delete_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await batch_delete_tasks_impl(db, ids, _safe_remove)


@router.post("/tasks/batch/retry")
async def batch_retry_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await batch_retry_tasks_impl(db, ids, _enqueue_task)


@router.post("/tasks/batch/convert")
async def batch_convert_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await batch_convert_tasks_impl(db, ids, _is_doc_file, _convert_to_pdf, _enqueue_task)


@router.get("/tasks/batch/download")
async def batch_download_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db)):
    buf = batch_download_tasks_impl(db, ids)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=mineru_batch_results.zip"},
    )


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    return get_task_impl(db, task_id)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await delete_task_impl(db, task_id, _safe_remove)


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    backend: str = Form(None),
    mineru_api: str = Form(None),
    server_url: str = Form(None),
    parse_method: str = Form(None),
    lang_list: str = Form(None),
    output_format: str = Form(None),
    timeout: str = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return update_task_impl(
        db, task_id, backend, mineru_api, server_url, parse_method, lang_list, output_format, timeout,
        _validate_external_url, ALLOW_PRIVATE_ENDPOINTS
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return cancel_task_impl(task_id, db)


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    mineru_api: str | None = Form(None),
    server_url: str | None = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return retry_task_impl(task_id, mineru_api, server_url, db, _validate_external_url, ALLOW_PRIVATE_ENDPOINTS, _enqueue_task)


@router.get("/tasks/{task_id}/preview")
async def preview_result(task_id: int, db: Session = Depends(get_db)):
    return await preview_result_impl(db, task_id, _safe_path)


@router.put("/tasks/{task_id}/content")
async def update_task_content(task_id: int, body: dict, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return await update_task_content_impl(db, task_id, body, _safe_path)


@router.get("/tasks/{task_id}/download")
async def download_result(task_id: int, db: Session = Depends(get_db)):
    result = download_result_impl(db, task_id, _safe_path, _sanitize_filename)
    if isinstance(result[0], io.BytesIO):
        buf, _, filename = result
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        path, format_val, filename = result
        return FileResponse(
            path,
            filename=filename,
            media_type="text/markdown" if format_val == "md" else "text/plain",
        )


@router.get("/logs")
async def list_logs(
    task_id: int = Query(None),
    level: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_logs_impl(db, task_id, level, page, size)


@router.get("/logs/grouped")
async def list_logs_grouped(
    level: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return await get_grouped_logs_impl(db, page, size, level)


@router.delete("/logs")
async def clear_logs(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    count = clear_logs_impl(db)
    return {"detail": "cleared", "count": count}


@router.get("/storage")
async def get_storage_stats():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mineru_batch.db")
    return get_storage_stats_impl(UPLOAD_DIR, OUTPUT_DIR, CONVERT_DIR, db_path)


@router.post("/storage/clean")
async def clean_storage(body: dict = None, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    targets = (body or {}).get("targets", [])
    cleaned = await clean_storage_impl(targets, OUTPUT_DIR, CONVERT_DIR, db)
    return {"detail": "cleaned", "counts": cleaned}


@router.post("/storage/clean-sources")
async def clean_completed_sources(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    result = await clean_completed_sources_impl(db)
    return {"detail": "cleaned", **result}


@router.get("/stats/trend")
async def get_stats_trend(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    return get_stats_trend_impl(db, days)


@router.get("/stats/filetypes")
async def get_filetype_stats(db: Session = Depends(get_db)):
    return get_filetype_stats_impl(db)
