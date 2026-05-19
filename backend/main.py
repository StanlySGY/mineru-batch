import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from models import init_db, SessionLocal, FileTask, TaskStatus
from routes import router, _notify_task_change, add_log, _enqueue_task, start_workers

BASE_DIR = Path(__file__).resolve().parent

_frontend = BASE_DIR / "frontend"
if not _frontend.is_dir():
    _frontend = BASE_DIR.parent / "frontend"
FRONTEND_DIR = _frontend
FRONTEND_DIST = FRONTEND_DIR / "dist"

_version = BASE_DIR / "VERSION"
if not _version.is_file():
    _version = BASE_DIR.parent / "VERSION"
VERSION_FILE = _version
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"

DEV_MODE = os.environ.get("DEV_MODE", "").strip() in ("1", "true", "yes")


def _ensure_frontend():
    if DEV_MODE or FRONTEND_DIST.exists():
        return
    print("=== 前端 dist 不存在，自动构建中... ===", flush=True)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(FRONTEND_DIR),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"=== 前端构建失败 ===\n{result.stderr}\n{result.stdout}", flush=True)
        sys.exit(1)
    print("=== 前端构建完成 ===", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_frontend()
    init_db()
    import sys as _sys
    print(f"=== MinerU Batch Backend started === Python={_sys.version}", flush=True)
    if DEV_MODE:
        print("=== 开发模式：前端由 Vite dev server 提供 ===", flush=True)
    db = SessionLocal()
    try:
        stale = db.query(FileTask).filter(
            FileTask.status.in_((TaskStatus.PROCESSING, TaskStatus.PENDING))
        ).all()
        for t in stale:
            t.status = TaskStatus.PENDING
            t.error_message = None
            t.started_at = None
            db.add(t)
        db.commit()
        if stale:
            print(f"=== 恢复 {len(stale)} 个未完成任务 ===", flush=True)
    finally:
        db.close()

    async def _requeue_stale():
        from models import SessionLocal as _sl
        _db = _sl()
        tasks = _db.query(FileTask).filter(FileTask.status == TaskStatus.PENDING).all()
        _db.close()
        for t in tasks:
            _enqueue_task(t.id)
    start_workers()
    asyncio.get_event_loop().call_later(1.0, lambda: asyncio.ensure_future(_requeue_stale()))

    async def _check_task_timeouts():
        while True:
            await asyncio.sleep(30)
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                stuck = db.query(FileTask).filter(
                    FileTask.status == TaskStatus.PROCESSING,
                    FileTask.started_at.isnot(None),
                ).all()
                for task in stuck:
                    elapsed = (now - task.started_at).total_seconds()
                    timeout = task.timeout or 600
                    if elapsed > timeout + 60:
                        task.status = TaskStatus.FAILED
                        task.error_message = f"任务超时（已运行 {int(elapsed)}s，超时 {timeout}s）"
                        task.completed_at = now
                        db.commit()
                        add_log(f"任务超时自动取消", task_id=task.id, level="warn",
                                detail=f"elapsed={int(elapsed)}s timeout={timeout}s")
                        _notify_task_change(task.id, "failed", error_message=task.error_message)
            except Exception:
                pass
            finally:
                db.close()
    timeout_task = asyncio.create_task(_check_task_timeouts())
    yield
    timeout_task.cancel()


app = FastAPI(title="MinerU Batch Processor", lifespan=lifespan)

_cors_origins = os.environ.get("CORS_ORIGINS", "").split(",")
_cors_origins = [o.strip() for o in _cors_origins if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router, prefix="/api")


@app.get("/api/version")
async def get_version():
    return {"version": APP_VERSION, "name": "mineru-batch"}


# Serve frontend static files (production mode only)
if not DEV_MODE and FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Other static files in dist root (favicon, icons, etc.)
    for f in FRONTEND_DIST.iterdir():
        if f.is_file() and f.name != "index.html":
            fp = f

            async def _serve_static(_request: Request, filepath: Path = fp):
                return FileResponse(filepath, headers={"Cache-Control": "public, max-age=86400"})
            app.get(f"/{f.name}")(_serve_static)

    # SPA fallback — no cache (always serve latest index.html)
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        if full_path.startswith("api/"):
            return Response(status_code=404)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
