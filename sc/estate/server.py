"""Each external system, as its own MCP server.

The requirement is that every system connects over MCP. The temptation is to
satisfy it with one server exposing ten tools named after ten systems, which
would be one system with a protocol bolted on - the exact thing the toolset
partition already argues against.

So each system gets its own server, its own endpoint, and its own tools, and
they are mounted at ``/mcp/{system_id}`` on the same process the UI is served
from. That is a deployment choice, not an architectural one: the calls still
cross the protocol, the endpoints are still separately addressable, and moving
one system to its own host would be a change to a URL. Running ten processes to
prove a point about boundaries would cost a demo ten things that can fail.

Every tool here is **read-only**. A supplier system that could write to the
retailer's catalog is not a supplier system, it is a compromise waiting to
happen, and the one server in this estate that changes what a channel sees
already exists and is not this.

The tools are the three questions you actually ask an upstream system when
something is wrong with what it sent:

    describe_system      who are you and what are you supposed to send
    recent_deliveries    what have you sent lately, and was any of it bad
    fetch_payload        show me exactly what you sent for this one
"""

from __future__ import annotations

from typing import Any

from sc.estate.manifest import BY_ID, SYSTEMS, System

#: Tools every system in the estate exposes. Named here so the connection
#: handshake can be checked against what the manifest promised, rather than
#: trusting whatever a server happens to answer with.
TOOLS: tuple[str, ...] = (
    "describe_system", "recent_deliveries", "fetch_payload")


def _describe(system: System) -> dict:
    return {
        "id": system.id,
        "title": system.title,
        "owner": system.owner,
        "purpose": system.why,
        "emits": list(system.emits),
        "precedence": system.precedence,
        # A system that says how it misbehaves is more useful than one that
        # claims it does not. This is the estate being honest about itself,
        # which is only possible because it is simulated - a real supplier
        # would not publish its own defect rate, and the retailer would have
        # to measure it. That measurement is what `arrivals` is.
        "known_defects": [str(d) for d in system.defects],
        "conforms": system.well_behaved,
    }


def _recent(system: System, limit: int = 20) -> list[dict]:
    from sc.estate import arrivals

    # Filtered in the query, not after it. See `arrivals.recent_for` for why
    # the estate-wide window this used to read was a wrong answer for a quiet
    # system rather than a slow one.
    rows = arrivals.recent_for(system.id, max(limit, 1))
    return [{"event_id": r["event_id"], "seq": r["seq"],
             "batch": r["batch_id"], "arrived_at": r["arrived_at"],
             "defects": r["defects"]}
            for r in rows]


def _payload(system: System, event_id: str) -> dict:
    """One payload, exactly as this system sent it.

    Scoped to the asking system on purpose. A supplier portal has no business
    reading what the data pool sent, and an estate where every system can read
    every other one's traffic is a single database with ten front doors.
    """
    from sc import db
    from sc.estate import arrivals

    if arrivals.system_for(event_id) != system.id:
        return {"error": f"{system.id} did not deliver {event_id}"}
    row = db.one("SELECT id, seq, ts, type, source, payload, body"
                 " FROM events WHERE id = ?", (event_id,))
    if row is None:
        return {"error": f"no such event: {event_id}"}
    return {
        "event_id": row["id"], "seq": row["seq"], "ts": row["ts"],
        "type": row["type"], "payload": db.loads(row["payload"]),
        "body": row["body"],
        "defects": arrivals.defects_for(event_id),
    }


def build(system: System) -> Any:
    """One system's MCP server.

    Built per system rather than parameterised at call time so that each
    endpoint's tool list is genuinely that system's own - a client asking
    ``tools/list`` gets an answer scoped to who it is talking to, which is the
    difference between ten servers and one server with a system argument.
    """
    from mcp.server.fastmcp import FastMCP

    # Served at the root of its own app rather than FastMCP's default `/mcp`
    # sub-path. Mounted at `/mcp/{id}`, the default would put the endpoint at
    # `/mcp/{id}/mcp`, so the address a connection record holds would not be
    # the address a reader sees in the estate listing - and the one that is
    # wrong answers 405 rather than saying so.
    mcp = FastMCP(system.id, streamable_http_path="/")

    @mcp.tool()
    def describe_system() -> dict:
        """Who this system is, what it emits, and how well it conforms."""
        return _describe(system)

    @mcp.tool()
    def recent_deliveries(limit: int = 20) -> list[dict]:
        """What this system has delivered lately, with any defects stamped."""
        return _recent(system, limit)

    @mcp.tool()
    def fetch_payload(event_id: str) -> dict:
        """The payload this system sent for one event, exactly as sent."""
        return _payload(system, event_id)

    return mcp


#: The built servers, held so their session managers can be started with the
#: application. Mounting a Starlette sub-app does not run its lifespan, and a
#: streamable-HTTP server whose session manager was never started accepts a
#: connection and then fails the first request - which reads as a broken system
#: rather than an unstarted one.
_SERVERS: list[Any] = []


async def start(stack) -> int:
    """Run every mounted system's session manager for the life of the app.

    Takes an ``AsyncExitStack`` owned by the caller rather than holding one
    here, so shutdown is the caller's business and this module has no lifecycle
    of its own to get out of step with the application's.
    """
    started = 0
    for server in _SERVERS:
        await stack.enter_async_context(server.session_manager.run())
        started += 1
    return started


def mount(app) -> list[dict]:
    """Publish every system onto a FastAPI app. Returns what was mounted.

    Streamable HTTP, which is what the current MCP specification defines. Each
    server is mounted under its own path, so a connection record's URL is the
    whole address of one system rather than a shared endpoint plus a routing
    argument.

    A system that fails to mount is reported and skipped rather than taken as
    fatal: nine suppliers and a note is a better demo than a stack trace.
    """
    mounted: list[dict] = []
    for system in SYSTEMS:
        # The trailing slash is load-bearing. Starlette's Mount strips the
        # prefix before the sub-app sees the request, so `/mcp/{id}` arrives at
        # the sub-app as an empty path and its only route is `/`. Without the
        # slash the endpoint answers 405, which reads as a broken server rather
        # than a wrong address.
        path = f"/mcp/{system.id}"
        try:
            server = build(system)
            app.mount(path, server.streamable_http_app())
            _SERVERS.append(server)
        except Exception as exc:  # noqa: BLE001 - one system is not the estate
            mounted.append({"id": system.id, "url": path, "error": str(exc)[:200]})
            continue
        mounted.append({
            "id": system.id,
            "title": system.title,
            "owner": system.owner,
            "url": f"{path}/",
            "transport": "http",
            "tools": list(TOOLS),
        })
    return mounted


def connect_all(base_url: str) -> list[dict]:
    """Connect every mounted system to itself, over HTTP.

    The estate ships in this process and could therefore be registered without
    a handshake. It is not, deliberately: a system that is only "connected"
    because a dictionary says so has not demonstrated anything, and the whole
    claim being made here is that these are reachable over a protocol. So each
    one is dialled the same way an external address would be, and one that does
    not answer is degraded exactly like an external one.

    Failures are recorded, never raised. Nine suppliers and a note is a better
    demo than a stack trace.
    """
    from sc.mcp import connections

    results: list[dict] = []
    for system in SYSTEMS:
        try:
            results.append(connections.connect_url(
                endpoint(system.id, base_url),
                connection_id=system.id,
                title=system.title,
                owner=system.owner,
                transport="http"))
        except Exception as exc:  # noqa: BLE001 - one system is not the estate
            results.append({"id": system.id, "state": connections.DEGRADED,
                            "detail": str(exc)[:200]})
    return results


def endpoint(system_id: str, base_url: str = "") -> str:
    """Where a system answers. One place that knows the URL shape."""
    if system_id not in BY_ID:
        raise KeyError(system_id)
    return f"{base_url}/mcp/{system_id}/"
