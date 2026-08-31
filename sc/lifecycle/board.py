"""The lifecycle board: every product, placed in a lane.

Composed from the reads that already exist rather than from a third traversal
of the catalog - ``readiness.search`` for the population and the verdicts,
``overlay`` for what each listing is actually doing, ``committed_actions`` for
what has been dispatched, ``planning.open_redactions`` for what is being held
back. Everything here is a join. Nothing here decides anything a check has not
already decided.
"""

from __future__ import annotations

from sc import db
from sc.lifecycle import stages as stages_mod
from sc.readiness.verdict import BLOCKED, READY, RETURN


def build(*, q: str = "", suppliers: list[str] | None = None,
          categories: list[str] | None = None, limit: int = 400,
          use_model: bool = False) -> dict:
    """Every product in scope, in its lane, with the counts a board needs."""
    import sc.readiness as readiness
    from sc.readiness import record as record_mod
    from sc.readiness import search as search_mod
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod
    from sc.tools import planning

    base = baseline_mod.get()
    rows = search_mod.find(q, limit=limit, suppliers=suppliers,
                           categories=categories)
    if not rows:
        return _empty()

    valid = record_mod._instant(None)
    overlay = overlay_mod.cached(valid, None)
    records = record_mod.build_many([r["entity_id"] for r in rows],
                                    overlay=overlay, base=base)

    dispatched = _dispatched_products(base)
    corrected = _corrected_products(base)
    redactions = _redactions_by_product(base, planning.open_redactions())

    by_product: dict[str, stages_mod.Placement] = {}
    for row in rows:
        record = records.get(row["entity_id"])
        if record is None:
            continue
        summary = readiness.assess(row["entity_id"], use_model=use_model,
                                   include_record=False, record=record,
                                   base=base)
        if summary is None:
            continue
        _place(by_product, row, summary, base, overlay, dispatched, corrected,
               redactions)

    placements = [p for p in by_product.values()]
    for placement in placements:
        placement.stage = stages_mod.stage_of(
            verdict=placement.verdict,
            listings=placement.listings,
            dispatched=placement.product_id in dispatched,
            corrected=placement.product_id in corrected,
            redacted=bool(placement.redactions))

    lanes = {stage: [] for stage in stages_mod.STAGES}

    # Proposals are not products and are not in the population above - the
    # catalog has never heard of them. They are on the board anyway, because
    # "a supplier has offered us a line and nobody has decided" is exactly the
    # kind of thing that otherwise sits unnoticed in a mailbox for a fortnight.
    from sc.lifecycle import drafts as drafts_mod

    for draft in drafts_mod.pending():
        lanes[stages_mod.DRAFT].append({
            "product_id": draft["draft_id"] or draft["submission_id"],
            "stage": stages_mod.DRAFT,
            "verdict": "",
            "name": draft["name"],
            "category": draft["category"],
            "supplier": draft["supplier"],
            "regulated": draft["category"].startswith("food."),
            "variants": [], "listings": {}, "findings": [],
            "systems": [draft["system"]],
            "redactions": [],
            "correction": {
                "source": "submission",
                "kind": "PRODUCT_DRAFT",
                "summary": draft["note"] or "a new line, awaiting a decision",
                "paths": [],
                "submission_id": draft["submission_id"],
                "supplier": draft["supplier"],
                "detected_at": draft["submitted_at"],
            },
        })
    for placement in sorted(placements, key=lambda p: p.product_id):
        lanes[placement.stage].append({
            **placement.as_dict(),
            "name": base.products[placement.product_id].name,
            "category": base.products[placement.product_id].category,
            "supplier": base.products[placement.product_id].supplier,
            "regulated": base.products[placement.product_id].regulated,
        })

    return {
        "lanes": [{"stage": stage,
                   "description": stages_mod.DESCRIPTIONS[stage],
                   "count": len(lanes[stage]),
                   "products": lanes[stage]}
                  for stage in stages_mod.STAGES],
        "totals": {stage: len(lanes[stage]) for stage in stages_mod.STAGES},
        "products": len(placements),
        "checks_complete": use_model,
        "caveat": None if use_model else (
            "placed without a model: the three checks that read regulation, "
            "internal documentation and copy meaning did not run, so a product "
            "in a cleared lane has passed six checks rather than nine"),
    }


def _empty() -> dict:
    return {"lanes": [{"stage": s, "description": stages_mod.DESCRIPTIONS[s],
                       "count": 0, "products": []}
                      for s in stages_mod.STAGES],
            "totals": {s: 0 for s in stages_mod.STAGES},
            "products": 0, "checks_complete": False, "caveat": None}


#: A product is as far along as its *least* advanced variant, and as blocked as
#: its worst one. A multipack nobody can launch holds the line.
_SEVERITY = {READY: 0, RETURN: 1, BLOCKED: 2}


def _place(by_product, row, summary, base, overlay, dispatched, corrected,
           redactions) -> None:
    product_id = row["product_id"]
    placement = by_product.get(product_id)
    if placement is None:
        placement = stages_mod.Placement(
            product_id=product_id, stage=stages_mod.CLEARED, verdict=READY,
            correction=corrected.get(product_id),
            redactions=redactions.get(product_id, []))
        by_product[product_id] = placement

    verdict = summary["verdict"]
    if _SEVERITY.get(verdict, 0) > _SEVERITY.get(placement.verdict, 0):
        placement.verdict = verdict

    statuses: dict[str, int] = {}
    for listing_id in base.listings_of.get(row["entity_id"], []):
        listing = base.listings[listing_id]
        status = overlay.channel_status.get(listing_id, listing.status)
        statuses[status] = statuses.get(status, 0) + 1
    for status, count in statuses.items():
        placement.listings[status] = placement.listings.get(status, 0) + count

    placement.variants.append({
        "entity_id": row["entity_id"],
        "sku": row["sku"],
        "name": row["name"],
        "verdict": verdict,
        "listings": statuses,
    })

    for finding in summary["findings"]:
        placement.findings.append({**finding, "entity_id": row["entity_id"]})
        system = finding.get("system")
        if system and system not in placement.systems:
            placement.systems.append(system)


def _dispatched_products(base) -> set[str]:
    """Products something has actually been committed against.

    Read from ``committed_actions`` through the incidents that own them, which
    is the only durable record that a resolution went out.
    """
    found: set[str] = set()
    for row in db.query(
            "SELECT DISTINCT i.doc AS doc FROM committed_actions c"
            "  JOIN incidents i ON i.id = c.incident_id"
            " WHERE c.rolled_back = 0"):
        blob = row["doc"] or ""
        for product_id in base.products:
            if product_id in blob:
                found.add(product_id)
    return found


def _corrected_products(base) -> dict[str, dict]:
    """Products something has landed against that has not been resolved yet.

    Two sources, and both are needed.

    A **correction signal in force** is what the graph acts on: a value the
    system has read and understood as contradicting what the copy was written
    against. It is the right answer once a run has read the document.

    An **unresolved submission on the live lane** is the answer before that.
    A supplier who has just sent a late change has changed nothing the graph
    has looked at yet - the document version is recorded and the reading has
    not happened. Waiting for the run would mean the board said "on sale, all
    well" for as long as it took somebody to notice, which is precisely the
    interval this lane exists to make visible.

    A submission stops counting once the audit ledger shows a run has examined
    the event it arrived on. After that the signal, if there is one, speaks for
    itself - and if there is not one, the platform has read the document and
    found nothing to do, which is an answer rather than a silence.
    """
    from sc.graph import nodes as graph_nodes
    from sc.replay import tape

    found: dict[str, dict] = {}

    for signal in graph_nodes._signals_in_force(tape.sim_now()):
        for entity_id in signal.get("entities") or []:
            product_id = _product_of(base, entity_id)
            if product_id and product_id not in found:
                found[product_id] = {
                    "source": "signal",
                    "kind": signal.get("kind"),
                    "summary": signal.get("summary"),
                    "paths": signal.get("attribute_paths") or [],
                    "old_value": signal.get("old_value"),
                    "new_value": signal.get("new_value"),
                    "detected_at": signal.get("detected_at"),
                }

    examined = {r["entity_id"] for r in db.query(
        "SELECT DISTINCT entity_id FROM audit WHERE action = 'EXAMINE'")}

    for row in db.query("SELECT * FROM submissions ORDER BY submitted_at DESC"):
        event_ids = set(db.loads(row["event_ids"]))
        if event_ids & examined:
            continue
        for entity_id in db.loads(row["entity_ids"]):
            product_id = _product_of(base, entity_id)
            if not product_id or product_id in found:
                continue
            found[product_id] = {
                "source": "submission",
                "kind": row["kind"],
                "summary": (row["note"]
                            or f"{row['supplier_id']} sent a "
                               f"{row['kind'].replace('_', ' ').lower()}"),
                "paths": [],
                "doc_ref": row["doc_ref"],
                "supplier": row["supplier_id"],
                "system": row["system_id"],
                "submission_id": row["id"],
                "effective_from": row["effective_from"],
                "detected_at": row["submitted_at"],
                "awaiting_extraction": True,
            }
    return found


def _product_of(base, entity_id: str) -> str | None:
    if entity_id in base.products:
        return entity_id
    return base.product_of_variant.get(entity_id)


def _redactions_by_product(base, rows: list[dict]) -> dict[str, list[dict]]:
    """What is being held back downstream, grouped by the product it belongs to."""
    found: dict[str, list[dict]] = {}
    for row in rows:
        listing = base.listings.get(row["listing_id"])
        if listing is None:
            continue
        product_id = base.product_of_variant.get(listing.variant_id)
        if not product_id:
            continue
        found.setdefault(product_id, []).append({
            **row, "channel_id": listing.channel_id})
    return found
