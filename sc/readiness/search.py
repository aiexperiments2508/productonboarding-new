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
NAV-AP300-MAX" would be a slower way to get a worse answer.
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


def _matches(row: dict, suppliers, categories) -> bool:
    """Does this row survive the facet filters?

    Categories match on prefix rather than equality, because the taxonomy is a
    path: somebody filtering on ``home.`` means the whole branch, and asking
    them to enumerate its leaves would make the filter useless on the one
    question it exists for.
    """
    if suppliers and row["supplier"] not in suppliers:
        return False
    if categories and not any(row["category"].startswith(prefix)
                              for prefix in categories):
        return False
    return True


def find(query: str, limit: int = 20, *, offset: int = 0,
         suppliers: list[str] | None = None,
         categories: list[str] | None = None,
         entity_ids: set[str] | None = None,
         count: bool = False) -> list[dict] | tuple[list[dict], int]:
    """Products matching a SKU, an identifier or words from a name.

    An empty query lists everything. The product view opens on this, and a page
    that stays empty until somebody types looks broken rather than ready.

    A query nothing matches returns an empty list rather than raising: a typo is
    a normal thing for a person to do and a 500 is a rude way to say so.

    Facets are applied *before* banding, so filtering cannot change how the
    remaining rows rank against each other - a supplier filter narrows the
    list, it does not reorder it.

    ``count=True`` also returns how many matched before the slice, which is
    what lets a page say "10 of 150" rather than implying it is showing
    everything.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    needle = (query or "").strip().lower()
    supplier_set = set(suppliers or ())
    category_list = list(categories or ())

    scored: list[tuple[int, str, dict]] = []
    for row in _rows(base):
        if entity_ids is not None and row["entity_id"] not in entity_ids:
            continue
        if not _matches(row, supplier_set, category_list):
            continue
        band = _band(row, needle)
        if band is None:
            continue
        # Entity id breaks ties inside a band, so two runs of the same query
        # return the same order.
        scored.append((band, row["entity_id"], row))

    scored.sort(key=lambda item: (item[0], item[1]))
    page = [row for _, _, row in scored[offset:offset + limit]]
    return (page, len(scored)) if count else page


def rank_products(query: str = "", *, suppliers: list[str] | None = None,
                  categories: list[str] | None = None,
                  limit: int = 10, offset: int = 0) -> tuple[list[str], int]:
    """The same ranking, answered in products rather than variants.

    The map draws products; the product list draws variants. Both have to agree
    about what "AER" matches, so they share one ranking rather than growing a
    second one that would disagree on the first ambiguous query.
    """
    rows = find(query, limit=10_000, suppliers=suppliers, categories=categories)
    ordered: list[str] = []
    for row in rows:
        if row["product_id"] not in ordered:
            ordered.append(row["product_id"])
    return ordered[offset:offset + limit], len(ordered)


def with_readiness(query: str, limit: int = 20, *,
                   use_model: bool = False, as_of: str | None = None,
                   offset: int = 0, rows: list[dict] | None = None) -> list[dict]:
    """Search results, each carrying its verdict.

    The list view's whole purpose is to show which products are holding a launch
    up, so a result without a verdict is a row nobody can act on.

    Model-backed checks are off by default here: a list of twenty products would
    otherwise make sixty model calls to render a page nobody has clicked into.
    The detail view asks for the full assessment.

    Every row is assessed against **one** projection of the fact store and one
    batched read of the provenance chain. Before, each row rebuilt the overlay
    from scratch and issued two more queries of its own, then serialised a full
    merged record so that three scalars could be taken off it and the rest
    dropped. At eight variants that was invisible; at four hundred it was the
    page.
    """
    import sc.readiness as readiness
    from sc.readiness import record as record_mod
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod

    if rows is None:
        rows = find(query, limit, offset=offset)
    if not rows:
        return []

    base = baseline_mod.get()
    overlay = overlay_mod.cached(record_mod._instant(as_of), None)
    records = record_mod.build_many([row["entity_id"] for row in rows], as_of,
                                    overlay=overlay, base=base)

    for row in rows:
        record = records.get(row["entity_id"])
        if record is None:
            continue
        summary = readiness.assess(row["entity_id"], as_of, use_model=use_model,
                                   include_record=False, record=record,
                                   base=base)
        if summary is None:
            continue
        row["verdict"] = summary["verdict"]
        row["findings"] = len(summary["findings"])
        row["checks_complete"] = summary["checks_complete"]
    return rows


def resolve(key: str, base=None) -> dict | None:
    """The variant a caller means, whatever they called it by.

    A SKU, an internal variant id and a product id are three names for
    overlapping things, and every one of them gets typed by somebody: a
    merchant reads the SKU off a purchase order, the product screen holds an
    entity id, and a report names the product. `_band` above already treats all
    three as an exact match for the same reason.

    A product resolves to its base variant. That is the same widening
    `Baseline.variants_in_scope` performs for `ScopeLevel.BASE`, and it is the
    reading a caller means: "the graph around PRD-01" is the graph around the
    thing PRD-01 is sold as.

    Returns what was asked for *and* what it turned out to be, so a caller
    never has to guess which of the three it was holding:

        {"key": "NAV-AP300-MAX", "entity_id": "VAR-01B",
         "sku": "NAV-AP300-MAX", "product_id": "PRD-01"}

    None when nothing matches, which is a 404 rather than an empty graph - a
    graph with no nodes and a typo'd SKU look identical on a screen.
    """
    from sc.state import baseline as baseline_mod

    base = base or baseline_mod.get()
    needle = (key or "").strip()
    if not needle:
        return None

    def _answer(entity_id: str) -> dict:
        variant = base.variants[entity_id]
        return {"key": needle, "entity_id": entity_id,
                "sku": variant.sku or None,
                "product_id": base.product_of_variant.get(entity_id)}

    if needle in base.variants:
        return _answer(needle)

    lowered = needle.lower()
    for entity_id in sorted(base.variants):
        if (base.variants[entity_id].sku or "").lower() == lowered:
            return _answer(entity_id)

    product_id = needle if needle in base.products else None
    if product_id is None:
        for candidate in base.products:
            if candidate.lower() == lowered:
                product_id = candidate
                break
    if product_id is not None:
        variants = base.variants_of.get(product_id, [])
        # The base variant, or the first if none is marked - sorted, so two
        # callers asking the same question get the same answer.
        for entity_id in variants:
            if base.variants[entity_id].is_base:
                return _answer(entity_id)
        if variants:
            return _answer(variants[0])

    return None
