"""Events service — business logic for SSE event streaming."""
import asyncio
import json


async def stream_task_events_impl(
    sse_subscribers: list[asyncio.Queue],
    sse_lock: asyncio.Lock,
) -> None:
    """Stream task events via SSE. Yields SSE-formatted messages."""
    q: asyncio.Queue = asyncio.Queue(maxsize=128)
    async with sse_lock:
        sse_subscribers.append(q)
    try:
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30)
                yield f"data: {msg}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        async with sse_lock:
            if q in sse_subscribers:
                sse_subscribers.remove(q)
