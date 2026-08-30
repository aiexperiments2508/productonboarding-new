"""Assembling one product as the estate has left it.

Nine checks need the same picture: what is in force, which document asserted it,
which system carried it, what lost a precedence contest, what imagery is held,
and which listings the product sits on. Built once and handed to all of them, so
that nine checks make one pass over the fact store and cannot disagree about
what is currently true.

The superseded half is the part that would be easy to leave out and should not
be. A disagreement that precedence settled is *settled*, not absent: the record
knows which value won and which it beat, and a reviewer asking "did anything
else say otherwise" is asking the question an estate of ten systems exists to
answer. Dropping the loser would make the record look like everybody agreed.
"""

from __future__ import annotations

from datetime import datetime

from sc import db
from sc.readiness.checks import Record
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod


def _instant(as_of: str | None) -> datetime:
    if as_of:
        return datetime.fromisoformat(as_of)
    from sc.replay import tape

    return tape.state().sim_clock


def build(entity_id: str, as_of: str | None = None) -> Record | None:
    """One variant's record at an instant, or None if the catalog has no such
    variant.

    Returns None rather than raising: a reader asking about something that does
    not exist has made a typo, and a 404 is a better answer than a stack trace.
    """
    base = baseline_mod.get()
    variant = base.variants.get(entity_id)
    if variant is None:
        return None

    product = base.products.get(variant.product_id)
    if product is None:
        return None

    valid = _instant(as_of)
    overlay = overlay_mod.build(valid, None)

    record = Record(
        entity_id=entity_id,
        product_id=product.id,
        category=product.category,
        regulated=product.regulated,
        media=list(base.media_by_entity.get(entity_id, [])),
        listings=sorted(base.listings_of.get(entity_id, [])),
    )

    # Baseline first, then whatever the overlay has put in force. The order
    # matters: the overlay is corrections *on top of* the seeded record, and
    # reversing it would show a corrected product as uncorrected.
    for (entity, path), value in base.attr_values.items():
        if entity != entity_id:
            continue
        record.values[path] = value
        source = base.attr_sources.get((entity, path))
        if source:
            record.sources[path] = f"{source.doc_id} {source.version}".strip()

    for (entity, path), state in overlay.attr_values.items():
        if entity != entity_id:
            continue
        # The overlay holds a value *and everything needed to defend it* -
        # version, fact id, provenance, confidence - because every gate
        # downstream is a question about where the number came from. The
        # readiness checks ask about the number itself, so the value is
        # unwrapped here rather than at nine call sites.
        record.values[path] = getattr(state, "value", state)
        version = getattr(state, "version", "")
        if version:
            existing = record.sources.get(path, "")
            document = existing.split(" ")[0] if existing else ""
            record.sources[path] = f"{document} {version}".strip()

    _attach_provenance(record)
    _attach_superseded(record)
    return record


def _attach_provenance(record: Record) -> None:
    """Which system carried each value, and what was wrong with the delivery.

    Read from the most recent fact per attribute rather than from the baseline,
    because the baseline is the seeded starting point and says nothing about who
    delivered a correction to it.

    A value with no recorded arrival gets ``None`` rather than a guess. "We do
    not know which system sent this" is a true and useful thing to say; naming
    the likeliest one would be a fabrication in a field a reviewer will use to
    decide who to email.
    """
    rows = db.query(
        "SELECT attr, provenance, recorded_at FROM facts"
        " WHERE entity_id = ? ORDER BY recorded_at DESC, id DESC",
        (record.entity_id,))
    for row in rows:
        path = row["attr"]
        if path in record.systems:
            continue
        try:
            provenance = db.loads(row["provenance"])
        except Exception:  # noqa: BLE001 - a bad row is not a bad record
            continue
        record.systems[path] = provenance.get("system")
        defects = provenance.get("defects") or ()
        if defects:
            record.defects[path] = tuple(defects)


def _attach_superseded(record: Record) -> None:
    """The values that lost.

    A fact naming the one it replaces is a chain, and the head of the chain is
    what is in force. Everything behind the head was believed once and is worth
    showing, because "two systems disagreed and this is why one won" is the
    thing the estate makes visible.
    """
    rows = db.query(
        "SELECT attr, value, provenance FROM facts"
        " WHERE entity_id = ? AND supersedes_id IS NOT NULL"
        " ORDER BY recorded_at, id",
        (record.entity_id,))
    for row in rows:
        try:
            provenance = db.loads(row["provenance"])
            value = db.loads(row["value"])
        except Exception:  # noqa: BLE001
            continue
        record.superseded.setdefault(row["attr"], []).append({
            "value": value,
            "system": provenance.get("system"),
            "source": provenance.get("source_id"),
        })


def as_dict(record: Record, base) -> dict:
    """The record as the API and the product view render it."""
    variant = base.variants[record.entity_id]
    product = base.products[record.product_id]
    return {
        "entity_id": record.entity_id,
        "sku": variant.sku,
        "name": variant.name,
        "product": {"id": product.id, "name": product.name,
                    "category": product.category, "supplier": product.supplier,
                    "regulated": product.regulated},
        "is_base": variant.is_base,
        "attributes": [
            {
                "path": path,
                "label": (base.attr_defs[path].label
                          if path in base.attr_defs else path),
                "value": value,
                "unit": (base.attr_defs[path].unit
                         if path in base.attr_defs else None),
                "source": record.sources.get(path),
                # Explicit rather than omitted: "we do not know which system
                # sent this" is an answer, and a missing key reads as an
                # oversight.
                "system": record.systems.get(path),
                "defects": list(record.defects.get(path, ())),
                "superseded": record.superseded.get(path, []),
            }
            for path, value in sorted(record.values.items())
        ],
        "media": [
            {"id": a.id, "role": str(a.role), "uri": a.uri,
             "alt_text": a.alt_text, "system": a.system}
            for a in record.media
        ],
        "listings": record.listings,
    }
