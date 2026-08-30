"""Calling the toolsets over MCP, for real.

``USE_MCP`` was documented as a supported switch and was never implemented -
the docstring claimed the graph could run either way and nothing checked. This
is the half that was missing.

With ``USE_MCP=1`` the investigator's evidence lookups leave the process: each
toolset is spawned as its own MCP server over stdio and the calls become
genuine round-trips across a protocol boundary. With it off, the same functions
are called directly. Both paths are recorded with the transport they used, so
the console shows which one actually happened rather than which one was
configured.

Three things make this safe to leave in a demo:

*   **Lazily started, then kept.** A subprocess per call would make the
    boundary real and the demo unusable. Sessions are opened on first use and
    held.
*   **Falls back rather than fails.** If a server cannot be spawned the call
    runs in-process and the log says so. A protocol demonstration is not worth
    losing a correction run over.
*   **Bounded to reads.** Only read-only tools are routed this way. Publishing
    to a channel over a pipe that might have died halfway is a considerably
    worse idea than publishing in-process, and the approval gate is not
    something to put a transport underneath.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from contextlib import AsyncExitStack
from typing import Any

from sc.mcp._runtime import record
from sc.mcp.registry import BY_ID, owner_of

# Which toolset serves which tool. Only read-only tools appear here, and only
# ones whose server wrapper returns exactly what the in-process function does -
# a route whose two transports disagree about the shape of an answer would make
# the switch a behavioural change, which is the one thing it must not be.
ROUTES: dict[str, str] = {
    "get_network_state": "product-catalog",
    "trace_dependencies": "product-catalog",
    "variant_diff": "product-catalog",
    "get_derivation": "product-catalog",
    "channel_rules": "channel-registry",
    "get_listing_state": "channel-registry",
    "search_docs": "knowledge-base",
    "get_doc": "knowledge-base",
}


def enabled() -> bool:
    """Is the MCP transport switched on?

    Read per call rather than cached: the System Control panel can flip it
    mid-demo, and a value captured at import would make the switch a lie in
    the other direction.
    """
    return os.environ.get("USE_MCP", "0").strip().lower() in {"1", "true", "yes"}


class _Bridge:
    """A background event loop holding one session per toolset.

    The graph is synchronous and the MCP client is not. Rather than sprinkle
    ``asyncio.run`` through the call sites - which would tear down and rebuild
    a session for every lookup - one loop runs on its own thread for the life
    of the process and the sync side submits work to it.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._sessions: dict[str, Any] = {}
        self._stack: AsyncExitStack | None = None
        self._lock = threading.Lock()
        self._failed: set[str] = set()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None:
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, daemon=True,
                                      name="mcp-bridge")
            thread.start()
            self._loop, self._thread = loop, thread
            return loop

    async def _session(self, toolset_id: str):
        if toolset_id in self._sessions:
            return self._sessions[toolset_id]

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if self._stack is None:
            self._stack = AsyncExitStack()

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", BY_ID[toolset_id].module],
            env=dict(os.environ),
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions[toolset_id] = session
        return session

    async def _call(self, toolset_id: str, tool: str, arguments: dict) -> Any:
        session = await self._session(toolset_id)
        result = await session.call_tool(tool, arguments)
        # FastMCP returns content blocks; the structured result is what the
        # in-process path would have returned, so prefer it and fall back to
        # parsing text only when it is absent.
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured.get("result", structured)
        import json
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
        return {}

    def call(self, tool: str, arguments: dict, timeout: float = 25.0) -> Any:
        toolset_id = ROUTES[tool]
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._call(toolset_id, tool, arguments), loop)
        return future.result(timeout=timeout)

    def note_failure(self, toolset_id: str) -> None:
        self._failed.add(toolset_id)

    def has_failed(self, toolset_id: str) -> bool:
        return toolset_id in self._failed


_bridge = _Bridge()


def call(tool: str, arguments: dict, direct) -> Any:
    """Run a tool over MCP if enabled, in-process otherwise.

    ``direct`` is the in-process callable, and it is also the fallback. The
    return value is the same either way - that is the property that makes the
    switch a transport decision rather than a behavioural one.
    """
    toolset_id = ROUTES.get(tool)

    if not enabled() or toolset_id is None or _bridge.has_failed(toolset_id):
        started = time.perf_counter()
        try:
            result = direct(**arguments)
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
            record(tool, "in-process", (time.perf_counter() - started) * 1000,
                   False, str(exc))
            raise
        record(tool, "in-process", (time.perf_counter() - started) * 1000, True)
        return result

    started = time.perf_counter()
    try:
        result = _bridge.call(tool, arguments)
        record(tool, "stdio", (time.perf_counter() - started) * 1000, True,
               f"{owner_of(tool)} over MCP")
        return result
    except Exception as exc:  # noqa: BLE001 - the demo matters more
        # One failure retires the toolset for the rest of the process. Retrying
        # a server that will not start, once per lookup, turns a misconfigured
        # switch into a run that appears to hang.
        _bridge.note_failure(toolset_id)
        record(tool, "stdio", (time.perf_counter() - started) * 1000, False,
               f"{exc} - falling back in-process")
        return direct(**arguments)


def status() -> dict:
    """What the console reports about the transport."""
    return {
        "enabled": enabled(),
        "routed_tools": sorted(ROUTES),
        "degraded": sorted(_bridge._failed),
    }
