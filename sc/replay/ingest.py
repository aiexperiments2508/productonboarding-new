"""Turn released events into bitemporal facts and correction signals.

Structured events land here and become RECORDED facts - an observation from a
supplier portal or a channel gateway, taken at face value.

Unstructured events are deliberately *not* interpreted here. A spec sheet's
arrival is a structured fact and is recorded; what the document says is left to
the graph, which reads the body with a model and writes it back through
``record_attribute`` as INFERRED with a confidence. Covering emails are left
alone entirely. That split is the whole point of the provenance taxonomy: a
reviewer can see at a glance which half of the picture was observed and which
was concluded, and the fail-closed safety gate only applies to the latter.

Attribute facts pin the source document version they were asserted at, so a
later revision of that document makes the copy built on the old one stale by
construction rather than by convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sc import db
from sc.contracts import (
    CorrectionKind,
    CorrectionSignal,
    Event,
    EventType,
    Provenance,
    ProvenanceKind,
    SourceRef,
)
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod
from sc.state import store
from sc.state.baseline import precedence

CONSUMER = "ingest"

#: One watermark per lane, and the reason is worth writing down.
#:
#: This consumer drops anything at or behind its cursor, which is what makes
#: redelivery free. With a single watermark across both lanes, one submission -
#: numbered from the live band, a hundred thousand above the recording - would
#: set that watermark past every remaining tape event. The recording would then
#: be dropped as already-seen for the rest of the process's life, and every
#: batch would report success while writing nothing.
#:
#: The lanes are independent sequences, so they get independent cursors.
CONSUMERS = {"TAPE": CONSUMER, "LIVE": "ingest@live"}

# A numeric attribute has to move by more than this to be a correction rather
# than noise. Everything a feed says still lands in the store; the threshold
# only decides whether a reviewer is told about it.
MATERIAL_PCT = 5.0

# The gateway's verdict on a feed, kept under its own attr so it cannot be
# mistaken for the listing's own publication state.
ATTR_FEED_STATUS = "feed_status"

# What an acknowledgement means for the listing the feed carried.
LISTING_STATUS = {"ACCEPTED": "LIVE", "REJECTED": "REJECTED"}

# The source-precedence policy, named in every conflict it settles.
PRECEDENCE_POLICY = "POL-002"


def cursor(lane: str = "TAPE") -> int:
    """How far this consumer has read the given lane."""
    row = db.one("SELECT last_seq FROM event_cursors WHERE consumer = ?",
                 (CONSUMERS.get(lane, CONSUMER),))
    return row["last_seq"] if row else 0


def _advance(seq: int, conn, lane: str = "TAPE") -> None:
    conn.execute(
        "INSERT INTO event_cursors (consumer, last_seq, updated_at)"
        " VALUES (?,?,?) ON CONFLICT(consumer) DO UPDATE SET"
        " last_seq = excluded.last_seq, updated_at = excluded.updated_at",
        (CONSUMERS.get(lane, CONSUMER), seq, datetime.now().isoformat()))


def ingest(events: list[Event]) -> list[CorrectionSignal]:
    """Process a batch. Returns the corrections worth investigating.

    The cursor advances inside the same transaction as the facts, so an
    interrupted batch is redelivered rather than silently skipped. Events at or
    behind the cursor are dropped first, so that redelivery writes nothing a
    second time.

    A batch may span both lanes, and each lane is filtered and advanced against
    its own watermark - see ``CONSUMERS``. The handlers do not know or care
    which lane an event came from: a submission is judged by the same rules as
    a taped event, which is the whole point of routing it through here rather
    than letting a vendor write a value directly.
    """
    by_lane: dict[str, list[Event]] = {}
    for event in events:
        by_lane.setdefault(getattr(event, "lane", "TAPE") or "TAPE",
                           []).append(event)

    signals: list[CorrectionSignal] = []
    for lane, batch in sorted(by_lane.items()):
        last = cursor(lane)
        fresh = [e for e in sorted(batch, key=lambda e: e.seq) if e.seq > last]
        if not fresh:
            continue
        with db.transaction() as conn:
            for event in fresh:
                signals.extend(_handle(event, conn))
            _advance(fresh[-1].seq, conn, lane)

    return signals


def pending(limit: int = 500) -> list[Event]:
    """Released events this consumer has not processed yet, both lanes."""
    from sc.replay import tape

    rows = db.query(
        "SELECT * FROM events WHERE lane = ? AND seq > ? AND seq <= ?"
        " ORDER BY seq LIMIT ?",
        (tape.LANE_TAPE, cursor(tape.LANE_TAPE), tape.cursor(), limit))
    live = db.query(
        "SELECT * FROM events WHERE lane = ? AND seq > ? ORDER BY seq LIMIT ?",
        (tape.LANE_LIVE, cursor(tape.LANE_LIVE), limit))
    return [tape._row_to_event(r) for r in list(rows) + list(live)]


def drain() -> list[CorrectionSignal]:
    return ingest(pending())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


Handler = Callable[..., list[CorrectionSignal]]


def _handle(event: Event, conn) -> list[CorrectionSignal]:
    handler = HANDLERS.get(event.type)
    return handler(event, conn) if handler is not None else []


def _carrier(event: Event) -> tuple[str | None, tuple[str, ...]]:
    """Which system delivered this event, and what was wrong with the delivery.

    Read once per event rather than once per row: a feed carrying eight
    attributes arrived once, and asking the arrivals table eight times would
    make the answer no better and the ingest eight times chattier.

    Absent when nothing has recorded an arrival - a tape loaded directly by a
    test, or a database seeded before the estate existed. The fact is still
    written; it simply does not name a carrier, which is honest.
    """
    try:
        from sc.estate import arrivals

        return arrivals.system_for(event.id), tuple(arrivals.defects_for(event.id))
    except Exception:  # noqa: BLE001 - a missing carrier is not a missing fact
        return None, ()


def _attribute_rows(event: Event, conn) -> list[CorrectionSignal]:
    """A supplier feed: one attribute row, or a batch of them."""
    rows = _raw_rows(event.payload)
    carrier = _carrier(event)
    signals: list[CorrectionSignal] = []
    for index, row in enumerate(rows, start=1):
        signal_id = f"SIG-{event.id}" if len(rows) == 1 else f"SIG-{event.id}-{index}"
        signal = _attribute_row(event, row, signal_id, conn, carrier)
        if signal is not None:
            signals.append(signal)
    return signals


def _catalog_update(event: Event, conn) -> list[CorrectionSignal]:
    """An internal edit.

    The edited attribute is a row like any other; the PIM also retires document
    versions on its own, which is a fact about the document rather than a value.
    An imaging system may also deliver an image, which is neither.
    """
    _doc_state(event, conn)
    _media_row(event, conn)
    return _attribute_rows(event, conn)


#: Delivered imagery lives under its own entity type rather than as an
#: attribute path. Two reasons, and the second is the load-bearing one: an
#: image is not an assertion about a value, and every attribute path that
#: enters the overlay is checked against the declared attribute set - so
#: `media.HERO` would be reported as an attribute nobody defined.
MEDIA_ENTITY = "media"


def _media_row(event: Event, conn) -> None:
    """Record an image a system delivered, by role.

    Roles are the closed set in ``MediaRole``: the requirement is per role, so
    an image filed under a name nobody checks is indistinguishable from an
    image that never arrived. One fact per (variant, role), superseded like any
    other - a replacement pack shot is a new assertion about the same role, not
    a second panel.
    """
    media = event.payload.get("media")
    if not isinstance(media, dict):
        return
    entity_id = str(media.get("entity_id") or event.payload.get("entity_id") or "")
    role = str(media.get("role") or "").upper()
    uri = str(media.get("uri") or "")
    if not (entity_id and role and uri):
        return

    store.record(
        MEDIA_ENTITY, entity_id, role,
        {"uri": uri, "alt_text": media.get("alt_text", ""),
         "system": media.get("system"), "sha256": media.get("sha256", "")},
        valid_from=event.ts, recorded_at=event.ts,
        provenance=Provenance(kind=ProvenanceKind.RECORDED,
                              source_id=event.id,
                              system=media.get("system"), note=event.id),
        conn=conn)


def _spec_doc(event: Event, conn) -> list[CorrectionSignal]:
    """A document version arrived. Its content is somebody else's problem.

    The arrival is structured - we know which document, which version, from
    which supplier - so it is RECORDED. The body is prose, so the graph's
    extraction node reads it and writes back through ``record_attribute``.
    """
    _doc_state(event, conn)
    return []


def _channel_status(event: Event, conn) -> list[CorrectionSignal]:
    """A feed acknowledgement or a rejection from a channel gateway."""
    payload = event.payload
    channel_id = str(payload.get("channel_id", ""))
    listing_id = str(payload.get("listing_id", ""))
    status = str(payload.get("status", ""))
    provenance = Provenance(kind=ProvenanceKind.RECORDED, source_id=event.id)

    if channel_id:
        store.record("channel", channel_id, ATTR_FEED_STATUS, status,
                     valid_from=event.ts, recorded_at=event.ts,
                     provenance=provenance, conn=conn)
    if listing_id:
        store.record("listing", listing_id, overlay_mod.ATTR_STATUS,
                     LISTING_STATUS.get(status, status), valid_from=event.ts,
                     recorded_at=event.ts, provenance=provenance, conn=conn)

    if status != "REJECTED":
        return []

    base = baseline_mod.get()
    code = str(payload.get("code", ""))
    field = str(payload.get("field", ""))
    detail = str(payload.get("detail", ""))
    return [CorrectionSignal(
        id=f"SIG-{event.id}",
        kind=CorrectionKind.CHANNEL_REJECTION,
        detected_at=event.ts,
        entities=[e for e in (listing_id, channel_id,
                              str(payload.get("variant_id", ""))) if e],
        # The rejection names the channel's own field; the fix has to be made
        # against the internal attributes behind it, and a marketplace may
        # render two of ours into one of theirs.
        attribute_paths=_paths_for_field(base, channel_id, field),
        new_value=code,
        summary=(f"{channel_id} rejected {listing_id} with {code}"
                 + (f": {detail}" if detail else "")),
        source_event_id=event.id,
        provenance=provenance,
    )]


# Types absent from this table are not interpreted here. PUBLISH_TELEMETRY is
# routine liveness - recorded on the tape for the audit trail and never an
# exception on its own - and COMMS is prose the graph extracts from.
HANDLERS: dict[EventType, Handler] = {
    EventType.CATALOG_UPDATE: _catalog_update,
    EventType.CHANNEL_STATUS: _channel_status,
    EventType.SPEC_DOC: _spec_doc,
    EventType.SUPPLIER_FEED: _attribute_rows,
}


# ---------------------------------------------------------------------------
# Attribute rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _InForce:
    """The value an attribute holds when a new one arrives, and who said so."""

    value: object
    doc_id: str


@dataclass(frozen=True)
class _Row:
    """One attribute assertion off a structured feed."""

    entity_type: str
    entity_id: str
    path: str
    value: object
    unit: str | None
    doc_id: str
    version: str

    @property
    def ref(self) -> str:
        return _doc_ref(self.doc_id, self.version)


def _raw_rows(payload: dict) -> list[dict]:
    """The attribute rows a feed event carries.

    One event may restate a batch; each row inherits the envelope's document.
    Price and stock rows carry no attribute path - they are not product
    information and this module has nothing to say about them.
    """
    envelope = {k: v for k, v in payload.items() if k != "rows"}
    batch = payload.get("rows")
    if isinstance(batch, list):
        rows = [envelope | row for row in batch
                if isinstance(row, dict) and row.get("path")]
        return sorted(rows, key=lambda r: (str(r["entity_id"]), str(r["path"])))
    return [envelope] if payload.get("path") else []


def _attribute_row(event: Event, raw: dict, signal_id: str, conn,
                   carrier: tuple[str | None, tuple[str, ...]] = (None, ()),
                   ) -> CorrectionSignal | None:
    base = baseline_mod.get()
    row = _row(base, raw)
    if row is None:
        return None

    held = _in_force(base, row, event.ts)
    material = _material(base, row.path, held.value, row.value)

    if material and precedence(base, row.doc_id) < precedence(base, held.doc_id):
        # POL-002 settles this rather than arrival order. Recording the row
        # would let a portal spreadsheet quietly beat the pack label, so the
        # disagreement is raised and the higher-ranked value stays in force.
        return _conflict(base, event, signal_id, row, held)

    system, defects = carrier
    store.record(row.entity_type, row.entity_id, row.path, row.value,
                 valid_from=event.ts, recorded_at=event.ts, conn=conn,
                 provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                       source_id=row.ref, note=event.id,
                                       # A value known to have arrived
                                       # malformed must not be
                                       # indistinguishable from one that
                                       # arrived clean.
                                       system=system, defects=defects))

    definition = base.attr_defs.get(row.path)
    if _is_gap(definition, row.value):
        return _signal(
            event, signal_id, row, held, CorrectionKind.DATA_GAP,
            entities=[row.entity_id, row.doc_id],
            summary=(f"{row.ref} sent {row.entity_id} {row.path} empty; it is "
                     f"required on {', '.join(sorted(definition.required_for))}"),
        )
    if not material:
        return None
    return _signal(
        event, signal_id, row, held, CorrectionKind.SPEC_CORRECTION,
        entities=[row.entity_id, row.doc_id],
        summary=(f"{row.ref} restates {row.entity_id} {row.path} "
                 f"{held.value} -> {row.value}"
                 + (f" {row.unit}" if row.unit else "")),
    )


def _conflict(base, event: Event, signal_id: str, row: _Row,
              held: _InForce) -> CorrectionSignal:
    incoming = base.source_docs.get(row.doc_id)
    standing = base.source_docs.get(held.doc_id)
    return _signal(
        event, signal_id, row, held, CorrectionKind.SOURCE_CONFLICT,
        entities=[row.entity_id, held.doc_id, row.doc_id],
        summary=(f"{row.ref} ({incoming.kind if incoming else 'unknown'}, "
                 f"precedence {precedence(base, row.doc_id)}) says "
                 f"{row.entity_id} {row.path} is {row.value}; {held.doc_id} "
                 f"({standing.kind if standing else 'unknown'}, precedence "
                 f"{precedence(base, held.doc_id)}) has {held.value} - "
                 f"{PRECEDENCE_POLICY} keeps {held.doc_id}, so the feed value "
                 f"is not in force"),
    )


def _signal(event: Event, signal_id: str, row: _Row, held: _InForce,
            kind: CorrectionKind, entities: list[str],
            summary: str) -> CorrectionSignal:
    return CorrectionSignal(
        id=signal_id,
        kind=kind,
        detected_at=event.ts,
        entities=entities,
        attribute_paths=[row.path],
        old_value=held.value,
        new_value=row.value,
        unit=row.unit,
        window_start=event.ts.date(),
        summary=summary,
        source_event_id=event.id,
        source=SourceRef(doc_id=row.doc_id, version=row.version),
        provenance=_feed_provenance(event),
    )


def _doc_state(event: Event, conn) -> None:
    """Record which version of a document is in force, and its standing.

    Status is written only when the event names one: a routine arrival leaves
    the document ACTIVE, while a PIM withdrawal is exactly the change worth
    recording.
    """
    payload = event.payload
    doc_id = str(payload.get("doc_id", ""))
    if not doc_id:
        return

    version = str(payload.get("doc_version", ""))
    provenance = Provenance(kind=ProvenanceKind.RECORDED,
                            source_id=_doc_ref(doc_id, version), note=event.id)
    if version:
        store.record("source_doc", doc_id, overlay_mod.ATTR_VERSION, version,
                     valid_from=event.ts, recorded_at=event.ts,
                     provenance=provenance, conn=conn)
    status = payload.get("status")
    if status:
        store.record("source_doc", doc_id, overlay_mod.ATTR_STATUS, str(status),
                     valid_from=event.ts, recorded_at=event.ts,
                     provenance=provenance, conn=conn)


# ---------------------------------------------------------------------------
# Writing an inferred attribute (called by the graph after extraction)
# ---------------------------------------------------------------------------


def record_attribute(
    entity_id: str,
    attribute_path: str,
    value: object,
    valid_from: datetime,
    source_event_id: str | None = None,
    source_doc: str = "",
    source_version: str = "",
    confidence: float = 0.8,
    agent: str = "extract",
    model: str | None = None,
    run_id: str | None = None,
    supersedes_id: str | None = None,
    recorded_at: datetime | None = None,
) -> str:
    """Persist a value read out of a document as an INFERRED fact.

    The graph's single entry point for everything this module refuses to
    interpret. ``valid_from`` is when the corrected value becomes true in the
    world, which is not the day the document arrived when a change is announced
    ahead of time.

    An extraction that revises a value passes ``supersedes_id``; the new row
    points at the one it replaces rather than overwriting it, so what the
    content team knew when they wrote the copy stays answerable.
    """
    from sc.replay import tape

    provenance = Provenance(
        kind=ProvenanceKind.INFERRED,
        # The overlay resolves a value's version from this, so it names the
        # document; the event that carried it is kept in the note.
        source_id=_doc_ref(source_doc, source_version) or source_event_id,
        confidence=confidence, agent=agent, model=model, run_id=run_id,
        note=(f"extracted from {source_event_id}" if source_event_id
              else "extracted from an unstructured supplier document"),
    )
    # Recorded time runs on the replay clock like everything else. Wall-clock
    # now would fall outside the horizon and hide the fact from every as-of
    # read the validator makes.
    recorded_at = recorded_at or tape.sim_now()

    if supersedes_id:
        # Two rows recorded at the same instant tie on the store's id order,
        # and a correction that loses that tie is invisible. Two extractions in
        # one run share a replay clock, so say what is true anyway: a
        # correction is learned after the thing it corrects.
        recorded_at = max(recorded_at,
                          _recorded_at(supersedes_id) + timedelta(microseconds=1))
        return store.correct(supersedes_id, value=value, provenance=provenance,
                             valid_from=valid_from, recorded_at=recorded_at)
    # An extraction naming something the catalog has not heard of is still an
    # assertion about a sellable form, and is stored as one rather than dropped.
    entity_type = _entity_type(baseline_mod.get(), entity_id) or "variant"
    return store.record(entity_type, entity_id, attribute_path, value,
                        valid_from=valid_from, recorded_at=recorded_at,
                        provenance=provenance)


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _feed_provenance(event: Event) -> Provenance:
    return Provenance(kind=ProvenanceKind.RECORDED, source_id=event.id)


def _recorded_at(fact_id: str) -> datetime:
    row = db.one("SELECT recorded_at FROM facts WHERE id = ?", (fact_id,))
    return datetime.fromisoformat(row["recorded_at"]) if row else datetime.min


def _doc_ref(doc_id: str, version: str) -> str:
    """How a fact names the document it came from, version pinned when known.

    Pinning matters: a fact left unpinned inherits whatever version of its
    document is in force, so a feed row confirming last month's value would
    appear to have been asserted by this month's revision.
    """
    if not doc_id:
        return ""
    return f"{doc_id}:{version}" if version else doc_id


def _entity_type(base, entity_id: str) -> str | None:
    if entity_id in base.variants:
        return "variant"
    if entity_id in base.products:
        return "product"
    return None


def _row(base, raw: dict) -> _Row | None:
    """Read one feed row, or nothing if it is not about a catalog attribute."""
    entity_id = str(raw.get("entity_id", ""))
    path = str(raw.get("path", ""))
    entity_type = _entity_type(base, entity_id)
    if entity_type is None or not path:
        return None

    definition = base.attr_defs.get(path)
    return _Row(
        entity_type=entity_type,
        entity_id=entity_id,
        path=path,
        value=raw.get("value"),
        unit=definition.unit if definition else raw.get("unit"),
        doc_id=str(raw.get("doc_id", "")),
        version=str(raw.get("doc_version", "")),
    )


def _in_force(base, row: _Row, at: datetime) -> _InForce:
    """The value this attribute holds as the event arrives.

    Falls back to the baseline, which is what the prepared copy was written
    against - a first correction has no fact to compare with, and comparing
    against nothing would make every routine confirmation look like news.
    """
    fact = store.get(row.entity_type, row.entity_id, row.path, as_of_valid=at,
                     as_of_recorded=at)
    if fact is not None:
        return _InForce(fact.value,
                        (fact.provenance.source_id or "").partition(":")[0])
    key = (row.entity_id, row.path)
    source = base.attr_sources.get(key)
    return _InForce(base.attr_values.get(key), source.doc_id if source else "")


def _material(base, path: str, old: object, new: object) -> bool:
    """Whether a change is a correction or noise.

    Numbers get a tolerance; lists and strings do not, because a reordered
    ingredient list or a changed filter type is a different declaration however
    small the edit looks. A safety attribute gets no tolerance at all: "may
    contain peanuts" is not a five percent change to anything, and an allergen
    a shopper is not told about is a recall rather than a rounding error.
    """
    if old == new:
        return False
    definition = base.attr_defs.get(path)
    if definition is not None and definition.safety_class:
        return True
    if isinstance(old, bool) or isinstance(new, bool):
        return True
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if old == 0:
            return True
        return abs(new - old) / abs(old) * 100.0 > MATERIAL_PCT
    return True


def _is_gap(definition, value: object) -> bool:
    """A mandatory attribute that arrived with nothing in it.

    An empty list is not a gap - an empty ``may_contain`` is a declared absence
    of allergens, and the validator counts it as answered. Only "no value at
    all" is missing information.
    """
    if definition is None or not definition.required_for:
        return False
    return value is None or value == ""


def _paths_for_field(base, channel_id: str, field: str) -> list[str]:
    """The internal attributes a channel renders into one of its own fields."""
    channel = base.channels.get(channel_id)
    if channel is None or not field:
        return []
    return sorted(path for path, name in channel.attribute_map.items()
                  if name == field)
