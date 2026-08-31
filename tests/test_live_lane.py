"""The live lane.

The recorded flight is replayed on a cursor the operator drives. A supplier's
submission is not part of that recording: it arrives while the process is
running, it is visible immediately, and rewinding the tape must not retract it.

Two lanes in one table, told apart by a column. The tests that matter most here
are the two that pin down why it is a column and not a sequence range - because
both failure modes are silent, and a system that keeps reporting success while
it stops recording facts is the worst thing this codebase could ship.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

os.environ.setdefault("DB_PATH", "data/test_live_lane.db")

from sc import db  # noqa: E402
from sc.contracts import EventType  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    yield
    db.close()


def _submit(path: str = "specs.power_w", value: object = 65,
            entity_id: str = "VAR-01B", system_id: str = "supplier-portal"):
    """One submission, shaped the way the intake server shapes them."""
    return tape.append_live(
        EventType.SPEC_DOC, "VENDOR_PORTAL",
        {"doc_id": "DOC-01", "doc_version": "v9", "supplier": "SUP-01",
         "entities": [entity_id], "applies_to": "VARIANT",
         "attribute_path": path, "new_value": value, "is_correction": True,
         "changes": [{"path": path, "value": value}]},
        system_id=system_id, body="The portal recorded a specification change.")


# ---------------------------------------------------------------------------
# The two silent failures
# ---------------------------------------------------------------------------


def test_the_replay_cursor_cannot_walk_into_the_live_lane():
    """Stepping to the end of the recording stops at the end of the recording.

    ``advance`` selects everything above the cursor. Unbounded, the step after
    the last taped event selects the submission instead and writes its sequence
    number - a hundred thousand times the length of the tape - into the cursor.
    The transport then reports having played far more than exists, the
    simulated clock jumps to whenever the submission was made, and there is no
    way back short of a reset.
    """
    end = tape.last_tape_seq()
    tape.jump_to(end)
    _submit()

    assert tape.advance(1) == []
    assert tape.cursor() == end
    assert tape.state().cursor_seq == end
    assert tape.state().total_events == end


def test_a_live_event_does_not_poison_the_tape_ingest_cursor():
    """A submission mid-replay does not stop the recording being ingested.

    Ingestion drops anything at or behind its watermark, which is what makes
    redelivery free. Sharing one watermark between the lanes would push it past
    every remaining taped event the moment a submission landed, and the rest of
    the recording would be discarded as already-seen - silently, on batches
    that all report success.
    """
    ingest.ingest(tape.jump_to(200))
    behind = ingest.cursor(tape.LANE_TAPE)

    _submit()
    assert ingest.cursor(tape.LANE_TAPE) == behind, "the tape watermark moved"
    assert ingest.cursor(tape.LANE_LIVE) >= tape.LIVE_BASE

    facts_before = db.one("SELECT COUNT(*) AS n FROM facts")["n"]
    ingest.ingest(tape.jump_to(400))
    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] > facts_before


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


def test_jumping_to_a_live_event_lands_on_the_end_of_the_recording():
    """The event feed offers "land the tape here" on every row it renders, and
    it renders submissions too. The target is clamped rather than the button
    hidden: a reader should be able to ask, and get a sensible answer."""
    event = _submit()
    tape.jump_to(event.seq)
    assert tape.cursor() == tape.last_tape_seq()


def test_resetting_the_tape_does_not_retract_a_submission():
    """A rewind un-plays a recording. It does not un-happen a submission."""
    event = _submit()
    tape.reset()

    assert tape.cursor() == 0
    row = db.one("SELECT released_at, lane FROM events WHERE id = ?", (event.id,))
    assert row["released_at"] is not None
    assert row["lane"] == tape.LANE_LIVE
    assert event.id in {e.id for e in tape.released(limit=50)}


def test_reloading_the_tape_does_not_delete_a_submission():
    """Reseeding the recording re-reads a file. It is not a retraction."""
    event = _submit()
    tape.load_tape(reset=True)
    assert db.one("SELECT id FROM events WHERE id = ?", (event.id,)) is not None


def test_a_submission_is_visible_before_the_cursor_reaches_it():
    """It has already happened. Withholding it until a cursor catches up would
    be showing the operator a past that is behind the actual present."""
    tape.jump_to(50)
    event = _submit()
    assert event.id in {e.id for e in tape.released(limit=20)}


def test_the_progress_denominator_counts_only_the_recorded_flight():
    """A progress bar whose denominator grew every time a supplier filled in a
    form would be measuring something nobody asked about."""
    before = tape.state().total_events
    _submit()
    assert tape.state().total_events == before


def test_the_clock_stops_at_the_end_of_the_recording():
    """``run_clock`` ends when there is no next event. Unbounded, a submission
    is always a next event and the clock never stops."""
    tape.jump_to(tape.last_tape_seq())
    _submit()
    nxt = db.one("SELECT ts FROM events WHERE lane = ? AND seq > ?"
                 " ORDER BY seq LIMIT 1", (tape.LANE_TAPE, tape.cursor()))
    assert nxt is None


# ---------------------------------------------------------------------------
# The clock a submission is stamped with
# ---------------------------------------------------------------------------


def test_a_submission_carries_the_simulated_clock_not_the_wall_clock():
    """Every as-of read in this system defaults both time axes to ``sim_now``,
    and the horizon is eight fixed weeks. A submission stamped with a real date
    would be recorded and then invisible to every query that looked for it."""
    tape.jump_to(300)
    event = _submit()

    base = baseline_mod.get()
    horizon_end = base.horizon_start + timedelta(days=base.horizon_days + 1)
    assert base.horizon_start <= event.ts.date() <= horizon_end


def test_a_submission_does_not_move_the_simulated_clock():
    """It is stamped with the clock; it must not also be the clock. Otherwise
    the horizon shifts under every open panel because somebody pressed Submit."""
    tape.jump_to(300)
    before = tape.sim_now()
    _submit()
    assert tape.sim_now() == before


def test_two_submissions_at_one_paused_instant_do_not_tie():
    """The fact store breaks a ``recorded_at`` tie by id, so one of two
    identically stamped submissions would silently never be the value in
    force."""
    tape.jump_to(300)
    first = _submit(value=65)
    second = _submit(value=70)
    assert second.ts > first.ts


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def test_a_submission_is_attributed_to_the_endpoint_it_arrived_through():
    """The recording only knows a coarse origin, so ``owner_of`` deals its
    events among the systems that declare the type. A submission is not a
    guess: the endpoint that accepted it is the system that carried it."""
    event = _submit(system_id="supplier-pim")
    row = db.one("SELECT system_id, defects FROM arrivals WHERE event_id = ?",
                 (event.id,))
    assert row is not None
    assert row["system_id"] == "supplier-pim"


def test_no_defect_is_stamped_on_a_submission():
    """Defect rates describe how a system behaves on the recording. Applied to
    a submission, the estate would tell a supplier that the form they had just
    filled in correctly arrived malformed."""
    event = _submit()
    assert db.loads(db.one("SELECT defects FROM arrivals WHERE event_id = ?",
                           (event.id,))["defects"]) == []


def test_the_backfill_leaves_submissions_alone():
    """Backfill deals released events to systems. A submission already knows
    which system carried it, and re-dealing would overwrite that with a draw."""
    from sc.estate import delivery

    event = _submit(system_id="gdsn-pool")
    delivery.backfill()
    row = db.one("SELECT system_id FROM arrivals WHERE event_id = ?", (event.id,))
    assert row["system_id"] == "gdsn-pool"


# ---------------------------------------------------------------------------
# The sink
# ---------------------------------------------------------------------------


def test_the_live_sink_is_told_what_landed_and_what_it_raised():
    """The seam that lets a submission reach the live feed without the estate
    importing the application that mounts it."""
    seen: list[tuple] = []
    tape.set_live_sink(lambda events, signals: seen.append((events, signals)))
    try:
        event = _submit()
    finally:
        tape.set_live_sink(None)

    assert len(seen) == 1
    assert [e.id for e in seen[0][0]] == [event.id]


def test_a_failing_sink_does_not_fail_the_submission():
    """A panel that cannot be told is a worse panel, not a lost submission."""
    def explode(events, signals):
        raise RuntimeError("no listeners")

    tape.set_live_sink(explode)
    try:
        event = _submit()
    finally:
        tape.set_live_sink(None)

    assert db.one("SELECT id FROM events WHERE id = ?", (event.id,)) is not None
