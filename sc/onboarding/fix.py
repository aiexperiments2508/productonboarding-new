"""Filling the gaps a model can cite, and nothing else.

The only part of onboarding that writes. Everything it writes goes through the
same door ``enrich`` writes through, with the same validation and the same
provenance, because a second filler would be a second set of rules about what a
model is allowed to assert - and the first thing the two would disagree about
is an allergen.

**Five things this must not do**, each of which would be easy and wrong:

*   It must not invent. A fill whose ``chunk_id`` is not one of the passages
    that were actually supplied is refused by ``_validated_fill`` and becomes a
    request to the supplier. That function is imported rather than reimplemented.
*   It must not write RECORDED. Every fill lands INFERRED with its confidence
    and its citation, through ``ingest.record_attribute``, which is what keeps
    the fail-closed safety gate able to see it. Calling ``store.record``
    directly here is exactly how a model's guess would acquire the provenance
    of a supplier's assertion.
*   It must not fill a safety-class attribute by default. Held, counted, and
    named - and even when a person explicitly asks for them, the value still
    lands INFERRED and still cannot publish below the confidence threshold.
*   It must not publish. "Pushed through" means a product now has no findings
    left, which is arithmetic; publication needs ``commit_plan``, a recorded
    approval and a channel reservation, and none of those are touched here. A
    button that published forty products would defeat the gate the rest of the
    system is built around.
*   It must not be anonymous. An actor is required and every fill is audited
    against it.

With no gateway the answer is *nothing filled*, every gap becomes a supplier
request, and the response says why - which is also the path the test suite
exercises, since it runs with the gateway pinned to a closed port.
"""

from __future__ import annotations

from sc.onboarding import fixable as fixable_mod

FILLED = "FILLED"
REQUESTED = "REQUEST_SUPPLIER_INPUT"


def apply(submission_id: str, *, actor: str,
          entity_ids: list[str] | None = None,
          include_safety_class: bool = False) -> dict:
    """Read the sources for one batch's gaps and fill what can be cited."""
    from sc.graph import prompts
    from sc.graph.nodes import _validated_fill, fast_model
    from sc.llm.gateway import GatewayError, complete_json
    from sc.onboarding import assess as assess_mod
    from sc.onboarding import batch as batch_mod
    from sc.rag import retrieve
    from sc.replay import ingest, tape
    from sc.state import baseline as baseline_mod
    from sc.tools import planning

    found = batch_mod.get(submission_id)
    if found is None:
        return {"error": f"no bundle called {submission_id!r}"}

    report = assess_mod.report(submission_id) or {}
    base = baseline_mod.get()
    wanted = set(entity_ids or [])

    gaps = [g for g in (report.get("fixable") or {}).get("gaps", [])
            if g["state"] == fixable_mod.CANDIDATE
            or (include_safety_class and g["state"] == fixable_mod.SAFETY_HELD)]
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
                       {"filled": [], "requested": 0,
                        "include_safety_class": include_safety_class,
                        "why": "no gap in this batch has a source passage"})
        return _result(submission_id, actor, [], [], held,
                       note=("nothing in this batch has a source passage on "
                             "file, so there is nothing a model could read a "
                             "value out of"))

    entities = sorted({g["entity_id"] for g in gaps})
    paths = sorted({g["attribute_path"] for g in gaps})
    chunks = retrieve.search(" ".join(paths)[:200] or "attribute", top_k=6,
                             doc_types=fixable_mod.DOC_TYPES, entities=entities)
    supplied = retrieve.cite(chunks)
    known_chunks = {c["chunk_id"] for c in supplied}
    definitions = [{"path": g["attribute_path"], "dtype": g["dtype"],
                    "unit": g["unit"], "ordered": False} for g in gaps]

    try:
        reply, _usage = complete_json(
            [{"role": "system", "content": prompts.ENRICH_SYSTEM},
             {"role": "user", "content": prompts.enrich_user(
                 gaps, supplied, definitions)}],
            model=fast_model(), agent="enrich", run_id=submission_id)
        proposed = reply.get("fills") or []
        outage = ""
    except GatewayError as exc:
        # The same posture as `enrich`: nothing is filled without a model to
        # read the extracts, and nothing is guessed either.
        proposed, outage = [], str(exc)[:200]

    filled: list[dict] = []
    requested: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for fill in proposed:
        if not isinstance(fill, dict):
            continue
        row, why = _validated_fill(base, fill, known_chunks)
        if row is None:
            continue
        key = (row["entity_id"], row["attribute_path"])
        if key in seen or not any(
                g["entity_id"] == key[0] and g["attribute_path"] == key[1]
                for g in gaps):
            # A fill for something nobody asked about is not an answer to the
            # question, whatever else it is.
            continue
        seen.add(key)
        citation = next((c for c in supplied
                         if c["chunk_id"] == row["chunk_id"]), {})
        ingest.record_attribute(
            entity_id=row["entity_id"], attribute_path=row["attribute_path"],
            # The simulated clock, never the wall clock: every as-of read in
            # this system defaults both time axes to sim_now(), so a fact
            # stamped with a real date is recorded and then invisible.
            value=row["value"], valid_from=tape.sim_now(),
            source_doc=citation.get("doc_id", ""),
            confidence=row["confidence"], agent="enrich",
            model=fast_model(), run_id=submission_id)
        filled.append({**row, "status": FILLED,
                       "doc_id": citation.get("doc_id", ""),
                       "heading": citation.get("heading", "")})

    for gap in gaps:
        if (gap["entity_id"], gap["attribute_path"]) in seen:
            continue
        requested.append({
            "entity_id": gap["entity_id"],
            "attribute_path": gap["attribute_path"],
            "status": REQUESTED,
            "why": (f"no model was available to read the source extracts: "
                    f"{outage}") if outage else
                   ("the supplied passages do not state this value, so there "
                    "is nothing to cite and it has to come from the supplier"),
        })

    planning.audit(actor, "APPLY_ENRICHMENT", "submission", submission_id,
                   {"filled": [(f["entity_id"], f["attribute_path"],
                                f["chunk_id"]) for f in filled],
                    "requested": len(requested),
                    "include_safety_class": include_safety_class})

    return _result(submission_id, actor, filled, requested, held, outage=outage)


def _result(submission_id: str, actor: str, filled: list[dict],
            requested: list[dict], held: list[dict], *, outage: str = "",
            note: str = "") -> dict:
    """The answer, and the sentence that keeps it honest."""
    from sc.onboarding import assess as assess_mod

    after = assess_mod.report(submission_id) or {}
    totals = after.get("totals") or {}
    return {
        "batch_id": submission_id,
        "actor": actor,
        "filled": filled,
        "requested": requested,
        "held_safety": held,
        "counts": {"filled": len(filled), "requested": len(requested),
                   "held_safety": len(held)},
        "gateway": {"reachable": not outage, "detail": outage},
        # Re-assessed rather than predicted. A product is ready because its
        # findings are gone, and the only way to know that is to look again.
        "totals": totals,
        "products": after.get("products") or [],
        "note": note or (
            "every value filled here is recorded INFERRED with the passage it "
            "was read from, never as something the supplier asserted. Nothing "
            "has been published: a product with no findings left is ready to "
            "launch, and launching it still needs a reviewer's approval and "
            "the publication gate"),
    }
