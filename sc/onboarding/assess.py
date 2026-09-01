"""The sequential pass over a batch: one product at a time, in file order.

**Two stages, and the order is the point.** Every product goes through the
compliance gate first - ``sc.onboarding.gate``, over the regulation and policy
checks ``readiness`` already ran - and a product the gate refuses does not get
onboarded. Its gaps are not collected, no source is retrieved for it and no
value is proposed, because proposing a wattage for a product that is going back
to its supplier is work somebody then has to read. The gate is the reason the
expensive half of this pass is conditional rather than universal.

Not a graph run, and the distinction is the whole design. The correction graph
answers *a published value changed - what does it reach*, and it is built round
a case, a blast radius and an approval interrupt. Onboarding asks *is this
record fit to launch*, which is what ``sc.readiness`` already answers,
deterministically, in milliseconds, over the same tables the publish-time
validator reads. Working forty new products through the graph would be forty
suspended threads and forty pending approvals in a queue that exists to hold
one, and minutes of gateway traffic to reach an answer arithmetic already has.

The loop itself is not new either. ``sc.estate.submissions._verdict`` already
walks a submission's entities, resolves each to its variants and assesses them,
carrying the caveat rather than dropping it. This is that function turned into
a generator - same resolution, same call, same caveat - yielding per product so
a screen can follow it, and finishing with ``rollup.tally``. Nothing about the
*assessment* is new; only the watching is.

**Sequential is the honest shape here, not a limitation.** The map lights one
product at a time because the system is looking at one product at a time.
``pace_ms`` slows that down so a person can read it, and it is named, defaulted
and documented as presentation - it cannot reach a result, and a run with
``pace_ms=0`` returns exactly the same report.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

#: Long enough to read a SKU, short enough that forty of them is under a
#: minute. Presentation only.
DEFAULT_PACE_MS = 320


def run(submission_id: str, *, use_model: bool = False,
        pace_ms: int = DEFAULT_PACE_MS) -> Iterator[dict]:
    """Walk a batch, yielding one message per product and one at the end.

    Yields ``batch_started``, then ``product`` per entity in the order the
    supplier's file listed them, then ``batch_finished`` carrying the whole
    report - so a caller that watched the stream never needs to fetch it.

    Every ``product`` message carries a ``gate``: whether it may be onboarded
    at all, on whose authority it was refused, and the findings that refused
    it.
    """
    from sc.onboarding import batch as batch_mod

    found = batch_mod.get(submission_id)
    if found is None:
        yield {"kind": "error",
               "detail": f"no bundle called {submission_id!r}"}
        return

    entities = found["entities"]
    yield {"kind": "batch_started", "batch_id": submission_id,
           "supplier": found["supplier"], "system": found["system"],
           "total": len(entities), "entities": entities,
           "use_model": use_model}

    for index, message in enumerate(_walk(found, use_model=use_model)):
        if pace_ms and index and message["kind"] == "product":
            time.sleep(pace_ms / 1000.0)
        yield message


def report(submission_id: str, *, use_model: bool = False) -> dict | None:
    """The same numbers, without the walk. For opening the report cold."""
    from sc.onboarding import batch as batch_mod

    found = batch_mod.get(submission_id)
    if found is None:
        return None
    final = None
    for message in _walk(found, use_model=use_model):
        if message["kind"] == "batch_finished":
            final = message
    return final


def _walk(found: dict, *, use_model: bool) -> Iterator[dict]:
    """One product at a time, then the tally."""
    import sc.readiness as readiness
    from sc.onboarding import fixable as fixable_mod
    from sc.onboarding import gate as gate_mod
    from sc.readiness import record as record_mod
    from sc.readiness import rollup as rollup_mod
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod

    base = baseline_mod.get()
    entities = found["entities"]

    # One overlay and one provenance pass for the whole batch. `build` asks two
    # queries per entity; forty products would be eighty round trips to answer
    # one question, which is the same batching `/api/products/summary` does and
    # for the same reason.
    overlay = overlay_mod.cached(record_mod._instant(None), None)
    records = record_mod.build_many(entities, overlay=overlay, base=base)

    assessments: list[tuple[dict, dict]] = []
    gap_rows: list[dict] = []
    products: list[dict] = []

    for index, entity_id in enumerate(entities, start=1):
        record = records.get(entity_id)
        variant = base.variants.get(entity_id)
        product = base.products.get(base.product_of_variant.get(entity_id, ""))
        if record is None or variant is None or product is None:
            continue

        summary = readiness.assess(entity_id, use_model=use_model,
                                   include_record=False, record=record,
                                   base=base)
        if summary is None:
            continue

        findings = summary.get("findings") or []

        # The gate, before anything else looks at the record. A partition of the
        # findings already in hand rather than a second pass - see `gate`.
        checked = gate_mod.evaluate(summary)

        # And the reason the gate is worth having: a product it refused
        # collects no gaps, so nothing below retrieves a source for it or
        # proposes a value. `gaps_for` would drop the gate findings anyway -
        # they are not gap checks - but handing it the data findings says which
        # half of the assessment onboarding is about.
        gaps = (fixable_mod.gaps_for(entity_id, checked["data_findings"], base)
                if checked["passed"] else [])
        gap_rows.extend(gaps)

        row = {"product_id": product.id, "entity_id": entity_id,
               "supplier": product.supplier, "category": product.category,
               "gate_passed": checked["passed"]}
        assessments.append((row, summary))

        one = {
            "kind": "product",
            "ordinal": index,
            "total": len(entities),
            "entity_id": entity_id,
            "product_id": product.id,
            "sku": variant.sku or entity_id,
            "name": product.name,
            "category": product.category,
            "verdict": summary.get("verdict", ""),
            "gate": checked,
            "open": len(findings),
            "blocking": sum(1 for f in findings
                            if f.get("severity") == "BLOCKING"),
            "gaps": len(gaps),
            "findings": findings,
            # The path the map lights, resolved here rather than in the
            # browser: the client should not have to rediscover that a variant
            # belongs to a product which belongs to a supplier.
            "entities": [entity_id, product.id, product.supplier],
        }
        products.append(one)
        yield one

    fixes = fixable_mod.assess(gap_rows, base)
    totals = rollup_mod.tally(assessments, base)

    yield {
        "kind": "batch_finished",
        "batch_id": found["batch_id"],
        "supplier": found["supplier"],
        "system": found["system"],
        "submitted_at": found["submitted_at"],
        "doc_ref": found["doc_ref"],
        "file": found["file"],
        "products": products,
        # Proposed new lines are *not* in `totals`, and this is the number that
        # keeps that honest. A bundle of eleven rows of which five are lines we
        # do not have is a report about six products, and saying "six assessed"
        # without saying what happened to the other five is the undercount this
        # whole system is arranged to avoid.
        "proposals": found.get("proposals") or [],
        "totals": totals,
        "fixable": {**fixes.counts(),
                    "gaps": [g.as_dict() for g in fixes.gaps]},
        "checks_complete": totals.get("checks_complete", False),
        "caveat": totals.get("caveat"),
    }
