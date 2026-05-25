"""Audit service."""
from models import add_log


def audit_admin_action(action: str, detail: str | None = None) -> None:
    add_log(f"管理员操作: {action}", level="info", detail=detail)
