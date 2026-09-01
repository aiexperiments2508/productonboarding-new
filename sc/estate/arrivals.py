"""What landed, from whom, when, and what was wrong with it.

This is the seam between two things that must not be confused.

**Arrival is concurrent.** Ten systems deliver at once, in batches, at
intervals none of them coordinates. Batches interleave and a later sequence can
land before an earlier one. That is real and the estate panel shows it.

**Ingestion is sequenced.** The consumer cursor in ``event_cursors`` is a
single watermark and ``ingest()`` drops anything at or behind it. Feed it a
batch containing sequence 50 while sequence 30 is still in flight and the
cursor advances past 30; when 30 finally lands it is discarded as already
seen. Nothing raises. Facts are simply missing, on a run that reports success.

So this module records arrivals as they land and releases them into ingestion
only up to the highest sequence *every* predecessor of which has arrived. An
early arrival waits for the gap in front of it to fill. That is what makes the
race visible without letting it change the record - and it is the same answer a
partitioned log gives, arrived at without a partition.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sc import db
from sc.estate.emitter import Batch

#: Where the display surfaces stop reading. An estate that has been running for
#: an hour has more arrivals than anybody scrolls.
RECENT_LIMIT = 200


def _now() -> str:
    """Real wall clock, deliberately.

    Everything else in this system records simulated time, because everything
    else is describing the world the tape is replaying. An arrival is not part
    of that world - it is a fact about this process talking to another one, and
    the useful question about it is "how long ago", not "on which simulated
    day".
    """
    return datetime.now().isoformat()


def record(batch: Batch, event_ids: dict[int, str]) -> list[dict]:
    """Record one delivery. One transaction, never one per event.

    Ten producers against a single SQLite writer is a contention problem the
    moment each event is its own commit; WAL permits one writer, and a batch of
    eight taken as eight transactions is eight chances to wait on the lock.

    Re-delivering a batch is a no-op rather than an error. A system that
    retries after a dropped connection has done nothing wrong, and the second
    copy carries the same sequence as the first.
    """
    batch_id = f"BAT-{batch.system_id}-{batch.ordinal:04d}"
    arrived_at = _now()
    rows = []
    with db.transaction() as conn:
        for sequence in batch.sequences:
            event_id = event_ids.get(sequence)
            if event_id is None:
                continue
            defects = [str(d) for d in batch.defects.get(sequence, ())]
            conn.execute(
                "INSERT OR IGNORE INTO arrivals"
                " (id, system_id, batch_id, event_id, seq, arrived_at, defects)"
                " VALUES (?,?,?,?,?,?,?)",
                (f"ARR-{uuid.uuid4().hex[:10]}", batch.system_id, batch_id,
                 event_id, sequence, arrived_at, db.dumps(defects)))
            rows.append({"system_id": batch.system_id, "batch_id": batch_id,
                         "event_id": event_id, "seq": sequence,
                         "arrived_at": arrived_at, "defects": defects})
    return rows


def releasable(after: int) -> int:
    """The highest sequence it is safe to release, given what has arrived.

    Walks forward from the cursor and stops at the first gap. Returning the
    maximum arrived sequence instead would be the bug this module exists to
    prevent: it would release past an event still in flight, and the cursor
    would then refuse that event when it landed.
    """
    rows = db.query(
        "SELECT seq FROM arrivals WHERE seq > ? ORDER BY seq", (after,))
    highest = after
    for row in rows:
        if row["seq"] != highest + 1:
            break
        highest = row["seq"]
    return highest


def defects_for(event_id: str) -> list[str]:
    """What was stamped on the arrival that carried this event."""
    row = db.one("SELECT defects FROM arrivals WHERE event_id = ?", (event_id,))
    return db.loads(row["defects"]) if row else []


def system_for(event_id: str) -> str | None:
    """Which system carried this event, or None if nothing has delivered it."""
    row = db.one("SELECT system_id FROM arrivals WHERE event_id = ?", (event_id,))
    return row["system_id"] if row else None


def recent(limit: int = RECENT_LIMIT) -> list[dict]:
    """The newest arrivals, newest first, for the estate panel."""
    rows = db.query(
        "SELECT * FROM arrivals ORDER BY arrived_at DESC, seq DESC LIMIT ?",
        (limit,))
    return [{**dict(r), "defects": db.loads(r["defects"])} for r in rows]


def recent_for(system_id: str, limit: int = RECENT_LIMIT) -> list[dict]:
    """This one system's newest arrivals, newest first.

    Separate from ``recent`` because reading the newest N across the whole
    estate and filtering afterwards is not a slower route to the same answer -
    it is a different answer, and a wrong one for a quiet system. A feed that
    delivers in ones and twos is crowded out of any fixed window by one that
    delivers in tens, so it reports having sent nothing while its rows sit in
    the table just past the cut. ``label-artwork`` is the live example: thirteen
    documents against a data pool that delivers thousands.

    ``idx_arrivals_system`` is on ``(system_id, seq)`` for exactly this.
    """
    rows = db.query(
        "SELECT * FROM arrivals WHERE system_id = ?"
        " ORDER BY arrived_at DESC, seq DESC LIMIT ?",
        (system_id, limit))
    return [{**dict(r), "defects": db.loads(r["defects"])} for r in rows]


def summary() -> list[dict]:
    """Per system: how much has landed, in how many batches, how much of it
    defective. What the estate panel counts."""
    rows = db.query(
        "SELECT system_id,"
        "       COUNT(*) AS arrivals,"
        "       COUNT(DISTINCT batch_id) AS batches,"
        "       SUM(CASE WHEN defects = '[]' THEN 0 ELSE 1 END) AS defective,"
        "       MAX(arrived_at) AS last_seen"
        " FROM arrivals GROUP BY system_id ORDER BY system_id")
    return [dict(r) for r in rows]


def counts_by_defect() -> dict[str, int]:
    """How many arrivals carry each defect. Used to check the answer key has
    not quietly stopped producing one of them."""
    tally: dict[str, int] = {}
    for row in db.query("SELECT defects FROM arrivals WHERE defects != '[]'"):
        for defect in db.loads(row["defects"]):
            tally[defect] = tally.get(defect, 0) + 1
    return tally
