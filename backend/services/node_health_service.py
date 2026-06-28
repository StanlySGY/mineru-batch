"""Node health service."""
import time

import httpx


async def _check_url(url: str, validate_url_fn, allow_private: bool, method: str = "get") -> tuple[bool, int | None, str]:
    started = time.perf_counter()
    validated = validate_url_fn(url, "endpoint", allow_private=allow_private)
    async with httpx.AsyncClient(timeout=5) as client:
        if method == "post":
            resp = await client.post(validated)
        else:
            resp = await client.get(validated.replace("/file_parse", "/").rstrip("/") or validated)
    latency = int((time.perf_counter() - started) * 1000)
    ok = resp.status_code < 500
    status = "green" if ok and latency < 800 else "yellow" if ok else "red"
    return ok, latency, status


async def check_node_health_impl(settings: dict, validate_url_fn, allow_private: bool) -> dict:
    nodes = []
    for idx, ep in enumerate(settings.get("mineruEndpoints", [])):
        if not ep.get("enabled", True):
            nodes.append({"index": idx, "url": ep.get("url"), "enabled": False, "ok": False, "latency_ms": None, "status": "disabled"})
            continue
        backend = ep.get("backend", "hybrid-http-client")
        server_url = ep.get("serverUrl", "")
        entry: dict = {"index": idx, "url": ep.get("url"), "enabled": True, "backend": backend}

        try:
            # POST to /file_parse without files — MinerU returns 4xx (param error) when healthy,
            # rather than checking the root path which may not respond.
            ok, latency, status = await _check_url(ep.get("url"), validate_url_fn, allow_private, method="post")
            entry.update(ok=ok, latency_ms=latency, status=status)
        except Exception as exc:
            entry.update(ok=False, latency_ms=None, status="red", error=str(exc))

        if backend == "vlm-http-client" and server_url:
            try:
                vlm_ok, vlm_latency, vlm_status = await _check_url(server_url, validate_url_fn, allow_private)
            except Exception as exc:
                vlm_ok, vlm_latency, vlm_status = False, None, "red"
                entry["vlm_error"] = str(exc)
            entry["vlm"] = {"url": server_url, "ok": vlm_ok, "latency_ms": vlm_latency, "status": vlm_status}
            entry["ok"] = entry.get("ok", False) and vlm_ok
            if entry["status"] == "green" and vlm_status != "green":
                entry["status"] = vlm_status

        nodes.append(entry)
    return {"total": len(nodes), "healthy": sum(1 for n in nodes if n.get("ok")), "nodes": nodes}
