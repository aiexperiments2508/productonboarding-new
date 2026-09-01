"""control-tower - feed flow, KPIs and model spend, over MCP.

    python -m sc.mcp.control_tower

Read-only, and it has to be. Every figure this serves is derived on read from
somewhere else - a verdict from ``sc.readiness``, a gate outcome from
``sc.onboarding.gate``, a lane from ``sc.lifecycle.stages``, a cost from the
spend ledger - so there is nothing here a tool could sensibly write to. A
dashboard that could be written to would be a second account of the truth, which
is the thing this codebase spends its design avoiding.

The one control that goes with these numbers - the model spend cap - is
deliberately **not** a tool here, for the same reason the approval gate is not
an A2A peer and ``commit_plan`` lives on the publishing server rather than
beside the reads. Moving a cap changes what the system will do unattended, and
that is a decision with a person behind it. It stays on the HTTP API where the
name that authorised it is demanded and audited.

This is a toolset and not an estate system. The estate at ``/mcp/{system}`` is
the external systems this platform *talks to*, and
``tests/test_estate.py::test_no_system_is_named_outside_the_manifest`` keeps it
that way. The control tower is a capability this platform *implements*, which is
the distinction ``/.well-known/agent-cards.json`` exists to keep.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve

mcp = FastMCP("control-tower")


@mcp.tool()
def tower_flow(start: str | None = None, end: str | None = None,
               supplier: str | None = None, system: str | None = None,
               limit: int = 200) -> dict:
    """Every feed's rows in a window, counted into the seven lifecycle states.

    Dates are ISO and run on the replay clock, which is the one the recorded
    flight happened on. The grain is the row a supplier sent - a variant - and
    the response says so, because Product Lifecycle places a product and the
    two can differ for the same pack without either being wrong.
    """
    def run() -> dict:
        from sc.tower import register as register_mod

        return register_mod.feeds(start, end, supplier=supplier, system=system,
                                  limit=limit, with_states=True)

    run.__name__ = "tower_flow"
    return instrumented(run)()


@mcp.tool()
def tower_feeds(start: str | None = None, end: str | None = None,
                supplier: str | None = None, system: str | None = None,
                kind: str | None = None, limit: int = 200) -> dict:
    """The feed register: what arrived in a window, from whom, carried by what.

    Arrival facts only - no readiness pass. `tower_flow` is the same window with
    every row assessed, and costs accordingly.
    """
    def run() -> dict:
        from sc.tower import register as register_mod

        return register_mod.feeds(start, end, supplier=supplier, system=system,
                                  kind=kind, limit=limit, with_states=False)

    run.__name__ = "tower_feeds"
    return instrumented(run)()


@mcp.tool()
def tower_feed(submission_id: str) -> dict:
    """One feed, row by row, with each row's state and gate outcome."""
    def run() -> dict:
        from sc.tower import flow as flow_mod

        detail = flow_mod.for_feed(submission_id)
        if detail is None:
            return {"error": f"no supplier data pack with id {submission_id}"}
        return detail

    run.__name__ = "tower_feed"
    return instrumented(run)()


@mcp.tool()
def tower_kpis(start: str | None = None, end: str | None = None,
               supplier: str | None = None, system: str | None = None,
               limit: int = 200) -> dict:
    """Volume, quality, correction, reliability, speed and cost for a window.

    Read `checks_complete` and `caveat` before quoting anything from this. A
    false `checks_complete` means the checks that read regulation, internal
    documentation and copy meaning did not run, so the counts are narrower
    rather than cleaner - and `truncated` means the figures are a sample of the
    window rather than the window.
    """
    def run() -> dict:
        from sc.tower import kpis as kpis_mod

        return kpis_mod.summary(start, end, supplier=supplier, system=system,
                                limit=limit)

    run.__name__ = "tower_kpis"
    return instrumented(run)()


@mcp.tool()
def tower_spend(start: str | None = None, end: str | None = None,
                group_by: str = "model") -> dict:
    """Tokens and cost for a window, grouped by model, surface, feed or kind.

    `cost_usd` is what was spent; `cost_avoided_usd` is what the response cache
    saved. They are separate sums and must not be added. `priced` false means
    the gateway put no price on these calls, so the cost is a floor and the
    token counts are the reliable half.
    """
    def run() -> dict:
        from sc.tower import spend as spend_mod

        try:
            return spend_mod.summary(start, end, group_by=group_by)
        except ValueError as exc:
            return {"error": str(exc)}

    run.__name__ = "tower_spend"
    return instrumented(run)()


if __name__ == "__main__":
    serve(mcp, "control-tower")
