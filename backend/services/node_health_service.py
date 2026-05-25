"""Node health service."""
import time

import httpx


async def check_node_health_impl(settings: dict, validate_url_fn, allow_private: bool) -> dict:
    nodes = []
    for idx, ep in enumerate(settings.get("mineruEndpoints", [])):
        if not ep.get("enabled", True):
            nodes.append({"index": idx, "url": ep.get("url"), "enabled": False, "ok": False, "latency_ms": None, "status": "disabled"})
            continue
        started = time.perf_counter()
        try:
            url = validate_url_fn(ep.get("url"), "MinerU endpoint", allow_private=allow_private)
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url.replace("/file_parse", "/"))
            latency = int((time.perf_counter() - started) * 1000)
            ok = resp.status_code < 500
            nodes.append({
                "index": idx,
                "url": ep.get("url"),
                "enabled": True,
                "ok": ok,
                "latency_ms": latency,
                "status": "green" if ok and latency < 800 else "yellow" if ok else "red",
            })
        except Exception as exc:
            nodes.append({
                "index": idx,
                "url": ep.get("url"),
                "enabled": True,
                "ok": False,
                "latency_ms": None,
                "status": "red",
                "error": str(exc),
            })
    return {"total": len(nodes), "healthy": sum(1 for n in nodes if n.get("ok")), "nodes": nodes}
