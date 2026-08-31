"""Lines a supplier has proposed, and the decision that lets one in.

A supplier can send a new product through the vendor intake. It arrives as a
document like any other submission, and it stops there: the catalog is a
generated pack, and ingestion drops any entity that pack does not name, so a
proposal is *received* and is not a product.

Making it one is a decision with a person's name on it. That is not
bureaucracy for its own sake - accepting a line means the retailer takes on
responsibility for what it says about something it has never sold, and there
is no rule that can take that on for somebody. So it is a reviewer's action,
recorded in the ledger beside every other decision.

**What acceptance actually does.** It writes the product and its variant into
``data/catalog.live.json`` and clears the cached baseline. From the next read
the line is an ordinary product: the checks assess it, the board places it,
the estate can carry it. It arrives with nothing held against it, so it lands
in the supplier's lap immediately with a list of what is missing - which is
correct and is the whole point. A new line is not ready because somebody
accepted it; it is ready when it passes the checks.
"""

from __future__ import annotations

from sc import db

#: Where accepted lines are numbered from. Deliberately outside the generated
#: pack's range - the seed pack numbers products PRD-01..PRD-244, and a line
#: accepted here should be recognisable as one at a glance.
ACCEPTED_PREFIX = "PRD-A"
VARIANT_PREFIX = "VAR-A"


def pending() -> list[dict]:
    """Proposals nobody has decided on yet."""
    accepted = _accepted_submissions()
    out = []
    for row in db.query(
            "SELECT * FROM submissions WHERE kind = 'PRODUCT_DRAFT'"
            " ORDER BY submitted_at DESC"):
        if row["id"] in accepted:
            continue
        payload = _payload_of(row)
        out.append({
            "submission_id": row["id"],
            "supplier": row["supplier_id"],
            "system": row["system_id"],
            "submitted_at": row["submitted_at"],
            "draft_id": (db.loads(row["entity_ids"]) or [""])[0],
            "name": payload.get("name", ""),
            "category": payload.get("category", ""),
            "attributes": payload.get("attributes") or {},
            "note": row["note"],
        })
    return out


def _accepted_submissions() -> set[str]:
    """Proposals already let in, read from the ledger rather than a column."""
    return {db.loads(r["detail"]).get("submission_id")
            for r in db.query("SELECT detail FROM audit"
                              " WHERE action = 'ACCEPT_LINE'")}


def _payload_of(row) -> dict:
    """What the supplier actually proposed, from the event they sent."""
    for event_id in db.loads(row["event_ids"]):
        event = db.one("SELECT payload FROM events WHERE id = ?", (event_id,))
        if event is not None:
            return db.loads(event["payload"])
    return {}


def accept(submission_id: str, *, actor: str, sku: str = "",
           name: str = "", category: str = "") -> dict:
    """Let a proposed line into the catalog. A reviewer's decision.

    Refuses a proposal it has already accepted rather than adding a second
    copy: the ledger is the record of what was decided, and asking it is
    cheaper than a column that could disagree with it.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import planning

    row = db.one("SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if row is None:
        return {"error": f"no submission {submission_id}", "accepted": False}
    if row["kind"] != "PRODUCT_DRAFT":
        return {"error": f"{submission_id} is not a proposed line",
                "accepted": False}
    if submission_id in _accepted_submissions():
        return {"error": f"{submission_id} has already been accepted",
                "accepted": False}

    payload = _payload_of(row)
    product_name = name or payload.get("name", "")
    product_category = category or payload.get("category", "")
    if not (product_name and product_category):
        return {"error": "a line needs a name and a category",
                "accepted": False}

    held = baseline_mod.accepted_lines()
    ordinal = len(held.get("products", [])) + 1
    product_id = f"{ACCEPTED_PREFIX}{ordinal:03d}"
    variant_id = f"{VARIANT_PREFIX}{ordinal:03d}"
    variant_sku = sku or f"{row['supplier_id']}-{ordinal:03d}"

    payload_out = {
        "products": list(held.get("products", [])) + [{
            "id": product_id, "name": product_name,
            "category": product_category, "supplier": row["supplier_id"],
            "regulated": baseline_mod.regulated_category(product_category),
        }],
        "variants": list(held.get("variants", [])) + [{
            "id": variant_id, "product_id": product_id,
            "name": product_name, "is_base": True, "sku": variant_sku,
        }],
        # A node per tier, so the line appears on the map as well as in the
        # lists. `group` is the category family, which is what the map draws
        # products by - the same value the generator writes.
        "nodes": list(held.get("nodes", [])) + [
            {"id": product_id, "kind": "PRODUCT", "name": product_name,
             "group": product_category.split(".")[0],
             "regulated": baseline_mod.regulated_category(product_category)},
            {"id": variant_id, "kind": "VARIANT", "name": product_name,
             "group": product_category.split(".")[0]},
        ],
    }

    baseline_mod.write_accepted(payload_out)
    # The cached baseline is process-wide, and every read after this one has to
    # see the new line. The same call `run.py` makes after a reseed.
    baseline_mod.get.cache_clear()

    planning.audit(actor, "ACCEPT_LINE", "product", product_id, {
        "submission_id": submission_id, "supplier": row["supplier_id"],
        "system": row["system_id"], "name": product_name,
        "category": product_category, "sku": variant_sku,
        "draft_id": (db.loads(row["entity_ids"]) or [""])[0],
    })

    return {
        "accepted": True,
        "product_id": product_id,
        "variant_id": variant_id,
        "sku": variant_sku,
        "supplier": row["supplier_id"],
        "note": ("the line is in the catalog and is assessed like any other. "
                 "It has no specification and no imagery yet, so it will come "
                 "back as not fit to launch until the supplier sends them"),
    }
