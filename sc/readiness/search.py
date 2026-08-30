"""Finding a product the way everybody outside this system names it.

The catalogue identifies things as `VAR-01B`. That is an internal key and it
stays one - renaming keys to look friendlier makes an audit trail harder to read
for a cosmetic gain. But a buyer, a supplier and a marketplace all say "SKU" and
all mean what is printed on a purchase order, so a product surface that cannot
be searched by it is a product surface built for this system rather than for the
people who use it.

Both work, and an exact identifier match always wins. Somebody typing a SKU
knows exactly what they want; somebody typing "purifier" is browsing, and
ranking the second above the first would make the precise query the unreliable
one.

Deliberately not the retrieval index. This is an exact and prefix match over a
few dozen rows, and fusing BM25 with embeddings to answer "which variant is
AER-300-MAX" would be a slower way to get a worse answer.
"""

from __future__ import annotations

#: Ranking bands, lowest first. Ordering by band before score means a name can
#: never outrank an identifier however many times the word appears.
EXACT_ID = 0
EXACT_SKU = 0
PREFIX = 1
NAME = 2


def _rows(base) -> list[dict]:
    rows = []
    for entity_id in sorted(base.variants):
        variant = base.variants[entity_id]
        product = base.products.get(variant.product_id)
        if product is None:
            continue
        rows.append({
            "entity_id": entity_id,
            "sku": variant.sku,
            "name": variant.name,
            "product_id": product.id,
            "product_name": product.name,
            "category": product.category,
            "supplier": product.supplier,
            "regulated": product.regulated,
            "is_base": variant.is_base,
        })
    return rows


def _band(row: dict, needle: str) -> int | None:
    """Which ranking band this row falls in for this query, or None to drop it."""
    if not needle:
        return NAME
    sku = (row["sku"] or "").lower()
    entity = row["entity_id"].lower()
    if needle in (sku, entity, row["product_id"].lower()):
        return EXACT_SKU
    if sku.startswith(needle) or entity.startswith(needle):
        return PREFIX
    haystack = f"{row['name']} {row['product_name']} {row['category']}".lower()
    if needle in haystack:
        return NAME
    return None


def find(query: str, limit: int = 20) -> list[dict]:
    """Products matching a SKU, an identifier or words from a name.

    An empty query lists everything. The product view opens on this, and a page
    that stays empty until somebody types looks broken rather than ready.

    A query nothing matches returns an empty list rather than raising: a typo is
    a normal thing for a person to do and a 500 is a rude way to say so.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    needle = (query or "").strip().lower()

    scored: list[tuple[int, str, dict]] = []
    for row in _rows(base):
        band = _band(row, needle)
        if band is None:
            continue
        # Entity id breaks ties inside a band, so two runs of the same query
        # return the same order.
        scored.append((band, row["entity_id"], row))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in scored[:limit]]


def with_readiness(query: str, limit: int = 20, *,
                   use_model: bool = False) -> list[dict]:
    """Search results, each carrying its verdict.

    The list view's whole purpose is to show which products are holding a launch
    up, so a result without a verdict is a row nobody can act on.

    Model-backed checks are off by default here: a list of twenty products would
    otherwise make sixty model calls to render a page nobody has clicked into.
    The detail view asks for the full assessment.
    """
    import sc.readiness as readiness

    rows = find(query, limit)
    for row in rows:
        summary = readiness.assess(row["entity_id"], use_model=use_model)
        if summary is None:
            continue
        row["verdict"] = summary["verdict"]
        row["findings"] = len(summary["findings"])
        row["checks_complete"] = summary["checks_complete"]
    return rows
