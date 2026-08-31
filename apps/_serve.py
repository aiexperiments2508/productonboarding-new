"""The chrome every one of these applications needs and none should re-invent.

A static mount for its own page, a health route, a live-update stream, and a
uvicorn entry point. Nothing domain-specific: what each application *is* lives
in its own ``server.py``.

**On the live stream.** These processes cannot subscribe to the platform's
in-process event bus - that is what being a separate process means. So each one
polls the platform over MCP on a single timer and fans out to its own browsers
over its own server-sent events. One poller per application, not one per open
tab: two tabs and six endpoints at one poll a second would put twelve calls a
second through the platform's MCP call log and flush the traffic anybody was
trying to look at within half a minute.

The alternative - subscribing to the platform's own event stream - is easier
and would break the only interesting claim these applications make. It is named
here so that choosing it later is a decision rather than a drift.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)

#: How often to ask the platform what has changed, and how far to back off when
#: the answer keeps being "nothing". A demonstration wants the fast end; a
#: window left open over lunch does not need it.
POLL_FAST = 1.0
POLL_SLOW = 5.0


class Broadcaster:
    """In-process fan-out to this application's own browsers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, kind: str, payload: dict) -> None:
        message = {"kind": kind, "ts": datetime.now().isoformat(), **payload}
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def build(name: str, title: str, web_dir: Path, client, bus: Broadcaster,
          *, colour: str = "") -> FastAPI:
    """A bare application: its page, its health, and its event stream."""
    app = FastAPI(title=title)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "app": name, "title": title,
                **client.status()}

    @app.get("/api/mcp")
    async def mcp_status() -> dict:
        """What this application has called, and where. Its own console.

        Every read and write this page makes crosses the protocol, and this is
        where that stops being a claim and becomes a list somebody can read.
        """
        return client.status()

    @app.get("/api/stream")
    async def stream():
        queue = bus.subscribe()

        async def generator():
            try:
                yield sse({"kind": "hello", "app": name})
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(),
                                                         timeout=15.0)
                        yield sse(message)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(generator(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.middleware("http")
    async def revalidate_the_page(request, call_next):
        """Make the browser check whether the page changed.

        These pages have no build step and no content hash in their filenames,
        so a browser that treats `/static/shop.js` as immutable will keep
        running the copy it fetched an hour ago - and the failure is silent and
        deeply confusing, because the server is serving the right file and the
        page is running the wrong one. `no-cache` means "revalidate", not "do
        not store": the 304 still saves the transfer.
        """
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if (web_dir / "index.html").exists():
        app.mount("/static", StaticFiles(directory=web_dir), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(web_dir / "index.html")
    else:
        @app.get("/")
        async def missing() -> JSONResponse:
            return JSONResponse({"error": f"no page in {web_dir}"}, 500)

    return app


async def poll_forever(bus: Broadcaster, tick, *, fast: float = POLL_FAST,
                       slow: float = POLL_SLOW) -> None:
    """Ask ``tick`` what changed, and tell the browsers when something did.

    ``tick`` returns a truthy value when something moved. Quiet rounds slow the
    loop down; a change speeds it back up, so the first thing that happens
    after a long quiet spell is still seen promptly.
    """
    delay = fast
    while True:
        try:
            moved = await tick()
            delay = fast if moved else min(slow, delay * 1.5)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the platform may be restarting
            log.debug("poll failed", exc_info=True)
            delay = slow
        await asyncio.sleep(delay)


def run(app: FastAPI, port: int, banner: str) -> None:
    import uvicorn

    print(banner)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
