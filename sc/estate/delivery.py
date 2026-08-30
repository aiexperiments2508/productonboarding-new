"""Recording what the estate delivered.

The tape decides *what* exists and when it becomes visible. This decides *who
carried it* and *in which batch*, and writes that down.

Kept apart from `tape.py` on purpose. The tape is the world's script - it would
be the same script if the retailer had one supplier and no integrations at all.
The estate is the set of pipes the script arrives through, and conflating the
two is how the MVP ended up with four suppliers standing in for ten systems.

The delivery is recorded, not simulated with sleeps. A batch that took two
seconds of real time to "arrive" would make the replay transport lie: an
operator who jumps to the inject expects to be at the inject, not two minutes
of pretend network away from it. What is faithful here is the *grouping* -
which system sent what, in what batch, with what stamped on it - and that is
what the Ingest Fabric renders and what the answer key is built from.
"""

from __future__ import annotations

from sc import db
from sc.contracts import Event
from sc.estate import arrivals, emitter
from sc.estate.manifest import SYSTEMS


def deliver(events: list[Event]) -> list[dict]:
    """Record a released window as arrivals from the systems that carried it.

    Events are dealt to their owning system, each system's share is cut into
    batches by its own seeded schedule, and each batch is written in one
    transaction. Ten producers against one SQLite writer is a contention
    problem the moment each event becomes its own commit.

    Idempotent: `arrivals.record` ignores an event it already holds, so
    re-releasing a window - which the replay transport does whenever somebody
    steps back and forward again - adds nothing and loses nothing.
    """
    if not events:
        return []

    owned: dict[str, list[int]] = {s.id: [] for s in SYSTEMS}
    ids: dict[int, str] = {}
    for event in events:
        system_id = emitter.owner_of(event.type, event.source, event.seq)
        owned.setdefault(system_id, []).append(event.seq)
        ids[event.seq] = event.id

    recorded: list[dict] = []
    for system_id, sequences in owned.items():
        if not sequences:
            continue
        system = next(s for s in SYSTEMS if s.id == system_id)
        for batch in emitter.schedule_for(system, sorted(sequences)):
            recorded.extend(arrivals.record(batch, ids))
    return recorded


def backfill() -> list[dict]:
    """Record arrivals for everything already released.

    A database seeded before the estate existed, or one where the clock was
    jumped past the inject by a script, has released events and no arrivals.
    Rather than leaving the Ingest Fabric empty on a system that has plainly
    been running, this deals out what is already visible.
    """
    rows = db.query(
        "SELECT * FROM events WHERE released_at IS NOT NULL"
        "  AND id NOT IN (SELECT event_id FROM arrivals) ORDER BY seq")
    if not rows:
        return []
    from sc.replay.tape import _row_to_event

    return deliver([_row_to_event(r) for r in rows])
