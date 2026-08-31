"""An MCP client, and the whole of how these applications reach the platform.

Each of the three applications in this package is a separate process on a
separate port, and none of them can see the platform's database, its API or its
event bus. What they can do is call tools on the MCP servers the platform
mounts. That is the entire interface, and this module is the entire
implementation of it.

**Why the session lives here and not in the browser.** MCP's streamable-HTTP
transport returns its session identifier in a response header, and the
platform's CORS configuration does not expose response headers - so a client
running in a page could complete a handshake and then be unable to continue the
session it had just opened. Holding the session in this process sidesteps that
without asking the platform to widen anything, and it has two better
consequences: a supplier identity is set server-side rather than being whatever
a browser sent, and there is one poller per application rather than one per open
tab.

**Why this is not ``sc.mcp.client``.** That module runs its sessions on a
background event loop on a thread of its own, because the caller it was written
for is a synchronous LangGraph pipeline. These applications are async from top
to bottom and need none of that. It also carries an in-process fallback, which
would be precisely the wrong thing here: if the platform is unreachable, these
applications have nothing to fall back *to*, and pretending otherwise would
hide the one failure they exist to make visible.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

#: A bounded local record of what this application has called, for its own
#: console. An observability aid, not an audit trail - the audit trail is the
#: platform's append-only ledger, and confusing the two would be a mistake in
#: the direction that matters.
CALL_LOG_SIZE = 200


#: How long a caller will wait for one tool call before giving up on it. The
#: platform answers in a quarter of a second warm and about a second cold, so
#: this is not a latency budget - it is the difference between an endpoint that
#: recovers from a broken session and one that hangs until somebody restarts
#: the process.
CALL_TIMEOUT = 30.0


class Endpoint:
    """One MCP server, and a session held open to it.

    Reconnects on failure rather than caching a dead session: these servers are
    in another process that a demonstrator may well restart mid-sentence, and
    an application that needed restarting alongside it would be a worse
    demonstration of a boundary, not a better one.

    **The session is owned by a task of its own, and that is not a style
    preference.** The streamable-HTTP transport runs a background reader inside
    the task that opened it, so a session opened while serving one HTTP request
    belongs to that request's task - and the moment the request finishes, the
    reader is inside a scope nobody is in any more. The next call gets a
    session whose replies are not being read, and waits for them for ever.

    That failure needs two calls to overlap, which is why it survived three
    releases: one page load made one call, and the background poller only
    overlapped it when a supplier had something being watched. It is not a rare
    bug, it is a bug with a narrow trigger, and a second call on page load is
    all it takes to make it certain.

    So one worker task per endpoint owns the session for its whole life,
    callers hand it work and wait for an answer, and a caller that goes away -
    a browser that navigated, a request that timed out - takes nothing down
    with it.
    """

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url
        self.tools: list[str] = []
        self.state = "unknown"
        self.detail = ""
        self._inbox: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None

    # -- the caller's half ---------------------------------------------------

    async def call(self, tool: str, arguments: dict | None = None) -> Any:
        """Call one tool. Opens or reopens the session as needed."""
        inbox = self._ensure_worker()
        answer: asyncio.Future = asyncio.get_running_loop().create_future()
        await inbox.put((tool, arguments, answer))
        try:
            # Shielded, so a caller that is cancelled - and a browser cancels
            # by navigating - leaves the call to finish rather than reaching
            # into the session that is servicing it.
            return await asyncio.wait_for(asyncio.shield(answer), CALL_TIMEOUT)
        except asyncio.TimeoutError:
            self.state = "unreachable"
            self.detail = (f"{tool} did not answer within {CALL_TIMEOUT:.0f}s; "
                           f"the session will be reopened")
            self._restart()
            raise RuntimeError(self.detail) from None

    async def close(self) -> None:
        worker, self._worker, self._inbox = self._worker, None, None
        if worker is not None and not worker.done():
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
        self.state = "closed"

    def _ensure_worker(self) -> asyncio.Queue:
        if self._worker is None or self._worker.done():
            self._inbox = asyncio.Queue()
            self._worker = asyncio.create_task(
                self._serve(self._inbox), name=f"mcp:{self.name}")
        assert self._inbox is not None
        return self._inbox

    def _restart(self) -> None:
        """Abandon a session that stopped answering. The next call reopens."""
        worker, self._worker, self._inbox = self._worker, None, None
        if worker is not None and not worker.done():
            worker.cancel()

    # -- the worker's half ---------------------------------------------------

    async def _serve(self, inbox: asyncio.Queue) -> None:
        """Own one session and answer from it, one call at a time."""
        stack: contextlib.AsyncExitStack | None = None
        session: Any = None
        try:
            while True:
                tool, arguments, answer = await inbox.get()
                if answer.done():          # the caller gave up before we began
                    continue
                for attempt in (1, 2):
                    try:
                        if session is None:
                            stack, session = await self._open()
                        result = await session.call_tool(tool, arguments or {})
                        if not answer.done():
                            answer.set_result(_unwrap(result))
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - reported, not raised
                        await _shut(stack)
                        stack = session = None
                        if attempt == 2:
                            self.state = "unreachable"
                            self.detail = str(exc)[:300]
                            if not answer.done():
                                answer.set_exception(exc)
        except asyncio.CancelledError:
            raise
        finally:
            await _shut(stack)

    async def _open(self) -> tuple[contextlib.AsyncExitStack, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        stack = contextlib.AsyncExitStack()
        await stack.__aenter__()
        try:
            read, write, _ = await stack.enter_async_context(
                streamable_http_client(self.url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listing = await session.list_tools()
        except BaseException:
            await stack.aclose()
            raise
        self.tools = sorted(t.name for t in listing.tools)
        self.state, self.detail = "connected", ""
        return stack, session


async def _shut(stack: contextlib.AsyncExitStack | None) -> None:
    """Close a session, from the task that opened it and nowhere else."""
    if stack is None:
        return
    with contextlib.suppress(Exception):
        await stack.aclose()


def _unwrap(result: Any) -> Any:
    """The useful half of a tool result.

    The SDK returns structured content when a tool declares a return type and
    text content otherwise. Both are handled here rather than at forty call
    sites, and a tool that returns text which happens to be JSON is parsed -
    the alternative is every caller doing it, differently.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps a bare return value under "result"; a dict return comes
        # back as itself.
        return structured.get("result", structured)
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text
    return None


class Client:
    """Every endpoint one application talks to, and its own call log."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._endpoints: dict[str, Endpoint] = {}
        self.calls: deque = deque(maxlen=CALL_LOG_SIZE)

    def endpoint(self, name: str, path: str) -> Endpoint:
        held = self._endpoints.get(name)
        if held is None:
            held = Endpoint(name, f"{self.base_url}{path}")
            self._endpoints[name] = held
        return held

    async def call(self, name: str, path: str, tool: str,
                   arguments: dict | None = None) -> Any:
        endpoint = self.endpoint(name, path)
        started = datetime.now()
        try:
            value = await endpoint.call(tool, arguments)
            self._note(endpoint, tool, started, ok=True)
            return value
        except Exception as exc:  # noqa: BLE001 - a refusal is a result
            self._note(endpoint, tool, started, ok=False, error=str(exc)[:200])
            raise

    def _note(self, endpoint: Endpoint, tool: str, started: datetime, *,
              ok: bool, error: str = "") -> None:
        self.calls.appendleft({
            "ts": started.isoformat(),
            "endpoint": endpoint.name,
            "url": endpoint.url,
            "tool": tool,
            "ok": ok,
            "error": error,
            "ms": round((datetime.now() - started).total_seconds() * 1000, 1),
            "transport": "streamable-http",
        })

    def status(self) -> dict:
        return {
            "platform": self.base_url,
            "endpoints": [{"name": e.name, "url": e.url, "state": e.state,
                           "detail": e.detail, "tools": e.tools}
                          for e in self._endpoints.values()],
            "calls": list(self.calls)[:60],
        }

    async def close(self) -> None:
        for endpoint in list(self._endpoints.values()):
            await endpoint.close()
