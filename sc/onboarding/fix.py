"""Filling the gaps a model can cite, and queuing the ones it cannot settle.

The only part of onboarding that writes. Everything it writes goes through one
of two doors here, with the same validation and the same provenance rules,
because a second filler would be a second set of rules about what a model is
allowed to assert - and the first thing the two would disagree about is an
allergen.

**Six things this must not do**, each of which would be easy and wrong:

*   It must not invent. A fill whose ``chunk_id`` is not one of the passages
    that were actually supplied is refused by ``_validated_fill`` and becomes a
    request to the supplier. That function is imported rather than
    reimplemented, and ``suggest`` calls it for the same reason.
*   It must not write RECORDED. An autonomous fill lands INFERRED with its
    confidence and its citation, through ``ingest.record_attribute``, which is
    what keeps the fail-closed safety gate able to see it. Calling
    ``store.record`` directly for one is exactly how a model's guess would
    acquire the provenance of a supplier's assertion.
*   It must not write INFERRED for a person. A value a category manager
    approved or typed lands DECIDED, named to them. Two classes of knowledge,
    two doors, and the audit trail can tell them apart.
*   It must not fill a safety-class attribute autonomously. Held, counted, and
    named - and even when a person explicitly asks for them, the proposal still
    goes to a person to decide.
*   It must not write below the threshold. A proposal the score does not clear
    becomes a queued question, not a quiet fact. This is the rule the whole
    feature exists for, and it is enforced in one place: ``decide.route``.
*   It must not publish. "Pushed through" means a product now has no findings
    left, which is arithmetic; publication needs ``commit_plan``, a recorded
    approval and a channel reservation, and none of those are touched here. A
    button that published forty products would defeat the gate the rest of the
    system is built around.

**A product the compliance gate stopped is not touched at all.** No source is
retrieved for it, no value proposed and nothing written - it is going back to
its supplier, and proposing a wattage for it would be work somebody then has to
read. ``assess`` collects no gaps for a stopped product, so this gets there by
construction rather than by remembering to check.

With no gateway, nothing is read from a document - and, unlike before, that is
no longer the same as nothing happening. ``suggest`` falls back to what the
catalog and the past decisions already say, which needs no network; those
proposals are corroborated by definition or they are capped below any usable
threshold, so the offline path produces questions for a person rather than
silent facts. That is also the path the test suite exercises, since it runs with
the gateway pinned to a closed port.
"""

from __future__ import annotations

from sc.onboarding import fixable as fixable_mod

FILLED = "FILLED"
QUEUED = "AWAITING_REVIEW"
REQUESTED = "REQUEST_SUPPLIER_INPUT"


def apply(submission_id: str, *, actor: str,
          entity_ids: list[str] | None = None,
          include_safety_class: bool = False) -> dict:
    """Read the sources for one batch's gaps, and route every proposal."""
    from sc.onboarding import assess as assess_mod
    from sc.onboarding import batch as batch_mod
    from sc.onboarding import decide as decide_mod
    from sc.onboarding import suggest as suggest_mod
    from sc.readiness import record as record_mod
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod
    from sc.tools import planning

    found = batch_mod.get(submission_id)
    if found is None:
        return {"error": f"no bundle called {submission_id!r}"}

    report = assess_mod.report(submission_id) or {}
    base = baseline_mod.get()
    overlay = overlay_mod.cached(record_mod._instant(None), None)
    wanted = set(entity_ids or [])
    limit = decide_mod.threshold()

    gaps = [g for g in (report.get("fixable") or {}).get("gaps", [])
            if g["state"] == fixable_mod.CANDIDATE
            or (include_safety_class and g["state"] == fixable_mod.SAFETY_HELD)
            # A gap with no retrievable passage still has priors, and the whole
            # point of reading the catalog is that "nothing to cite" is not the
            # same as "nothing known". It reaches a person or it reaches the
            # supplier; either way it is no longer silently nothing.
            or g["state"] == fixable_mod.NO_SOURCE]
    if wanted:
        gaps = [g for g in gaps if g["entity_id"] in wanted]

    held = [g for g in (report.get("fixable") or {}).get("gaps", [])
            if g["state"] == fixable_mod.SAFETY_HELD] if not include_safety_class else []

    if not gaps:
        # Audited even though nothing was written. "Somebody asked and there
        # was nothing to read" is precisely the fact a reviewer needs a week
        # later when they ask why the batch is still with the supplier, and an
        # empty ledger would leave them to assume nobody tried.
        planning.audit(actor, "APPLY_ENRICHMENT", "submission", submission_id,
                       {"filled": [], "queued": 0, "requested": 0,
                        "threshold": limit,
                        "include_safety_class": include_safety_class,
                        "why": ("every product in this batch either cleared the "
                                "compliance gate with no gaps or was stopped "
                                "by it")})
        return _result(submission_id, actor, [], [], [], held, limit,
                       note=("there is nothing open on this batch that a value "
                             "could close — either the records are complete or "
                             "the products were stopped before onboarding"))

    proposals = suggest_mod.for_gaps(
        gaps, base, run_id=submission_id, use_model=True, overlay=overlay,
        include_safety_class=include_safety_class)

    filled: list[dict] = []
    queued: list[dict] = []
    settled: set[tuple[str, str]] = set()

    for proposal in proposals:
        key = (proposal.entity_id, proposal.attribute_path)
        routed = decide_mod.route(proposal, limit)
        suggestion_id = decide_mod.record(submission_id, proposal,
                                          routed=routed, limit=limit)
        settled.add(key)

        if routed == decide_mod.AUTONOMOUS:
            citation = proposal.citation or {}
            fact_id = write_inferred(
                entity_id=proposal.entity_id,
                attribute_path=proposal.attribute_path,
                value=proposal.value, confidence=proposal.confidence,
                source_doc=citation.get("doc_id", ""), run_id=submission_id)
            filled.append({**proposal.as_dict(), "status": FILLED,
                           "suggestion_id": suggestion_id, "fact_id": fact_id,
                           "doc_id": citation.get("doc_id", ""),
                           "heading": citation.get("heading", "")})
        else:
            queued.append({**proposal.as_dict(), "status": QUEUED,
                           "suggestion_id": suggestion_id,
                           "why": _why_queued(proposal, limit)})

    requested = [{
        "entity_id": gap["entity_id"],
        "attribute_path": gap["attribute_path"],
        "status": REQUESTED,
        "why": ("nothing on file bears on this value at all — no passage states "
                "it, no other variant or product in the category holds it, and "
                "nobody has decided it before, so it has to come from the "
                "supplier"),
    } for gap in gaps
        if (gap["entity_id"], gap["attribute_path"]) not in settled
        and not (gap["safety_class"] and not include_safety_class)]

    planning.audit(actor, "APPLY_ENRICHMENT", "submission", submission_id,
                   # `or {}` rather than a `get` default: the key is always
                   # present and is None for a proposal built from the catalog
                   # rather than from a passage, which a default never reaches.
                   {"filled": [(f["entity_id"], f["attribute_path"],
                                (f.get("citation") or {}).get("chunk_id"))
                               for f in filled],
                    "queued": [q["suggestion_id"] for q in queued],
                    "requested": len(requested),
                    "threshold": limit,
                    "include_safety_class": include_safety_class})

    return _result(submission_id, actor, filled, queued, requested, held, limit)


def _why_queued(proposal, limit: float) -> str:
    """Why this one is a question rather than a fact, in one line."""
    if proposal.safety_class:
        return ("safety class: a value a model inferred rather than read blocks "
                "publication instead of degrading it, so this one is decided by "
                "a person whatever agrees with it")
    return (f"{proposal.confidence:.0%} confidence, below the {limit:.0%} the "
            f"autonomous threshold is set to — the evidence beside it is what "
            f"the score was composed from")


# ---------------------------------------------------------------------------
# The two doors
# ---------------------------------------------------------------------------


def write_inferred(*, entity_id: str, attribute_path: str, value: object,
                   confidence: float, source_doc: str = "",
                   run_id: str = "") -> str:
    """A model's reading, written as one.

    ``ingest.record_attribute`` and nothing else - the same door ``enrich``
    writes through. It stamps INFERRED with the confidence and the document,
    which is what keeps ``sim.engine._check_safety`` able to see the value and
    fail closed on it at publish time.
    """
    from sc.graph.nodes import fast_model
    from sc.replay import ingest, tape

    return ingest.record_attribute(
        entity_id=entity_id, attribute_path=attribute_path, value=value,
        # The simulated clock, never the wall clock: every as-of read in this
        # system defaults both time axes to sim_now(), so a fact stamped with a
        # real date is recorded and then invisible.
        valid_from=tape.sim_now(), source_doc=source_doc,
        confidence=confidence, agent="enrich", model=fast_model(),
        run_id=run_id)


def write_decided(*, entity_id: str, attribute_path: str, value: object,
                  actor: str, suggestion_id: str = "",
                  citation: dict | None = None, note: str = "") -> str:
    """A person's choice, written as one.

    Deliberately not ``record_attribute``, which stamps INFERRED by definition.
    ``ProvenanceKind`` keeps "an LLM concluded it" and "a human chose it" apart
    because they are different kinds of knowledge, and two places downstream act
    on the difference: the audit trail, which is meant to be able to say who
    asserted a value, and the publish-time safety gate, which fails closed on a
    low-confidence *inference* and has no business second-guessing a named
    person who took responsibility for the value.

    ``confidence`` is deliberately absent from the provenance. A person is not
    seventy per cent sure in the sense a model is; they decided. The proposal's
    score is kept on the suggestion row, where it belongs, as the thing they
    were shown rather than a property of what they chose.
    """
    from sc.contracts import Provenance, ProvenanceKind
    from sc.replay import ingest, tape
    from sc.state import baseline as baseline_mod
    from sc.state import store

    base = baseline_mod.get()
    doc = (citation or {}).get("doc_id") or ""
    entity_type = ingest._entity_type(base, entity_id) or "variant"
    provenance = Provenance(
        kind=ProvenanceKind.DECIDED,
        source_id=actor,
        agent="onboarding.decide",
        note=" · ".join(p for p in (
            note, f"proposal {suggestion_id}" if suggestion_id else "",
            f"shown alongside {doc}" if doc else "") if p),
    )
    return store.record(entity_type, entity_id, attribute_path, value,
                        valid_from=tape.sim_now(), provenance=provenance,
                        recorded_at=tape.sim_now())


def _result(submission_id: str, actor: str, filled: list[dict],
            queued: list[dict], requested: list[dict], held: list[dict],
            limit: float, *, note: str = "") -> dict:
    """The answer, and the sentence that keeps it honest."""
    from sc.onboarding import assess as assess_mod

    after = assess_mod.report(submission_id) or {}
    totals = after.get("totals") or {}
    return {
        "batch_id": submission_id,
        "actor": actor,
        "threshold": limit,
        "filled": filled,
        "queued": queued,
        "requested": requested,
        "held_safety": held,
        "counts": {"filled": len(filled), "queued": len(queued),
                   "requested": len(requested), "held_safety": len(held)},
        # Re-assessed rather than predicted. A product is ready because its
        # findings are gone, and the only way to know that is to look again.
        "totals": totals,
        "products": after.get("products") or [],
        "note": note or (
            f"{len(filled)} value(s) cleared the {limit:.0%} threshold and were "
            f"recorded INFERRED with the passage they were read from; "
            f"{len(queued)} are waiting on a category manager with the evidence "
            f"their score was composed from. Nothing has been published: a "
            f"product with no findings left is ready to launch, and launching it "
            f"still needs a reviewer and the publication gate"),
    }
