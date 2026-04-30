from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Boolean, ForeignKey
from sqlalchemy import create_engine, event
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
    mineru_api = Column(String(512), default="http://172.16.100.26:8086/file_parse")
    backend = Column(String(128), default="hybrid-http-client")
    server_url = Column(String(512), default="http://10.8.132.224:6002/v1")
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
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "pdf_path": self.pdf_path,
            "timeout": self.timeout,
            "auto_convert_doc": self.auto_convert_doc,
            "mineru_api": self.mineru_api,
            "backend": self.backend,
            "server_url": self.server_url,
            "parse_method": self.parse_method,
            "lang_list": self.lang_list,
            "formula_enable": self.formula_enable,
            "table_enable": self.table_enable,
            "return_md": self.return_md,
            "return_middle_json": self.return_middle_json,
            "return_model_output": self.return_model_output,
            "return_content_list": self.return_content_list,
            "return_images": self.return_images,
            "response_format_zip": self.response_format_zip,
            "replace_image_url": self.replace_image_url,
            "start_page_id": self.start_page_id,
            "end_page_id": self.end_page_id,
            "status": self.status.value if self.status else None,
            "output_format": self.output_format.value if self.output_format else None,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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


DATABASE_URL = "sqlite:///./mineru_batch.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_log(message: str, level: str = "info", task_id: int = None, detail: str = None):
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
    except Exception:
        db.rollback()
    finally:
        db.close()
