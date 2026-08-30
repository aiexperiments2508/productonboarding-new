"""Safe-orchestration controls.

The brief asks for permissions, approvals, idempotency, retries and
partial-failure recovery, and the finale explicitly requires that a correction
never be published twice or published stale. These tests pin the mechanisms
that deliver that:

*   a partial unique index makes HARD publish locks exclusive,
*   idempotency keys make replayed tool calls no-ops,
*   ``commit_plan`` refuses to act without a recorded approval, refuses once a
    later source version is in force, and refuses while a safety or allergen
    declaration is still open.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("DB_PATH", "data/test_orchestration.db")

from sc import db  # noqa: E402
from sc.contracts import ApprovalDecision, Provenance, ProvenanceKind  # noqa: E402
from sc.state import store  # noqa: E402
from sc.tools import planning  # noqa: E402

INCIDENT = "INC-TEST"
SCENARIO_A = "SC-A"
SCENARIO_B = "SC-B"
BATCH_DATE = "2026-09-29"
RESOURCE = "CH-MKT-A:PRD-01"

DOC01_V2 = {"doc_id": "DOC-01", "version": "v2",
            "excerpt": "The rated power of the AeroPure 300 is 65 W."}
DOC04_V2 = {"doc_id": "DOC-04", "version": "v2",
            "excerpt": "Shared line: may contain peanuts."}

# The main inject, scoped to the Max: 65 W, published to Marketplace A.
DELTA = {
    "id": "CS-1",
    "scope": {"level": "VARIANT", "entities": ["VAR-01B"], "confidence": 0.82},
    "actions": [{
        "kind": "SET_ATTRIBUTE", "id": "a1", "entity_id": "VAR-01B",
        "attribute_path": "specs.power_w", "old_value": 45, "new_value": 65,
        "unit": "W", "confidence": 0.93, "source": DOC01_V2,
        "resource_id": RESOURCE, "bucket_date": BATCH_DATE,
    }],
}


def _allergen_delta(confidence: float) -> dict:
    """Scenario two, which cannot be published as it stands: nothing on the
    prepared pages declares peanuts yet."""
    return {
        "id": "CS-2",
        "scope": {"level": "VARIANT", "entities": ["VAR-02A"]},
        "actions": [{
            "kind": "SET_ATTRIBUTE", "id": "a1", "entity_id": "VAR-02A",
            "attribute_path": "food.allergens.may_contain",
            "old_value": [], "new_value": ["peanuts"], "confidence": confidence,
            "source": DOC04_V2,
            "resource_id": "CH-MKT-A:PRD-02", "bucket_date": BATCH_DATE,
        }],
    }


@pytest.fixture(autouse=True)
def fresh_db():
    db.init_db(drop=True)
    yield
    db.close()


def _approve(scenario_id: str, decision=ApprovalDecision.APPROVE) -> None:
    conn = db.connect()
    conn.execute(
        "INSERT INTO incidents (id, thread_id, opened_at, status, severity,"
        " title, doc) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
        (INCIDENT, "T-1", datetime.now().isoformat(), "AWAITING_APPROVAL",
         "HIGH", "test", "{}"))
    conn.execute(
        "INSERT INTO scenarios (id, incident_id, name, doc)"
        " VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING",
        (scenario_id, INCIDENT, "test", "{}"))
    conn.execute(
        "INSERT INTO approvals (id, incident_id, scenario_id, decision, actor,"
        " comment, decided_at) VALUES (?,?,?,?,?,?,?)",
        (f"APP-{scenario_id}", INCIDENT, scenario_id, str(decision), "planner",
         "", datetime.now().isoformat()))
    conn.commit()


def _lands(version: str, value: int = 65) -> None:
    """A supplier document version in force for the Max's wattage."""
    store.record("variant", "VAR-01B", "specs.power_w", value,
                 valid_from=datetime(2026, 9, 29),
                 recorded_at=datetime(2026, 9, 29),
                 provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                       source_id=f"DOC-01:{version}"))


# ---------------------------------------------------------------------------
# Conflicting republishing - the finale's explicit requirement
# ---------------------------------------------------------------------------


def test_two_hard_locks_on_the_same_channel_product_day_conflict():
    first = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT,
                                     SCENARIO_A, "HARD")
    second = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT,
                                      SCENARIO_B, "HARD")

    assert first["reserved"] is True
    assert second["reserved"] is False
    assert second["error"] == "conflict"
    assert second["held_by"]["scenario_id"] == SCENARIO_A


def test_conflict_names_the_resource_and_the_holder():
    planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT, SCENARIO_A, "HARD")
    clash = planning.reserve_publish(RESOURCE, BATCH_DATE, "INC-OTHER",
                                     SCENARIO_B, "HARD")

    violation = clash["violation"]
    assert violation["constraint"] == "publish_conflict"
    assert violation["entity_id"] == RESOURCE
    assert violation["channel_id"] == "CH-MKT-A"
    assert SCENARIO_A in violation["detail"]


def test_soft_holds_do_not_block_each_other():
    """Resolutions explore in parallel; only publication is exclusive."""
    a = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT, SCENARIO_A)
    b = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT, SCENARIO_B)
    assert a["reserved"] and b["reserved"]


def test_different_batch_dates_do_not_conflict():
    a = planning.reserve_publish(RESOURCE, "2026-09-29", INCIDENT, SCENARIO_A,
                                 "HARD")
    b = planning.reserve_publish(RESOURCE, "2026-09-30", INCIDENT, SCENARIO_B,
                                 "HARD")
    assert a["reserved"] and b["reserved"]


def test_second_publish_of_the_same_listing_is_refused():
    """The end-to-end version: two approved resolutions, one channel batch."""
    _approve(SCENARIO_A)
    _approve(SCENARIO_B)

    first = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)
    second = planning.commit_plan(INCIDENT, SCENARIO_B, DELTA)

    assert first["committed"] is True
    assert second["committed"] is False
    assert second["error"] == "conflict"


def test_released_lock_frees_the_batch():
    held = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT, SCENARIO_A,
                                    "HARD")
    planning.release_reservation(held["reservation_id"])
    retry = planning.reserve_publish(RESOURCE, BATCH_DATE, INCIDENT, SCENARIO_B,
                                     "HARD")
    assert retry["reserved"] is True


# ---------------------------------------------------------------------------
# Idempotency - the event plane is at-least-once
# ---------------------------------------------------------------------------


def test_replayed_commit_returns_the_original_result():
    _approve(SCENARIO_A)
    key = "commit:INC-TEST:SC-A"

    first = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                 idempotency_key=key)
    second = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                  idempotency_key=key)

    assert first["committed"] is True
    assert second["committed"] is True
    assert second["idempotent_replay"] is True

    rows = db.query("SELECT * FROM committed_actions WHERE incident_id = ?",
                    (INCIDENT,))
    assert len(rows) == 1, "a replayed publish must not act twice"


def test_distinct_keys_are_not_deduplicated():
    _approve(SCENARIO_A)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA, idempotency_key="k1")
    second = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                  idempotency_key="k2")
    assert "idempotent_replay" not in second


def test_failed_calls_are_not_cached_as_results():
    """A refusal must stay refusable - caching it would make a later, properly
    approved retry silently fail."""
    key = "publish:once"
    refused = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                   idempotency_key=key)
    assert refused["committed"] is False

    _approve(SCENARIO_A)
    retry = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                 idempotency_key=key)
    assert retry["committed"] is True


# ---------------------------------------------------------------------------
# Approval gating
# ---------------------------------------------------------------------------


def test_commit_without_approval_is_refused():
    result = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)
    assert result["committed"] is False
    assert result["error"] == "not_approved"


def test_commit_after_rejection_is_refused():
    _approve(SCENARIO_A, ApprovalDecision.REJECT)
    result = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)
    assert result["committed"] is False
    assert "REJECT" in result["detail"]


def test_approved_commit_writes_an_audit_trail():
    _approve(SCENARIO_A)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)

    rows = db.query("SELECT * FROM audit WHERE action = 'COMMIT'")
    assert len(rows) == 1
    provenance = db.loads(rows[0]["provenance"])
    assert provenance["kind"] == "COMMITTED"


def test_a_commit_records_what_went_live():
    """The audit trail has to say what each channel actually received, so the
    published value is a COMMITTED fact citing the version it came from."""
    _approve(SCENARIO_A)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)

    value = db.one("SELECT * FROM facts WHERE entity_id = 'VAR-01B'"
                   " AND attr = 'specs.power_w'")
    assert db.loads(value["value"]) == 65
    assert db.loads(value["provenance"])["kind"] == "COMMITTED"
    assert db.loads(value["provenance"])["source_id"] == "DOC-01:v2"

    published = db.query("SELECT * FROM facts WHERE attr = ?",
                         ("published.specs.power_w",))
    assert {r["entity_id"] for r in published} == {"LST-05", "LST-06", "LST-07",
                                                   "LST-08"}


# ---------------------------------------------------------------------------
# The stale-version gate - the finale
# ---------------------------------------------------------------------------


def test_publish_is_refused_once_a_later_source_version_is_in_force():
    """A print batch prepared under DOC-01 v2 must not go out after v3 has
    landed, however good it looked when it was approved."""
    _approve(SCENARIO_A)
    _lands("v3")

    result = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                  as_of="2026-10-03T00:00:00")

    assert result["committed"] is False
    assert result["error"] == "stale_version"
    breach = result["violations"][0]
    assert breach["constraint"] == "stale_version"
    assert breach["entity_id"] == "VAR-01B:specs.power_w"
    assert breach["severity"] == "HARD"
    assert breach["required"] == 3.0 and breach["available"] == 2.0
    assert "revalidated" in breach["detail"]


def test_a_refused_publish_takes_no_lock_and_is_on_the_record():
    """Fail closed: the batch stays free for the revalidated resolution, and
    the refusal is a row rather than an absence."""
    _approve(SCENARIO_A)
    _lands("v3")
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                         as_of="2026-10-03T00:00:00")

    assert planning.open_reservations() == []
    refusals = db.query("SELECT * FROM audit WHERE action = 'REFUSE'")
    assert len(refusals) == 1
    assert db.loads(refusals[0]["detail"])["reason"] == "stale_version"


def test_the_source_version_the_resolution_cites_still_publishes():
    _approve(SCENARIO_A)
    _lands("v2")

    result = planning.commit_plan(INCIDENT, SCENARIO_A, DELTA,
                                  as_of="2026-10-03T00:00:00")
    assert result["committed"] is True


# ---------------------------------------------------------------------------
# The safety gate
# ---------------------------------------------------------------------------


def test_publish_is_refused_while_a_safety_violation_is_open():
    """An allergen the model is 62% sure of is not a fact, and no approval
    turns it into one."""
    _approve(SCENARIO_A)

    result = planning.commit_plan(INCIDENT, SCENARIO_A, _allergen_delta(0.62))

    assert result["committed"] is False
    assert result["error"] == "safety_hold"
    assert "safety_confidence" in {v["constraint"] for v in result["violations"]}
    assert planning.open_reservations() == []


def test_publish_is_refused_while_an_allergen_declaration_is_open():
    """Confident is not the same as declared: the prepared pages still do not
    mention peanuts anywhere."""
    _approve(SCENARIO_A)

    result = planning.commit_plan(INCIDENT, SCENARIO_A, _allergen_delta(0.95))

    assert result["committed"] is False
    assert result["error"] == "safety_hold"
    assert {v["constraint"] for v in result["violations"]} == {
        "allergen_declaration"}
    assert all(v["severity"] == "HARD" for v in result["violations"])


# ---------------------------------------------------------------------------
# Ranking - safety is a pre-sort, not a weight
# ---------------------------------------------------------------------------


def test_a_safety_flag_outranks_any_weighting():
    def result(delta_id, safety, ready):
        return {"delta_id": delta_id, "feasible": True,
                "kpis": {"listings_ready_pct": ready, "completeness_pct": 100.0,
                         "fields_affected": 1, "republish_steps": 1,
                         "safety_flags": safety}}

    flagged = result("CS-FLAGGED", 1, 100.0)
    clean = result("CS-CLEAN", 0, 40.0)
    ranked = planning._score([flagged, clean], {"readiness": 1.0})

    assert [r["delta_id"] for r in ranked] == ["CS-CLEAN", "CS-FLAGGED"]
    assert ranked[0]["score"] < ranked[1]["score"], "and not because it scored"


# ---------------------------------------------------------------------------
# Rollback - partial-failure recovery
# ---------------------------------------------------------------------------


def test_rollback_releases_locks_and_reverses_actions():
    _approve(SCENARIO_A)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)

    result = planning.rollback(INCIDENT, SCENARIO_A, reason="v3 landed")

    assert result["rolled_back"] is True
    assert result["actions_reversed"] == 1
    assert db.one("SELECT status FROM reservations WHERE resource_id = ?",
                  (RESOURCE,))["status"] == "RELEASED"


def test_rollback_retracts_what_was_published():
    """Releasing the lock is not unpublishing.

    An as-of read taken after a rollback must not still return the value the
    channel has been told to stop showing - and one taken while it was live
    still has to, because it was.
    """
    _approve(SCENARIO_A)
    live = datetime(2026, 9, 29, 9, 0)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA, as_of=live.isoformat())
    assert store.get_value("variant", "VAR-01B", "specs.power_w",
                           as_of_valid=live, as_of_recorded=live) == 65

    result = planning.rollback(INCIDENT, SCENARIO_A, reason="v3 landed")

    assert result["retracted"], "the published facts are retracted, not deleted"
    after = datetime(2026, 10, 5)
    # What is in force now is what the publish displaced - the 45 W the
    # prepared content stands on - and the channel holds no published value.
    assert store.get_value("variant", "VAR-01B", "specs.power_w",
                           as_of_valid=after, as_of_recorded=after) == 45
    assert store.get_value("listing", "LST-06", "published.specs.power_w",
                           as_of_valid=after, as_of_recorded=after) is None
    # What was known while it was live is untouched: it did go out.
    assert store.get_value("variant", "VAR-01B", "specs.power_w",
                           as_of_valid=live, as_of_recorded=live) == 65


def test_a_repeated_rollback_retracts_nothing_twice():
    _approve(SCENARIO_A)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)
    planning.rollback(INCIDENT, SCENARIO_A)

    assert planning.rollback(INCIDENT, SCENARIO_A)["retracted"] == []


def test_the_batch_is_reusable_after_rollback():
    """Rollback must genuinely free the lock, not just mark a flag."""
    _approve(SCENARIO_A)
    _approve(SCENARIO_B)
    planning.commit_plan(INCIDENT, SCENARIO_A, DELTA)
    planning.rollback(INCIDENT, SCENARIO_A)

    retry = planning.commit_plan(INCIDENT, SCENARIO_B, DELTA)
    assert retry["committed"] is True


def test_proposal_surfaces_conflicts_before_approval():
    """Conflicts belong at proposal time, not after a reviewer has approved
    something unpublishable."""
    planning.reserve_publish(RESOURCE, BATCH_DATE, "INC-OTHER", "SC-X", "HARD")
    proposal = planning.propose_change(INCIDENT, SCENARIO_A, DELTA)

    assert proposal["proposed"] is False
    assert len(proposal["conflicts"]) == 1
