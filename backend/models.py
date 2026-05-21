import os
import time
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Boolean, ForeignKey
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import enum

Base = declarative_base()


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(str, enum.Enum):
    MD = "md"
    TXT = "txt"
    HTML = "html"


class LogLevel(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class FileTask(Base):
    __tablename__ = "file_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    original_filename = Column(String(512), nullable=False)
    saved_filename = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size = Column(Integer, default=0)
    pdf_path = Column(String(1024), nullable=True)
    timeout = Column(Integer, default=600)
    auto_convert_doc = Column(Boolean, default=True)
    # MinerU connection
    mineru_api = Column(String(512), default="http://localhost:8086/file_parse")
    backend = Column(String(128), default="hybrid-http-client")
    server_url = Column(String(512), default="http://localhost:6002/v1")
    # MinerU parse options
    parse_method = Column(String(64), default="auto")
    lang_list = Column(String(128), default="ch")
    formula_enable = Column(Boolean, default=True)
    table_enable = Column(Boolean, default=True)
    return_md = Column(Boolean, default=True)
    return_middle_json = Column(Boolean, default=True)
    return_model_output = Column(Boolean, default=True)
    return_content_list = Column(Boolean, default=False)
    return_images = Column(Boolean, default=False)
    response_format_zip = Column(Boolean, default=False)
    replace_image_url = Column(Boolean, default=True)
    start_page_id = Column(Integer, default=0)
    end_page_id = Column(Integer, default=99999)
    api_key = Column(String(256), nullable=True)
    webhook_url = Column(String(1024), nullable=True)
    batch_id = Column(String(64), nullable=True, index=True)
    batch_name = Column(String(256), nullable=True)
    priority = Column(Integer, default=0, index=True)  # 0=普通, 1=高, 2=紧急
    # output
    output_format = Column(Enum(OutputFormat), default=OutputFormat.MD)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    output_path = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    logs = relationship("ProcessLog", backref="task", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self):
        _EXCLUDE = {"saved_filename", "api_key", "output_path"}
        result = {}
        for col in self.__table__.columns:
            if col.name in _EXCLUDE:
                continue
            val = getattr(self, col.name)
            if val is None:
                result[col.name] = None
            elif isinstance(col.type, Enum):
                result[col.name] = val.value
            elif isinstance(col.type, DateTime):
                result[col.name] = val.isoformat()
            else:
                result[col.name] = val
        return result


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ProcessLog(Base):
    __tablename__ = "process_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("file_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    level = Column(Enum(LogLevel), default=LogLevel.INFO, index=True)
    message = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "level": self.level.value if self.level else None,
            "message": self.message,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./mineru_batch.db")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_compatible_schema():
    inspector = inspect(engine)
    if "file_tasks" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("file_tasks")}
    with engine.begin() as conn:
        if "batch_id" not in columns:
            conn.execute(text("ALTER TABLE file_tasks ADD COLUMN batch_id VARCHAR(64)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_file_tasks_batch_id ON file_tasks (batch_id)"))
        if "batch_name" not in columns:
            conn.execute(text("ALTER TABLE file_tasks ADD COLUMN batch_name VARCHAR(256)"))
        if "priority" not in columns:
            conn.execute(text("ALTER TABLE file_tasks ADD COLUMN priority INTEGER DEFAULT 0"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_log(message: str, level: str = "info", task_id: int = None, detail: str = None):
    for attempt in range(3):
        db = SessionLocal()
        try:
            log = ProcessLog(
                task_id=task_id,
                level=LogLevel(level),
                message=message,
                detail=detail,
            )
            db.add(log)
            db.commit()
            return
        except Exception:
            db.rollback()
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
        finally:
            db.close()
