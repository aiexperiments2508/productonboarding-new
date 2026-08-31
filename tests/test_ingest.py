"""Event ingestion.

The properties under test are the ones the audit story rests on: a structured
feed row is an observation and is recorded as one, a document's *content* is
never guessed at here, a change too small to matter is not paraded as an
exception, a lower-ranked source does not get to quietly overwrite a
higher-ranked one, and the cursor moves with the facts or not at all.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("DB_PATH", "data/test_ingest.db")

from sc import db  # noqa: E402
from sc.contracts import (  # noqa: E402
    CorrectionKind,
    Event,
    EventType,
    ProvenanceKind,
)
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.state import store  # noqa: E402

FEED = EventType.SUPPLIER_FEED

# A synthetic event has to arrive after everything the tape has already said.
# Derived from the horizon rather than written down: the clock the fixture
# leaves behind moves whenever the recorded flight does, and a literal date
# here would quietly start reading a window the tape has not reached.
def _after_the_tape() -> datetime:
    from datetime import timedelta

    base = baseline_mod.get()
    return datetime.combine(
        base.horizon_start + timedelta(days=base.horizon_days + 4),
        datetime.min.time()).replace(hour=9)


NOW = _after_the_tape()


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    # As far as the allergen change, which is the last arc these tests read
    # against. Named rather than counted: "twelve events past the inject" is a
    # statement about traffic density, and the density is not what is under
    # test here.
    released = tape.jump_to(_seq_of(doc_id="DOC-04", version="v2"))
    ingest.ingest(released)
    yield
    db.close()


def _seq_of(*, doc_id: str, version: str) -> int:
    """Where an arc sits on the tape, by what it carries rather than by count."""
    for row in db.query("SELECT seq, payload FROM events ORDER BY seq"):
        payload = db.loads(row["payload"])
        if (payload.get("doc_id") == doc_id
                and payload.get("doc_version") == version):
            return int(row["seq"])
    raise AssertionError(f"no {doc_id} {version} on the tape")


def _event(offset: int, type_: EventType, payload: dict,
           source: str = "SUPPLIER_PORTAL") -> Event:
    seq = ingest.cursor() + offset
    return Event(id=f"EVT-T{seq:05d}", seq=seq, ts=NOW, type=type_,
                 source=source, payload=payload)


def _weight_row(doc_id: str, value: object, version: str = "v1") -> dict:
    return {"kind": "ATTRIBUTE", "entity_id": "VAR-02A", "supplier": "SUP-02",
            "path": "food.net_weight_g", "value": value, "unit": "g",
            "doc_id": doc_id, "doc_version": version}


def _facts(entity_type: str, entity_id: str, attr: str) -> int:
    return db.one("SELECT COUNT(*) AS n FROM facts WHERE entity_type = ?"
                  " AND entity_id = ? AND attr = ?",
                  (entity_type, entity_id, attr))["n"]


def _held(entity_id: str, path: str):
    return store.get("variant", entity_id, path, as_of_valid=NOW,
                     as_of_recorded=NOW)


# ---------------------------------------------------------------------------
# The RECORDED / INFERRED split
# ---------------------------------------------------------------------------


def test_a_feed_row_becomes_a_recorded_fact_naming_document_and_event():
    event = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                             "path": "specs.coverage_m2", "value": 44,
                             "doc_id": "DOC-01", "doc_version": "v1",
                             "supplier": "SUP-01"})
    signals = ingest.ingest([event])
    fact = _held("VAR-01A", "specs.coverage_m2")

    assert fact.value == 44
    assert fact.provenance.kind == ProvenanceKind.RECORDED
    # The document is pinned at the version that asserted the value, so a later
    # revision does not appear to have said it.
    assert fact.provenance.source_id == "DOC-01:v1"
    assert fact.provenance.note == event.id
    assert fact.recorded_at == event.ts, "recorded time runs on the replay clock"
    assert [s.kind for s in signals] == [CorrectionKind.SPEC_CORRECTION]


def test_documents_and_emails_write_no_attribute_facts():
    """Their arrival is structured; their content is the graph's to extract."""
    doc = _event(1, EventType.SPEC_DOC, {
        "doc_id": "DOC-01", "doc_version": "v2", "kind": "SPEC_SHEET",
        "supplier": "SUP-01", "product": "PRD-01", "entities": ["PRD-01"],
        "attribute_path": "specs.power_w", "old_value": 45, "new_value": 65,
        "applies_to": "UNCLEAR", "is_correction": True})
    mail = _event(2, EventType.COMMS, {
        "from": "specs@sup-01.example", "to": "product-content@internal",
        "subject": "Northaven AP300 - corrected rated power", "doc_id": "DOC-01",
        "doc_version": "v2", "product": "PRD-01"}, source="MAILBOX")
    before = _facts("variant", "VAR-01B", "specs.power_w")

    assert ingest.ingest([doc, mail]) == []
    assert _facts("variant", "VAR-01B", "specs.power_w") == before
    assert store.get("source_doc", "DOC-01", "version", as_of_valid=NOW,
                     as_of_recorded=NOW).value == "v2"


# ---------------------------------------------------------------------------
# Materiality
# ---------------------------------------------------------------------------


def test_an_immaterial_change_is_recorded_without_raising_a_signal():
    event = _event(1, FEED, _weight_row("DOC-03", 41))

    assert ingest.ingest([event]) == [], "2.5% is noise, not an exception"
    assert _held("VAR-02A", "food.net_weight_g").value == 41


def test_any_change_to_a_safety_attribute_is_material(monkeypatch):
    """The same 2.5% edit, on an attribute a shopper could be harmed by."""
    base = baseline_mod.get()
    monkeypatch.setattr(base.attr_defs["food.net_weight_g"], "safety_class", True)
    event = _event(1, FEED, _weight_row("DOC-03", 41))

    signals = ingest.ingest([event])

    assert [s.kind for s in signals] == [CorrectionKind.SPEC_CORRECTION]
    assert signals[0].attribute_paths == ["food.net_weight_g"]


def test_a_required_attribute_arriving_empty_is_a_data_gap():
    event = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-02A",
                             "path": "identifiers.gtin", "value": "",
                             "doc_id": "DOC-03", "doc_version": "v2",
                             "supplier": "SUP-02"})
    signals = ingest.ingest([event])

    assert [s.kind for s in signals] == [CorrectionKind.DATA_GAP]
    assert "CH-MKT-A" in signals[0].summary, "a gap names where the field is needed"


# ---------------------------------------------------------------------------
# Source precedence
# ---------------------------------------------------------------------------


def test_a_lower_precedence_source_does_not_overwrite_a_higher_one():
    """Arc 2: the portal spreadsheet disagrees with the pack label."""
    # The pack label speaks first, and this test writes that itself rather than
    # relying on the tape having happened to confirm the attribute inside the
    # fixture's window. What is under test is which of two sources wins, so
    # both of them belong in the test.
    ingest.ingest([_event(1, FEED, {
        "kind": "ATTRIBUTE", "entity_id": "VAR-02A",
        "path": "identifiers.gtin", "value": "05098765400011",
        "doc_id": "DOC-03", "doc_version": "v1", "supplier": "SUP-02"})])

    event = _event(2, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-02A",
                             "path": "identifiers.gtin",
                             "value": "05098765499999", "doc_id": "DOC-05",
                             "doc_version": "v1", "supplier": "SUP-02"})
    signals = ingest.ingest([event])
    signal = signals[0]

    assert [s.kind for s in signals] == [CorrectionKind.SOURCE_CONFLICT]
    assert {"DOC-03", "DOC-05"} <= set(signal.entities), "both documents named"
    assert ingest.PRECEDENCE_POLICY in signal.summary, "the binding rule is named"
    assert _held("VAR-02A", "identifiers.gtin").value == "05098765400011"


def test_both_halves_of_the_provenance_split_enforce_the_same_policy():
    """POL-002 is applied twice - here on structured feeds, and in the graph on
    what a model reads out of prose. Two copies of the rule are two rules as
    soon as one of them is edited, so there is one function and both import it.
    """
    from sc.graph import nodes
    from sc.state import baseline

    assert ingest.precedence is baseline.precedence is nodes.precedence

    base = baseline_mod.get()
    assert baseline.precedence(base, "DOC-03") > baseline.precedence(base, "DOC-05")
    # A document the seed pack does not know ranks below every one it does.
    assert baseline.precedence(base, "DOC-99") == 0


def test_an_equal_ranked_source_is_recorded_rather_than_disputed():
    event = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-02A",
                             "path": "identifiers.gtin",
                             "value": "05098765499999", "doc_id": "DOC-03",
                             "doc_version": "v2", "supplier": "SUP-02"})
    signals = ingest.ingest([event])

    assert [s.kind for s in signals] == [CorrectionKind.SPEC_CORRECTION]
    assert _held("VAR-02A", "identifiers.gtin").value == "05098765499999"


# ---------------------------------------------------------------------------
# Channel feedback
# ---------------------------------------------------------------------------


def test_a_channel_rejection_carries_its_code():
    """Arc 5: Marketplace B refuses the republished allergen statement."""
    event = _event(1, EventType.CHANNEL_STATUS, {
        "channel_id": "CH-MKT-B", "listing_id": "LST-11", "variant_id": "VAR-02A",
        "status": "REJECTED", "code": "MKB-2201", "field": "allergenCodes",
        "detail": "allergen_statement format invalid", "feed_version": "v1",
    }, source="CHANNEL_GATEWAY")
    signals = ingest.ingest([event])
    signal = signals[0]

    assert signal.kind == CorrectionKind.CHANNEL_REJECTION
    assert signal.new_value == "MKB-2201"
    assert "MKB-2201" in signal.summary
    # The rejection names a channel-side field; the fix is made against the
    # internal paths behind it.
    assert signal.attribute_paths == ["food.allergens.contains",
                                      "food.allergens.may_contain"]
    assert store.get("listing", "LST-11", "status", as_of_valid=NOW,
                     as_of_recorded=NOW).value == "REJECTED"
    assert store.get("channel", "CH-MKT-B", ingest.ATTR_FEED_STATUS,
                     as_of_valid=NOW, as_of_recorded=NOW).value == "REJECTED"


def test_an_acknowledgement_is_recorded_without_raising_a_signal():
    event = _event(1, EventType.CHANNEL_STATUS, {
        "channel_id": "CH-WEB", "listing_id": "LST-01", "variant_id": "VAR-01A",
        "status": "ACCEPTED", "code": "", "detail": "", "feed_version": "v1",
    }, source="CHANNEL_GATEWAY")

    assert ingest.ingest([event]) == []
    assert store.get("listing", "LST-01", "status", as_of_valid=NOW,
                     as_of_recorded=NOW).value == "LIVE"


# ---------------------------------------------------------------------------
# The graph's way back in
# ---------------------------------------------------------------------------


def test_an_extracted_value_is_inferred_and_supersedes_rather_than_overwrites():
    first = ingest.record_attribute(
        "VAR-01B", "specs.power_w", 65, valid_from=NOW,
        source_event_id="EVT-00145", source_doc="DOC-01", source_version="v2",
        confidence=0.72, run_id="RUN-1")
    fact = _held("VAR-01B", "specs.power_w")

    assert fact.id == first
    assert fact.value == 65
    assert fact.provenance.kind == ProvenanceKind.INFERRED
    assert fact.provenance.source_id == "DOC-01:v2"
    assert fact.provenance.confidence == 0.72
    assert "EVT-00145" in fact.provenance.note

    second = ingest.record_attribute(
        "VAR-01B", "specs.power_w", 44, valid_from=NOW,
        source_event_id="EVT-00169", source_doc="DOC-01", source_version="v3",
        confidence=0.9, supersedes_id=first)

    assert [f.value for f in store.lineage(second)] == [44, 65]
    assert _held("VAR-01B", "specs.power_w").value == 44, (
        "a correction recorded on the same replay tick still wins")


# ---------------------------------------------------------------------------
# The cursor
# ---------------------------------------------------------------------------


def test_the_cursor_advances_with_the_batch_and_redelivery_is_a_no_op():
    event = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                             "path": "specs.coverage_m2", "value": 44,
                             "doc_id": "DOC-01", "doc_version": "v1"})

    assert len(ingest.ingest([event])) == 1
    assert ingest.cursor() == event.seq
    written = _facts("variant", "VAR-01A", "specs.coverage_m2")

    assert ingest.ingest([event]) == [], "an event behind the cursor is not replayed"
    assert _facts("variant", "VAR-01A", "specs.coverage_m2") == written


def test_a_failed_batch_leaves_the_cursor_and_the_store_untouched(monkeypatch):
    """Facts and the cursor move together, so a crash redelivers the batch."""
    good = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                            "path": "specs.coverage_m2", "value": 44,
                            "doc_id": "DOC-01", "doc_version": "v1"})
    bad = _event(2, EventType.CHANNEL_STATUS, {"channel_id": "CH-WEB",
                                               "listing_id": "LST-01",
                                               "status": "ACCEPTED"},
                 source="CHANNEL_GATEWAY")

    def boom(event, conn):
        raise RuntimeError("channel gateway went away mid-batch")

    monkeypatch.setitem(ingest.HANDLERS, EventType.CHANNEL_STATUS, boom)
    before = ingest.cursor()

    with pytest.raises(RuntimeError):
        ingest.ingest([good, bad])

    assert ingest.cursor() == before
    assert _held("VAR-01A", "specs.coverage_m2") is None


# ---------------------------------------------------------------------------
# Which system carried it
#
# A supplier is *who asserted* a value; a system is *what carried it*. The MVP
# collapsed the two, which made "these two systems disagree about the same
# supplier's product" inexpressible - and that disagreement is the whole reason
# an estate of ten is more interesting than a feed of one.
# ---------------------------------------------------------------------------


def _deliver(event, system_id: str, defects: tuple[str, ...] = ()) -> None:
    """Record an arrival for an event, as the named system, before ingesting."""
    from sc.estate import arrivals, emitter

    arrivals.record(
        emitter.Batch(system_id=system_id, ordinal=event.seq,
                      sequences=(event.seq,), after=0.0,
                      defects={event.seq: defects}),
        {event.seq: event.id})


def test_a_recorded_fact_names_the_system_that_carried_it():
    first = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                             "path": "specs.coverage_m2", "value": 44,
                             "doc_id": "DOC-01", "doc_version": "v1",
                             "supplier": "SUP-01"})
    _deliver(first, "supplier-portal")
    ingest.ingest([first])
    carried_by_portal = _held("VAR-01A", "specs.coverage_m2")

    second = _event(2, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                              "path": "specs.noise_db", "value": 33,
                              "doc_id": "DOC-01", "doc_version": "v1",
                              "supplier": "SUP-01"})
    _deliver(second, "gdsn-pool")
    ingest.ingest([second])
    carried_by_pool = _held("VAR-01A", "specs.noise_db")

    assert carried_by_portal.provenance.system == "supplier-portal"
    assert carried_by_pool.provenance.system == "gdsn-pool"
    # Same supplier, same document, two systems. Distinguishable on that field
    # alone, which is what makes a contradiction attributable.
    assert carried_by_portal.provenance.source_id == \
        carried_by_pool.provenance.source_id
    assert (carried_by_portal.provenance.system
            != carried_by_pool.provenance.system)


def test_a_defect_stamped_on_arrival_survives_into_the_record():
    """A value known to have arrived malformed must not be indistinguishable
    from one that arrived clean."""
    from sc.estate.defects import Defect

    dirty = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                             "path": "specs.coverage_m2", "value": 44,
                             "doc_id": "DOC-01", "doc_version": "v1",
                             "supplier": "SUP-01"})
    _deliver(dirty, "gdsn-pool", (str(Defect.FOREIGN_VOCABULARY),))
    ingest.ingest([dirty])

    clean = _event(2, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                             "path": "specs.noise_db", "value": 33,
                             "doc_id": "DOC-01", "doc_version": "v1",
                             "supplier": "SUP-01"})
    _deliver(clean, "label-artwork")
    ingest.ingest([clean])

    assert _held("VAR-01A", "specs.coverage_m2").provenance.defects == \
        (str(Defect.FOREIGN_VOCABULARY),)
    assert _held("VAR-01A", "specs.noise_db").provenance.defects == ()


def test_a_fact_with_no_recorded_arrival_still_lands():
    """A tape loaded directly, or a store seeded before the estate existed. The
    fact is written and simply does not name a carrier, which is honest."""
    orphan = _event(1, FEED, {"kind": "ATTRIBUTE", "entity_id": "VAR-01A",
                              "path": "specs.coverage_m2", "value": 44,
                              "doc_id": "DOC-01", "doc_version": "v1",
                              "supplier": "SUP-01"})
    ingest.ingest([orphan])
    fact = _held("VAR-01A", "specs.coverage_m2")

    assert fact.value == 44
    assert fact.provenance.system is None
    assert fact.provenance.defects == ()
