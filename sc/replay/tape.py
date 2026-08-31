"""Event replay.

Replaces the message broker. ``events.jsonl`` is loaded once into the ``events``
table, then released to consumers on a controllable clock - pause, single step,
1x, 10x, or jump straight to the inject. That control is what makes the demo
drivable: a judge asks "what happens when the supplier email lands?" and you
step one event.

Consumers track their offset in ``event_cursors`` and advance it in the same
transaction that writes their output, so a crash mid-processing redelivers
rather than loses. Reprocessing is safe because every downstream mutation is
idempotency-keyed.

**Two lanes.** Everything above describes ``lane = 'TAPE'``: the recorded
flight, which the transport may rewind, step and re-release at will. A second
lane, ``LIVE``, holds what arrived through a vendor intake while the process
was running - see ``append_live``.

The distinction is a column and never a sequence range, and that is worth
stating because the sequence range is the tempting version. Live events *are*
numbered from a high band so they are unmistakable in a sqlite shell, but no
query may infer a lane from a number. Two things go wrong the moment one does:

* ``advance`` selects ``seq > cursor`` with no upper bound, so the cursor walks
  into the band by itself and the clock never finds an end. The transport then
  reports 19,000% through a recording it has not played.
* ``ingest`` keeps one integer watermark. Handing it a live event at 1,000,000
  sets that watermark to 1,000,000, and every remaining tape event is dropped
  as already-seen. Ingestion stops permanently and reports success.

Both are silent. So every query below that means "the recorded flight" says
``lane = 'TAPE'`` in as many words, and exactly one - ``released`` - widens.
"""

from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from sc import db
from sc.contracts import Event, ReplayState
from sc.state import baseline as baseline_mod

log = logging.getLogger(__name__)

CURSOR_KEY = "replay_cursor"
SPEED_KEY = "replay_speed"
RUNNING_KEY = "replay_running"

# Seconds of wall clock per simulated day at 1x. A 56-day horizon replays in
# about two minutes, which is the right pace to narrate over.
SECONDS_PER_DAY = 2.0

LANE_TAPE = "TAPE"
LANE_LIVE = "LIVE"

#: Where live sequence numbers start. The recording is a few thousand events,
#: so a live row is unmistakable at a glance in a log line or a sqlite shell.
#: This is a numbering convention and nothing else - see the module docstring
#: for why it must never become a predicate.
LIVE_BASE = 1_000_000

#: Called with (events, signals) once a submission has been ingested, so it
#: reaches the live feed the way a released event does. Mirrors
#: ``run_clock(on_events)`` deliberately: it is the seam that keeps the estate
#: from importing the application that mounts it.
_live_sink = None


def set_live_sink(sink) -> None:
    """Register what to tell when a submission lands. See ``_live_sink``."""
    global _live_sink
    _live_sink = sink


def load_tape(path: Path | None = None, reset: bool = False) -> dict:
    """Load the tape into SQLite. Idempotent unless ``reset``."""
    tape = path or (baseline_mod.data_dir() / "events.jsonl")
    conn = db.connect()

    if reset:
        # The recorded flight only. Reloading the tape reseeds the recording,
        # and a supplier's submission is not part of the recording - deleting
        # it here would retract history because a file was re-read.
        conn.execute("DELETE FROM events WHERE lane = ?", (LANE_TAPE,))
        conn.execute("DELETE FROM event_cursors")
        db.set_config(CURSOR_KEY, "0")

    existing = db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?",
                      (LANE_TAPE,))["n"]
    if existing and not reset:
        return {"loaded": 0, "total": existing, "skipped": True}

    rows = []
    with tape.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            rows.append((e["id"], e["seq"], e["ts"], e["type"], e["source"],
                         db.dumps(e["payload"]), e.get("body")))

    with db.transaction() as c:
        c.executemany(
            "INSERT OR REPLACE INTO events (id, seq, ts, type, source, payload,"
            " body, lane) VALUES (?,?,?,?,?,?,?,'TAPE')", rows)
    db.set_config(CURSOR_KEY, "0")
    return {"loaded": len(rows), "total": len(rows), "skipped": False}


# ---------------------------------------------------------------------------
# Cursor and state
# ---------------------------------------------------------------------------


def cursor() -> int:
    return int(db.get_config(CURSOR_KEY, "0") or 0)


def total_events() -> int:
    """How long the recording is.

    The transport's denominator, so it counts the recorded flight and nothing
    else. A progress bar whose denominator grew every time a supplier filled in
    a form would be measuring the wrong thing.
    """
    row = db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?", (LANE_TAPE,))
    return row["n"] if row else 0


def last_tape_seq() -> int:
    """The end of the recording. What a jump target is clamped to."""
    row = db.one("SELECT MAX(seq) AS s FROM events WHERE lane = ?", (LANE_TAPE,))
    return int(row["s"]) if row and row["s"] is not None else 0


def state() -> ReplayState:
    seq = cursor()
    row = db.one("SELECT ts FROM events WHERE lane = ? AND seq <= ?"
                 " ORDER BY seq DESC LIMIT 1", (LANE_TAPE, seq))
    return ReplayState(
        running=db.get_config(RUNNING_KEY, "0") == "1",
        speed=float(db.get_config(SPEED_KEY, "1") or 1.0),
        cursor_seq=seq,
        total_events=total_events(),
        sim_clock=datetime.fromisoformat(row["ts"]) if row else None,
    )


def sim_now() -> datetime:
    """The system's notion of "now".

    Everything time-aware runs on the replay clock, not on wall-clock time.
    Defaulting an as-of query to datetime.now() would ask about a date outside
    the planning horizon entirely and quietly return nothing.

    Reads the recorded flight only, and here that is load bearing rather than
    tidy. A live submission is stamped *with* this clock; if it also moved this
    clock it would become the newest event the instant it landed, and the
    horizon would shift under every open panel because somebody pressed Submit.
    """
    row = db.one("SELECT ts FROM events WHERE lane = ? AND seq <= ?"
                 " ORDER BY seq DESC LIMIT 1", (LANE_TAPE, cursor()))
    if row is not None:
        return datetime.fromisoformat(row["ts"])
    base = baseline_mod.get()
    return datetime.combine(base.horizon_start, datetime.min.time())


def _row_to_event(row) -> Event:
    # `lane` is read defensively: a sqlite3.Row raises IndexError on a missing
    # key rather than returning None, and not every caller selects it.
    keys = row.keys() if hasattr(row, "keys") else ()
    return Event(
        id=row["id"], seq=row["seq"], ts=datetime.fromisoformat(row["ts"]),
        type=row["type"], source=row["source"],
        payload=db.loads(row["payload"]), body=row["body"],
        lane=(row["lane"] if "lane" in keys else None) or LANE_TAPE,
    )


def released(limit: int = 200, since_seq: int = 0,
             event_type: str | None = None) -> list[Event]:
    """Events visible so far. The UI never sees the future of the tape.

    The one query in this module that spans both lanes. A submission is visible
    the moment it lands: it has already happened, and there is no sense in
    which a reader is being shown the future by being told about it.
    """
    sql = ("SELECT * FROM events WHERE (lane = 'LIVE' OR seq <= ?) AND seq > ?"
           + (" AND type = ?" if event_type else "")
           + " ORDER BY seq DESC LIMIT ?")
    params: tuple = ((cursor(), since_seq, event_type, limit) if event_type
                     else (cursor(), since_seq, limit))
    return [_row_to_event(r) for r in db.query(sql, params)]


def advance(steps: int = 1) -> list[Event]:
    """Release the next events and return them.

    Bounded to the recorded flight. Without that bound this selects a live
    event once the cursor reaches the end of the tape, and writes its sequence
    number - a hundred thousand times the length of the recording - into the
    cursor, from which nothing recovers.
    """
    start = cursor()
    rows = db.query("SELECT * FROM events WHERE lane = ? AND seq > ?"
                    " ORDER BY seq LIMIT ?", (LANE_TAPE, start, steps))
    if not rows:
        return []
    events = [_row_to_event(r) for r in rows]
    now = datetime.now().isoformat()
    with db.transaction() as conn:
        conn.executemany("UPDATE events SET released_at = ? WHERE id = ?",
                         [(now, e.id) for e in events])
    db.set_config(CURSOR_KEY, str(events[-1].seq))
    _record_arrivals(events)
    return events


def _record_arrivals(events: list[Event]) -> None:
    """Note which system carried each released event, in which batch.

    Imported here rather than at module scope: the estate reads the tape to
    work out who owns what, and a module-level import would close the circle.

    Never fatal. Arrivals are how the Ingest Fabric explains a delivery; the
    record is written by ingestion and does not depend on any of this. Losing
    the explanation is a worse panel, not a worse run.
    """
    try:
        from sc.estate import delivery

        delivery.deliver(events)
    except Exception:  # noqa: BLE001 - a display concern must not end a run
        log.debug("could not record arrivals for %d event(s)", len(events),
                  exc_info=True)


def jump_to(seq: int) -> list[Event]:
    """Release everything up to a sequence number in one go.

    The target is clamped to the end of the recording. The event feed offers a
    "land the tape here" button on every row it shows, and it shows live rows
    too - so without the clamp one click on a submission would put the cursor
    in the live band.
    """
    seq = min(seq, last_tape_seq())
    start = cursor()
    if seq <= start:
        db.set_config(CURSOR_KEY, str(max(seq, 0)))
        return []
    rows = db.query("SELECT * FROM events WHERE lane = ? AND seq > ? AND seq <= ?"
                    " ORDER BY seq", (LANE_TAPE, start, seq))
    events = [_row_to_event(r) for r in rows]
    now = datetime.now().isoformat()
    with db.transaction() as conn:
        conn.executemany("UPDATE events SET released_at = ? WHERE id = ?",
                         [(now, e.id) for e in events])
    db.set_config(CURSOR_KEY, str(seq))
    _record_arrivals(events)
    return events


def inject_seq() -> int:
    """Sequence of the first finale event - what 'jump to inject' targets."""
    base = baseline_mod.get()
    inject_date = base.inject.get("date")
    if not inject_date:
        return 0
    row = db.one("SELECT seq FROM events WHERE lane = ? AND ts >= ?"
                 " ORDER BY seq LIMIT 1", (LANE_TAPE, inject_date))
    return row["seq"] if row else 0


def set_speed(speed: float) -> None:
    db.set_config(SPEED_KEY, str(max(0.1, min(speed, 200.0))))


def set_running(running: bool) -> None:
    db.set_config(RUNNING_KEY, "1" if running else "0")


def reset() -> None:
    """Rewind the recording to the start.

    Scoped to the recorded flight. Rewinding a recording and retracting a
    supplier's submission are different acts, and the unscoped version did the
    second one by accident: clearing ``released_at`` everywhere would hide every
    past submission from every read while the facts those submissions produced
    stayed in the store - a record disagreeing with the events that made it.

    Note what this deliberately does not do: it does not clear ``facts``. That
    has always been true of the tape and is equally true of the live lane. A
    rewind replays the recording over facts already there, which is safe
    because every downstream write is idempotency-keyed.
    """
    db.set_config(CURSOR_KEY, "0")
    set_running(False)
    conn = db.connect()
    conn.execute("UPDATE events SET released_at = NULL WHERE lane = ?",
                 (LANE_TAPE,))
    conn.commit()


# ---------------------------------------------------------------------------
# The live lane
# ---------------------------------------------------------------------------


def _next_live_seq(conn) -> int:
    row = conn.execute("SELECT MAX(seq) AS s FROM events WHERE lane = ?",
                       (LANE_LIVE,)).fetchone()
    held = row["s"] if row and row["s"] is not None else None
    return LIVE_BASE if held is None else int(held) + 1


def _live_instant(conn, proposed: datetime | None) -> datetime:
    """When a submission happened, on the clock everything else runs on.

    The simulated clock, never the wall clock. Every as-of read in this system
    defaults both of its time axes to ``sim_now()``, and the horizon is a
    fixed eight weeks - so a fact stamped with a real 2026 date is recorded and
    then invisible to every query that would look for it.

    Nudged strictly past the newest submission. Two submissions made while the
    transport is paused would otherwise carry an identical ``recorded_at``, and
    the fact store breaks that tie by id: one of the two would silently never
    be the value in force. ``record_attribute`` already does this for the same
    reason.
    """
    instant = proposed or sim_now()
    row = conn.execute("SELECT MAX(ts) AS t FROM events WHERE lane = ?",
                       (LANE_LIVE,)).fetchone()
    if row and row["t"]:
        newest = datetime.fromisoformat(row["t"])
        if instant <= newest:
            instant = newest + timedelta(microseconds=1)
    return instant


def append_live(event_type: str, source: str, payload: dict, *,
                system_id: str, body: str | None = None,
                event_id: str | None = None,
                ts: datetime | None = None) -> Event:
    """Put a submission on the live lane, and let the platform judge it.

    The only way anything outside this process puts an event into the record.
    It appends and it does not decide: the event goes through the same
    ``ingest`` that reads the recorded flight, under the same precedence rules,
    the same materiality threshold and the same safety override. A submission
    that contradicts a better-attested document loses, and it loses in exactly
    the way a taped one would.

    Returns the event. Arrival recording and the live feed are both best
    effort - a supplier's submission must not fail because a panel could not be
    told about it - but ingestion is not, and is deliberately not wrapped.
    """
    with db.transaction() as conn:
        seq = _next_live_seq(conn)
        instant = _live_instant(conn, ts)
        identifier = event_id or f"EVT-L{seq}"
        conn.execute(
            "INSERT INTO events (id, seq, ts, type, source, payload, body,"
            " released_at, lane) VALUES (?,?,?,?,?,?,?,?,?)",
            (identifier, seq, instant.isoformat(), str(event_type), source,
             db.dumps(payload), body, datetime.now().isoformat(), LANE_LIVE))

    event = Event(id=identifier, seq=seq, ts=instant, type=event_type,
                  source=source, payload=payload, body=body, lane=LANE_LIVE)

    try:
        from sc.estate import delivery

        delivery.deliver_live(system_id, [event])
    except Exception:  # noqa: BLE001 - an explanation is not the record
        log.debug("could not record the arrival of %s", identifier,
                  exc_info=True)

    from sc.replay import ingest

    signals = ingest.ingest([event])

    if _live_sink is not None:
        try:
            _live_sink([event], signals)
        except Exception:  # noqa: BLE001 - the feed is a display concern
            log.debug("live sink failed for %s", identifier, exc_info=True)

    return event


def live_events(limit: int = 100) -> list[Event]:
    """Submissions, newest first. The Ingest Fabric's live half."""
    return [_row_to_event(r) for r in db.query(
        "SELECT * FROM events WHERE lane = ? ORDER BY seq DESC LIMIT ?",
        (LANE_LIVE, limit))]


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------


async def run_clock(on_events: Callable[[list[Event]], None],
                    poll: float = 0.25) -> None:
    """Background task: release events in simulated-time order.

    Pacing follows the gap between event timestamps rather than a fixed tick,
    so a quiet night passes quickly and a busy morning does not blur past.
    """
    while True:
        try:
            if db.get_config(RUNNING_KEY, "0") != "1":
                await asyncio.sleep(poll)
                continue

            speed = float(db.get_config(SPEED_KEY, "1") or 1.0)
            current = cursor()
            # Lane-bounded, or `nxt` is never None once a submission exists
            # and the clock runs on forever past the end of the recording.
            nxt = db.one("SELECT ts FROM events WHERE lane = ? AND seq > ?"
                         " ORDER BY seq LIMIT 1", (LANE_TAPE, current))
            if nxt is None:
                set_running(False)
                continue

            prev = db.one("SELECT ts FROM events WHERE lane = ? AND seq = ?",
                          (LANE_TAPE, current))
            gap_days = 0.0
            if prev is not None:
                gap = (datetime.fromisoformat(nxt["ts"])
                       - datetime.fromisoformat(prev["ts"]))
                gap_days = max(0.0, gap.total_seconds() / 86400.0)

            await asyncio.sleep(min(gap_days * SECONDS_PER_DAY / speed, 3.0))

            events = advance(1)
            if events:
                on_events(events)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A replay fault must not kill the clock mid-demo.
            await asyncio.sleep(1.0)
