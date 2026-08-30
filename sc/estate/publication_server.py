"""Each publication system, as its own MCP endpoint.

The ingest estate is ten servers because ten systems send data. The publication
estate is six because six channels own listings, and the same argument applies:
one server with a channel argument is one system with a protocol bolted on.

What is different here, and it is the whole reason this file is separate from
`server.py`, is that these systems **change what a shopper sees**. So the
partition matters more rather than less.

**The safeguards travel with the tool, not with the caller.** The three refusals
- a recorded approval, evidence that has not moved, no open safety violation -
are enforced at the planning boundary, and every path through here goes through
it. Reaching `publish` over a pipe does not exempt it, and there is deliberately
no code here that could publish on its own: the tool asks `remediation`, which
asks `tools.planning`, which refuses on its own terms.

**Reading is separate from writing, per system.** `impact` and `plan` answer
what a correction reaches and what would happen, and neither writes. An operator
who wants to show somebody the blast radius does not have to hand over the
ability to act on it.

The freeze rule is applied here as well as in the report, because a tool that
would attempt a print run inside its window is a tool that should not exist -
not one whose caller is expected to check first.
"""

from __future__ import annotations

from typing import Any

from sc.estate import publication

#: What a publication system exposes. Two reads and one write, and the write is
#: the one that goes through every gate.
TOOLS: tuple[str, ...] = ("describe_channel", "impact", "publish_correction")

#: The servers, held so their session managers can be started with the
#: application - mounting a Starlette sub-app does not run its lifespan.
_SERVERS: list[Any] = []


def _describe(system) -> dict:
    return {
        "id": system.id,
        "channel_id": system.channel_id,
        "title": system.title,
        "owner": system.owner,
        # The two facts that decide how a correction reaching this channel is
        # handled, said plainly rather than left for a caller to infer from a
        # number of days.
        "recallable": system.recallable,
        "freeze_days": system.freeze_days,
        "note": ("what this channel publishes cannot be recalled"
                 if not system.recallable
                 else "published content can be replaced in place"),
    }


def _impact(system, entity_id: str) -> dict:
    """What a correction to this entity would mean *for this channel*.

    Scoped to the asking system. A marketplace connector has no business
    enumerating what the print channel is about to publish, and an estate where
    every publisher can read every other's queue is one database with six front
    doors.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    mine = [group for group in publication.blast_to_systems(trace, base)
            if group["system"] == system.id]
    if not mine:
        return {"channel_id": system.channel_id, "affected": False,
                "skus": [], "listings": []}
    group = mine[0]
    return {
        "channel_id": system.channel_id,
        "affected": True,
        "skus": group["skus"],
        "listings": group["listings"],
        "recallable": system.recallable,
    }


def _publish(system, incident_id: str, scenario_id: str,
             entity_id: str) -> dict:
    """Push an approved correction to this channel.

    Every gate is somewhere else and every one of them still binds. This
    function cannot publish; it asks the thing that can, and that thing refuses
    without a recorded approval whichever server it was reached through.

    A channel whose artefact cannot be recalled, inside its window, is refused
    here rather than attempted - a tool that would start a print run it cannot
    stop should not exist, rather than existing and expecting its caller to
    check first.
    """
    from sc.estate import remediation
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    if not system.recallable and system.freeze_days:
        return {
            "channel_id": system.channel_id,
            "sent": False,
            "reason": (f"{system.channel_id} is inside a "
                       f"{system.freeze_days}-day freeze window and what it "
                       f"publishes cannot be recalled"),
        }

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    result = remediation.dispatch(incident_id, scenario_id, trace, base)
    mine = [row for row in result["systems"] if row["system"] == system.id]
    return {
        "channel_id": system.channel_id,
        "sent": bool(result["committed"]) and bool(
            mine and mine[0]["outcome"] == remediation.SENT),
        "reason": (mine[0]["reason"] if mine else "")
                  or ("" if result["committed"] else result.get("reason", "")),
        "committed": result["committed"],
    }


def build(system) -> Any:
    """One publication system's MCP server."""
    from mcp.server.fastmcp import FastMCP

    # Served at the root of its own app, for the same reason the ingest servers
    # are: mounted at a path, FastMCP's default sub-path would put the endpoint
    # somewhere the connection record does not name.
    mcp = FastMCP(system.id, streamable_http_path="/")

    @mcp.tool()
    def describe_channel() -> dict:
        """What this channel is, and whether what it publishes can be recalled."""
        return _describe(system)

    @mcp.tool()
    def impact(entity_id: str) -> dict:
        """Which SKUs on this channel a correction to an entity would reach."""
        return _impact(system, entity_id)

    @mcp.tool()
    def publish_correction(incident_id: str, scenario_id: str,
                           entity_id: str) -> dict:
        """Push an approved correction to this channel.

        Refuses without a recorded approval, without unmoved evidence, and with
        an open safety violation - none of which is checked here, and all of
        which still bind.
        """
        return _publish(system, incident_id, scenario_id, entity_id)

    return mcp


async def start(stack) -> int:
    """Run every mounted publisher's session manager for the life of the app."""
    started = 0
    for server in _SERVERS:
        await stack.enter_async_context(server.session_manager.run())
        started += 1
    return started


def mount(app) -> list[dict]:
    """Publish every publication system onto a FastAPI app.

    The trailing slash is load-bearing: Starlette's Mount strips the prefix, so
    a sub-app whose only route is "/" answers 405 without it.
    """
    from sc.state import baseline as baseline_mod

    mounted: list[dict] = []
    try:
        systems = publication.systems(baseline_mod.get())
    except Exception as exc:  # noqa: BLE001 - no catalog, no publishers
        return [{"error": str(exc)[:200]}]

    for system in systems:
        path = f"/mcp/publish/{system.channel_id.lower()}"
        try:
            server = build(system)
            app.mount(path, server.streamable_http_app())
            _SERVERS.append(server)
        except Exception as exc:  # noqa: BLE001 - one channel is not the estate
            mounted.append({"id": system.id, "url": path,
                            "error": str(exc)[:200]})
            continue
        mounted.append({
            "id": system.id,
            "channel_id": system.channel_id,
            "title": system.title,
            "url": f"{path}/",
            "transport": "http",
            "tools": list(TOOLS),
            # Named here so an operator can see, from the listing alone, which
            # of these servers can change what a shopper sees.
            "mutating": ["publish_correction"],
        })
    return mounted
