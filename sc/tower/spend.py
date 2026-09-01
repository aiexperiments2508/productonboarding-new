"""What the models cost, and what the cache saved.

Two sums over one table, and keeping them apart is the whole design. A call
served from the response cache is recorded in ``llm_ledger`` with its tokens
intact and no cost, so:

    spend    = SUM(cost_usd) WHERE served_from_cache = 0
    avoided  = SUM(tokens)   WHERE served_from_cache = 1

Adding the second to the first would double-count; dropping it would erase the
cache's argument. Reporting them side by side is both the honest reading and
the flattering one, which is the only reason to prefer it over a single number.

**Windows run on the simulated clock.** ``sim_at`` is what every filter uses,
because every other date on this dashboard is simulated and one real column
among them would return an empty window on a demo machine that was last reset
this morning. ``sc/readiness/window.py`` documents that trap; this obeys it.

**A cost of zero is not a fact about the price.** Cost comes from the gateway's
own ``response_cost``, and a model its price map does not recognise yields no
figure at all. Those rows carry ``priced = 0`` and are counted separately, so a
window nobody could price says so rather than reporting a confident $0.0000.
"""

from __future__ import annotations

from sc import db
from sc.readiness import window as window_mod

#: How a caller may slice the ledger. A closed set, because the value is
#: interpolated into the SELECT and an open one would be an injection.
GROUPS = {
    "model": "model",
    "surface": "surface",
    "feed": "submission_id",
    "kind": "kind",
}


def _totals(low: str, high: str) -> dict:
    row = db.one(
        "SELECT"
        "  COUNT(*) AS calls,"
        "  SUM(CASE WHEN l.served_from_cache = 0 THEN 1 ELSE 0 END) AS live_calls,"
        "  SUM(CASE WHEN l.served_from_cache = 1 THEN 1 ELSE 0 END) AS cache_hits,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0"
        "                    THEN l.prompt_tokens + l.completion_tokens END), 0) AS tokens,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 1"
        "                    THEN l.prompt_tokens + l.completion_tokens END), 0) AS tokens_avoided,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0 THEN l.prompt_tokens END), 0) AS prompt_tokens,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0 THEN l.completion_tokens END), 0) AS completion_tokens,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0 THEN l.cost_usd END), 0) AS cost,"
        # A cached row carries no cost of its own - by design, so that summing
        # the column cannot overstate spend. What that call *would* have cost
        # is what it cost the day it was real, and `llm_calls` still holds it.
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 1 THEN c.cost_usd END), 0) AS cost_avoided,"
        "  SUM(CASE WHEN l.served_from_cache = 0 AND l.priced = 0 THEN 1 ELSE 0 END) AS unpriced,"
        "  AVG(CASE WHEN l.served_from_cache = 0 THEN l.latency_ms END) AS avg_latency"
        " FROM llm_ledger l LEFT JOIN llm_calls c ON c.cache_key = l.cache_key"
        " WHERE l.sim_at >= ? AND l.sim_at <= ?", (low, high))
    if row is None:
        row = {}
    return {
        "calls": int(row["calls"] or 0),
        "live_calls": int(row["live_calls"] or 0),
        "cache_hits": int(row["cache_hits"] or 0),
        "prompt_tokens": int(row["prompt_tokens"] or 0),
        "completion_tokens": int(row["completion_tokens"] or 0),
        "tokens": int(row["tokens"] or 0),
        "tokens_avoided": int(row["tokens_avoided"] or 0),
        "cost_usd": round(float(row["cost"] or 0.0), 6),
        # What the same calls would have cost had the cache not answered them.
        # Read off the cached rows' own recorded price, never re-estimated.
        "cost_avoided_usd": round(float(row["cost_avoided"] or 0.0), 6),
        "unpriced_calls": int(row["unpriced"] or 0),
        "avg_latency_ms": round(float(row["avg_latency"] or 0.0), 1),
    }


def _grouped(low: str, high: str, column: str) -> list[dict]:
    rows = db.query(
        f"SELECT COALESCE(l.{column}, 'unattributed') AS key,"
        "  COUNT(*) AS calls,"
        "  SUM(CASE WHEN l.served_from_cache = 1 THEN 1 ELSE 0 END) AS cache_hits,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0"
        "                    THEN l.prompt_tokens + l.completion_tokens END), 0) AS tokens,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 1"
        "                    THEN l.prompt_tokens + l.completion_tokens END), 0) AS tokens_avoided,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0 THEN l.cost_usd END), 0) AS cost,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 1 THEN c.cost_usd END), 0) AS cost_avoided"
        " FROM llm_ledger l LEFT JOIN llm_calls c ON c.cache_key = l.cache_key"
        " WHERE l.sim_at >= ? AND l.sim_at <= ?"
        f" GROUP BY COALESCE(l.{column}, 'unattributed')"
        " ORDER BY cost DESC, tokens DESC", (low, high))
    return [{"key": r["key"], "calls": int(r["calls"] or 0),
             "cache_hits": int(r["cache_hits"] or 0),
             "tokens": int(r["tokens"] or 0),
             "tokens_avoided": int(r["tokens_avoided"] or 0),
             "cost_usd": round(float(r["cost"] or 0.0), 6),
             "cost_avoided_usd": round(float(r["cost_avoided"] or 0.0), 6)}
            for r in rows]


def summary(start: str | None = None, end: str | None = None,
            group_by: str = "model") -> dict:
    """Spend for a window, sliced one way.

    ``group_by`` is one of ``GROUPS``; anything else is refused rather than
    silently falling back, because a caller that asked for a slice and got a
    different one would have no way to tell.
    """
    if group_by not in GROUPS:
        raise ValueError(
            f"group_by must be one of {sorted(GROUPS)}, not {group_by!r}")

    low, high = window_mod._bounds(start, end)
    totals = _totals(low, high)
    from sc.llm import gateway

    return {
        "window": {"start": start or None, "end": end or None},
        "bounded": window_mod.bounded(start, end),
        "group_by": group_by,
        **totals,
        # False when the window has live calls and not one of them could be
        # priced. The tokens are still right; the money is not known.
        "priced": totals["live_calls"] == 0
                  or totals["unpriced_calls"] < totals["live_calls"],
        "caveat": None if totals["unpriced_calls"] == 0 else (
            f"{totals['unpriced_calls']} of {totals['live_calls']} calls in this "
            "window came back with no price from the gateway, so the cost below "
            "is a floor rather than a total. Token counts are unaffected."),
        "groups": _grouped(low, high, GROUPS[group_by]),
        "budget": gateway.budget(),
    }


def for_feed(submission_id: str) -> dict:
    """What one feed cost. The join the register hangs its cost column on."""
    row = db.one(
        "SELECT COUNT(*) AS calls,"
        "  SUM(CASE WHEN l.served_from_cache = 1 THEN 1 ELSE 0 END) AS cache_hits,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0"
        "                    THEN l.prompt_tokens + l.completion_tokens END), 0) AS tokens,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 0 THEN l.cost_usd END), 0) AS cost,"
        "  COALESCE(SUM(CASE WHEN l.served_from_cache = 1 THEN c.cost_usd END), 0) AS avoided"
        " FROM llm_ledger l LEFT JOIN llm_calls c ON c.cache_key = l.cache_key"
        " WHERE l.submission_id = ?", (submission_id,))
    return {"calls": int(row["calls"] or 0) if row else 0,
            "cache_hits": int(row["cache_hits"] or 0) if row else 0,
            "tokens": int(row["tokens"] or 0) if row else 0,
            "cost_usd": round(float(row["cost"] or 0.0), 6) if row else 0.0,
            "cost_avoided_usd": round(float(row["avoided"] or 0.0), 6) if row else 0.0}
