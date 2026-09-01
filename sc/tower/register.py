"""What arrived, feed by feed, over a window.

The feed register. One row per submission - which supplier sent it, which
system carried it, how many rows and how many images it held, where its
products got to, and what the models spent on it.

**A feed is not a new object.** There is no feeds table and there is
deliberately not going to be one, for the reason ``sc/onboarding/batch.py``
gives for not having a batch table: a feed is already a submission. It has an
id, a supplier, a carrier, a timestamp, the events it appended and the entities
it named, all in columns. Minting a second identifier beside that would be two
accounts of one arrival.

**An image feed is not a separate kind of thing either.** The brief asks about
product feeds and image feeds as though they were two pipes; in this system they
are one pipe carrying two payloads. What actually distinguishes them is the
*carrier* - ``imaging-dam`` and ``label-artwork`` deliver imagery, ``gdsn-pool``
cannot - and the payload type on the event. So the register reports
``media_events`` and ``system`` per feed and lets a caller filter on either,
rather than inventing a second feed type the code does not have and the estate
would immediately contradict.

**Windows run on ``submitted_at``, which is the simulated clock.** Not
``wall_at``. Filtering the real clock returns everything or nothing depending on
when the demo was last reset - the trap ``sc/readiness/window.py`` documents at
length.
"""

from __future__ import annotations

from sc import db
from sc.estate.intake import DATA_PACK, DOCUMENT, IMAGE, PRODUCT_DRAFT, SPEC_CHANGE
from sc.readiness import window as window_mod
from sc.tower import flow as flow_mod

#: Every kind a supplier can send. Listed rather than discovered so a window
#: with none of one kind still reports that kind as zero.
KINDS: tuple[str, ...] = (DATA_PACK, SPEC_CHANGE, DOCUMENT, IMAGE, PRODUCT_DRAFT)

#: Which kinds carry imagery. Derived from what the payload is, not from the
#: carrier's name, because a supplier portal accepts both.
MEDIA_KINDS = frozenset({IMAGE, DATA_PACK})


def feeds(start: str | None = None, end: str | None = None, *,
          supplier: str | None = None, system: str | None = None,
          kind: str | None = None, limit: int = 200,
          use_model: bool = False, with_states: bool = True) -> dict:
    """The feeds that arrived in a window, newest first.

    ``with_states`` off returns the arrival facts alone and skips the readiness
    pass. A list of a hundred feeds does not need every product in each of them
    assessed to be useful, and the detail view asks for the full picture - the
    same trade ``readiness.assess_all`` makes for the product list.
    """
    low, high = window_mod._bounds(start, end)
    clauses = ["submitted_at >= ?", "submitted_at <= ?"]
    params: list = [low, high]
    if supplier:
        clauses.append("supplier_id = ?")
        params.append(supplier)
    if system:
        clauses.append("system_id = ?")
        params.append(system)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    # How many the window actually holds, before the limit is applied. Without
    # this a caller asking for twenty gets twenty and no way to know it was a
    # sample - and the newest twenty of a busy window are all one kind, so the
    # bias is not even random. A cap that is not reported reads as a total.
    matched = db.one(
        "SELECT COUNT(*) AS n FROM submissions WHERE " + " AND ".join(clauses),
        tuple(params))
    matched = int(matched["n"] or 0) if matched else 0

    rows = db.query(
        "SELECT * FROM submissions WHERE " + " AND ".join(clauses)
        + " ORDER BY submitted_at DESC, wall_at DESC LIMIT ?",
        tuple(params + [limit]))

    ctx = flow_mod.build_context() if with_states else None
    listed = [_feed(row, ctx, use_model, with_states) for row in rows]

    totals = flow_mod.blank_counts()
    for entry in listed:
        for state, n in entry["counts"].items():
            totals[state] += n

    # Folded over the feeds that were actually assessed, not over every feed in
    # the window. A window of nothing but product drafts has had no checks run
    # on it and no checks skipped either, and reporting it as narrow would
    # attach a caveat about a model to a screen no model was needed for.
    placed = [e for e in listed if e["kind"] == DATA_PACK]
    complete = all(e["checks_complete"] for e in placed) if placed else True
    return {
        "window": {"start": start or None, "end": end or None},
        "bounded": window_mod.bounded(start, end),
        "filters": {"supplier": supplier, "system": system, "kind": kind},
        "feeds": listed,
        "count": len(listed),
        "matched": matched,
        "truncated": matched > len(listed),
        "limit": limit,
        "by_kind": _counted(listed, "kind"),
        "by_supplier": _counted(listed, "supplier"),
        "by_system": _counted(listed, "system"),
        "totals": totals,
        "products": sum(totals.values()),
        "states_assessed": with_states and bool(placed),
        "assessable_feeds": len(placed),
        "checks_complete": complete if with_states else False,
        "caveat": _caveat(with_states, bool(placed), complete,
                          truncated=matched > len(listed), matched=matched,
                          shown=len(listed)),
    }


def _caveat(with_states: bool, placed: bool, complete: bool, *,
            truncated: bool = False, matched: int = 0,
            shown: int = 0) -> str | None:
    """What this window did not do, in the one wording that says it.

    Four different silences, and they are not the same silence: the window
    was truncated, nobody asked for states, nothing in the window has states
    to ask for, or the states were reached without a model. Truncation leads
    because it is the one that makes every other number on the screen a
    sample rather than an answer.
    """
    if truncated:
        return (f"this window holds {matched} feeds and the newest {shown} were "
                "read: every figure below is that sample, not the window. Raise "
                "the limit or narrow the dates to make it the whole answer")
    if not with_states:
        return ("arrival facts only: nothing in this window was assessed, so "
                "the state counts are zero because the question was not asked")
    if not placed:
        return ("nothing in this window was a supplier data pack, so there is "
                "no onboarding population to report on - the feeds listed are "
                "documents, images, single corrections and proposed lines")
    return None if complete else flow_mod._CAVEAT


def _feed(row, ctx: dict | None, use_model: bool,
          with_states: bool) -> dict:
    from sc.tower import spend as spend_mod

    submission_id = row["id"]
    entities = db.loads(row["entity_ids"]) or []
    events = db.loads(row["event_ids"]) or []
    files = db.loads(row["files"]) or []

    entry = {
        "feed_id": submission_id,
        "supplier": row["supplier_id"],
        "system": row["system_id"],
        "kind": row["kind"],
        "submitted_at": row["submitted_at"],
        "wall_at": row["wall_at"],
        "doc_ref": row["doc_ref"] or "",
        "rows": len(entities),
        # Files the supplier actually sent, split the way the intake stored
        # them: an archive at /packs/ and its photographs under /media/.
        "media_files": len([f for f in files
                            if "/media/" in str(f.get("path", ""))]),
        "carries_media": row["kind"] in MEDIA_KINDS,
        "events": len(events),
        "ingested": flow_mod._ingested(events),
        "counts": flow_mod.blank_counts(),
        "ai_corrected": 0,
        "decided_by_person": 0,
        "checks_complete": False,
        "spend": spend_mod.for_feed(submission_id),
    }

    if not with_states or row["kind"] != DATA_PACK:
        # Only a data pack has a product population to place. A document, an
        # image or a single spec change names entities too, but its story is
        # the correction thread rather than an onboarding pass, and reporting
        # its one entity as a "feed of one" would inflate every count on the
        # screen.
        return entry

    detail = flow_mod.for_feed(submission_id, use_model=use_model, context=ctx)
    if detail is None:
        return entry
    entry.update({
        "counts": detail["counts"],
        "ai_corrected": detail["ai_corrected"],
        "decided_by_person": detail["decided_by_person"],
        "proposals": detail["proposals"],
        "checks_complete": detail["checks_complete"],
    })
    return entry


def _counted(listed: list[dict], key: str) -> list[dict]:
    """Feeds and rows grouped one way, biggest first."""
    found: dict[str, dict] = {}
    for entry in listed:
        bucket = found.setdefault(str(entry[key]),
                                  {"key": entry[key], "feeds": 0, "rows": 0})
        bucket["feeds"] += 1
        bucket["rows"] += entry["rows"]
    return sorted(found.values(), key=lambda b: (-b["feeds"], str(b["key"])))
