from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import init_db
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    import sys
    print(f"=== MinerU Batch Backend started === Python={sys.version}", flush=True)
    yield


app = FastAPI(title="MinerU Batch Processor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
