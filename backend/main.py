from contextlib import asynccontextmanager
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db, SessionLocal, FileTask, TaskStatus
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    import sys
    print(f"=== MinerU Batch Backend started === Python={sys.version}", flush=True)
    # 恢复上次未完成的任务
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
    # 延迟调度，确保 router 已就绪
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

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3001,http://127.0.0.1:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
