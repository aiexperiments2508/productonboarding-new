"""Bitemporal store behaviour.

The scenario under test is the one the finale actually exercises: a supplier
commits a quantity, then days later corrects it downward. The system must be
able to answer both "what is true?" and "what did we believe on Monday?" -
because a recommendation made on Monday has to be defensible on Monday's
evidence, not judged against facts that arrived on Wednesday.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("DB_PATH", "data/test_bitemporal.db")

from sc import db  # noqa: E402
from sc.contracts import Provenance, ProvenanceKind  # noqa: E402
from sc.state import store  # noqa: E402

RECORDED = Provenance(kind=ProvenanceKind.RECORDED, source_id="EVT-1")
INFERRED = Provenance(kind=ProvenanceKind.INFERRED, source_id="MAIL-9", confidence=0.9)

SEP = lambda d, h=0: datetime(2026, 9, d, h)  # noqa: E731


@pytest.fixture(autouse=True)
def fresh_db():
    db.init_db(drop=True)
    yield
    db.close()


def _commitment(qty: float, recorded_day: int, provenance=RECORDED) -> str:
    return store.record(
        entity_type="supplier",
        entity_id="SUP-03",
        attr="commitment_qty",
        value=qty,
        valid_from=SEP(1),
        recorded_at=SEP(recorded_day),
        provenance=provenance,
    )


def test_correction_is_invisible_before_it_arrives():
    """The core guarantee: recorded time gates what a query can see."""
    original = _commitment(1000, recorded_day=1)
    store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)

    # Same instant in the world, two different states of knowledge.
    believed_monday = store.get_value(
        "supplier", "SUP-03", "commitment_qty",
        as_of_valid=SEP(5), as_of_recorded=SEP(2),
    )
    known_now = store.get_value(
        "supplier", "SUP-03", "commitment_qty",
        as_of_valid=SEP(5), as_of_recorded=SEP(10),
    )

    assert believed_monday == 1000, "a correction must not leak backwards in time"
    assert known_now == 400


def test_latest_correction_wins_among_several():
    original = _commitment(1000, recorded_day=1)
    first = store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)
    store.correct(first, value=650, recorded_at=SEP(6), provenance=RECORDED)

    assert store.get_value("supplier", "SUP-03", "commitment_qty",
                           as_of_valid=SEP(9), as_of_recorded=SEP(4)) == 400
    assert store.get_value("supplier", "SUP-03", "commitment_qty",
                           as_of_valid=SEP(9), as_of_recorded=SEP(9)) == 650


def test_valid_window_excludes_facts_not_yet_in_force():
    """A fact recorded today about next week is not true today."""
    store.record(
        "lane", "LANE-07", "capacity_per_day", 120,
        valid_from=SEP(10), recorded_at=SEP(1), provenance=RECORDED,
    )
    assert store.get("lane", "LANE-07", "capacity_per_day",
                     as_of_valid=SEP(5), as_of_recorded=SEP(20)) is None
    assert store.get_value("lane", "LANE-07", "capacity_per_day",
                           as_of_valid=SEP(12), as_of_recorded=SEP(20)) == 120


def test_closed_window_stops_applying():
    store.record(
        "plant", "PLANT-A", "capacity_per_day", 800,
        valid_from=SEP(1), valid_to=SEP(5), recorded_at=SEP(1), provenance=RECORDED,
    )
    assert store.get_value("plant", "PLANT-A", "capacity_per_day",
                           as_of_valid=SEP(3), as_of_recorded=SEP(20)) == 800
    assert store.get("plant", "PLANT-A", "capacity_per_day",
                     as_of_valid=SEP(6), as_of_recorded=SEP(20)) is None


def test_get_many_returns_one_winning_row_per_entity_attr():
    original = _commitment(1000, recorded_day=1)
    store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)
    store.record("supplier", "SUP-04", "commitment_qty", 250,
                 valid_from=SEP(1), recorded_at=SEP(1), provenance=RECORDED)

    facts = store.get_many("supplier", as_of_valid=SEP(5), as_of_recorded=SEP(9))
    values = {f.entity_id: f.value for f in facts}

    assert values == {"SUP-03": 400, "SUP-04": 250}
    assert len(facts) == 2, "superseded rows must not appear alongside their winner"


def test_lineage_walks_back_to_the_original():
    original = _commitment(1000, recorded_day=1)
    first = store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)
    latest = store.correct(first, value=650, recorded_at=SEP(6), provenance=RECORDED)

    chain = store.lineage(latest)

    assert [f.value for f in chain] == [650, 400, 1000]
    assert [f.provenance.kind for f in chain] == [
        ProvenanceKind.RECORDED, ProvenanceKind.INFERRED, ProvenanceKind.RECORDED,
    ]


def test_correction_inherits_validity_window_unless_overridden():
    original = store.record(
        "supplier", "SUP-03", "commitment_qty", 1000,
        valid_from=SEP(1), valid_to=SEP(8), recorded_at=SEP(1), provenance=RECORDED,
    )
    corrected = store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)

    fact = store.lineage(corrected)[0]
    assert fact.valid_from == SEP(1)
    assert fact.valid_to == SEP(8)


def test_corrections_since_surfaces_late_arrivals():
    """The monitor uses this to notice a live run is on stale evidence."""
    original = _commitment(1000, recorded_day=1)
    store.correct(original, value=400, recorded_at=SEP(3), provenance=INFERRED)

    assert [f.value for f in store.corrections_since(SEP(2))] == [400]
    assert store.corrections_since(SEP(4)) == []


def test_provenance_kinds_are_counted_separately():
    _commitment(1000, recorded_day=1)
    store.record("supplier", "SUP-05", "commitment_qty", 10,
                 valid_from=SEP(1), recorded_at=SEP(1), provenance=INFERRED)

    assert store.counts_by_provenance() == {"RECORDED": 1, "INFERRED": 1}
