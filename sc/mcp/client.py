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


def _route_for(toolset_id: str) -> tuple[str, str]:
    """How to reach a toolset: its transport, and the address for that transport.

    Built-in toolsets are spawned as modules, which is what they have always
    been and what their tests assert. A connected system is reached at the
    address its connection record holds.

    Built-in wins where both exist. A connected system claiming a built-in
    identifier must not become the way that toolset is reached, for the same
    reason its tool cannot shadow a built-in tool name: the estate may add
    capabilities and may not redefine the ones that publish.
    """
    if toolset_id in BY_ID:
        return "stdio", BY_ID[toolset_id].module

    from sc.mcp import connections

    record = connections.get(toolset_id)
    if record is None:
        raise KeyError(f"no route to toolset {toolset_id!r}")
    return record["transport"] or "http", record["url"]


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
        """One session per toolset, opened on first use and held.

        The transport comes from the connection record rather than from this
        module, so a toolset that ships here is spawned and one somebody
        connected five minutes ago is dialled - and both are reached through the
        same `call()`, which is what keeps the switch a transport decision
        rather than a behavioural one.
        """
        if toolset_id in self._sessions:
            return self._sessions[toolset_id]

        from mcp import ClientSession

        if self._stack is None:
            self._stack = AsyncExitStack()

        transport, address = _route_for(toolset_id)
        if transport == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            streams = await self._stack.enter_async_context(stdio_client(
                StdioServerParameters(command=sys.executable,
                                      args=["-m", address],
                                      env=dict(os.environ))))
        elif transport == "sse":
            from mcp.client.sse import sse_client

            streams = await self._stack.enter_async_context(sse_client(address))
        else:
            from mcp.client.streamable_http import streamable_http_client

            streams = await self._stack.enter_async_context(
                streamable_http_client(address))

        # streamable_http yields a third element (a session-id callback); stdio
        # and sse yield two. Taking the first two works for all three rather
        # than branching on a shape that is not ours to depend on.
        read, write = streams[0], streams[1]
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
        # Resolved by the caller, which knows about admitted tools; looking it
        # up again here from ROUTES alone would silently refuse every tool that
        # arrived from a connected system.
        toolset_id = route_of(tool)
        if toolset_id is None:
            raise KeyError(f"no route for tool {tool!r}")
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._call(toolset_id, tool, arguments), loop)
        return future.result(timeout=timeout)

    def note_failure(self, toolset_id: str) -> None:
        self._failed.add(toolset_id)

    def has_failed(self, toolset_id: str) -> bool:
        return toolset_id in self._failed


_bridge = _Bridge()


def route_of(tool: str) -> str | None:
    """Which toolset serves a tool - built-in first, then admitted.

    A tool nothing declares returns None and runs in-process, which is the
    behaviour every caller already relies on.

    Only *admitted* tools from connected systems are routable. A discovered tool
    is visible and not callable, and this is the second place that is enforced
    rather than the only one: the evidence desk will not offer it either.
    """
    if tool in ROUTES:
        return ROUTES[tool]

    try:
        from sc.mcp import connections

        for record in connections.all_connections():
            if (record["state"] == connections.CONNECTED
                    and tool in record["admitted_tools"]):
                return record["id"]
    except Exception:  # noqa: BLE001 - an unreadable estate routes nothing
        return None
    return None


def call(tool: str, arguments: dict, direct) -> Any:
    """Run a tool over MCP if enabled, in-process otherwise.

    ``direct`` is the in-process callable, and it is also the fallback. The
    return value is the same either way - that is the property that makes the
    switch a transport decision rather than a behavioural one.
    """
    toolset_id = route_of(tool)

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
        transport, _ = _route_for(toolset_id)
        record(tool, transport, (time.perf_counter() - started) * 1000, True,
               f"{toolset_id} over MCP")
        return result
    except Exception as exc:  # noqa: BLE001 - the demo matters more
        # One failure retires the toolset for the rest of the process. Retrying
        # a server that will not start, once per lookup, turns a misconfigured
        # switch into a run that appears to hang.
        _bridge.note_failure(toolset_id)
        try:
            transport, _ = _route_for(toolset_id)
        except KeyError:
            transport = "stdio"
        record(tool, transport, (time.perf_counter() - started) * 1000, False,
               f"{exc} - falling back in-process")
        return direct(**arguments)


def handshake(url: str, transport: str = "http",
              timeout: float = 4.0) -> tuple[list[str], str | None]:
    """Ask an address what it can do. Returns (tools, error).

    A real MCP ``initialize`` followed by ``tools/list`` - never a guess from
    the URL. An address that answers is a system; one that does not is an
    address, and the difference is exactly what a connection record is for.

    Never raises. Every failure mode here - wrong scheme, nothing listening,
    something listening that is not an MCP server, a server too slow to answer -
    is a thing the operator needs told, not a thing that should end the request
    they made. The caller records the reason and marks the connection degraded.
    """
    async def ask() -> list[str]:
        from mcp import ClientSession

        if transport == "sse":
            from mcp.client.sse import sse_client as open_client
            args: tuple = (url,)
        else:
            # `streamable_http_client`, not the older `streamablehttp_client`
            # spelling - the latter is deprecated in mcp 1.29 and warns on
            # every call.
            from mcp.client.streamable_http import (
                streamable_http_client as open_client)
            args = (url,)

        async with open_client(*args) as streams:
            # streamable_http yields a third element (a session-id callback);
            # sse yields two. Taking the first two works for both rather than
            # branching on a shape that is not ours to depend on.
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                return sorted(t.name for t in listing.tools)

    loop = _bridge._ensure_loop()
    future = asyncio.run_coroutine_threadsafe(ask(), loop)
    try:
        return future.result(timeout=timeout), None
    except Exception as exc:  # noqa: BLE001 - every failure is a report
        future.cancel()
        return [], _reason(exc)


def _reason(exc: BaseException) -> str:
    """The useful sentence inside a failed handshake.

    The MCP clients run their transport in a task group, so almost everything
    that goes wrong arrives as an ExceptionGroup whose own message is
    "unhandled errors in a TaskGroup" - true, and no help at all to somebody
    who has just pasted an address. This digs out the innermost cause, which is
    the connection refused, the 404 or the bad scheme they actually need told.
    """
    seen: list[str] = []
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop(0)
        nested = getattr(current, "exceptions", None)
        if nested:
            stack.extend(nested)
            continue
        text = str(current).strip() or type(current).__name__
        label = f"{type(current).__name__}: {text}"
        if label not in seen:
            seen.append(label)
    return "; ".join(seen)[:400] or f"{type(exc).__name__}"


def status() -> dict:
    """What the console reports about the transport."""
    return {
        "enabled": enabled(),
        "routed_tools": sorted(ROUTES),
        "degraded": sorted(_bridge._failed),
    }
