"""The numbers an executive quotes, and where each one comes from.

Every figure here is arithmetic over something another module already decided.
Nothing reaches a verdict, weights anything, or produces a score - the same rule
``sc/readiness/rollup.py`` states for itself, and it matters more on this surface
because a number on a dashboard gets repeated by people who never saw the
product it came from.

**Two clocks, and each is used only for what it can answer.** This is the one
place a plausible number can be quietly wrong, so it is stated rather than
assumed:

* ``submissions.submitted_at``, ``onboarding_suggestions.created_at`` and the
  spend ledger's ``sim_at`` run on the **replay clock**. They are what a window
  filters on, because the whole recorded flight happened in simulated July and
  August, and a real-clock filter over it returns everything or nothing
  depending on when the demo was last reset.
* ``submissions.wall_at``, ``audit.ts`` and ``committed_actions.committed_at``
  run on the **real clock**. They are what a *duration* is measured on.

Subtracting one from the other would produce a confident number with no meaning:
a feed that arrived on the simulated third of August and was published at half
past nine this morning did not take four weeks. So every duration below has both
ends on the real clock, and every window has both ends on the simulated one.
``clock: "real"`` is carried beside the durations so a reader knows which
question was answered. In production these are one clock and the distinction
disappears; on a replay it is the difference between an SLA and a fiction.

**A rate over nothing is not zero.** Every rate is ``None`` when its denominator
is empty, and the screen renders that as a dash. Reporting a 0% compliance pass
rate for a window in which nothing was assessed is the kind of figure that gets
screenshotted.
"""

from __future__ import annotations

from datetime import datetime

from sc import db
from sc.readiness import window as window_mod
from sc.tower import flow as flow_mod
from sc.tower import register as register_mod

#: Which states mean the row got through. ON_HOLD is not among them: a row
#: waiting on a person has not cleared, it has stopped somewhere politer.
_THROUGH = (flow_mod.ALL_CLEAR, flow_mod.PUSHED_DOWNSTREAM, flow_mod.ON_SALE)


def _rate(numerator: int, denominator: int) -> float | None:
    """A proportion, or None when there was nothing to take it of."""
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def _hours(start: str, end: str) -> float | None:
    """Elapsed hours between two real-clock stamps, or None if they do not
    subtract. A negative result is dropped rather than reported: it means the
    two ends were not on the same clock after all, and a negative duration on a
    dashboard is worse than a missing one."""
    try:
        delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    except (TypeError, ValueError):
        return None
    hours = delta.total_seconds() / 3600.0
    return round(hours, 3) if hours >= 0 else None


def _median(values: list[float]) -> float | None:
    """The middle one. A mean would be dragged by the single feed somebody left
    open over a weekend, which is not what "how long does this take" means."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 3)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 3)


def summary(start: str | None = None, end: str | None = None, *,
            supplier: str | None = None, system: str | None = None,
            use_model: bool = False, limit: int = 200) -> dict:
    """Every KPI for one window, over the feeds that arrived in it."""
    from sc.tower import spend as spend_mod

    reg = register_mod.feeds(start, end, supplier=supplier, system=system,
                             limit=limit, use_model=use_model, with_states=True)
    feeds = reg["feeds"]
    feed_ids = [f["feed_id"] for f in feeds]
    states = reg["totals"]

    assessed = sum(states.values())
    through = sum(states[s] for s in _THROUGH)
    blocked = states[flow_mod.BLOCKED]
    on_hold = states[flow_mod.ON_HOLD]
    on_sale = states[flow_mod.ON_SALE]

    proposals = _proposal_counts(feed_ids)
    defective = _defective_feeds(feed_ids)
    money = spend_mod.summary(start, end)
    residual = _residual_findings(feeds)
    speed = _speed(feeds)

    return {
        "window": {"start": start or None, "end": end or None},
        "bounded": window_mod.bounded(start, end),
        "filters": {"supplier": supplier, "system": system},
        "grain": "variant",

        # -- volume ----------------------------------------------------------
        # `feeds_received` is what was read. `feeds_matched` is what the window
        # holds. They differ when the limit bit, and every figure below is then
        # a sample - which `truncated` says rather than leaving to arithmetic.
        "feeds_received": reg["count"],
        "feeds_matched": reg["matched"],
        "truncated": reg["truncated"],
        "rows_received": sum(f["rows"] for f in feeds),
        "rows_assessed": assessed,
        "states": states,

        # -- quality ---------------------------------------------------------
        "compliance_pass_rate": _rate(assessed - blocked, assessed),
        "all_clear_rate": _rate(through, assessed),
        "blocked_rate": _rate(blocked, assessed),
        "awaiting_decision_rate": _rate(on_hold, assessed),
        # Rows that are on sale and still carry an open finding. Not a second
        # blocked count: these are live, and the finding is what the process
        # let through rather than what it stopped.
        "residual_error_rate": _rate(residual, on_sale),
        "residual_errors": residual,

        # -- correction: what the AI did, and what a person did ---------------
        "proposals": proposals["total"],
        "autonomous_fills": proposals["autonomous"],
        "decisions_by_person": proposals["decided"],
        "awaiting_decision": proposals["pending"],
        "autonomous_fill_rate": _rate(proposals["autonomous"],
                                      proposals["total"]),
        "human_decision_rate": _rate(proposals["decided"], proposals["total"]),

        # -- reliability ------------------------------------------------------
        "feed_success_rate": _rate(reg["count"] - defective, reg["count"]),
        "feeds_with_defects": defective,

        # -- speed. Real clock at both ends; see the module docstring. --------
        "clock": "real",
        "median_hours_to_downstream": speed["downstream"],
        "median_hours_to_first_fill": speed["first_fill"],
        "measured_downstream": speed["downstream_n"],
        "measured_first_fill": speed["first_fill_n"],

        # -- cost --------------------------------------------------------------
        "tokens": money["tokens"],
        "tokens_avoided": money["tokens_avoided"],
        "cost_usd": money["cost_usd"],
        "cost_avoided_usd": money["cost_avoided_usd"],
        "cost_per_row_cleared_usd": (
            round(money["cost_usd"] / through, 6) if through else None),
        "priced": money["priced"],

        # -- the honest half ---------------------------------------------------
        "checks_complete": reg["checks_complete"],
        "caveat": reg["caveat"],
    }


def _proposal_counts(feed_ids: list[str]) -> dict[str, int]:
    """Proposals for these feeds, split by who settled them.

    ``autonomous`` is a route, not an outcome: it is what the system wrote
    without asking. ``decided`` is a person having answered. A proposal routed
    to a person and not yet answered is neither, and is counted as pending.
    Three buckets that add up, because here they genuinely can.
    """
    blank = {"total": 0, "autonomous": 0, "decided": 0, "pending": 0}
    if not feed_ids:
        return blank
    marks = ",".join("?" * len(feed_ids))
    row = db.one(
        "SELECT COUNT(*) AS total,"
        "  SUM(CASE WHEN route = 'AUTONOMOUS' THEN 1 ELSE 0 END) AS autonomous,"
        "  SUM(CASE WHEN decision IN ('APPROVE','RECTIFY') THEN 1 ELSE 0 END) AS decided,"
        "  SUM(CASE WHEN decision IS NULL AND route = 'HUMAN' THEN 1 ELSE 0 END) AS pending"
        " FROM onboarding_suggestions WHERE submission_id IN (" + marks + ")",
        tuple(feed_ids))
    if row is None:
        return blank
    return {"total": int(row["total"] or 0),
            "autonomous": int(row["autonomous"] or 0),
            "decided": int(row["decided"] or 0),
            "pending": int(row["pending"] or 0)}


def _defective_feeds(feed_ids: list[str]) -> int:
    """How many feeds arrived carrying at least one stamped defect.

    Joined through ``arrivals``, which is where the estate records what it did
    to a payload on the way in. A feed whose every row parsed is one the
    supplier got right; one with a defect is not necessarily refused, and that
    distinction is what makes this a reliability number rather than a second
    blocked count.
    """
    if not feed_ids:
        return 0
    marks = ",".join("?" * len(feed_ids))
    rows = db.query(
        "SELECT s.id AS feed_id FROM submissions s"
        "  JOIN json_each(s.event_ids) e"
        "  JOIN arrivals a ON a.event_id = e.value"
        " WHERE s.id IN (" + marks + ") AND a.defects != '[]'", tuple(feed_ids))
    return len({r["feed_id"] for r in rows})


def _residual_findings(feeds: list[dict]) -> int:
    """Rows that are on sale and still carry an open finding."""
    return sum(1 for feed in feeds
               for product in feed.get("products", [])
               if product["state"] == flow_mod.ON_SALE
               and product["open_findings"])


def _speed(feeds: list[dict]) -> dict:
    """How long from a feed landing to something happening to it.

    Both ends on the real clock. ``wall_at`` is when this process actually
    received the submission; ``audit.ts`` and ``committed_at`` are when the
    enrichment and the publish actually ran.

    A feed nothing has happened to contributes nothing, rather than a zero. The
    count of what was measurable is returned beside each median, because "four
    hours" over two feeds and over two hundred are different claims.
    """
    ids = [f["feed_id"] for f in feeds]
    landed = {f["feed_id"]: f["wall_at"] for f in feeds}
    if not ids:
        return {"downstream": None, "first_fill": None,
                "downstream_n": 0, "first_fill_n": 0}
    marks = ",".join("?" * len(ids))

    # `APPLY_ENRICHMENT` is audited against the submission itself, so this is a
    # direct join rather than a search through detail JSON.
    fills = db.query(
        "SELECT entity_id AS feed_id, MIN(ts) AS at FROM audit"
        " WHERE action = 'APPLY_ENRICHMENT' AND entity_type = 'submission'"
        "   AND entity_id IN (" + marks + ") GROUP BY entity_id", tuple(ids))
    to_fill = [hours for r in fills
               if (hours := _hours(landed.get(r["feed_id"], ""),
                                   r["at"])) is not None]

    # A commit is recorded against an incident, not a feed, so the join runs
    # through the variants the feed named. This is the same substring match
    # `sc/lifecycle/board.py::_dispatched_products` makes against the incident
    # document, and it has the same limitation: it rests on entity ids not
    # being substrings of one another, which in this catalog they are not.
    commits = db.query(
        "SELECT s.id AS feed_id, MIN(c.committed_at) AS at"
        "  FROM submissions s"
        "  JOIN json_each(s.entity_ids) e"
        "  JOIN incidents i ON i.doc LIKE '%' || e.value || '%'"
        "  JOIN committed_actions c ON c.incident_id = i.id AND c.rolled_back = 0"
        " WHERE s.id IN (" + marks + ") GROUP BY s.id", tuple(ids))
    to_downstream = [hours for r in commits
                     if (hours := _hours(landed.get(r["feed_id"], ""),
                                         r["at"])) is not None]

    return {"downstream": _median(to_downstream),
            "first_fill": _median(to_fill),
            "downstream_n": len(to_downstream),
            "first_fill_n": len(to_fill)}
