"""event-plane - the integration bus, over MCP.

    python -m sc.mcp.event_plane

Supplier feeds, spec documents and channel acknowledgements as they arrived.

Not read-only, and the exception is worth naming: advancing the tape is a demo
control. In a real deployment events arrive because the world produced them,
and nothing would expose a tool that manufactures them. It moves the clock,
never the catalog - which is why the estate still has exactly one server that
can change what a channel sees, and this is not it.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.replay import ingest, tape

mcp = FastMCP("event-plane")


@mcp.tool()
def query_events(limit: int = 50, since_seq: int = 0,
                 event_type: str | None = None) -> dict:
    """Events released so far. The future of the tape is never visible.

    event_type: SUPPLIER_FEED | SPEC_DOC | CHANNEL_STATUS | CATALOG_UPDATE |
    PUBLISH_TELEMETRY | COMMS
    """
    def run() -> dict:
        events = tape.released(limit=limit, since_seq=since_seq,
                               event_type=event_type)
        return {"events": [e.model_dump(mode="json") for e in events],
                "replay": tape.state().model_dump(mode="json")}

    run.__name__ = "query_events"
    return instrumented(run)()


@mcp.tool()
def advance_events(steps: int = 1) -> dict:
    """Release the next events from the tape and ingest them.

    Returns the correction signals ingestion derived, which is where a
    structured feed row becomes a detected correction.
    """
    def run() -> dict:
        released = tape.advance(steps)
        signals = ingest.ingest(released)
        return {"released": [e.model_dump(mode="json") for e in released],
                "signals": [s.model_dump(mode="json") for s in signals],
                "replay": tape.state().model_dump(mode="json")}

    run.__name__ = "advance_events"
    return instrumented(run)()


@mcp.tool()
def replay_state() -> dict:
    """Where the simulated clock currently sits."""
    def run() -> dict:
        return {"replay": tape.state().model_dump(mode="json"),
                "inject_seq": tape.inject_seq(),
                "ingest_cursor": ingest.cursor()}

    run.__name__ = "replay_state"
    return instrumented(run)()


if __name__ == "__main__":
    serve(mcp, "event-plane")
