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
            entity_id: str = "VAR-01B", system_id: str = "supplier-portal",
            doc_version: str = "v9"):
    """One submission, shaped the way the intake server shapes them."""
    return tape.append_live(
        EventType.SPEC_DOC, "VENDOR_PORTAL",
        {"doc_id": "DOC-01", "doc_version": doc_version, "supplier": "SUP-01",
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


# ---------------------------------------------------------------------------
# Clearing
# ---------------------------------------------------------------------------


def test_clearing_removes_the_portal_traffic_and_rewinds_the_tape():
    """The deliberate act ``reset`` refuses to be.

    A rehearsal that starts on top of the last one's submissions opens its feed
    on somebody else's work. ``clear`` is the verb that fixes that, and the
    counts it returns are what the operator is shown - so they are asserted
    here rather than inferred from a later query.
    """
    ingest.ingest(tape.jump_to(200))
    event = _submit()

    counts = tape.clear()

    assert counts["live_events"] == 1
    assert db.one("SELECT id FROM events WHERE id = ?", (event.id,)) is None
    assert db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?",
                  (tape.LANE_LIVE,))["n"] == 0
    assert tape.cursor() == 0
    assert db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?"
                  " AND released_at IS NOT NULL", (tape.LANE_TAPE,))["n"] == 0
    # The recording itself survives. Clearing is about what arrived, not about
    # the tape being reloaded.
    assert db.one("SELECT COUNT(*) AS n FROM events WHERE lane = ?",
                  (tape.LANE_TAPE,))["n"] > 0


def test_clearing_leaves_the_facts_a_submission_recorded():
    """The chosen scope, pinned so nobody widens it by accident.

    Clearing the tape and retracting a fact are different acts. This one is
    only the first, and the control says so where it is pressed - a test that
    let the fact disappear would make that sentence a lie.
    """
    _submit(path="specs.power_w", value=65, entity_id="VAR-01B")
    before = db.one("SELECT COUNT(*) AS n FROM facts")["n"]
    assert before > 0

    tape.clear()

    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] == before


def test_a_submission_after_a_clear_is_still_ingested():
    """The silent failure this feature could have introduced.

    Live sequence numbers restart at ``LIVE_BASE`` once the rows are gone. A
    watermark left behind at the old high-water mark would drop every
    subsequent submission as already-seen - ingestion would stop and keep
    reporting success, which is the exact failure the lane column exists to
    prevent.

    Asserted on what ingestion actually does with a specification document: it
    records which version is in force and declines to guess at what the
    document says. So a second submission being taken in is a second version
    being in force, and nothing else would prove it.
    """
    _submit(doc_version="v9")
    tape.clear()

    assert ingest.cursor(tape.LANE_LIVE) == 0

    event = _submit(doc_version="v10")
    assert event.seq == tape.LIVE_BASE
    assert ingest.cursor(tape.LANE_LIVE) >= event.seq

    held = db.one(
        "SELECT value FROM facts WHERE entity_type = 'source_doc'"
        " AND entity_id = ? AND attr = 'version'"
        " ORDER BY recorded_at DESC LIMIT 1", ("DOC-01",))
    assert held is not None and "v10" in held["value"]


def test_a_clear_does_not_let_a_later_submission_tie_with_a_surviving_fact():
    """The silent failure the clear itself could have introduced.

    ``_live_instant`` nudges each submission strictly past the newest live
    event, because the fact store breaks a ``recorded_at`` tie by id - so a tie
    means one of the two silently never becomes the value in force. Clearing
    deletes those events and deliberately keeps the facts they wrote, so the
    anchor has to outlive the rows. It does, in ``runtime_config``.
    """
    first = _submit(doc_version="v9")
    tape.clear()
    second = _submit(doc_version="v10")

    assert second.ts > first.ts, "the instant went backwards across a clear"

    versions = [r["value"] for r in db.query(
        "SELECT value FROM facts WHERE entity_type = 'source_doc'"
        " AND entity_id = 'DOC-01' AND attr = 'version'"
        " ORDER BY recorded_at")]
    assert versions == ['"v9"', '"v10"']


def _submission_for(event) -> str:
    """The submissions row an intake would have written for this event.

    ``append_live`` is the transport and does not record a submission -
    ``sc.estate.intake`` does, and pulling a whole bundle upload in here to get
    one row would test the datapack writers rather than the clear. The columns
    that matter are the two ``clear`` reads: the id, and the events it carried.
    """
    identifier = "SUB-testclear01"
    db.connect().execute(
        "INSERT INTO submissions (id, supplier_id, system_id, kind,"
        " submitted_at, wall_at, event_ids, entity_ids)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (identifier, "SUP-01", "supplier-portal", "DATA_PACK",
         event.ts.isoformat(), event.ts.isoformat(),
         db.dumps([event.id]), db.dumps(["VAR-01B"])))
    db.connect().commit()
    return identifier


def test_clearing_takes_the_open_questions_and_leaves_the_answered_ones():
    """A question about a bundle that no longer exists is unanswerable.

    An *answered* proposal is a different thing entirely: it is a record of
    what a person decided, ``onboarding.history`` reads it back as a prior on
    the next batch, and a reviewer's own past decisions surviving a rewind is
    the point of keeping them at all.
    """
    from sc.onboarding import decide as decide_mod
    from sc.onboarding import suggest as suggest_mod

    event = _submit()
    submission_id = _submission_for(event)

    def proposal(path):
        return suggest_mod.Suggestion(
            entity_id="VAR-01B", attribute_path=path, label=path, dtype="int",
            unit="W", safety_class=False, value=65, confidence=0.4,
            supporters=1, reasons=[])

    open_id = decide_mod.record(submission_id, proposal("specs.power_w"),
                                routed=decide_mod.HUMAN, limit=0.95)
    answered_id = decide_mod.record(submission_id, proposal("specs.mass_g"),
                                    routed=decide_mod.HUMAN, limit=0.95)
    decide_mod.decide(answered_id, actor="gr25", decision=decide_mod.APPROVE)
    # Never a question: written without review, with a fact in force behind it.
    written_id = decide_mod.record(submission_id, proposal("specs.width_mm"),
                                   routed=decide_mod.AUTONOMOUS, limit=0.95)

    counts = tape.clear()

    assert counts["submissions"] == 1
    assert counts["open_questions"] == 1
    assert decide_mod.get(open_id) is None

    held = decide_mod.get(answered_id)
    assert held is not None and held["decision"] == decide_mod.APPROVE

    autonomous = decide_mod.get(written_id)
    assert autonomous is not None, ("an autonomous proposal is a record of a "
                                    "value that was written, not a question")
    assert event.id not in {e.id for e in tape.released(limit=50)}
