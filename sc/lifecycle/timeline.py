"""One product's journey, as a list of things that happened.

Joined from five tables, each of which owns a different part of the story: what
arrived and through which system, what the platform recorded, what a reviewer
decided, what was committed, and what is still owed. None of it is a second
account - every row here is read from the table that already had it.

Ordered by when it happened on the simulated clock, except for arrivals, which
carry both clocks because "an hour ago" is the useful question about a delivery
and "on which simulated day" is the useful question about everything else.
"""

from __future__ import annotations

from sc import db


def build(product_id: str, limit: int = 120) -> dict:
    """Everything that has happened to one product, newest last."""
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    product = base.products.get(product_id)
    if product is None:
        return {"error": f"no such product: {product_id}"}

    variants = base.variants_of.get(product_id, [])
    listings = [l for v in variants for l in base.listings_of.get(v, [])]
    ids = {product_id, *variants, *listings}

    events = (_submissions(product_id, variants) + _arrivals(ids)
              + _decisions(ids) + _publications(ids) + _obligations(listings))
    events.sort(key=lambda e: (e.get("at") or "", e.get("kind") or ""))

    return {
        "product": product.model_dump(mode="json"),
        "variants": [base.variants[v].model_dump(mode="json") for v in variants],
        "listings": sorted(listings),
        "events": events[-limit:],
    }


def _entry(kind: str, at: str, title: str, detail: str = "", **extra) -> dict:
    return {"kind": kind, "at": at, "title": title, "detail": detail, **extra}


def _submissions(product_id: str, variants: list[str]) -> list[dict]:
    """What a supplier sent, from the supplier's own side of the ledger."""
    wanted = {product_id, *variants}
    out = []
    for row in db.query("SELECT * FROM submissions ORDER BY submitted_at"):
        if not (set(db.loads(row["entity_ids"])) & wanted):
            continue
        out.append(_entry(
            "submission", row["submitted_at"],
            f"{row['supplier_id']} sent a "
            f"{row['kind'].replace('_', ' ').lower()}",
            row["note"] or row["doc_ref"],
            system=row["system_id"], submission_id=row["id"],
            doc_ref=row["doc_ref"], wall_at=row["wall_at"]))
    return out


def _arrivals(ids: set[str]) -> list[dict]:
    """What landed, through which system, in which batch."""
    out = []
    for row in db.query(
            "SELECT a.system_id, a.batch_id, a.arrived_at, a.defects,"
            "       e.ts, e.type, e.payload, e.lane"
            "  FROM arrivals a JOIN events e ON e.id = a.event_id"
            " ORDER BY e.seq DESC LIMIT 4000"):
        payload = db.loads(row["payload"])
        named = {str(v) for v in (payload.get("entities") or [])}
        named.add(str(payload.get("product") or ""))
        named.add(str(payload.get("entity_id") or ""))
        if not (named & ids):
            continue
        defects = db.loads(row["defects"])
        out.append(_entry(
            "arrival", row["ts"],
            f"{row['system_id']} delivered a "
            f"{row['type'].replace('_', ' ').lower()}",
            ", ".join(defects) if defects else "",
            system=row["system_id"], batch=row["batch_id"],
            arrived_at=row["arrived_at"], lane=row["lane"],
            defects=defects))
    return out


def _decisions(ids: set[str]) -> list[dict]:
    """Approvals and releases - the two moments a person decided something."""
    out = []
    for row in db.query(
            "SELECT a.*, i.doc AS incident_doc FROM approvals a"
            "  JOIN incidents i ON i.id = a.incident_id"
            " ORDER BY a.decided_at"):
        if not _mentions(row["incident_doc"], ids):
            continue
        out.append(_entry(
            "approval", row["decided_at"],
            f"{row['actor']} {row['decision'].lower()}d the resolution",
            row["comment"] or "", incident_id=row["incident_id"],
            decision=row["decision"]))

    for row in db.query(
            "SELECT r.*, i.doc AS incident_doc FROM releases r"
            "  JOIN incidents i ON i.id = r.incident_id"
            " ORDER BY r.decided_at"):
        if not _mentions(row["incident_doc"], ids):
            continue
        out.append(_entry(
            "release", row["decided_at"],
            f"{row['actor']} {row['decision'].lower()}d the release",
            row["comment"] or "", incident_id=row["incident_id"],
            decision=row["decision"]))
    return out


def _mentions(blob: str | None, ids: set[str]) -> bool:
    text = blob or ""
    return any(identifier and identifier in text for identifier in ids)


def _publications(ids: set[str]) -> list[dict]:
    """Everything the ledger recorded against these listings.

    The ledger is append-only, so this is the part of the timeline that cannot
    have been rewritten after the fact - which is exactly why the audit view
    reads it and why this does too.
    """
    out = []
    for row in db.query("SELECT * FROM audit ORDER BY ts DESC LIMIT 600"):
        if row["entity_id"] not in ids:
            continue
        detail = db.loads(row["detail"])
        out.append(_entry(
            "ledger", row["ts"],
            f"{row['action']} on {row['entity_id']}",
            detail.get("reason") or detail.get("detail")
            or detail.get("attribute_path") or "",
            actor=row["actor"], action=row["action"], entity=row["entity_id"],
            detail_json=detail))
    return out


def _obligations(listings: list[str]) -> list[dict]:
    """Work still owed to the world, and whether it has been done."""
    if not listings:
        return []
    placeholders = ",".join("?" * len(listings))
    out = []
    for row in db.query(
            f"SELECT * FROM obligations WHERE listing_id IN ({placeholders})"
            f" ORDER BY opened_at", tuple(listings)):
        out.append(_entry(
            "obligation", row["opened_at"],
            f"{row['kind'].lower()} owed on {row['channel_id']}",
            db.loads(row["detail"]).get("reason", ""),
            obligation_id=row["id"], status=row["status"],
            due_by=row["due_by"], discharged_by=row["discharged_by"],
            discharged_at=row["discharged_at"]))
    return out
