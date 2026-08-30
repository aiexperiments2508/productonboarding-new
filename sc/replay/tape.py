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
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from sc import db
from sc.contracts import Event, ReplayState
from sc.state import baseline as baseline_mod

CURSOR_KEY = "replay_cursor"
SPEED_KEY = "replay_speed"
RUNNING_KEY = "replay_running"

# Seconds of wall clock per simulated day at 1x. A 56-day horizon replays in
# about two minutes, which is the right pace to narrate over.
SECONDS_PER_DAY = 2.0


def load_tape(path: Path | None = None, reset: bool = False) -> dict:
    """Load the tape into SQLite. Idempotent unless ``reset``."""
    tape = path or (baseline_mod.data_dir() / "events.jsonl")
    conn = db.connect()

    if reset:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM event_cursors")
        db.set_config(CURSOR_KEY, "0")

    existing = db.one("SELECT COUNT(*) AS n FROM events")["n"]
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
            " body) VALUES (?,?,?,?,?,?,?)", rows)
    db.set_config(CURSOR_KEY, "0")
    return {"loaded": len(rows), "total": len(rows), "skipped": False}


# ---------------------------------------------------------------------------
# Cursor and state
# ---------------------------------------------------------------------------


def cursor() -> int:
    return int(db.get_config(CURSOR_KEY, "0") or 0)


def total_events() -> int:
    row = db.one("SELECT COUNT(*) AS n FROM events")
    return row["n"] if row else 0


def state() -> ReplayState:
    seq = cursor()
    row = db.one("SELECT ts FROM events WHERE seq <= ? ORDER BY seq DESC LIMIT 1",
                 (seq,))
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
    """
    row = db.one("SELECT ts FROM events WHERE seq <= ? ORDER BY seq DESC LIMIT 1",
                 (cursor(),))
    if row is not None:
        return datetime.fromisoformat(row["ts"])
    base = baseline_mod.get()
    return datetime.combine(base.horizon_start, datetime.min.time())


def _row_to_event(row) -> Event:
    return Event(
        id=row["id"], seq=row["seq"], ts=datetime.fromisoformat(row["ts"]),
        type=row["type"], source=row["source"],
        payload=db.loads(row["payload"]), body=row["body"],
    )


def released(limit: int = 200, since_seq: int = 0,
             event_type: str | None = None) -> list[Event]:
    """Events visible so far. The UI never sees the future of the tape."""
    sql = ("SELECT * FROM events WHERE seq <= ? AND seq > ?"
           + (" AND type = ?" if event_type else "")
           + " ORDER BY seq DESC LIMIT ?")
    params: tuple = ((cursor(), since_seq, event_type, limit) if event_type
                     else (cursor(), since_seq, limit))
    return [_row_to_event(r) for r in db.query(sql, params)]


def advance(steps: int = 1) -> list[Event]:
    """Release the next events and return them."""
    start = cursor()
    rows = db.query("SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?",
                    (start, steps))
    if not rows:
        return []
    events = [_row_to_event(r) for r in rows]
    now = datetime.now().isoformat()
    with db.transaction() as conn:
        conn.executemany("UPDATE events SET released_at = ? WHERE id = ?",
                         [(now, e.id) for e in events])
    db.set_config(CURSOR_KEY, str(events[-1].seq))
    return events


def jump_to(seq: int) -> list[Event]:
    """Release everything up to a sequence number in one go."""
    start = cursor()
    if seq <= start:
        db.set_config(CURSOR_KEY, str(max(seq, 0)))
        return []
    rows = db.query("SELECT * FROM events WHERE seq > ? AND seq <= ? ORDER BY seq",
                    (start, seq))
    events = [_row_to_event(r) for r in rows]
    now = datetime.now().isoformat()
    with db.transaction() as conn:
        conn.executemany("UPDATE events SET released_at = ? WHERE id = ?",
                         [(now, e.id) for e in events])
    db.set_config(CURSOR_KEY, str(seq))
    return events


def inject_seq() -> int:
    """Sequence of the first finale event - what 'jump to inject' targets."""
    base = baseline_mod.get()
    inject_date = base.inject.get("date")
    if not inject_date:
        return 0
    row = db.one("SELECT seq FROM events WHERE ts >= ? ORDER BY seq LIMIT 1",
                 (inject_date,))
    return row["seq"] if row else 0


def set_speed(speed: float) -> None:
    db.set_config(SPEED_KEY, str(max(0.1, min(speed, 200.0))))


def set_running(running: bool) -> None:
    db.set_config(RUNNING_KEY, "1" if running else "0")


def reset() -> None:
    db.set_config(CURSOR_KEY, "0")
    set_running(False)
    conn = db.connect()
    conn.execute("UPDATE events SET released_at = NULL")
    conn.commit()


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
            nxt = db.one("SELECT ts FROM events WHERE seq > ? ORDER BY seq LIMIT 1",
                         (current,))
            if nxt is None:
                set_running(False)
                continue

            prev = db.one("SELECT ts FROM events WHERE seq = ?", (current,))
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
