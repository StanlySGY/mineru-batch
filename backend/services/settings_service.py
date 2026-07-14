"""Settings service — business logic for settings operations."""
import ipaddress
import json
import os
import re
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import HTTPException
from models import AppSetting
from sqlalchemy.orm import Session

SETTINGS_KEY = "app_settings"
MASKED_API_KEY = "********"
ALLOW_PRIVATE_ENDPOINTS = os.environ.get("ALLOW_PRIVATE_ENDPOINTS", "true").lower() in ("1", "true", "yes")
BLOCKED_URL_HOSTS = {"localhost", "localhost.localdomain"}

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


def _is_public_ip(addr: str) -> bool:
    """Check if IP address is public."""
    ip = ipaddress.ip_address(addr)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_external_url(url: str, label: str = "URL", allow_private: bool = False) -> str:
    """Validate and normalize URL."""
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, f"{label} must be http or https URL")
    if allow_private:
        return value
    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_URL_HOSTS:
        raise HTTPException(400, f"{label} host is not allowed")
    try:
        addresses = [host] if re.fullmatch(r"[0-9a-fA-F:.]+", host) else socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        for addr_info in addresses:
            addr = addr_info[4][0] if isinstance(addr_info, tuple) else addr_info
            if not _is_public_ip(addr):
                raise HTTPException(400, f"{label} host is not allowed")
    except (socket.gaierror, OSError):
        raise HTTPException(400, f"{label} host cannot be resolved") from None
    return value


def clone_default_settings() -> dict:
    """Clone default settings."""
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def get_settings_from_db(db: Session) -> dict:
    """Get settings from database or return defaults."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    if not row:
        return clone_default_settings()
    try:
        data = json.loads(row.value_json)
    except json.JSONDecodeError:
        return clone_default_settings()
    defaults = {**DEFAULT_SETTINGS["defaults"], **data.get("defaults", {})}
    endpoints = data.get("mineruEndpoints")
    if not isinstance(endpoints, list) or not endpoints:
        endpoints = clone_default_settings()["mineruEndpoints"]
    return {"defaults": defaults, "mineruEndpoints": endpoints}


def sanitize_settings(data: dict) -> dict:
    """Remove sensitive data from settings for API response."""
    sanitized = json.loads(json.dumps(data))
    for ep in sanitized.get("mineruEndpoints", []):
        key = ep.pop("apiKey", None)
        ep["hasApiKey"] = bool(key)
    return sanitized


def validate_endpoint(ep: dict) -> dict:
    """Validate and clean endpoint configuration."""
    url = _validate_external_url(ep.get("url"), "MinerU endpoint", allow_private=ALLOW_PRIVATE_ENDPOINTS)
    server_url_raw = str(ep.get("serverUrl") or "").strip()
    server_url = _validate_external_url(server_url_raw, "serverUrl", allow_private=ALLOW_PRIVATE_ENDPOINTS) if server_url_raw else ""
    ALLOWED_BACKENDS = ("pipeline", "vlm-engine", "vlm-http-client", "hybrid-engine", "hybrid-http-client")
    backend = str(ep.get("backend") or "hybrid-http-client").strip()
    if backend not in ALLOWED_BACKENDS:
        raise HTTPException(400, f"backend is invalid, allowed: {', '.join(ALLOWED_BACKENDS)}")
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


def validate_settings_payload(payload: dict, current: dict | None = None) -> dict:
    """Validate settings payload before saving."""
    current = current or clone_default_settings()
    raw_defaults = payload.get("defaults") or {}
    defaults = {**DEFAULT_SETTINGS["defaults"], **raw_defaults}
    try:
        defaults["timeout"] = int(defaults.get("timeout", 600))
        defaults["startPageId"] = int(defaults.get("startPageId", 0))
        defaults["endPageId"] = int(defaults.get("endPageId", 99999))
    except (TypeError, ValueError):
        raise HTTPException(400, "timeout and page range must be integers") from None
    if defaults["timeout"] < 10 or defaults["timeout"] > 7200:
        raise HTTPException(400, "timeout must be between 10 and 7200 seconds")
    if defaults["startPageId"] < 0 or defaults["endPageId"] < defaults["startPageId"]:
        raise HTTPException(400, "page range is invalid")
    if defaults["outputFormat"] not in ("md", "txt", "html"):
        raise HTTPException(400, "outputFormat is invalid")

    current_by_url = {ep.get("url"): ep for ep in current.get("mineruEndpoints", [])}
    endpoints = []
    for ep in payload.get("mineruEndpoints") or []:
        clean = validate_endpoint(ep)
        old_key = current_by_url.get(clean["url"], {}).get("apiKey")
        if "apiKey" not in clean and old_key:
            clean["apiKey"] = old_key
        endpoints.append(clean)
    if not endpoints:
        endpoints = clone_default_settings()["mineruEndpoints"]
    return {"defaults": defaults, "mineruEndpoints": endpoints}


def export_settings_payload(db: Session) -> dict:
    """Export sanitized settings."""
    return sanitize_settings(get_settings_from_db(db))


def import_settings_payload(db: Session, payload: dict) -> dict:
    """Validate and save imported settings."""
    current = get_settings_from_db(db)
    return save_settings(db, validate_settings_payload(payload or {}, current))


def save_settings(db: Session, data: dict) -> dict:
    """Save settings to database."""
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    if not row:
        row = AppSetting(key=SETTINGS_KEY, value_json="{}")
        db.add(row)
    row.value_json = json.dumps(data, ensure_ascii=False)
    row.updated_at = datetime.now(UTC)
    db.commit()
    return data


def get_endpoint_api_key(db: Session, url: str | None) -> str | None:
    """Get API key for a specific endpoint URL."""
    if not url:
        return None
    settings = get_settings_from_db(db)
    for ep in settings.get("mineruEndpoints", []):
        if ep.get("url") == url and ep.get("apiKey"):
            return ep.get("apiKey")
    return None
