"""Reading the reference pack out of SQLite, for the in-process backend.

One join, one query. The other source is ``scripts/load_graph.py``, which asks
the same four systems the same questions over MCP; both hand
``sc/kg/project.py`` the identical ``(system_id, event_type, payload)`` triples.

**Why this reads the database directly rather than dialling MCP.**

``/api/kg/*`` handlers are synchronous, and FastAPI runs those in a bounded
worker pool. A handler that blocked on an HTTP call to a route in *this same
process* would hold a pool slot while waiting for one, which under concurrent
readers is a deadlock with no error message attached to it. The one self-dial
this platform already does - ``estate_server.connect_all`` - is careful to run
once, at startup, off the request path, in a background task, and says why.

It would also be theatre. ``sc.main`` *is* the platform; going over a protocol
to read its own SQLite file demonstrates no boundary, it adds a hop. The
protocol claim is earned where it is genuinely true - by the loader and by the
back-office console, which are separate processes that cannot see this database
at all. Making the API pretend as well would cheapen both.

The honesty is carried by the ``route`` field instead: this path stamps
``sqlite`` and the loader stamps ``mcp``, so a graph can always say how it was
built.
"""

from __future__ import annotations

from sc import db


def reference_events() -> list[tuple[str, str, dict]]:
    """Everything the reference systems delivered, with its carrier.

    Selected by **lane**, not by system id. ``sc/`` may not name a system
    outside the manifest - ``tests/test_estate.py`` walks this directory to
    check - and selecting by lane is also the more truthful query: what makes
    a row reference data is which lane it is on, not which of four ids happens
    to be against it today.

    Ordered by sequence so two reads of the same database project the same
    graph. The projection folds campaigns together and takes the newest stock
    snapshot per depot, and both of those depend on the order it sees them in.
    """
    from sc.replay.tape import LANE_REF

    rows = db.query(
        "SELECT a.system_id AS system_id, e.type AS type, e.payload AS payload"
        "  FROM events e JOIN arrivals a ON a.event_id = e.id"
        " WHERE e.lane = ? ORDER BY e.seq", (LANE_REF,))
    return [(r["system_id"], r["type"], db.loads(r["payload"])) for r in rows]


def reference_count() -> int:
    """How many reference events are loaded. Reported by ``/api/kg/status``."""
    from sc.replay.tape import LANE_REF

    row = db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?", (LANE_REF,))
    return row["n"] if row else 0
