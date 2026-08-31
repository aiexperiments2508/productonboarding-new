"""Taking a wrong value down.

A late correction lands against copy that is already live. Between knowing the
value is wrong and having a validated replacement, the wrong value is still on
sale - and for an allergen declaration that gap is the whole problem.

The properties under test are the ones that make hiding it safe: a redaction is
a new fact and never an edit, so what a page showed at two o'clock is still
answerable at four; a channel that cannot recall its artefact is never reported
as redacted; hiding a value does not make the validator think the problem went
away; and neither a rollback nor an unapproved caller can quietly put a
suppressed safety claim back on air.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_redaction.db")

from sc import db  # noqa: E402
from sc.contracts import ApprovalDecision  # noqa: E402
from sc.estate import publication, redaction  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.state import overlay as overlay_mod  # noqa: E402
from sc.state import store  # noqa: E402
from sc.tools import network as network_tools  # noqa: E402
from sc.tools import planning  # noqa: E402

INCIDENT = "INC-RED"
SCENARIO = "SCN-RED"
ENTITY = "VAR-05A"
SAFETY_PATH = "food.allergens.may_contain"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(tape.inject_seq() + 12))
    _open_case()
    yield
    db.close()


def _open_case() -> None:
    now = tape.sim_now().isoformat()
    conn = db.connect()
    conn.execute(
        "INSERT INTO incidents (id, thread_id, opened_at, status, severity,"
        " title, doc) VALUES (?,?,?,'OPEN','HIGH','late allergen change','{}')",
        (INCIDENT, "T-RED", now))
    conn.execute(
        "INSERT INTO scenarios (id, incident_id, name, feasible, doc)"
        " VALUES (?,?,'apply',1,'{}')", (SCENARIO, INCIDENT))
    conn.commit()


def _approve(actor: str = "r.okafor") -> None:
    conn = db.connect()
    conn.execute(
        "INSERT INTO approvals (id, incident_id, scenario_id, decision, actor,"
        " comment, decided_at) VALUES ('APP-RED',?,?,?,?,'',?)",
        (INCIDENT, SCENARIO, str(ApprovalDecision.APPROVE), actor,
         tape.sim_now().isoformat()))
    conn.commit()


def _redact(**kwargs):
    return redaction.redact(INCIDENT, ENTITY, [SAFETY_PATH],
                            actor="r.okafor", reason="peanut handling added",
                            **kwargs)


def _row_for(result, channel_id: str) -> dict:
    return next(r for r in result["systems"] if r["channel_id"] == channel_id)


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def test_a_redaction_without_an_approval_refuses_every_system():
    """Hiding a live claim is safer than replacing one, and it is still a
    decision. Nobody has agreed the value is wrong yet."""
    result = _redact()
    assert result["authorised"] is False
    assert result["redacted"] == 0
    assert result["refused"] == len(result["systems"])
    assert planning.open_redactions() == []


def test_the_approval_that_authorises_a_redaction_is_read_and_never_written():
    """A redaction must not be able to satisfy the resolution gate. If it wrote
    an approvals row, the act of hiding a value would authorise publishing
    whatever replaced it."""
    before = db.one("SELECT COUNT(*) AS n FROM approvals")["n"]
    _approve()
    _redact()
    assert db.one("SELECT COUNT(*) AS n FROM approvals")["n"] == before + 1


def test_a_replayed_redaction_acts_once():
    _approve()
    _redact()
    first = len(planning.open_redactions())
    _redact()
    assert len(planning.open_redactions()) == first


# ---------------------------------------------------------------------------
# What it writes, and what it must not
# ---------------------------------------------------------------------------


def test_a_redaction_is_a_new_fact_and_never_an_edit():
    _approve()
    _redact()
    hidden = planning.open_redactions()
    assert hidden
    listing_id = hidden[0]["listing_id"]
    rows = db.query(
        "SELECT COUNT(*) AS n FROM facts WHERE entity_type = 'listing'"
        " AND entity_id = ? AND attr = ?",
        (listing_id, planning.redaction_attr(SAFETY_PATH)))
    assert rows[0]["n"] == 1


def test_what_a_channel_showed_before_a_redaction_is_still_readable_as_of_then():
    """The audit question is "what was on this page at two o'clock", and an
    edit in place would make it unanswerable."""
    _approve()
    before = tape.sim_now()
    _redact()
    listing_id = planning.open_redactions()[0]["listing_id"]

    from datetime import timedelta

    earlier = before - timedelta(hours=1)
    assert planning.open_redactions([listing_id], as_of=earlier) == []
    assert planning.open_redactions([listing_id]) != []


def test_a_redaction_writes_no_attribute_fact_and_moves_no_published_version():
    """Both would send every in-flight scenario stale against a version nothing
    published, and dead-end the republish this whole sequence exists to allow."""
    _approve()
    before_attrs = db.one(
        "SELECT COUNT(*) AS n FROM facts WHERE entity_type IN"
        " ('variant','product')")["n"]
    before_versions = db.one(
        "SELECT COUNT(*) AS n FROM facts WHERE attr = ?",
        (overlay_mod.ATTR_PUBLISHED_VERSION,))["n"]

    _redact()

    assert db.one("SELECT COUNT(*) AS n FROM facts WHERE entity_type IN"
                  " ('variant','product')")["n"] == before_attrs
    assert db.one("SELECT COUNT(*) AS n FROM facts WHERE attr = ?",
                  (overlay_mod.ATTR_PUBLISHED_VERSION,))["n"] == before_versions


def test_a_redaction_is_invisible_to_the_validator():
    """A channel rule that stopped failing because the wrong value was hidden
    would be reporting that the problem had gone away. It has not: the wrong
    value is still wrong, and the corrected one is not published yet."""
    _approve()
    _redact()
    overlay = overlay_mod.build(tape.sim_now())
    assert not any(str(attr).startswith(planning.REDACTION_PREFIX)
                   for (_entity, attr) in overlay.attr_values)


def test_no_change_set_action_is_emitted_by_a_redaction():
    """``engine.simulate`` skips every check for a withheld listing. A redaction
    routed through a WITHHOLD_CHANNEL action would therefore erase the
    frozen-version violation from the validator while the wrong catalogues were
    still in the world - which is the postmortem this codebase already has."""
    _approve()
    before = db.one("SELECT COUNT(*) AS n FROM committed_actions")["n"]
    _redact()
    assert db.one("SELECT COUNT(*) AS n FROM committed_actions")["n"] == before


# ---------------------------------------------------------------------------
# Per channel
# ---------------------------------------------------------------------------


def test_a_channel_that_cannot_be_recalled_is_never_reported_as_redacted():
    """Two hundred thousand catalogues are in the world. There is nothing to
    take down, and saying otherwise is the one lie that matters here."""
    _approve()
    row = _row_for(_redact(), "CH-PRINT")
    assert row["outcome"] == redaction.ERRATUM
    assert row["redacted"] is False


def test_a_print_channel_gets_an_erratum_obligation_instead_of_a_redaction():
    _approve()
    _redact()
    errata = [o for o in redaction.open_obligations() if o["kind"] == "ERRATUM"]
    assert len(errata) == 1
    assert errata[0]["channel_id"] == "CH-PRINT"
    assert errata[0]["due_by"]


def test_a_shelf_redaction_queues_a_reprint_rather_than_claiming_it_is_done():
    """The label stays wrong in the aisle until somebody walks over with a
    printer."""
    _approve()
    row = _row_for(_redact(), "CH-SHELF")
    assert row["outcome"] == redaction.QUEUED
    assert any(o["kind"] == "REPRINT" for o in redaction.open_obligations())


def test_a_marketplace_withdraws_a_safety_field_rather_than_placeholdering_it():
    """Its own rules forbid the placeholder: the allergen statement is REQUIRED
    and its format is matched against a pattern, so a placeholder would itself
    be a hard violation."""
    _approve()
    row = _row_for(_redact(), "CH-MKT-A")
    assert row["kind"] == redaction.WITHDRAWN


def test_a_search_facet_is_dropped_rather_than_left_indexing_a_wrong_value():
    """A shopper filtering for no-peanuts and being shown peanuts is the harm."""
    _approve()
    row = _row_for(_redact(), "CH-SEARCH")
    assert row["kind"] == redaction.FACET_DROPPED
    assert row["outcome"] == redaction.REDACTED


def test_withdrawing_a_listing_takes_it_off_air_in_the_shape_the_gateway_writes():
    """Reusing the channel gateway's own status convention is what makes every
    existing panel render this with no new code."""
    _approve()
    _redact()
    listing_id = _row_for(_redact(), "CH-WEB")["listings"][0]
    fact = store.get("listing", listing_id, overlay_mod.ATTR_STATUS,
                     tape.sim_now(), tape.sim_now())
    assert fact is not None and fact.value == "WITHHELD"


def test_one_correction_gets_a_different_right_answer_on_each_kind_of_channel():
    """The summary sentence the whole surface exists to be able to say."""
    _approve()
    result = _redact()
    assert result["redacted"] == 4
    assert result["queued"] == 1
    assert result["errata"] == 1
    assert result["refused"] == 0


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------


def test_a_restore_puts_back_what_was_hidden_without_deleting_it():
    _approve()
    _redact()
    listing_id = planning.open_redactions()[0]["listing_id"]
    before = db.one("SELECT COUNT(*) AS n FROM facts WHERE entity_id = ?"
                    " AND attr = ?",
                    (listing_id, planning.redaction_attr(SAFETY_PATH)))["n"]

    redaction.restore(INCIDENT, ENTITY, [SAFETY_PATH], actor="r.okafor")

    after = db.one("SELECT COUNT(*) AS n FROM facts WHERE entity_id = ?"
                   " AND attr = ?",
                   (listing_id, planning.redaction_attr(SAFETY_PATH)))["n"]
    assert after == before + 1
    assert not any(r["listing_id"] == listing_id
                   for r in planning.open_redactions())


def test_a_restore_refuses_where_the_redaction_was_an_erratum():
    """You cannot un-print a catalogue, so there was never anything hidden
    there to put back. The same asymmetry ``revert`` already models for a
    channel that was never sent to."""
    _approve()
    _redact()
    row = _row_for(
        redaction.restore(INCIDENT, ENTITY, [SAFETY_PATH], actor="r.okafor"),
        "CH-PRINT")
    assert row["outcome"] == redaction.REFUSED
    assert "never hidden" in row["reason"]


def test_a_rollback_does_not_undo_a_safety_redaction():
    """``_retract_published`` retracts by matching ``agent='commit_plan'``. The
    redaction agent is what keeps a rollback of the *publish* from silently
    putting a suppressed allergen claim back on air."""
    _approve()
    _redact()
    hidden_before = len(planning.open_redactions())

    planning.rollback(INCIDENT, SCENARIO, reason="reverting the publish")

    assert len(planning.open_redactions()) == hidden_before


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def test_every_redaction_lands_in_the_ledger_with_actor_reason_and_system():
    """One row per listing per field, not one row per call: the index is on
    (entity_type, entity_id), and a row carrying a JSON array of six systems is
    not queryable by system."""
    _approve()
    result = _redact()
    rows = db.query("SELECT actor, entity_id, detail FROM audit"
                    " WHERE action = 'REDACT'")
    assert len(rows) == sum(len(r["listings"]) for r in result["systems"]
                            if r["outcome"] == redaction.REDACTED)
    for row in rows:
        detail = db.loads(row["detail"])
        assert row["actor"] == "r.okafor"
        assert detail["attribute_path"] == SAFETY_PATH
        assert detail["reason"]


def test_an_erratum_and_a_reprint_are_recorded_under_their_own_verbs():
    _approve()
    _redact()
    actions = {r["action"] for r in db.query("SELECT action FROM audit")}
    assert "ERRATUM_OPEN" in actions
    assert "REPRINT_QUEUE" in actions


def test_an_obligation_stays_open_until_somebody_discharges_it():
    _approve()
    _redact()
    obligation = next(o for o in redaction.open_obligations()
                      if o["kind"] == "ERRATUM")

    result = redaction.discharge(obligation["id"], actor="print.ops",
                                 evidence="erratum card in issue 34")
    assert result["discharged"] is True
    assert not any(o["id"] == obligation["id"]
                   for o in redaction.open_obligations())
    assert "ERRATUM_DISCHARGE" in {r["action"] for r in
                                   db.query("SELECT action FROM audit")}


def test_a_system_cannot_discharge_another_systems_obligation():
    """A marketplace has no business closing the print channel's errata."""
    _approve()
    _redact()
    obligation = next(o for o in redaction.open_obligations()
                      if o["kind"] == "ERRATUM")
    result = redaction.discharge(obligation["id"], actor="mkt.ops",
                                 system_id="pub-ch-mkt-a")
    assert result["discharged"] is False


def test_planning_a_redaction_changes_nothing():
    _approve()
    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(ENTITY)
    rows = redaction.plan_redaction(trace, base, attribute_paths=[SAFETY_PATH])

    assert len(rows) == len(publication.blast_to_systems(trace, base))
    assert planning.open_redactions() == []
    assert redaction.open_obligations() == []


# ---------------------------------------------------------------------------
# The release gate
# ---------------------------------------------------------------------------


def test_a_release_decision_is_not_written_to_the_approvals_table():
    """``commit_plan`` reads the newest approval and tests only that it is
    APPROVE. A release recorded there would satisfy the resolution gate on its
    own - the second approval would have removed the first."""
    before = db.one("SELECT COUNT(*) AS n FROM approvals")["n"]
    planning.record_release(INCIDENT, SCENARIO, "APPROVE", "r.okafor")
    assert db.one("SELECT COUNT(*) AS n FROM approvals")["n"] == before
    assert db.one("SELECT COUNT(*) AS n FROM releases")["n"] == 1


def test_a_release_approval_alone_does_not_publish_an_unapproved_resolution():
    """The regression test for the whole design of the second gate."""
    planning.record_release(INCIDENT, SCENARIO, "APPROVE", "r.okafor")
    result = planning.commit_plan(INCIDENT, SCENARIO, actions=[])
    assert result.get("committed") is not True
    assert result["error"] == "not_approved"


def _republish_action(path: str = "food.fibre_g", old: object = 7.2,
                      new: object = 7.4) -> list[dict]:
    """A change set that republishes one attribute on the staged variant.

    Defaults to an ordinary figure rather than the allergen. The allergen is
    the *subject* of the redaction, and a change set that also moved it would
    be stopped by the third refusal before ever reaching the fourth - which is
    correct, and would mean these tests were watching a different gate from the
    one they name.
    """
    return [{
        "id": "ACT-1",
        "kind": "SET_ATTRIBUTE",
        "entity_id": ENTITY,
        "attribute_path": path,
        "old_value": old,
        "new_value": new,
        "rationale": "supplier revision",
        "source": {"doc_id": "DOC-05", "version": "v1"},
    }]


def test_publishing_to_a_listing_holding_a_safety_redaction_is_refused():
    """The second gate, doing its job.

    Hiding a wrong claim and publishing over the listing that is hiding it are
    different decisions. The reviewer who agreed the allergen line was wrong
    has not thereby agreed that the page may go back on air - and the listing
    is holding a safety field back while this change would republish it.
    """
    _approve()
    _redact()

    result = planning.commit_plan(INCIDENT, SCENARIO, _republish_action())

    assert result.get("committed") is not True
    assert result["error"] == "not_released"
    assert "release decision is required" in result["detail"]
    assert result["redactions"], "the refusal should name what is being held"


def test_the_same_publish_goes_through_once_the_release_is_recorded():
    """And the gate is a gate rather than a wall."""
    _approve()
    _redact()
    assert planning.commit_plan(
        INCIDENT, SCENARIO, _republish_action())["error"] == "not_released"

    planning.record_release(INCIDENT, SCENARIO, "APPROVE", "d.laurent")

    result = planning.commit_plan(INCIDENT, SCENARIO, _republish_action())
    assert result.get("error") != "not_released"


def test_a_rejected_release_does_not_open_the_gate():
    _approve()
    _redact()
    planning.record_release(INCIDENT, SCENARIO, "REJECT", "d.laurent",
                            comment="wording still wrong")
    assert planning.commit_plan(
        INCIDENT, SCENARIO, _republish_action())["error"] == "not_released"


def test_a_redaction_of_an_ordinary_field_does_not_hold_a_publish():
    """Only safety-class fields hold a republish. A hidden marketing figure is
    a tidiness problem; a hidden allergen declaration is the reason the whole
    sequence exists."""
    _approve()
    redaction.redact(INCIDENT, ENTITY, ["food.fibre_g"], actor="r.okafor",
                     reason="figure under review")

    result = planning.commit_plan(INCIDENT, SCENARIO, _republish_action())
    assert result.get("error") != "not_released"


def test_an_open_allergen_violation_is_still_reported_before_the_release_gate():
    """Ordering, and it is deliberate.

    The fourth refusal was added last so that every existing failure still
    reports the message it has always reported. A change set that moves the
    allergen while the copy has not caught up is a safety hold, and calling it
    an unreleased publish would send a reviewer to the wrong screen.
    """
    _approve()
    _redact()
    result = planning.commit_plan(
        INCIDENT, SCENARIO,
        _republish_action(SAFETY_PATH, ["milk"], ["milk", "peanuts"]))
    assert result["error"] == "safety_hold"


def test_a_release_is_recorded_against_the_person_who_took_it():
    planning.record_release(INCIDENT, SCENARIO, "APPROVE", "d.laurent",
                            comment="corrected wording checked")
    row = db.one("SELECT * FROM releases WHERE incident_id = ?", (INCIDENT,))
    assert row["actor"] == "d.laurent"
    assert row["decision"] == "APPROVE"
    assert "RELEASE" in {r["action"] for r in db.query("SELECT action FROM audit")}
