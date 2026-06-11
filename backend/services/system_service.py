"""System service — business logic for system operations."""
import httpx
from fastapi import HTTPException


async def test_connection_impl(body: dict | None, validate_url_fn, allow_private: bool) -> dict:
    """Test connection to MinerU API and server endpoints."""
    mineru_api = (body or {}).get("mineru_api", "")
    server_url = (body or {}).get("server_url", "")
    results = {}
    if mineru_api:
        try:
            safe_mineru_api = validate_url_fn(mineru_api, "mineru_api", allow_private=allow_private)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(safe_mineru_api)
                results["mineru"] = {"ok": resp.status_code < 500, "status": resp.status_code}
        except Exception as e:
            results["mineru"] = {"ok": False, "error": str(e)}
    if server_url:
        try:
            safe_server_url = validate_url_fn(server_url, "server_url", allow_private=allow_private)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{safe_server_url.rstrip('/')}/models")
                results["server"] = {"ok": resp.status_code < 500, "status": resp.status_code}
        except Exception as e:
            results["server"] = {"ok": False, "error": str(e)}
    ok = all(r.get("ok") for r in results.values()) if results else False
    return {"ok": ok, "detail": results}
