"""Assembling one product as the estate has left it.

Nine checks need the same picture: what is in force, which document asserted it,
which system carried it, what lost a precedence contest, what imagery is held,
and which listings the product sits on. Built once and handed to all of them, so
that eleven checks make one pass over the fact store and cannot disagree about
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
from sc.state import store


def _instant(as_of: str | None) -> datetime:
    """The instant to read the record at.

    ``tape.sim_now`` rather than ``tape.state().sim_clock``: the latter is None
    until the replay has released its first event, so on a freshly reset
    database - which is the state a presenter opens on - every product read
    failed with an AttributeError. `sim_now` falls back to the start of the
    horizon, which is the right answer to "what time is it" when the recorded
    flight has not started playing yet.
    """
    if as_of:
        return datetime.fromisoformat(as_of)
    from sc.replay import tape

    return tape.sim_now()


def _by_entity(pairs) -> dict[str, list[tuple[str, object]]]:
    """Group a ``(entity, path) -> value`` mapping by entity.

    The baseline and the overlay are both keyed on the pair, which is the right
    shape for "what is this one attribute" and the wrong shape for "everything
    about this one product". Scanning the whole mapping per record is invisible
    at eight variants and is four hundred full scans at four hundred.
    """
    grouped: dict[str, list[tuple[str, object]]] = {}
    for (entity, path), value in pairs.items():
        grouped.setdefault(entity, []).append((path, value))
    return grouped


def build(entity_id: str, as_of: str | None = None, *,
          overlay=None, base=None, _defer_facts: bool = False,
          _baseline_index=None, _overlay_index=None,
          _media_index=None) -> Record | None:
    """One variant's record at an instant, or None if the catalog has no such
    variant.

    Returns None rather than raising: a reader asking about something that does
    not exist has made a typo, and a 404 is a better answer than a stack trace.

    ``overlay`` and ``base`` are injectable so that a caller building many
    records - the product list, the rollup - assembles the projection once and
    hands the same one to every record. Left out, this behaves exactly as it
    always did.
    """
    base = base if base is not None else baseline_mod.get()
    variant = base.variants.get(entity_id)
    if variant is None:
        return None

    product = base.products.get(variant.product_id)
    if product is None:
        return None

    valid = _instant(as_of)
    if overlay is None:
        overlay = overlay_mod.cached(valid, None)

    record = Record(
        entity_id=entity_id,
        product_id=product.id,
        category=product.category,
        regulated=product.regulated,
        media=_media_for(entity_id, valid, base, _media_index),
        listings=sorted(base.listings_of.get(entity_id, [])),
    )

    # Baseline first, then whatever the overlay has put in force. The order
    # matters: the overlay is corrections *on top of* the seeded record, and
    # reversing it would show a corrected product as uncorrected.
    if _baseline_index is None:
        _baseline_index = _by_entity(base.attr_values)
    if _overlay_index is None:
        _overlay_index = _by_entity(overlay.attr_values)

    for path, value in _baseline_index.get(entity_id, ()):
        record.values[path] = value
        source = base.attr_sources.get((entity_id, path))
        if source:
            record.sources[path] = f"{source.doc_id} {source.version}".strip()

    for path, state in _overlay_index.get(entity_id, ()):
        # The overlay holds a value *and everything needed to defend it* -
        # version, fact id, provenance, confidence - because every gate
        # downstream is a question about where the number came from. The
        # readiness checks ask about the number itself, so the value is
        # unwrapped here rather than at eleven call sites.
        record.values[path] = getattr(state, "value", state)
        version = getattr(state, "version", "")
        if version:
            existing = record.sources.get(path, "")
            document = existing.split(" ")[0] if existing else ""
            record.sources[path] = f"{document} {version}".strip()

    if not _defer_facts:
        _attach_provenance(record)
        _attach_superseded(record)
    return record


def _media_for(entity_id: str, valid, base, index=None) -> list:
    """The imagery held against a variant: seeded, plus whatever has arrived.

    The seed pack is what the estate delivered before the horizon opened.
    Anything delivered since is a fact like any other and has to be read here,
    or the readiness check cannot see it - which would mean a supplier could
    upload the missing ingredient panel and be told, correctly formatted and in
    detail, that no ingredient panel is held.

    A delivered image supersedes a seeded one in the same role. A replacement
    pack shot is a new assertion about one role, not a second pack shot.
    """
    from sc.contracts import MediaAsset

    seeded = list(base.media_by_entity.get(entity_id, []))
    rows = (index.get(entity_id, ()) if index is not None
            else _media_rows(valid, [entity_id]).get(entity_id, ()))
    if not rows:
        return seeded

    delivered = {}
    for attr, value in rows:
        if not isinstance(value, dict) or not value.get("uri"):
            continue
        delivered[attr] = MediaAsset(
            id=f"MED-{entity_id}-{attr}", entity_id=entity_id, role=attr,
            uri=str(value["uri"]), alt_text=str(value.get("alt_text") or ""),
            system=value.get("system"))

    kept = [a for a in seeded if str(a.role) not in delivered]
    return sorted(kept + list(delivered.values()),
                  key=lambda a: (str(a.role), a.id))


def _media_rows(valid, entity_ids=None) -> dict[str, list]:
    """Delivered imagery, in one query. Keyed by variant."""
    from sc.replay import ingest as ingest_mod

    found: dict[str, list] = {}
    for fact in store.get_many(ingest_mod.MEDIA_ENTITY, valid, None,
                               entity_ids=entity_ids):
        found.setdefault(fact.entity_id, []).append((fact.attr, fact.value))
    return found


def build_many(entity_ids: list[str], as_of: str | None = None,
               *, overlay=None, base=None) -> dict[str, Record]:
    """Many variants' records at one instant, in a fixed number of queries.

    ``build`` issues two queries per entity - one for provenance, one for the
    values that lost. Correct for one product and quadratic-looking for a list:
    four hundred variants was eight hundred round trips to answer one question.
    This asks both once, for the whole set, and deals the rows out.

    Same records, same content. The only thing that changes is how many times
    the fact store is asked.
    """
    base = base if base is not None else baseline_mod.get()
    valid = _instant(as_of)
    if overlay is None:
        overlay = overlay_mod.cached(valid, None)

    wanted = [e for e in entity_ids if e in base.variants]
    baseline_index = _by_entity(base.attr_values)
    overlay_index = _by_entity(overlay.attr_values)
    media_index = _media_rows(valid, wanted)

    records: dict[str, Record] = {}
    for entity_id in wanted:
        record = build(entity_id, as_of, overlay=overlay, base=base,
                       _defer_facts=True, _baseline_index=baseline_index,
                       _overlay_index=overlay_index,
                       _media_index=media_index)
        if record is not None:
            records[entity_id] = record
    if not records:
        return {}

    _attach_provenance_many(records)
    _attach_superseded_many(records)
    return records


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


def _chunks(items: list[str], size: int = 400):
    """SQLite caps a statement at 999 host parameters by default."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _attach_provenance_many(records: dict[str, Record]) -> None:
    """``_attach_provenance`` for a whole set, in one query per chunk.

    Same ordering as the single-record form - most recent fact per attribute
    wins - so a record built here and a record built alone carry the same
    carriers and the same defects.
    """
    ids = list(records)
    for chunk in _chunks(ids):
        holes = ",".join("?" * len(chunk))
        rows = db.query(
            f"SELECT entity_id, attr, provenance FROM facts"
            f" WHERE entity_id IN ({holes})"
            f" ORDER BY recorded_at DESC, id DESC", tuple(chunk))
        for row in rows:
            record = records.get(row["entity_id"])
            if record is None or row["attr"] in record.systems:
                continue
            try:
                provenance = db.loads(row["provenance"])
            except Exception:  # noqa: BLE001 - a bad row is not a bad record
                continue
            record.systems[row["attr"]] = provenance.get("system")
            defects = provenance.get("defects") or ()
            if defects:
                record.defects[row["attr"]] = tuple(defects)


def _attach_superseded_many(records: dict[str, Record]) -> None:
    """``_attach_superseded`` for a whole set, in one query per chunk."""
    ids = list(records)
    for chunk in _chunks(ids):
        holes = ",".join("?" * len(chunk))
        rows = db.query(
            f"SELECT entity_id, attr, value, provenance FROM facts"
            f" WHERE entity_id IN ({holes}) AND supersedes_id IS NOT NULL"
            f" ORDER BY recorded_at, id", tuple(chunk))
        for row in rows:
            record = records.get(row["entity_id"])
            if record is None:
                continue
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
