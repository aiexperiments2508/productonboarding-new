"""Graph branching.

A correction run is not one shape. A notice that restates a value nobody
publishes, a notice two supplier documents disagree about, and a notice whose
affected variant nothing in the record settles are three different problems,
and these tests cover the predicates that send each of them somewhere different
- plus the property that matters more than any of them: the routing is a pure
function of state, so the same correction always takes the same path. Variety,
not randomness - the trace hash and the audit trail both depend on a run being
reproducible.

The routers are tested directly rather than through a full run. A router is a
one-line function over state, and driving the whole graph to exercise one
``if`` would be slow and would obscure which condition actually fired.
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_PATH", "data/test_branches.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

import pytest  # noqa: E402

from sc.contracts import CorrectionKind  # noqa: E402
from sc.graph import branches  # noqa: E402
from sc.graph import build as graph_build  # noqa: E402
from sc.graph.state import RESET  # noqa: E402

CONFLICT = str(CorrectionKind.SOURCE_CONFLICT)


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def test_immateriality_is_read_from_the_verdict_not_re_derived():
    """triage overrides the model deterministically when a safety-class
    attribute or a regulated product is in scope. A predicate that decided
    materiality for itself here would be a second opinion with the authority to
    route past that override."""
    assert branches.is_immaterial({"material": False})
    assert not branches.is_immaterial({"material": True})
    assert branches.is_immaterial({}), "an unclassified run is not material yet"


def test_precedent_needs_a_matched_incident():
    assert branches.has_precedent({"prior_incidents": ["INC-2026-002"]})
    assert not branches.has_precedent({"prior_incidents": []})
    assert not branches.has_precedent({})


def test_an_open_source_conflict_is_a_question_for_the_supplier():
    """Two documents asserting different values for one field. POL-002 decides
    which stands for now, which is not the same as deciding which is true."""
    state = {"signals": [{"id": "SIG-1", "kind": CONFLICT},
                         {"id": "SIG-2", "kind": "SPEC_CORRECTION"}]}
    assert branches.sources_conflict(state)


def test_a_scope_no_reading_can_settle_is_the_same_question():
    """The quieter half of the same branch: every reading the record supports
    came back below the floor, which is the honest form of "nothing on file says
    which variant this applies to"."""
    below = branches.SCOPE_CONFIDENCE_FLOOR - 0.01
    assert branches.sources_conflict({"scope_candidates": [{"confidence": below},
                                                           {"confidence": 0.1}]})


def test_a_confident_reading_settles_the_scope():
    above = branches.SCOPE_CONFIDENCE_FLOOR + 0.01
    assert not branches.sources_conflict(
        {"scope_candidates": [{"confidence": above}, {"confidence": 0.1}]})


def test_no_readings_at_all_is_not_a_disagreement():
    """An absent candidate list is not a claim about confidence. Reading it as
    one would send every run with nothing to resolve to the supplier."""
    assert not branches.sources_conflict({"scope_candidates": []})
    assert not branches.sources_conflict({})


def _option(actions: int = 1, violations: tuple[dict, ...] = ()) -> dict:
    return {"scenario_id": f"SC-{actions}-{len(violations)}",
            "delta": {"actions": [{"kind": "SET_ATTRIBUTE"}] * actions},
            "violations": list(violations)}


def _hard(constraint: str) -> dict:
    return {"constraint": constraint, "severity": "HARD"}


def test_nothing_publishable_needs_candidates_to_judge():
    assert branches.nothing_publishable({"ranked": []})
    assert branches.nothing_publishable({})


def test_a_candidate_the_content_leg_could_still_fix_is_publishable():
    """Deliberately not "no candidate is feasible".

    At rank the candidates are attribute changes and nothing else - every asset
    that quoted the old figure is still stale - so on any correction that
    matters nothing is feasible yet. Routing on feasibility here would send
    every real run to a reviewer with the content work undone.
    """
    blocked_but_fixable = _option(violations=(_hard("stale_literal"),
                                              _hard("citation_missing")))
    assert not branches.nothing_publishable({"ranked": [blocked_but_fixable]})


def test_a_candidate_no_rewrite_can_clear_is_not_publishable():
    """A source version that moved needs re-extracting, not rewriting."""
    assert branches.nothing_publishable(
        {"ranked": [_option(violations=(_hard("stale_version"),))]})
    assert branches.nothing_publishable(
        {"ranked": [_option(violations=(_hard("publish_conflict"),))]})


def test_one_workable_candidate_is_enough():
    ranked = [_option(violations=(_hard("stale_version"),)),
              _option(violations=(_hard("stale_literal"),))]
    assert not branches.nothing_publishable({"ranked": ranked})


def test_a_candidate_that_does_nothing_publishes_nothing():
    """Do-nothing carries no violations, so counting it as workable would
    report a blocked run as publishable."""
    assert branches.nothing_publishable({"ranked": [_option(actions=0)]})


def test_publish_conflict_is_a_race_and_a_stale_version_is_another():
    assert branches.publish_conflicted({"commit_result": {"error": "conflict"}})
    assert branches.publish_conflicted({"commit_result": {"error": "stale_version"}})


def test_a_refusal_another_plan_would_reproduce_is_not_a_race():
    """No approval on file and an open safety hold are verdicts. Re-planning
    would reproduce them exactly, so the cycle must not fire."""
    assert not branches.publish_conflicted({"commit_result": {"error": "not_approved"}})
    assert not branches.publish_conflicted({"commit_result": {"error": "safety_hold"}})
    assert not branches.publish_conflicted({"commit_result": {"committed": True}})
    assert not branches.publish_conflicted({})


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_immaterial_corrections_are_parked_not_propagated():
    assert graph_build._route_after_triage({"material": False}) == "ack_and_park"
    assert graph_build._route_after_triage({"material": True}) == "resolve_scope"


def test_a_disagreement_outranks_a_postmortem():
    """Both exceptions can hold at once, and the order is not arbitrary: a
    question a human has to send is a fact about *this* correction, where a
    resemblance to a past incident is reading material for the writer."""
    both = {"signals": [{"kind": CONFLICT}],
            "prior_incidents": ["INC-2026-002"]}
    assert graph_build._route_after_scope(both) == "supplier_clarification"
    assert graph_build._route_after_scope(
        {"prior_incidents": ["INC-2026-002"]}) == "apply_precedent"
    assert graph_build._route_after_scope({}) == "plan_candidates"


def test_a_correction_with_no_candidate_still_reaches_a_reviewer():
    """An empty Send list would leave the superstep with no tasks and strand
    the run short of close, so the empty result is routed onward as a finding."""
    assert graph_build._route_after_candidates({"scenarios": []}) == "rank"


def test_nothing_publishable_goes_to_the_blocked_review():
    assert graph_build._route_after_rank({"ranked": []}) == "blocked_review"
    assert graph_build._route_after_rank(
        {"ranked": [_option(violations=(_hard("stale_literal"),))]}) == "propagate"


def test_a_run_with_no_recommendation_closes_rather_than_asking():
    assert graph_build._route_after_recommend({"recommendation": {}}) == "close"
    assert graph_build._route_after_recommend(
        {"recommendation": {"scenario_id": "SC-1"}}) == "request_approval"


def test_a_refused_publish_plans_again():
    """The one cycle in the graph, read off the status rather than the
    predicate: by the time this runs the retry has been spent, and the
    predicate would be answering for the next attempt."""
    assert graph_build._route_after_verify(
        {"status": branches.REPLAN_AFTER_CONFLICT}) == "plan_candidates"
    assert graph_build._route_after_verify(
        {"status": branches.REPLAN_AFTER_STALE}) == "plan_candidates"
    assert graph_build._route_after_verify({"status": "PUBLISHED"}) == "close"
    assert graph_build._route_after_verify({"status": "PUBLISH_REFUSED"}) == "close"


# ---------------------------------------------------------------------------
# The retry cycle, end to end through the node that spends the budget
# ---------------------------------------------------------------------------


def test_a_lost_publish_lock_re_plans_and_clears_the_old_verdicts():
    """Leaving the first attempt's verdicts in sim_results would put options
    scored against the world before the conflict on the same comparison table
    as options scored after it."""
    update = branches.verify_publish(
        {"status": branches.REPLAN_AFTER_CONFLICT, "publish_retries": 1,
         "commit_result": {"error": "conflict", "conflicts": ["CH-WEB:PRD-01"]}})

    assert update["status"] == branches.REPLAN_AFTER_CONFLICT
    assert update["sim_results"] == [RESET]
    assert graph_build._route_after_verify(update) == "plan_candidates"


def test_a_later_source_version_spends_one_retry():
    update = branches.verify_publish(
        {"commit_result": {"error": "stale_version", "violations": []},
         "publish_retries": 0})

    assert update["publish_retries"] == 1
    assert update["status"] == branches.REPLAN_AFTER_STALE
    assert update["sim_results"] == [RESET]
    assert graph_build._route_after_verify(update) == "plan_candidates"


def test_a_second_retry_is_a_queue_not_a_recovery():
    update = branches.verify_publish(
        {"commit_result": {"error": "stale_version", "violations": []},
         "publish_retries": branches.MAX_PUBLISH_RETRIES})

    assert update["status"] == "STALE_UNRESOLVED"
    assert "sim_results" not in update
    assert graph_build._route_after_verify(update) == "close"


def test_a_published_run_does_not_re_enter_the_cycle():
    update = branches.verify_publish(
        {"status": "PUBLISHED", "commit_result": {"committed": True,
                                                  "actions": [1, 2], "locks": [1]}})
    assert "status" not in update, "a terminal status must be left alone"
    assert graph_build._route_after_verify({"status": "PUBLISHED"}) == "close"


# ---------------------------------------------------------------------------
# The property the whole design rests on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("router", [
    graph_build._route_after_triage,
    graph_build._route_after_scope,
    graph_build._route_after_rank,
    graph_build._route_after_recommend,
    graph_build._route_after_verify,
])
def test_routing_is_deterministic(router):
    """Same state, same destination, every time.

    The point of branching here is that different corrections take different
    paths - not that the same correction takes a different path on Tuesday. A
    graph that rolled dice would trade the reproducibility the audit trail
    depends on for the appearance of sophistication.
    """
    state = {
        "material": True,
        "signals": [{"id": "SIG-1", "kind": CONFLICT},
                    {"id": "SIG-2", "kind": "ALLERGEN_CHANGE"}],
        "scope_candidates": [{"confidence": 0.3}, {"confidence": 0.67}],
        "prior_incidents": ["INC-2026-002"],
        "ranked": [_option(violations=(_hard("stale_literal"),)),
                   _option(violations=(_hard("stale_version"),))],
        "recommendation": {"scenario_id": "SC-1"},
        "status": branches.REPLAN_AFTER_STALE,
    }
    first = router(state)
    assert all(router(state) == first for _ in range(20))


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


def test_the_graph_actually_branches():
    """Guards against the topology quietly collapsing back to a line."""
    graph = graph_build.build_graph().compile().get_graph()

    conditional = {(e.source, e.target) for e in graph.edges if e.conditional}
    sources = {source for source, _ in conditional}

    assert len(sources) >= 6, f"only {len(sources)} branch points: {sources}"
    for node in ("apply_precedent", "supplier_clarification", "blocked_review",
                 "verify_publish", "ack_and_park"):
        assert node in graph.nodes, f"{node} missing from the graph"


def test_both_scope_exceptions_rejoin_the_main_line():
    """Additive, not terminal. A supplier who has been asked a question has not
    answered it yet, and the wrong figure is live on six channels meanwhile."""
    edges = {(e.source, e.target)
             for e in graph_build.build_graph().compile().get_graph().edges}

    assert ("supplier_clarification", "plan_candidates") in edges
    assert ("apply_precedent", "plan_candidates") in edges
    assert ("blocked_review", "recommend") in edges


def test_the_publish_conflict_cycle_exists():
    """A graph with no cycle cannot recover from losing a race."""
    edges = {(e.source, e.target)
             for e in graph_build.build_graph().compile().get_graph().edges}
    assert ("verify_publish", "plan_candidates") in edges
    assert ("publish", "verify_publish") in edges


def test_the_approval_gate_can_reach_both_outcomes():
    """request_approval routes with Command rather than a static edge, so the
    declared destinations are what tells a renderer it is not a dead end."""
    edges = {(e.source, e.target)
             for e in graph_build.build_graph().compile().get_graph().edges}
    assert ("request_approval", "publish") in edges
    assert ("request_approval", "close") in edges
