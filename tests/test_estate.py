"""The external estate: who feeds the retailer, and how badly.

Two properties are under test here and they pull against each other, which is
why the file exists.

The estate has to look alive. Ten systems, batches of varying size, irregular
pauses, deliveries that interleave. A reader watching the Ingest Fabric should
see several systems talking at once, because that is what a retailer's morning
actually looks like.

The record has to be reproducible. Same seed, same facts, same trace hash -
the audit trail is worth nothing otherwise, and a demo that cannot be rehearsed
is not a demo.

Both hold because the randomness is in the *schedule*, drawn from the seed, and
the ordering is in *ingestion*, which sorts by sequence. The tests below check
each half and then check the seam: that arrivals landing in any order leave the
same record behind.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_estate.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.estate import arrivals, emitter, manifest  # noqa: E402
from sc.estate.defects import ALL, Defect  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    yield
    db.close()


def _owned() -> dict[str, list[int]]:
    """Every sequence on the tape, dealt to the system that carried it."""
    owned: dict[str, list[int]] = {s.id: [] for s in manifest.SYSTEMS}
    for row in db.query("SELECT seq, type, source FROM events ORDER BY seq"):
        owner = emitter.owner_of(row["type"], row["source"], row["seq"])
        owned[owner].append(row["seq"])
    return owned


def _event_ids() -> dict[int, str]:
    return {r["seq"]: r["id"]
            for r in db.query("SELECT seq, id FROM events")}


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_the_manifest_declares_ten_systems_with_owners():
    systems = manifest.SYSTEMS

    assert len(systems) >= 10
    assert len({s.id for s in systems}) == len(systems), "duplicate system id"
    for system in systems:
        assert system.title and system.owner and system.why
        assert system.emits, f"{system.id} emits nothing"
        assert 0.0 <= system.defect_rate <= 1.0
        for defect in system.defects:
            assert defect in ALL


def test_no_system_is_named_outside_the_manifest():
    """A system that has to be mentioned by name in code is a system nobody can
    add. The manifest is where they live; everything else asks it."""
    allowed = {ROOT / "sc" / "estate" / "manifest.py",
               ROOT / "sc" / "estate" / "emitter.py",
               Path(__file__)}
    offenders: list[str] = []
    for path in sorted((ROOT / "sc").rglob("*.py")):
        if path in allowed or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for system in manifest.SYSTEMS:
            if f'"{system.id}"' in text or f"'{system.id}'" in text:
                offenders.append(f"{path.relative_to(ROOT)} names {system.id}")
    assert not offenders, "; ".join(offenders)


def test_the_estate_spans_good_and_bad_citizens():
    """An estate where everything is equally suspect measures nothing: with no
    contrast, no finding tells a reviewer which system to go and fix."""
    clean = [s for s in manifest.SYSTEMS if s.well_behaved]
    messy = [s for s in manifest.SYSTEMS if len(s.defects) > 1]

    assert clean, "no system is trustworthy, so nothing can arbitrate"
    assert messy, "no system is unreliable, so validation is never exercised"


# ---------------------------------------------------------------------------
# Delivering in batches, at irregular times
# ---------------------------------------------------------------------------


def test_a_system_delivers_in_batches_of_varying_size_and_spacing():
    owned = _owned()
    plan = emitter.schedule(owned)

    busiest = max(plan, key=lambda k: len(plan[k]))
    batches = plan[busiest]
    assert len(batches) > 1, f"{busiest} delivered everything in one go"
    assert len({b.size for b in batches}) > 1, "every batch is the same size"
    assert len({b.after for b in batches}) > 1, "every pause is the same"

    for system_id, owned_seqs in owned.items():
        carried = [s for b in plan[system_id] for s in b.sequences]
        assert carried == sorted(owned_seqs), \
            f"{system_id} lost, duplicated or reordered its own events"


def test_the_estate_delivers_concurrently():
    """Several systems in flight at once, not a queue being drained."""
    plan = emitter.schedule(_owned())
    assert len(emitter.overlaps(plan)) >= 1


def test_the_same_seed_produces_the_same_schedule():
    owned = _owned()
    assert emitter.schedule(owned, 20802) == emitter.schedule(owned, 20802)
    # And a different seed genuinely reshuffles it, or the first assertion is
    # only telling us the function is pure.
    assert emitter.schedule(owned, 20802) != emitter.schedule(owned, 999)


def test_adding_a_system_does_not_reshuffle_the_others():
    """Each system draws from its own named stream. Sharing one generator would
    make every schedule depend on how many systems came before it, so adding an
    eleventh would invalidate every expectation about the ten."""
    owned = _owned()
    first = manifest.SYSTEMS[0]
    before = emitter.schedule_for(first, owned[first.id])
    trimmed = {k: v for k, v in owned.items() if k != manifest.SYSTEMS[-1].id}
    after = emitter.schedule_for(first, trimmed[first.id])
    assert before == after


# ---------------------------------------------------------------------------
# Arrival, then sequencing
# ---------------------------------------------------------------------------


def test_an_arrival_names_its_system_batch_and_instant():
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    system_id = next(k for k, v in plan.items() if v)
    batch = plan[system_id][0]

    rows = arrivals.record(batch, ids)
    assert rows
    for row in rows:
        assert row["system_id"] == system_id
        assert row["batch_id"].startswith("BAT-")
        assert row["arrived_at"]
        assert row["seq"] in batch.sequences
    # One batch identifier shared across the delivery, not one per event.
    assert len({r["batch_id"] for r in rows}) == 1


def test_a_redelivered_batch_is_recorded_once():
    """A system retrying after a dropped connection has done nothing wrong."""
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    batch = next(b for bs in plan.values() for b in bs)

    arrivals.record(batch, ids)
    arrivals.record(batch, ids)
    held = db.one("SELECT COUNT(*) AS n FROM arrivals")["n"]
    assert held == len(batch.sequences)


def test_ingestion_follows_sequence_not_arrival():
    """The release point walks forward from the cursor and stops at the first
    gap. Releasing to the highest arrived sequence instead would push the
    watermark past an event still in flight, and that event would then be
    refused when it landed - silently, on a run that reports success."""
    ids = _event_ids()
    ordered = sorted(ids)[:6]

    late, rest = ordered[0], ordered[1:]
    for sequence in rest:
        arrivals.record(
            emitter.Batch(system_id="supplier-portal", ordinal=sequence,
                          sequences=(sequence,), after=0.0, defects={}), ids)

    # Everything except the first has landed, so nothing may be released yet.
    assert arrivals.releasable(late - 1) == late - 1

    arrivals.record(
        emitter.Batch(system_id="supplier-portal", ordinal=0,
                      sequences=(late,), after=0.0, defects={}), ids)
    assert arrivals.releasable(late - 1) == ordered[-1]


def test_arrival_order_does_not_change_the_record():
    """The property the whole split exists to protect."""
    ids = _event_ids()
    window = sorted(ids)[:24]

    def facts_after(order: list[int]) -> list[tuple]:
        db.init_db(drop=True)
        tape.load_tape(reset=True)
        fresh_ids = _event_ids()
        for sequence in order:
            arrivals.record(
                emitter.Batch(system_id="supplier-portal", ordinal=sequence,
                              sequences=(sequence,), after=0.0, defects={}),
                fresh_ids)
        ingest.ingest(tape.jump_to(arrivals.releasable(0)))
        return [(r["entity_id"], r["attr"], r["value"], r["valid_from"])
                for r in db.query(
                    "SELECT entity_id, attr, value, valid_from FROM facts"
                    " ORDER BY entity_id, attr, value, valid_from")]

    forward = facts_after(window)
    backward = facts_after(list(reversed(window)))

    assert forward, "nothing was recorded, so this proves nothing"
    assert forward == backward


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------


def test_every_defect_is_named_and_attributed():
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    for batches in plan.values():
        for batch in batches:
            arrivals.record(batch, ids)

    named = {d for row in arrivals.recent(10_000) for d in row["defects"]}
    assert named, "the estate introduced no defects at all"
    assert named <= {str(d) for d in ALL}, f"undeclared defect: {named}"

    for row in arrivals.recent(10_000):
        if row["defects"]:
            system = manifest.BY_ID[row["system_id"]]
            for defect in row["defects"]:
                assert Defect(defect) in system.defects, \
                    f"{system.id} stamped {defect}, which it does not declare"


def test_a_well_behaved_system_stamps_nothing():
    plan = emitter.schedule(_owned())
    for system in manifest.SYSTEMS:
        if not system.well_behaved:
            continue
        stamped = [d for b in plan[system.id] for d in b.defects.values()]
        assert not stamped, f"{system.id} is declared clean and stamped {stamped}"


def test_every_stamped_defect_is_detected():
    """A defect the estate can produce and nothing downstream reports is a lie
    in the answer key. This is the check that keeps the closed set honest.

    Detection is asserted against the deterministic surfaces rather than a
    model: each defect has to be nameable by a rule, or it is not a defect this
    system can claim to catch.
    """
    from sc.estate import detection

    undetected = [d for d in ALL if not detection.detector_for(d)]
    assert not undetected, \
        f"the estate stamps {undetected} and nothing reports them"
