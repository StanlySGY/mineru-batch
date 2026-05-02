import os
import asyncio
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, FileTask, TaskStatus, OutputFormat, get_db
import routes as routes_module


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def tmp_dirs(tmp_path):
    upload = tmp_path / "uploads"
    output = tmp_path / "outputs"
    convert = tmp_path / "converted"
    upload.mkdir()
    output.mkdir()
    convert.mkdir()
    safe = (str(upload), str(output), str(convert))
    yield {"upload": str(upload), "output": str(output), "convert": str(convert)}


@pytest.fixture
def client(engine, db_session, tmp_dirs):
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_test_db():
        s = test_session_factory()
        try:
            yield s
        finally:
            s.close()

    app = FastAPI()
    app.include_router(routes_module.router, prefix="/api")
    app.dependency_overrides[get_db] = _get_test_db

    patches = [
        patch.object(routes_module, "UPLOAD_DIR", tmp_dirs["upload"]),
        patch.object(routes_module, "OUTPUT_DIR", tmp_dirs["output"]),
        patch.object(routes_module, "CONVERT_DIR", tmp_dirs["convert"]),
        patch.object(routes_module, "_SAFE_DIRS",
                     (tmp_dirs["upload"], tmp_dirs["output"], tmp_dirs["convert"])),
        patch.object(routes_module, "SessionLocal", test_session_factory),
        patch("models.SessionLocal", test_session_factory),
        patch.object(routes_module, "_task_semaphore", asyncio.Semaphore(5)),
        patch.object(routes_module, "_cancelled_tasks", set()),
        patch.object(routes_module, "_sse_subscribers", []),
    ]
    for p in patches:
        p.start()

    with TestClient(app) as c:
        yield c

    for p in patches:
        p.stop()
    app.dependency_overrides.clear()


@pytest.fixture
def sample_task(db_session, **kwargs):
    defaults = {
        "original_filename": "test.pdf",
        "saved_filename": "abc123.pdf",
        "file_path": "/tmp/test.pdf",
        "file_size": 1024,
        "status": TaskStatus.PENDING,
        "output_format": OutputFormat.MD,
    }
    defaults.update(kwargs)
    task = FileTask(**defaults)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n109\n%%EOF"
