"""Where a feed's products have got to, from received to on sale.

Two state spines already exist and neither answers this on its own.
``sc.estate.submissions`` walks one submission through nine stages and stops at
``verdict`` - it knows what arrived and what the system made of it, and nothing
about what happened next. ``sc.lifecycle.stages`` places a product in one of six
lanes from its *current* state - it knows a product is on sale and nothing about
which archive delivered it. Between the two there is no answer to the question a
category manager actually asks: this supplier sent forty rows on the fourth of
July, where are they now.

This is that join, and it is only a join. Every input is read from the module
that owns it - the gate from ``sc.onboarding.gate``, the verdict from
``sc.readiness``, the lane from ``sc.lifecycle.stages``, the proposals from
``onboarding_suggestions`` - and nothing here reaches a second opinion about any
of them.

**Position is exclusive; history is not.** ``state_of`` returns exactly one
state, because a product is in one place. But "AI corrected this" is a fact about
the past that does not stop being true when the product moves on, so it is
carried beside the state as a flag and a count rather than as a seventh place to
be. This is the same trade ``sc/readiness/rollup.py`` makes for ``stopped`` and
for the same reason: filing every product under exactly one heading would mean
either losing the autonomous fills into ``ALL_CLEAR``, where nobody would see
them, or reporting a product as corrected when what it actually is now is on
sale.

**Nothing here is stored.** Every state is recomputed on read, for the reason
``sc/lifecycle/stages.py`` gives for not storing a lane.
"""

from __future__ import annotations

from sc import db
from sc.lifecycle import stages as stages_mod
from sc.readiness.verdict import BLOCKED as V_BLOCKED
from sc.readiness.verdict import READY as V_READY
from sc.readiness.verdict import RETURN as V_RETURN

#: The states, in the order work moves through them.
RECEIVED = "RECEIVED"
PROCESSING = "PROCESSING"
BLOCKED = "BLOCKED"
ON_HOLD = "ON_HOLD"
ALL_CLEAR = "ALL_CLEAR"
PUSHED_DOWNSTREAM = "PUSHED_DOWNSTREAM"
ON_SALE = "ON_SALE"

STATES: tuple[str, ...] = (RECEIVED, PROCESSING, BLOCKED, ON_HOLD, ALL_CLEAR,
                           PUSHED_DOWNSTREAM, ON_SALE)

#: What each means, in the words the screen uses. Beside the names so the UI
#: cannot describe a state differently from the rule that fills it.
DESCRIPTIONS: dict[str, str] = {
    RECEIVED: "Arrived and not yet taken into the record. The events are on the "
              "live lane behind the ingest watermark.",
    PROCESSING: "In the record and assessed, with gaps still open. Nothing has "
                "stopped it; nothing has cleared it either.",
    BLOCKED: "Stopped, and back with its supplier. Either a regulation or this "
             "organisation's own policy refused it, or the record has a "
             "blocking finding.",
    ON_HOLD: "Waiting on a person. A value was proposed that the system will "
             "not write unattended - a safety-class field, a single source, or "
             "one below the confidence threshold.",
    ALL_CLEAR: "Fit to launch, and not pushed anywhere yet.",
    PUSHED_DOWNSTREAM: "Dispatched. The listings are prepared and waiting on "
                       "their launch date.",
    ON_SALE: "On the floor. What a shopper sees is what the record says.",
}

#: Which lifecycle lanes mean the product has left onboarding behind. Read from
#: `stages` rather than restated, so a lane renamed there cannot silently stop
#: matching here.
_DOWNSTREAM = {stages_mod.PUSHED_DOWNSTREAM: PUSHED_DOWNSTREAM,
               stages_mod.LIVE: ON_SALE}


def state_of(*, ingested: bool, gate_passed: bool | None, verdict: str,
             lane: str, pending_decisions: int) -> str:
    """One product's position in one feed. Pure: no clock, no database.

    Precedence is argued rather than arbitrary, and it is the same argument
    ``stages.stage_of`` makes one level up:

    * **Not ingested outranks everything.** A product the record has not taken
      in yet has no verdict worth reporting, and showing the last assessment
      beside a feed that has just landed would date-stamp a screen with an
      answer about a different version of the record.
    * **Stopped outranks downstream.** A product that is on sale *and* has just
      been refused by the gate is the single row somebody has to look at, and a
      board filing it under "on sale" would hide it.
    * **Downstream outranks waiting.** A pending proposal on a product already
      dispatched is real, but where the product *is* is downstream; the
      proposal shows up in the count of open decisions either way.

    ``BLOCKED`` is the gate stopping it or a blocking finding - the two things a
    supplier has to fix. A bare ``RETURN_TO_SOURCE`` is **not** blocked: it is a
    record with a gap in it, the gate let it through, and the next thing that
    happens is the system trying to fill that gap from what it already holds.
    Filing it as blocked would count the entire AI-correction lane as a failure,
    which is the opposite of what it is.
    """
    if not ingested:
        return RECEIVED
    if gate_passed is False or verdict == V_BLOCKED:
        return BLOCKED
    placed = _DOWNSTREAM.get(lane)
    if placed is not None:
        return placed
    if pending_decisions:
        return ON_HOLD
    if verdict == V_READY:
        return ALL_CLEAR
    # RETURN_TO_SOURCE with nothing proposed yet. Mid-flight rather than
    # refused: the gate passed it, so nothing is wrong with it that a value
    # would not fix, and the suggestion pass has not run or found nothing.
    return PROCESSING


def blank_counts() -> dict[str, int]:
    return {state: 0 for state in STATES}


def _pending_by_entity(submission_id: str) -> dict[str, int]:
    """Undecided proposals per entity, for one feed."""
    rows = db.query(
        "SELECT entity_id, COUNT(*) AS n FROM onboarding_suggestions"
        " WHERE submission_id = ? AND decision IS NULL AND route = 'HUMAN'"
        " GROUP BY entity_id", (submission_id,))
    return {r["entity_id"]: int(r["n"]) for r in rows}


def _autonomous_by_entity(submission_id: str) -> dict[str, int]:
    """Values this system wrote unattended, per entity, for one feed.

    Counted from the proposal queue rather than from ``facts``, because the
    queue is what records *why* it was written without a person - the
    confidence, the threshold it was judged against and the evidence. A fact
    alone would say a value is INFERRED and not that nobody was asked.
    """
    rows = db.query(
        "SELECT entity_id, COUNT(*) AS n FROM onboarding_suggestions"
        " WHERE submission_id = ? AND route = 'AUTONOMOUS'"
        " GROUP BY entity_id", (submission_id,))
    return {r["entity_id"]: int(r["n"]) for r in rows}


def _decided_by_entity(submission_id: str) -> dict[str, int]:
    """Values a person settled, per entity, for one feed."""
    rows = db.query(
        "SELECT entity_id, COUNT(*) AS n FROM onboarding_suggestions"
        " WHERE submission_id = ? AND decision IN ('APPROVE', 'RECTIFY')"
        " GROUP BY entity_id", (submission_id,))
    return {r["entity_id"]: int(r["n"]) for r in rows}


def _ingested(event_ids: list[str]) -> bool:
    """Has the record taken this feed's events in yet?

    The same watermark comparison ``sc.estate.submissions._ingested`` makes, and
    deliberately the same one: two readings of "is this in the record" would
    disagree the first time a batch was mid-flight, which is exactly when
    somebody is looking.
    """
    from sc.replay import ingest, tape

    if not event_ids:
        return False
    seqs = [r["seq"] for r in db.query(
        "SELECT seq FROM events WHERE id IN (%s)"
        % ",".join("?" * len(event_ids)), tuple(event_ids))]
    return bool(seqs) and max(seqs) <= ingest.cursor(tape.LANE_LIVE)


def for_feed(submission_id: str, *, use_model: bool = False,
             context: dict | None = None) -> dict | None:
    """One feed's rows, each in its state. ``None`` if no such submission.

    **The grain is the row the supplier sent**, which is a variant, and that is
    stated rather than implied because it is the one place this surface can be
    read as contradicting another. The Lifecycle board places a *product*, and a
    product is as blocked as its worst variant - so a pack whose 500ml is fit to
    sell and whose 1L is not appears there, correctly, as one product with its
    supplier. Asked of a feed, the honest answer is that one row cleared and one
    did not, because that is what the supplier has to act on.

    So the lane is recomputed here per variant, from ``stages.stage_of`` and the
    same three signals ``board.signals`` gives that module. Same function, same
    inputs, finer grain - not a second set of rules.

    ``context`` lets a caller building many feeds pass the baseline, overlay and
    signals in once. Rebuilding them per feed over a window of thirty is the
    difference between a page and a wait.
    """
    from sc.onboarding import batch as batch_mod
    from sc.onboarding import gate as gate_mod

    feed = batch_mod.get(submission_id)
    if feed is None:
        return None
    ctx = context if context is not None else build_context()

    ingested = _ingested(feed["event_ids"])
    pending = _pending_by_entity(submission_id)
    autonomous = _autonomous_by_entity(submission_id)
    decided = _decided_by_entity(submission_id)

    products, counts = [], blank_counts()
    complete = True
    for entity_id, summary, row in _assess(feed["entities"], use_model, ctx):
        gate = gate_mod.evaluate(summary)
        lane = _lane_of(entity_id, row["product_id"], summary["verdict"], ctx)
        state = state_of(
            ingested=ingested,
            gate_passed=gate["passed"],
            verdict=summary.get("verdict", ""),
            lane=lane,
            pending_decisions=pending.get(entity_id, 0))
        counts[state] += 1
        complete = complete and bool(summary.get("checks_complete"))
        products.append({
            "entity_id": entity_id,
            "product_id": row["product_id"],
            "sku": row["sku"],
            "name": row["name"],
            "category": row["category"],
            "supplier": row["supplier"],
            "state": state,
            "verdict": summary.get("verdict", ""),
            "gate": {"passed": gate["passed"], "outcome": gate["outcome"],
                     "authority": gate["authority"], "why": gate["why"]},
            "open_findings": len(summary.get("findings") or []),
            "awaiting_decision": pending.get(entity_id, 0),
            "ai_corrected": autonomous.get(entity_id, 0),
            "decided_by_person": decided.get(entity_id, 0),
            "lane": lane,
        })

    return {
        "feed_id": submission_id,
        "supplier": feed["supplier"],
        "system": feed["system"],
        "submitted_at": feed["submitted_at"],
        "kind": "DATA_PACK",
        "grain": "variant",
        "ingested": ingested,
        "rows": len(feed["entities"]),
        "assessed": len(products),
        "media_events": len(feed["images"]),
        "proposals": len(feed["proposals"]),
        "counts": counts,
        # Overlapping on purpose - see the module docstring. A row corrected
        # unattended and since put on sale is counted in ON_SALE *and* here,
        # because both are true and the second answers "what did the AI
        # actually do for us", which nothing else on the screen reports.
        "ai_corrected": sum(1 for p in products if p["ai_corrected"]),
        "decided_by_person": sum(1 for p in products if p["decided_by_person"]),
        "checks_complete": complete,
        "caveat": None if complete else _CAVEAT,
        "products": products,
    }


def build_context(*, base=None) -> dict:
    """The catalog, the overlay and the three lane signals, gathered once.

    All four are whole-estate reads. Doing them per feed is what turns a
    thirty-feed window into a wait, and they cannot change between feeds within
    one request anyway.
    """
    from sc.lifecycle import board as board_mod
    from sc.readiness import record as record_mod
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod

    base = base if base is not None else baseline_mod.get()
    dispatched, corrected, redactions = board_mod.signals(base)
    return {
        "base": base,
        "overlay": overlay_mod.cached(record_mod._instant(None), None),
        "dispatched": dispatched,
        "corrected": corrected,
        "redactions": redactions,
    }


def _lane_of(entity_id: str, product_id: str, verdict: str, ctx: dict) -> str:
    """This variant's lane, from the same rule the board applies to a product.

    The listings are the variant's own; dispatch, correction and redaction are
    genuinely product-level facts - a correction lands on a product and a commit
    is recorded against an incident - so they apply to every variant under it.
    """
    base, overlay = ctx["base"], ctx["overlay"]
    statuses: dict[str, int] = {}
    for listing_id in base.listings_of.get(entity_id, []):
        listing = base.listings[listing_id]
        status = overlay.channel_status.get(listing_id, listing.status)
        statuses[status] = statuses.get(status, 0) + 1
    return stages_mod.stage_of(
        verdict=verdict,
        listings=statuses,
        dispatched=product_id in ctx["dispatched"],
        corrected=product_id in ctx["corrected"],
        redacted=bool(ctx["redactions"].get(product_id)))


#: Said once, because three surfaces report it and a second wording would be a
#: second claim about what did not run.
_CAVEAT = ("some products here were assessed without a model: the checks that "
           "read regulation, internal documentation and copy meaning did not "
           "run on them, so this is a narrower count rather than a cleaner one")


def _assess(entity_ids: list[str], use_model: bool, ctx: dict):
    """Assess a feed's entities, yielding ``(entity_id, summary, row)``.

    Skips an entity the catalog does not have - a bundle can name a SKU that
    became a proposal rather than a product, and those are counted by the
    register as proposals rather than silently dropped into a state.
    """
    import sc.readiness as readiness

    base = ctx["base"]
    for entity_id in entity_ids:
        variant = base.variants.get(entity_id)
        if variant is None:
            continue
        summary = readiness.assess(entity_id, use_model=use_model,
                                   include_record=False, base=base)
        if summary is None:
            continue
        product_id = base.product_of_variant.get(entity_id, "")
        product = base.products.get(product_id)
        yield entity_id, summary, {
            "product_id": product_id,
            "sku": getattr(variant, "sku", "") or entity_id,
            "name": getattr(product, "name", "") or getattr(variant, "name", ""),
            "category": getattr(product, "category", ""),
            "supplier": getattr(product, "supplier", ""),
        }
