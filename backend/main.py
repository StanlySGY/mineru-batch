import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from models import init_db, SessionLocal, FileTask, TaskStatus
from routes import router

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
DEV_MODE = os.environ.get("DEV_MODE", "").strip() in ("1", "true", "yes")


def _ensure_frontend():
    """Auto-build frontend if dist/ is missing."""
    if DEV_MODE or FRONTEND_DIST.exists():
        return
    frontend_dir = BASE_DIR.parent / "frontend"
    print("=== 前端 dist 不存在，自动构建中... ===", flush=True)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(frontend_dir),
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
            from routes import _process_task
            asyncio.create_task(_process_task(t.id))
    asyncio.get_event_loop().call_later(1.0, lambda: asyncio.ensure_future(_requeue_stale()))
    yield


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

# Serve frontend static files (production mode only)
if not DEV_MODE and FRONTEND_DIST.exists():
    # Assets with hash filenames — cache 1 year
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", max_age=31536000), name="assets")

    # Other static files in dist root (favicon, icons, etc.)
    for f in FRONTEND_DIST.iterdir():
        if f.is_file() and f.name != "index.html":
            path = f"/{f.name}"

            def _make_static(filepath: Path):
                async def _serve(request: Request):
                    return FileResponse(filepath, headers={"Cache-Control": "public, max-age=86400"})
                return _serve
            app.get(path)(_make_static(f))

    # SPA fallback — no cache (always serve latest index.html)
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        if full_path.startswith("api/"):
            return Response(status_code=404)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
