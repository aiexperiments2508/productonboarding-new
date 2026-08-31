"""Which products anything arrived for, between two dates.

The question this answers is the one a category manager actually asks: *in the
first two weeks of July, from these suppliers, how much came in fit to publish
and how much had to go back*. That is a question about arrival, and arrival is
the part it is easy to get subtly wrong.

**It is not the ``arrivals`` table.** That table's ``arrived_at`` is real wall
clock - the moment the replayer happened to release a batch this afternoon -
and it says so. Filtering a July window on it returns nothing, or worse,
returns everything, depending on when the demo was last run. The column that
carries simulated arrival time is ``events.ts``, which is the recorded flight
of the estate and the only clock the horizon exists on.

``arrivals`` is still joined, but for a different fact: *which system carried
it*. That is what turns "eleven products came back" into "eleven products came
back and nine of them came through the data pool", which is the answer somebody
can act on.

**Scope, stated rather than implied.** A product is in the window if at least
one event naming it arrived inside it. Which product an event names is decided
by ``sc.estate.reach``, shared with the map, because an event that says
``variant_id`` is naming a product just as much as one that says ``entity_id``
and two readings of that would disagree the first time it mattered.

**A verdict is read at the end of the window, not averaged across it.** A
verdict is a statement about the record as it stands; a mean of daily verdicts
would be a number with no referent, and the whole package refuses to produce
one of those.
"""

from __future__ import annotations

from sc import db


def _bounds(start: str | None, end: str | None) -> tuple[str, str]:
    """The window as two ISO strings, half-open: ``start <= ts < end``.

    Half-open so that consecutive windows tile without double-counting the
    product that arrived at midnight. A bare date is accepted and read as the
    start of that day, because that is what somebody typing into a date field
    means.
    """
    low = (start or "0000-01-01").strip()
    high = (end or "9999-12-31").strip()
    if len(low) == 10:
        low = f"{low}T00:00:00"
    if len(high) == 10:
        # An end date somebody typed is inclusive of that day.
        high = f"{high}T23:59:59.999999"
    return low, high


def touched(start: str | None = None, end: str | None = None) -> dict[str, dict]:
    """Products with at least one arrival in the window, and what arrived.

    One pass over the events in range, resolved through the shared reference
    reader. Returns ``product_id -> {first_seen, last_seen, events, systems,
    event_types}``.
    """
    from sc.estate import reach as reach_mod
    from sc.state import baseline as baseline_mod

    low, high = _bounds(start, end)
    base = baseline_mod.get()

    rows = db.query(
        "SELECT e.id AS id, e.ts AS ts, e.type AS type, e.payload AS payload,"
        "       a.system_id AS system_id"
        "  FROM events e"
        "  LEFT JOIN arrivals a ON a.event_id = e.id"
        " WHERE e.ts >= ? AND e.ts <= ?"
        " ORDER BY e.seq", (low, high))

    found: dict[str, dict] = {}
    for row in rows:
        try:
            payload = db.loads(row["payload"])
        except Exception:  # noqa: BLE001 - a bad payload is not a bad window
            continue
        for product_id in reach_mod.products_of(base, payload):
            entry = found.get(product_id)
            if entry is None:
                entry = found[product_id] = {
                    "first_seen": row["ts"], "last_seen": row["ts"],
                    "events": 0, "systems": set(), "event_types": set(),
                }
            entry["last_seen"] = row["ts"]
            entry["events"] += 1
            entry["event_types"].add(row["type"])
            if row["system_id"]:
                entry["systems"].add(row["system_id"])

    for entry in found.values():
        entry["systems"] = sorted(entry["systems"])
        entry["event_types"] = sorted(entry["event_types"])
    return found


def bounded(start: str | None, end: str | None) -> bool:
    """Is this actually a window, or the whole tape?

    Worth asking explicitly: a summary over an unbounded window is a summary of
    the estate, and saying "1 July to 31 August" over it would be a caption
    that happens to be true rather than a filter that was applied.
    """
    return bool((start or "").strip() or (end or "").strip())
