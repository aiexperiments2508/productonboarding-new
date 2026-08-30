"""Getting a fix out to the systems that own the listings.

`commit_plan` publishes an approved resolution and `rollback` retracts it. Both
were right and both were whole-plan: one call, one outcome, all channels
together. That is the correct shape for a decision and the wrong shape for a
dispatch, because the systems on the other side are independent and fail
independently.

So this is dispatch, and it is deliberately thin. It does not decide anything.
The approval gate, the stale-evidence check and the safety gate all still live
where they were, at the planning boundary, and this runs after them or not at
all. What it adds is:

*   **Per-system results.** A correction is "published to four of five, one
    deferred", never "failed". A marketplace connector that is down must not be
    able to hold up the four channels that are answering, and a caller told
    "failed" cannot tell the difference between nothing having gone out and
    almost everything having gone out.
*   **A refusal that names the reason.** A print run inside its freeze window is
    deferred rather than attempted, because the artefact cannot be recalled and
    a failed attempt to change it is worse than a decision not to.

The safeguards travel with the tool rather than the caller. Nothing here can
publish without an approval, because nothing here publishes - it asks
`tools.planning` to, and that function refuses on its own terms whichever server
it is reached through.
"""

from __future__ import annotations

from sc.estate import publication

#: A dispatch outcome, per system.
SENT = "SENT"
DEFERRED = "DEFERRED"
REFUSED = "REFUSED"


def _freeze_bound(system, base) -> str | None:
    """Why this system cannot be pushed to right now, or None.

    Only one reason today, and it is the important one: a channel whose
    artefact cannot be recalled inside its freeze window. Attempting it would
    produce a printed catalogue nobody can correct, which is strictly worse than
    an entry in a report saying it was not attempted.
    """
    if not system.recallable and system.freeze_days:
        return (f"{system.channel_id} is inside a {system.freeze_days}-day "
                f"freeze window and what it publishes cannot be recalled")
    return None


def plan_dispatch(trace: dict, base) -> list[dict]:
    """What would be sent where, without sending anything.

    A reviewer approving a correction should be able to see which systems it
    reaches and which of them will refuse it before deciding, rather than
    discovering the print channel was frozen from a report afterwards.
    """
    rows = []
    lookup = publication.by_channel(base)
    for group in publication.blast_to_systems(trace, base):
        system = lookup[group["channel_id"]]
        blocked = _freeze_bound(system, base)
        rows.append({
            **group,
            "verb": "push_update",
            "outcome": DEFERRED if blocked else SENT,
            "reason": blocked or "",
            "endpoint": system.endpoint,
        })
    return rows


def dispatch(incident_id: str, scenario_id: str, trace: dict, base, *,
             actor: str = "publisher") -> dict:
    """Publish an approved resolution, and report per system.

    The whole-plan commit still happens once and still enforces its three
    refusals - approval on record, evidence unmoved, no open safety violation.
    This wraps it so that the *result* is expressed the way the estate is
    shaped: which systems were told, which were deferred and why.

    A commit that refuses refuses everything, and that is correct: the refusals
    are properties of the resolution rather than of any one channel, and
    publishing to four channels a resolution nobody approved would be four
    problems instead of none.
    """
    from sc.tools import planning

    planned = plan_dispatch(trace, base)
    result = planning.commit_plan(incident_id, scenario_id, actions=[],
                                  actor=actor)

    if not result.get("committed"):
        # One refusal, applied to every system, carrying the reason the
        # planning boundary gave. Not re-derived here: two accounts of why a
        # publish was refused is one account too many.
        reason = result.get("reason") or result.get("error") or "refused"
        for row in planned:
            row["outcome"] = REFUSED
            row["reason"] = reason
        return {"incident_id": incident_id, "scenario_id": scenario_id,
                "committed": False, "reason": reason, "systems": planned,
                "sent": 0, "deferred": 0,
                "refused": len(planned)}

    return {
        "incident_id": incident_id,
        "scenario_id": scenario_id,
        "committed": True,
        "systems": planned,
        "sent": sum(1 for r in planned if r["outcome"] == SENT),
        "deferred": sum(1 for r in planned if r["outcome"] == DEFERRED),
        "refused": 0,
    }


def revert(incident_id: str, scenario_id: str, trace: dict, base, *,
           reason: str = "", actor: str = "publisher") -> dict:
    """Roll a published resolution back, and report per system.

    A rollback restores what each published value displaced rather than
    deleting anything, so "what did this channel hold, and when" stays
    answerable. What this adds is the same per-system shape the dispatch has,
    and one honest asymmetry: a channel that could not be recalled was never
    sent to, so it has nothing to roll back - and reporting it as reverted would
    be a lie about a printed page.
    """
    from sc.tools import planning

    result = planning.rollback(incident_id, scenario_id, reason=reason,
                               actor=actor)
    rows = []
    lookup = publication.by_channel(base)
    for group in publication.blast_to_systems(trace, base):
        system = lookup[group["channel_id"]]
        blocked = _freeze_bound(system, base)
        rows.append({
            **group,
            "verb": "restore_listing",
            "outcome": DEFERRED if blocked else SENT,
            "reason": (f"never sent: {blocked}" if blocked else ""),
            "endpoint": system.endpoint,
        })
    return {
        "incident_id": incident_id,
        "scenario_id": scenario_id,
        "reverted": bool(result.get("rolled_back", result.get("reversed"))),
        "detail": result,
        "systems": rows,
        "restored": sum(1 for r in rows if r["outcome"] == SENT),
        "deferred": sum(1 for r in rows if r["outcome"] == DEFERRED),
    }
