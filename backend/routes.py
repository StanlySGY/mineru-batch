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
import aiofiles
import httpx
import json as _json
import html
import markdown
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models import (
    FileTask, TaskStatus, OutputFormat, ProcessLog, LogLevel, AppSetting,
    get_db, SessionLocal, add_log,
)

router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs"))
CONVERT_DIR = os.environ.get("CONVERT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "converted"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CONVERT_DIR, exist_ok=True)

DOC_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_lo_semaphore = asyncio.Semaphore(2)
_rr_counter = 0
_rr_lock = threading.Lock()
_task_semaphore = asyncio.Semaphore(5)
_cancelled_tasks: set[int] = set()
_cancel_lock = threading.Lock()
_max_concurrency = 5
_SAFE_DIRS = (os.path.normpath(UPLOAD_DIR), os.path.normpath(OUTPUT_DIR), os.path.normpath(CONVERT_DIR))

# 工作池：避免 create_task 风暴
_task_queue: asyncio.Queue[int] = asyncio.Queue()
_workers: list[asyncio.Task] = []

DEFAULT_SETTINGS = {
    "defaults": {
        "backend": "hybrid-http-client",
        "mineruApi": "http://localhost:8086/file_parse",
        "serverUrl": "http://localhost:6002/v1",
        "outputFormat": "md",
        "parseMethod": "auto",
        "langList": "ch",
        "formulaEnable": True,
        "tableEnable": True,
        "returnMd": True,
        "returnMiddleJson": True,
        "returnModelOutput": True,
        "returnContentList": False,
        "returnImages": False,
        "responseFormatZip": False,
        "replaceImageUrl": True,
        "startPageId": 0,
        "endPageId": 99999,
        "timeout": 600,
        "autoConvert": True,
    },
    "mineruEndpoints": [
        {
            "url": "http://localhost:8086/file_parse",
            "backend": "hybrid-http-client",
            "serverUrl": "http://localhost:6002/v1",
            "enabled": True,
        }
    ],
}
SETTINGS_KEY = "app_settings"
MASKED_API_KEY = "********"


def _clone_default_settings() -> dict:
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def _settings_from_db(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    if not row:
        return _clone_default_settings()
    try:
        data = json.loads(row.value_json)
    except json.JSONDecodeError:
        return _clone_default_settings()
    defaults = {**DEFAULT_SETTINGS["defaults"], **data.get("defaults", {})}
    endpoints = data.get("mineruEndpoints")
    if not isinstance(endpoints, list) or not endpoints:
        endpoints = _clone_default_settings()["mineruEndpoints"]
    return {"defaults": defaults, "mineruEndpoints": endpoints}


def _sanitize_settings(data: dict) -> dict:
    sanitized = json.loads(json.dumps(data))
    for ep in sanitized.get("mineruEndpoints", []):
        key = ep.pop("apiKey", None)
        ep["hasApiKey"] = bool(key)
    return sanitized


def _validate_endpoint(ep: dict) -> dict:
    url = str(ep.get("url") or "").strip()
    server_url = str(ep.get("serverUrl") or "").strip()
    backend = str(ep.get("backend") or "hybrid-http-client").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "MinerU endpoint must be http or https URL")
    if server_url and not server_url.startswith(("http://", "https://")):
        raise HTTPException(400, "serverUrl must be http or https URL")
    if backend not in ("hybrid-http-client", "vlm-http-client"):
        raise HTTPException(400, "backend is invalid")
    clean = {
        "url": url,
        "backend": backend,
        "serverUrl": server_url or DEFAULT_SETTINGS["defaults"]["serverUrl"],
        "enabled": bool(ep.get("enabled", True)),
    }
    api_key = ep.get("apiKey")
    if isinstance(api_key, str) and api_key and api_key != MASKED_API_KEY:
        clean["apiKey"] = api_key
    return clean


def _validate_settings_payload(payload: dict, current: dict | None = None) -> dict:
    current = current or _clone_default_settings()
    raw_defaults = payload.get("defaults") or {}
    defaults = {**DEFAULT_SETTINGS["defaults"], **raw_defaults}
    try:
        defaults["timeout"] = int(defaults.get("timeout", 600))
        defaults["startPageId"] = int(defaults.get("startPageId", 0))
        defaults["endPageId"] = int(defaults.get("endPageId", 99999))
    except (TypeError, ValueError):
        raise HTTPException(400, "timeout and page range must be integers")
    if defaults["timeout"] < 10 or defaults["timeout"] > 7200:
        raise HTTPException(400, "timeout must be between 10 and 7200 seconds")
    if defaults["startPageId"] < 0 or defaults["endPageId"] < defaults["startPageId"]:
        raise HTTPException(400, "page range is invalid")
    if defaults["outputFormat"] not in ("md", "txt", "html"):
        raise HTTPException(400, "outputFormat is invalid")

    current_by_url = {ep.get("url"): ep for ep in current.get("mineruEndpoints", [])}
    endpoints = []
    for ep in payload.get("mineruEndpoints") or []:
        clean = _validate_endpoint(ep)
        old_key = current_by_url.get(clean["url"], {}).get("apiKey")
        if "apiKey" not in clean and old_key:
            clean["apiKey"] = old_key
        endpoints.append(clean)
    if not endpoints:
        endpoints = _clone_default_settings()["mineruEndpoints"]
    return {"defaults": defaults, "mineruEndpoints": endpoints}


def _save_settings(db: Session, data: dict) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    if not row:
        row = AppSetting(key=SETTINGS_KEY, value_json="{}")
        db.add(row)
    row.value_json = json.dumps(data, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return data


def _endpoint_key_from_settings(db: Session, url: str | None) -> str | None:
    if not url:
        return None
    settings = _settings_from_db(db)
    for ep in settings.get("mineruEndpoints", []):
        if ep.get("url") == url and ep.get("apiKey"):
            return ep.get("apiKey")
    return None


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


def _enqueue_task(task_id: int):
    _task_queue.put_nowait(task_id)


async def _worker_loop(worker_id: int):
    while True:
        task_id = await _task_queue.get()
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
    payload = _json.dumps({"type": event_type, "task_id": task_id, **(data or {})}, ensure_ascii=False)
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
        raise RuntimeError("没有可用的 MinerU 服务节点")
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


def _is_doc_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in DOC_EXTENSIONS


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
            raise RuntimeError(f"LibreOffice exit {result.returncode}: {result.stderr[:500] or result.stdout[:500]}")
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
            raise RuntimeError("PDF 文件未生成")
        add_log(f"转换完成: {os.path.basename(pdf_path)}", task_id=task_id)
        return pdf_path
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreOffice 转换超时(120s)")
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
    api_url = task.mineru_api
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
                raise RuntimeError(f"MinerU API error {resp.status_code}: {resp.text[:500]}")
            content_type = resp.headers.get("content-type", "")
            if "application/zip" in content_type or "application/octet-stream" in content_type:
                add_log(f"MinerU 返回 ZIP 流，保存中...", task_id=task_id)
                bundle_dir = os.path.join(OUTPUT_DIR, f"_bundle_{task_id}")
                os.makedirs(bundle_dir, exist_ok=True)
                zip_path = os.path.join(bundle_dir, "mineru_raw.zip")
                with open(zip_path, "wb") as zf:
                    zf.write(resp.content)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(bundle_dir)
                os.remove(zip_path)
                add_log(f"ZIP 已解压到 {bundle_dir}", task_id=task_id)
                md_content = ""
                for root, _, files in os.walk(bundle_dir):
                    for fn in files:
                        if fn.endswith(".md"):
                            with open(os.path.join(root, fn), "r", encoding="utf-8") as mf:
                                md_content = mf.read()
                            break
                    if md_content:
                        break
                if not md_content:
                    for root, _, files in os.walk(bundle_dir):
                        for fn in files:
                            if fn.endswith(".txt"):
                                with open(os.path.join(root, fn), "r", encoding="utf-8") as mf:
                                    md_content = mf.read()
                                break
                        if md_content:
                            break
                return {"_bundle_dir": bundle_dir, "results": {os.path.splitext(task.original_filename)[0]: {"md_content": md_content}}}
            return resp.json()
    except httpx.ConnectError as e:
        add_log(f"连接 MinerU 失败", task_id=task_id, level="error", detail=str(e))
        raise
    except httpx.TimeoutException as e:
        add_log(f"调用 MinerU 超时({timeout}s)", task_id=task_id, level="error", detail=str(e))
        raise
    except json.JSONDecodeError as e:
        add_log(f"MinerU 响应非 JSON", task_id=task_id, level="error", detail=f"{e}\nbody_preview={resp.text[:500]}")
        raise
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
    with _cancel_lock:
        return task_id in _cancelled_tasks


def _process_task_sync(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(FileTask).filter(FileTask.id == task_id).first()
        if not task or _is_cancelled(task_id):
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

        if _is_cancelled(task_id):
            task.status = TaskStatus.FAILED
            task.error_message = "任务已取消"
            db.commit()
            return

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        db.commit()
        add_log(f"任务开始处理", task_id=task_id)
        _notify_task_change(task_id, "processing")

        if _is_cancelled(task_id):
            task.status = TaskStatus.FAILED
            task.error_message = "任务已取消"
            db.commit()
            return

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
            output_content = (
                '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
                f'<title>{escaped_title}</title>'
                '<style>'
                'body{max-width:900px;margin:40px auto;font-family:system-ui,sans-serif;line-height:1.8;color:#333;padding:0 20px}'
                'h1,h2,h3{margin-top:24px}h1{font-size:1.6em;border-bottom:1px solid #ddd;padding-bottom:8px}'
                'h2{font-size:1.3em}h3{font-size:1.1em}'
                'code{background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:0.9em}'
                'pre{background:#f4f4f4;padding:16px;border-radius:6px;overflow-x:auto}'
                'pre code{background:none;padding:0}'
                'table{border-collapse:collapse;margin:16px 0}th,td{border:1px solid #ddd;padding:8px 12px}th{background:#f8f8f8}'
                'blockquote{border-left:4px solid #ddd;padding-left:16px;color:#666;margin:12px 0}'
                'img{max-width:100%;border-radius:4px}'
                '</style></head><body>'
                f'{md_html}'
                '</body></html>'
            )

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
        if _is_cancelled(task_id):
            if os.path.exists(out_path):
                os.remove(out_path)
            task.status = TaskStatus.FAILED
            task.error_message = "任务已取消"
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
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
        with _cancel_lock:
            _cancelled_tasks.discard(task_id)
        db.close()


async def _process_task(task_id: int):
    async with _task_semaphore:
        await asyncio.to_thread(_process_task_sync, task_id)


@router.get("/concurrency")
async def get_concurrency():
    return {"concurrency": _max_concurrency}


@router.put("/concurrency")
async def set_concurrency_endpoint(body: dict):
    n = body.get("concurrency", 5)
    if not isinstance(n, int) or n < 1 or n > 20:
        raise HTTPException(400, "concurrency must be 1-20")
    set_concurrency(n)
    return {"concurrency": _max_concurrency}


@router.post("/test-connection")
async def test_connection(body: dict = None):
    mineru_api = (body or {}).get("mineru_api", "")
    server_url = (body or {}).get("server_url", "")
    results = {}
    if mineru_api:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(mineru_api.replace("/file_parse", "/"))
                results["mineru"] = {"ok": resp.status_code < 500, "status": resp.status_code}
        except Exception as e:
            results["mineru"] = {"ok": False, "error": str(e)}
    if server_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{server_url.rstrip('/')}/models")
                results["server"] = {"ok": resp.status_code < 500, "status": resp.status_code}
        except Exception as e:
            results["server"] = {"ok": False, "error": str(e)}
    ok = all(r.get("ok") for r in results.values()) if results else False
    return {"ok": ok, "detail": results}


@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)):
    return _sanitize_settings(_settings_from_db(db))


@router.put("/settings")
async def update_settings(body: dict, db: Session = Depends(get_db)):
    current = _settings_from_db(db)
    saved = _save_settings(db, _validate_settings_payload(body or {}, current))
    return _sanitize_settings(saved)


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(FileTask.id)).scalar()
    by_status = (
        db.query(FileTask.status, func.count(FileTask.id))
        .group_by(FileTask.status)
        .all()
    )
    status_map = {s.value: c for s, c in by_status}
    avg_row = db.execute(text(
        "SELECT AVG(STRFTIME('%s', completed_at) - STRFTIME('%s', started_at)) * 1000 "
        "FROM file_tasks WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL"
    )).scalar()
    avg_duration_ms = float(avg_row) if avg_row else 0
    return {
        "total": total,
        "pending": status_map.get("pending", 0),
        "processing": status_map.get("processing", 0),
        "completed": status_map.get("completed", 0),
        "failed": status_map.get("failed", 0),
        "avg_duration_ms": avg_duration_ms,
    }


@router.get("/reports/quality")
async def get_quality_report(db: Session = Depends(get_db)):
    stats = await get_stats(db)
    done = stats["completed"] + stats["failed"]
    recent_failed = (
        db.query(FileTask)
        .filter(FileTask.status == TaskStatus.FAILED)
        .order_by(FileTask.id.desc())
        .limit(5)
        .all()
    )
    return {
        "total": stats["total"],
        "completed": stats["completed"],
        "failed": stats["failed"],
        "processing": stats["processing"],
        "pending": stats["pending"],
        "success_rate": round(stats["completed"] / done * 100, 1) if done else 0,
        "avg_duration_ms": stats["avg_duration_ms"],
        "recent_failures": [
            {
                "id": t.id,
                "filename": t.original_filename,
                "error_message": t.error_message,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in recent_failed
        ],
    }


@router.get("/tasks/events")
async def task_events():
    async def _stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        async with _sse_lock:
            _sse_subscribers.append(q)
        try:
            yield f"data: {_json.dumps({'type': 'connected'})}\n\n"
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
    try:
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format")
    tasks = db.query(FileTask).filter(FileTask.updated_at >= cutoff).all()
    return {"items": [t.to_dict() for t in tasks]}


MAX_FILE_SIZE = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
                      ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


@router.post("/upload")
async def upload_files(
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
    db: Session = Depends(get_db),
):
    if output_format not in ("md", "txt", "html"):
        raise HTTPException(400, "output_format must be md, txt or html")

    def _b(val: str) -> bool:
        return val.lower() in ("true", "1", "yes")

    try:
        _start_page = int(start_page_id)
        _end_page = int(end_page_id)
        _timeout = int(timeout)
    except ValueError:
        raise HTTPException(400, "start_page_id, end_page_id, timeout must be integers")
    if _timeout < 10 or _timeout > 7200:
        raise HTTPException(400, "timeout must be between 10 and 7200 seconds")
    if _start_page < 0:
        raise HTTPException(400, "start_page_id must be >= 0")

    upload_batch_id = (batch_id or uuid.uuid4().hex).strip()[:64]
    upload_batch_name = (batch_name or "").strip()[:256] or None

    endpoints_list = None
    if mineru_endpoints:
        try:
            endpoints_list = json.loads(mineru_endpoints)
        except json.JSONDecodeError:
            endpoints_list = None

    results = []
    rel_paths = []
    if relative_paths:
        try:
            rel_paths = json.loads(relative_paths)
        except json.JSONDecodeError:
            rel_paths = []

    for idx, file in enumerate(files):
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型: {ext}，允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, f"文件 {file.filename} 超过大小限制({MAX_FILE_SIZE // 1024 // 1024}MB)")
        await file.seek(0)
        saved_name, save_path = _save_upload(file)
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)

        original_name = file.filename
        if idx < len(rel_paths) and rel_paths[idx] and "/" in rel_paths[idx]:
            original_name = rel_paths[idx].replace("/", "_")

        ep = _pick_endpoint(endpoints_list) if endpoints_list else None
        selected_api = ep.get("apiKey") if ep else api_key
        selected_url = ep["url"] if ep else mineru_api
        selected_api = _endpoint_key_from_settings(db, selected_url) or selected_api
        task = FileTask(
            original_filename=original_name,
            saved_filename=saved_name,
            file_path=save_path,
            file_size=len(content),
            mineru_api=selected_url,
            backend=ep.get("backend", backend) if ep else backend,
            server_url=ep.get("serverUrl", server_url) if ep else server_url,
            parse_method=parse_method,
            lang_list=lang_list,
            formula_enable=_b(formula_enable),
            table_enable=_b(table_enable),
            return_md=_b(return_md),
            return_middle_json=_b(return_middle_json),
            return_model_output=_b(return_model_output),
            return_content_list=_b(return_content_list),
            return_images=_b(return_images),
            response_format_zip=_b(response_format_zip),
            replace_image_url=_b(replace_image_url),
            start_page_id=_start_page,
            end_page_id=_end_page,
            output_format=OutputFormat(output_format),
            timeout=_timeout,
            auto_convert_doc=_b(auto_convert),
            api_key=selected_api,
            webhook_url=webhook_url,
            batch_id=upload_batch_id,
            batch_name=upload_batch_name,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        results.append(task.to_dict())
        add_log(f"文件上传成功: {file.filename}", task_id=task.id)
        _notify_task_change(task.id, "pending")

        if _is_doc_file(file.filename) and not _b(auto_convert):
            add_log(f"文档格式文件，等待手动转换为 PDF", task_id=task.id)

    for r in results:
        tid = r["id"]
        task = db.query(FileTask).filter(FileTask.id == tid).first()
        if _is_doc_file(task.original_filename) and not task.auto_convert_doc:
            continue
        _enqueue_task(tid)

    return {"tasks": results}


@router.post("/tasks/{task_id}/convert")
async def convert_doc_to_pdf(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not _is_doc_file(task.original_filename):
        raise HTTPException(400, "Not a convertible document file")
    if task.pdf_path and os.path.exists(task.pdf_path):
        return {"detail": "already converted", "pdf_path": task.pdf_path}

    try:
        pdf_path = await _convert_to_pdf(task.file_path, task_id)
        task.pdf_path = pdf_path
        task.auto_convert_doc = True
        db.commit()
        add_log(f"手动转换完成，开始解析", task_id=task_id)
        _enqueue_task(task.id)
        return {"detail": "converted", "pdf_path": pdf_path}
    except Exception as e:
        raise HTTPException(500, f"Conversion failed: {e}")


@router.get("/tasks")
async def list_tasks(
    status: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    batch_id: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(FileTask)
    if status:
        q = q.filter(FileTask.status == status)
    if search:
        q = q.filter(FileTask.original_filename.ilike(f"%{search}%"))
    if batch_id:
        q = q.filter(FileTask.batch_id == batch_id)
    total = q.count()
    items = q.order_by(FileTask.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [t.to_dict() for t in items]}


@router.delete("/tasks/batch")
async def batch_delete_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        return {"detail": "batch deleted", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list)).all()
    for task in tasks:
        await asyncio.to_thread(_safe_remove, task.file_path)
        await asyncio.to_thread(_safe_remove, task.output_path)
        await asyncio.to_thread(_safe_remove, task.pdf_path)
        db.delete(task)
    db.commit()
    return {"detail": "batch deleted", "count": len(tasks)}


@router.post("/tasks/batch/retry")
async def batch_retry_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
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
        _enqueue_task(task.id)
    db.commit()
    return {"detail": "batch retried", "count": len(tasks)}


@router.post("/tasks/batch/convert")
async def batch_convert_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        return {"detail": "batch converted", "count": 0}
    tasks = db.query(FileTask).filter(FileTask.id.in_(id_list)).all()
    converted = 0
    for task in tasks:
        if _is_doc_file(task.original_filename) and not task.pdf_path:
            try:
                pdf_path = await _convert_to_pdf(task.file_path, task.id)
                task.pdf_path = pdf_path
                task.auto_convert_doc = True
                db.commit()
                add_log(f"批量转换完成，开始解析", task_id=task.id)
                _enqueue_task(task.id)
                converted += 1
            except Exception as e:
                add_log(f"批量转换失败: {e}", task_id=task.id, level="error")
    return {"detail": "batch converted", "count": converted}


@router.get("/tasks/batch/download")
async def batch_download_tasks(ids: str = Query(..., description="comma-separated task IDs"), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
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
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=mineru_batch_results.zip"},
    )


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    return task.to_dict()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    await asyncio.to_thread(_safe_remove, task.file_path)
    await asyncio.to_thread(_safe_remove, task.output_path)
    await asyncio.to_thread(_safe_remove, task.pdf_path)
    db.delete(task)
    db.commit()
    return {"detail": "deleted"}


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
):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if backend:
        task.backend = backend
    if mineru_api:
        task.mineru_api = mineru_api
    if server_url:
        task.server_url = server_url
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


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(400, "只能取消等待中或处理中的任务")
    with _cancel_lock:
        _cancelled_tasks.add(task_id)
    task.status = TaskStatus.FAILED
    task.error_message = "用户取消"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    add_log(f"任务已取消", task_id=task_id, level="warn")
    return task.to_dict()


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    mineru_api: str | None = Form(None),
    server_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.output_path and os.path.exists(task.output_path):
        os.remove(task.output_path)
    task.output_path = None
    task.status = TaskStatus.PENDING
    task.error_message = None
    if mineru_api:
        task.mineru_api = mineru_api
    if server_url:
        task.server_url = server_url
    db.commit()
    add_log(f"任务重新提交", task_id=task_id)

    _enqueue_task(task.id)
    return task.to_dict()


@router.get("/tasks/{task_id}/preview")
async def preview_result(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    safe = _safe_path(task.output_path)
    if not os.path.exists(safe):
        raise HTTPException(404, "Output file missing on disk")
    async with aiofiles.open(safe, "r", encoding="utf-8") as f:
        content = await f.read()
    return {"content": content, "filename": os.path.basename(safe), "format": task.output_format.value}


@router.get("/tasks/{task_id}/download")
async def download_result(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    safe = _safe_path(task.output_path)
    if not os.path.exists(safe):
        raise HTTPException(404, "Output file missing on disk")
    if os.path.isdir(safe):
        stem = _sanitize_filename(task.original_filename)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(safe):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.join(stem, os.path.relpath(fp, safe))
                    zf.write(fp, arc)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={stem}_bundle.zip"},
        )
    return FileResponse(
        safe,
        filename=os.path.basename(safe),
        media_type="text/markdown" if task.output_format == OutputFormat.MD else "text/plain",
    )


@router.get("/logs")
async def list_logs(
    task_id: int = Query(None),
    level: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(ProcessLog)
    if task_id:
        q = q.filter(ProcessLog.task_id == task_id)
    if level:
        q = q.filter(ProcessLog.level == level)
    total = q.count()
    items = q.order_by(ProcessLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [l.to_dict() for l in items]}


@router.get("/logs/grouped")
async def list_logs_grouped(
    level: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    task_ids = db.query(ProcessLog.task_id).filter(ProcessLog.task_id.isnot(None)).distinct().order_by(ProcessLog.task_id.desc())
    all_ids = [t[0] for t in task_ids.all()]
    total = len(all_ids)
    paged_ids = all_ids[(page - 1) * size: page * size]

    tasks_map = {}
    if paged_ids:
        for t in db.query(FileTask).filter(FileTask.id.in_(paged_ids)).all():
            tasks_map[t.id] = t

    logs_q = db.query(ProcessLog).filter(ProcessLog.task_id.in_(paged_ids))
    if level:
        logs_q = logs_q.filter(ProcessLog.level == level)
    logs_by_task: dict = {}
    for log in logs_q.order_by(ProcessLog.id.asc()).all():
        logs_by_task.setdefault(log.task_id, []).append(log)

    groups = []
    for tid in paged_ids:
        task = tasks_map.get(tid)
        groups.append({
            "task_id": tid,
            "filename": task.original_filename if task else f"Task#{tid}",
            "status": task.status.value if task else "unknown",
            "created_at": task.created_at.isoformat() if task and task.created_at else None,
            "logs": [l.to_dict() for l in logs_by_task.get(tid, [])],
        })
    return {"total": total, "items": groups}


@router.delete("/logs")
async def clear_logs(db: Session = Depends(get_db)):
    count = db.query(ProcessLog).delete()
    db.commit()
    return {"detail": "cleared", "count": count}


@router.get("/storage")
async def get_storage_stats():
    def _dir_size(path: str) -> int:
        total_bytes = 0
        if not os.path.exists(path):
            return 0
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                if os.path.isfile(fp):
                    total_bytes += os.path.getsize(fp)
        return total_bytes

    uploads_size = _dir_size(UPLOAD_DIR)
    outputs_size = _dir_size(OUTPUT_DIR)
    converted_size = _dir_size(CONVERT_DIR)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mineru_batch.db")
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {
        "uploads": uploads_size,
        "outputs": outputs_size,
        "converted": converted_size,
        "database": db_size,
        "total": uploads_size + outputs_size + converted_size + db_size,
    }


@router.post("/storage/clean")
async def clean_storage(body: dict = None, db: Session = Depends(get_db)):
    targets = (body or {}).get("targets", [])
    cleaned = {}
    if "outputs" in targets:
        n = 0
        for f in os.listdir(OUTPUT_DIR):
            fp = os.path.join(OUTPUT_DIR, f)
            try:
                if os.path.isfile(fp):
                    await asyncio.to_thread(os.remove, fp)
                    n += 1
                elif os.path.isdir(fp):
                    await asyncio.to_thread(shutil.rmtree, fp)
                    n += 1
            except OSError:
                pass
        cleaned["outputs"] = n
        db.query(FileTask).filter(FileTask.output_path.isnot(None)).update({"output_path": None})
        db.commit()
    if "converted" in targets:
        n = 0
        for f in os.listdir(CONVERT_DIR):
            if f.startswith("."):
                continue
            fp = os.path.join(CONVERT_DIR, f)
            try:
                if os.path.isfile(fp):
                    await asyncio.to_thread(os.remove, fp)
                    n += 1
                elif os.path.isdir(fp):
                    await asyncio.to_thread(shutil.rmtree, fp)
                    n += 1
            except OSError:
                pass
        cleaned["converted"] = n
    return {"detail": "cleaned", "counts": cleaned}


@router.post("/storage/clean-sources")
async def clean_completed_sources(db: Session = Depends(get_db)):
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
    return {"detail": "cleaned", "count": count, "freed_bytes": freed}


@router.get("/stats/trend")
async def get_stats_trend(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT DATE(created_at) AS d,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
        FROM file_tasks
        WHERE created_at >= DATE('now', '-' || :days || ' days')
        GROUP BY DATE(created_at)
        ORDER BY d
    """), {"days": days}).fetchall()
    return [{"date": r[0], "completed": r[1], "failed": r[2]} for r in rows]


@router.get("/stats/filetypes")
async def get_filetype_stats(db: Session = Depends(get_db)):
    tasks = db.query(FileTask.original_filename).all()
    ext_count: dict[str, int] = {}
    for (filename,) in tasks:
        ext = os.path.splitext(filename)[1].lower() or '.unknown'
        ext_count[ext] = ext_count.get(ext, 0) + 1
    return [{"type": ext, "count": cnt} for ext, cnt in sorted(ext_count.items(), key=lambda x: -x[1])]
