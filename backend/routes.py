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
import typing
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models import (
    FileTask, TaskStatus, OutputFormat, ProcessLog, LogLevel,
    get_db, SessionLocal, add_log,
)

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
CONVERT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "converted")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CONVERT_DIR, exist_ok=True)

DOC_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_lo_lock = threading.Lock()
_rr_counter = 0
_rr_lock = threading.Lock()
_task_semaphore = asyncio.Semaphore(5)
_cancelled_tasks: set[int] = set()
_cancel_lock = threading.Lock()
_max_concurrency = 5


def set_concurrency(n: int):
    global _task_semaphore, _max_concurrency
    _max_concurrency = max(1, min(n, 20))
    _task_semaphore = asyncio.Semaphore(_max_concurrency)

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
        with _lo_lock:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                    env={**os.environ, "HOME": "/tmp"})
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
        with httpx.Client(timeout=timeout) as client:
            with open(file_to_parse, "rb") as f:
                file_data = f.read()
            add_log(f"文件读取完成，大小 {len(file_data)} 字节", task_id=task_id)
            form_data = _build_mineru_form(task)
            add_log(f"发送参数", task_id=task_id, detail=json.dumps(form_data, ensure_ascii=False))
            resp = client.post(
                api_url,
                files={"files": (os.path.basename(file_to_parse), file_data, "application/octet-stream")},
                data=form_data,
            )
            add_log(f"MinerU 响应: HTTP {resp.status_code}", task_id=task_id,
                    level="info" if resp.status_code == 200 else "error",
                    detail=f"status={resp.status_code}\ncontent_type={resp.headers.get('content-type','')}\nbody_preview={resp.text[:2000]}")
            if resp.status_code != 200:
                raise RuntimeError(f"MinerU API error {resp.status_code}: {resp.text[:500]}")
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
        out_name = f"{original_stem}.{ext}"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        counter = 1
        while os.path.exists(out_path):
            out_name = f"{original_stem}_{counter}.{ext}"
            out_path = os.path.join(OUTPUT_DIR, out_name)
            counter += 1

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        add_log(f"结果已保存: {out_name} ({len(md_content)} 字符)", task_id=task_id)
        task.output_path = out_path
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        _notify_task_change(task_id, "completed")
    except Exception as e:
        task = db.query(FileTask).filter(FileTask.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            add_log(f"任务失败: {e}", task_id=task_id, level="error", detail=traceback.format_exc())
            _notify_task_change(task_id, "failed", error_message=str(e))
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


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(FileTask.id)).scalar()
    by_status = (
        db.query(FileTask.status, func.count(FileTask.id))
        .group_by(FileTask.status)
        .all()
    )
    status_map = {s.value: c for s, c in by_status}
    # 平均处理耗时（仅统计已完成的任务）
    completed_tasks = (
        db.query(FileTask.started_at, FileTask.completed_at)
        .filter(FileTask.status == TaskStatus.COMPLETED, FileTask.started_at.isnot(None), FileTask.completed_at.isnot(None))
        .all()
    )
    avg_duration_ms = 0
    if completed_tasks:
        durations = [(c.completed_at - c.started_at).total_seconds() * 1000 for c in completed_tasks]
        avg_duration_ms = sum(durations) / len(durations)
    return {
        "total": total,
        "pending": status_map.get("pending", 0),
        "processing": status_map.get("processing", 0),
        "completed": status_map.get("completed", 0),
        "failed": status_map.get("failed", 0),
        "avg_duration_ms": avg_duration_ms,
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


MAX_FILE_SIZE = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
                      ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    backend: str = Form("hybrid-http-client"),
    mineru_api: str = Form("http://172.16.100.26:8086/file_parse"),
    server_url: str = Form("http://10.8.132.224:6002/v1"),
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
    db: Session = Depends(get_db),
):
    if output_format not in ("md", "txt"):
        raise HTTPException(400, "output_format must be md or txt")

    def _b(val: str) -> bool:
        return val.lower() in ("true", "1", "yes")

    endpoints_list = None
    if mineru_endpoints:
        try:
            endpoints_list = json.loads(mineru_endpoints)
        except json.JSONDecodeError:
            endpoints_list = None

    results = []
    for file in files:
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

        ep = _pick_endpoint(endpoints_list) if endpoints_list else None
        task = FileTask(
            original_filename=file.filename,
            saved_filename=saved_name,
            file_path=save_path,
            file_size=len(content),
            mineru_api=ep["url"] if ep else mineru_api,
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
            start_page_id=int(start_page_id),
            end_page_id=int(end_page_id),
            output_format=OutputFormat(output_format),
            timeout=int(timeout),
            auto_convert_doc=_b(auto_convert),
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
        asyncio.create_task(_process_task(tid))

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
        pdf_path = await asyncio.to_thread(_convert_to_pdf_sync, task.file_path, task_id)
        task.pdf_path = pdf_path
        task.auto_convert_doc = True
        db.commit()
        add_log(f"手动转换完成，开始解析", task_id=task_id)
        asyncio.create_task(_process_task(task.id))
        return {"detail": "converted", "pdf_path": pdf_path}
    except Exception as e:
        raise HTTPException(500, f"Conversion failed: {e}")


@router.get("/tasks")
async def list_tasks(
    status: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(FileTask)
    if status:
        q = q.filter(FileTask.status == status)
    if search:
        q = q.filter(FileTask.original_filename.ilike(f"%{search}%"))
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
        if task.file_path and os.path.exists(task.file_path):
            os.remove(task.file_path)
        if task.output_path and os.path.exists(task.output_path):
            os.remove(task.output_path)
        if task.pdf_path and os.path.exists(task.pdf_path):
            os.remove(task.pdf_path)
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
        asyncio.create_task(_process_task(task.id))
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
                pdf_path = await asyncio.to_thread(_convert_to_pdf_sync, task.file_path, task.id)
                task.pdf_path = pdf_path
                task.auto_convert_doc = True
                db.commit()
                add_log(f"批量转换完成，开始解析", task_id=task.id)
                asyncio.create_task(_process_task(task.id))
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
            ext = os.path.splitext(t.output_path)[1] or ".md"
            stem = _sanitize_filename(t.original_filename)
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
    if task.file_path and os.path.exists(task.file_path):
        os.remove(task.file_path)
    if task.output_path and os.path.exists(task.output_path):
        os.remove(task.output_path)
    if task.pdf_path and os.path.exists(task.pdf_path):
        os.remove(task.pdf_path)
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
    if output_format and output_format in ("md", "txt"):
        task.output_format = OutputFormat(output_format)
    if timeout:
        task.timeout = int(timeout)
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
async def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.output_path and os.path.exists(task.output_path):
        os.remove(task.output_path)
    task.output_path = None
    task.status = TaskStatus.PENDING
    task.error_message = None
    db.commit()
    add_log(f"任务重新提交", task_id=task_id)

    asyncio.create_task(_process_task(task.id))
    return task.to_dict()


@router.get("/tasks/{task_id}/preview")
async def preview_result(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    if not os.path.exists(task.output_path):
        raise HTTPException(404, "Output file missing on disk")
    async with aiofiles.open(task.output_path, "r", encoding="utf-8") as f:
        content = await f.read()
    return {"content": content, "filename": os.path.basename(task.output_path), "format": task.output_format.value}


@router.get("/tasks/{task_id}/download")
async def download_result(task_id: int, db: Session = Depends(get_db)):
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        raise HTTPException(400, "Result not ready")
    if not os.path.exists(task.output_path):
        raise HTTPException(404, "Output file missing on disk")
    return FileResponse(
        task.output_path,
        filename=os.path.basename(task.output_path),
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

    groups = []
    for tid in paged_ids:
        task = db.query(FileTask).filter(FileTask.id == tid).first()
        q = db.query(ProcessLog).filter(ProcessLog.task_id == tid)
        if level:
            q = q.filter(ProcessLog.level == level)
        logs = q.order_by(ProcessLog.id.asc()).all()
        groups.append({
            "task_id": tid,
            "filename": task.original_filename if task else f"Task#{tid}",
            "status": task.status.value if task else "unknown",
            "created_at": task.created_at.isoformat() if task and task.created_at else None,
            "logs": [l.to_dict() for l in logs],
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
            if os.path.isfile(fp):
                os.remove(fp)
                n += 1
        cleaned["outputs"] = n
    if "converted" in targets:
        n = 0
        for f in os.listdir(CONVERT_DIR):
            fp = os.path.join(CONVERT_DIR, f)
            if os.path.isfile(fp) and not f.startswith("."):
                os.remove(fp)
                n += 1
        cleaned["converted"] = n
    return {"detail": "cleaned", "counts": cleaned}


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
