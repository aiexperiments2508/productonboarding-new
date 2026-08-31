"""Re-planning and the investigator's evidence desk.

Both features exist because the brief asks for them in particular terms, so the
tests are written against those terms rather than against the implementation: a
revision must keep the thread, carry the superseded readings forward and report
what moved; the evidence desk must refuse anything outside its allowlist. The
graph tests run with the gateway deliberately unreachable, and so do these -
none of this may depend on a model being available.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_replan.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.graph import evidence  # noqa: E402
from sc.graph.nodes import _carry_forward, _plan_diff  # noqa: E402
from sc.graph.state import RESET, merge_signals, resettable_add  # noqa: E402
from sc.mcp import registry as mcp_registry  # noqa: E402
from sc.rag import index as rag_index  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402

# The purifier correction as the extractor hands it to the desk, and the blast
# radius the lineage walk measured for it.
POWER_SIGNAL = {"id": "SIG-1", "kind": "SPEC_CORRECTION", "entities": ["VAR-01B"],
                "attribute_paths": ["specs.power_w"],
                "source": {"doc_id": "DOC-01", "version": "v2"}}
ALLERGEN_SIGNAL = {"id": "SIG-2", "kind": "ALLERGEN_CHANGE",
                   "entities": ["VAR-02A"],
                   "attribute_paths": ["food.allergens.may_contain"],
                   "source": {"doc_id": "DOC-04", "version": "v2"}}
BLAST = {"affected": {"channels": ["CH-MKT-A", "CH-MKT-B", "CH-PRINT", "CH-SHELF",
                                   "CH-WEB"]}}


@pytest.fixture
def seeded():
    """A database for the tests that actually execute evidence tools.

    Requested rather than autouse, and function-scoped rather than module-
    scoped: conftest pins DB_PATH per test with a function-scoped fixture, so a
    module-scoped seed would build its schema in whichever database the previous
    module left selected. Most of this file is contract and arithmetic checks
    that touch no data at all, so paying the tape load only where it is needed
    costs nothing either.
    """
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    rag_index.build(embed=False)
    ingest.ingest(tape.jump_to(tape.inject_seq() + 12))
    yield
    db.close()


# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------


# Everything in the estate that changes state, assembled from the MCP registry
# rather than copied out of it. That is the whole point of checking by name: a
# tool added to `publishing-execution` tomorrow lands in this set on its own,
# and the assertion below fails before the desk can offer it to a model.
MUTATING = (
    {tool for toolset in mcp_registry.TOOLSETS for tool in toolset.mutating}
    | {"release_reservation", "expire_soft_holds", "record_attribute", "audit",
       "ingest", "drain"}
)


def test_every_allowlisted_tool_is_read_only():
    """Guards the property that makes the desk safe to hand to a model.

    Checked by name against the mutating surface rather than by inspecting
    behaviour: if someone later adds `commit_plan` or `reserve_publish` to the
    table, this fails before it ships.
    """
    assert MUTATING, "an empty mutating surface would make this check vacuous"
    assert not (set(evidence.TOOLS) & MUTATING)


def test_an_allowlisted_tool_the_registry_knows_is_on_a_read_only_toolset():
    """Two of the desk's entries are catalog tools the MCP registry also owns.
    Their classification has to agree, or one of the two is lying."""
    for name in evidence.TOOLS:
        owner = mcp_registry.owner_of(name)
        if owner == "unknown":
            continue  # a desk-only lookup, covered by the check above
        assert name not in mcp_registry.BY_ID[owner].mutating


def test_the_catalogue_offered_to_the_model_matches_the_allowlist():
    """The prompt cannot drift from the governance actually in force."""
    catalogue = evidence.catalogue()
    for name, tool in evidence.TOOLS.items():
        assert f"{name}({tool.takes})" in catalogue
    assert catalogue.count("\n") + 1 == len(evidence.TOOLS)


def test_a_tool_outside_the_allowlist_is_refused_not_executed():
    """The whole point of a closed set is that naming something else fails."""
    records = evidence.run_requests([
        {"tool": "commit_plan", "argument": "SC-1", "why": "just publish it"},
    ])
    assert len(records) == 1
    assert records[0]["status"] == "REFUSED"
    assert "not an allowed evidence tool" in records[0]["result"]["error"]


def test_a_refusal_is_recorded_rather_than_dropped(seeded):
    """A reviewer should see what the investigator wanted and did not get -
    often the more interesting half."""
    records = evidence.run_requests([
        {"tool": "variant_diff", "argument": "PRD-01", "why": "base or Max"},
        {"tool": "rm", "argument": "-rf /", "why": "not a catalog question"},
    ])
    assert [r["status"] for r in records] == ["OK", "REFUSED"]
    assert [r["tool"] for r in records] == ["variant_diff", "rm"]
    assert records[1]["why"] == "not a catalog question"


def test_a_tool_called_without_its_argument_is_refused_with_guidance():
    records = evidence.run_requests([{"tool": "lineage", "argument": "", "why": ""}])

    assert records[0]["status"] == "REFUSED"
    # The message has to say what the tool wanted, or the model cannot recover.
    assert evidence.TOOLS["lineage"].takes in records[0]["result"]["error"]


def test_a_failing_lookup_is_evidence_rather_than_a_dead_run():
    """Nothing here raises: a tool that cannot answer is a fact about the
    investigation, not a reason to abandon a run with a deterministic path to a
    recommendation."""
    records = evidence.run_requests(
        [{"tool": "source_versions", "argument": "DOC-99", "why": "does it exist"}])

    assert len(records) == 1
    assert "error" in records[0]["result"]


def test_the_loop_is_bounded():
    assert evidence.MAX_PASSES >= 1
    assert evidence.MAX_PASSES <= 3, "an uncapped investigation is a bill"
    assert evidence.MAX_REQUESTS_PER_PASS >= 1


# ---------------------------------------------------------------------------
# Mandatory evidence, and who asked for it
# ---------------------------------------------------------------------------


def test_the_standing_questions_are_about_the_catalog_not_the_corpus():
    """"Does this apply to the base model or the variant" is a question about
    the current catalog. A retrieved postmortem will happily assert an answer,
    and a model reading one will believe it, so the desk answers from the
    record first, every time."""
    required = evidence.mandatory_requests([POWER_SIGNAL], BLAST)

    asked = {(r["tool"], r["argument"]) for r in required}
    assert ("variant_diff", "PRD-01") in asked
    assert ("source_versions", "DOC-01") in asked
    assert all(r["origin"] == "REQUIRED" for r in required)
    assert len(required) <= evidence.MAX_REQUIRED


def test_a_safety_class_correction_also_pulls_the_channel_rules():
    """A safety-class attribute fails closed, and what it fails closed on is a
    channel rule - so the rule is evidence."""
    required = evidence.mandatory_requests([ALLERGEN_SIGNAL], BLAST)
    channels = [r["argument"] for r in required if r["tool"] == "channel_rules"]

    assert channels, "a safety correction pulled no channel rule"
    assert channels == sorted(channels), "unsorted evidence makes a re-run differ"
    assert len(channels) <= evidence.MAX_SAFETY_CHANNELS


def test_a_correction_that_touches_nothing_safety_class_pulls_no_channel_rules():
    required = evidence.mandatory_requests([POWER_SIGNAL], BLAST)
    assert not [r for r in required if r["tool"] == "channel_rules"]


def test_mandatory_requests_run_before_any_agent_request(seeded):
    """And are labelled as such. A request the agent chose to make is a
    different claim from one the standard required, and collapsing them would
    overstate what the model decided."""
    records = evidence.run_requests(
        evidence.mandatory_requests([POWER_SIGNAL], BLAST)
        + [{"tool": "policy", "argument": "which document wins",
            "why": "the investigator asked"}])

    origins = [r["origin"] for r in records]
    assert origins[-1] == "AGENT"
    assert set(origins[:-1]) == {"REQUIRED"}
    assert origins.count("AGENT") == 1


def test_an_agent_flood_cannot_crowd_out_a_mandatory_lookup(seeded):
    """The two budgets are separate on purpose: a governance question that fell
    off the end of the model's allowance would be a rule the run quietly
    skipped."""
    flood = [{"tool": "policy", "argument": f"question {i}", "why": "curious"}
             for i in range(12)]
    records = evidence.run_requests(
        flood + evidence.mandatory_requests([POWER_SIGNAL], BLAST))

    agent = [r for r in records if r["origin"] == "AGENT"]
    required = [r for r in records if r["origin"] == "REQUIRED"]
    assert len(agent) <= evidence.MAX_REQUESTS_PER_PASS + 2
    assert {r["argument"] for r in required} == {
        r["argument"] for r in evidence.mandatory_requests([POWER_SIGNAL], BLAST)}


# ---------------------------------------------------------------------------
# Reducers a revision depends on
# ---------------------------------------------------------------------------


def test_reset_marker_replaces_rather_than_appends():
    """Without this a revision shows both revisions' readings at once."""
    assert resettable_add([1, 2], [3]) == [1, 2, 3]
    assert resettable_add([1, 2], [RESET, 9]) == [9]
    assert resettable_add([1, 2], [RESET]) == []


def test_signals_reset_on_a_revision():
    old = [{"id": "SIG-old", "kind": "SPEC_CORRECTION", "entities": ["PRD-01"]}]
    new = [{"id": "SIG-new", "kind": "ALLERGEN_CHANGE", "entities": ["VAR-02A"]}]
    assert merge_signals(old, [RESET, *new]) == new


# ---------------------------------------------------------------------------
# Carrying the superseded plan forward
# ---------------------------------------------------------------------------


def _reading(name: str, actions: list[dict]) -> dict:
    return {"scenario_id": f"SC-{name}", "name": name, "summary": "",
            "delta": {"id": f"D-{name}", "actions": actions}}


def _set_power(entity_id: str, value: int = 65) -> dict:
    return {"kind": "SET_ATTRIBUTE", "id": f"SA-{entity_id}",
            "entity_id": entity_id, "attribute_path": "specs.power_w",
            "new_value": value}


def test_previous_readings_are_carried_into_the_revision():
    """A revision that cannot re-offer yesterday's plan is a restart. The
    reviewer gets to see the reading they nearly approved, re-scored against
    what has arrived since."""
    previous = [_reading("Every variant", [_set_power("VAR-01A"),
                                           _set_power("VAR-01B")])]
    fresh = [_reading("Max only", [_set_power("VAR-01B")])]

    carried = _carry_forward(previous, fresh)

    assert len(carried) == 1
    assert carried[0]["name"].endswith("(previous plan)")
    assert carried[0]["carried_from"] == "SC-Every variant"


def test_a_carried_reading_gets_a_fresh_delta_id():
    """The validator keys idempotency on the delta id.

    Reusing it would return the previous revision's verdict against the new
    world - the exact failure re-planning exists to avoid.
    """
    previous = [_reading("Every variant", [_set_power("VAR-01B")])]
    carried = _carry_forward(previous, [])
    assert carried[0]["delta"]["id"] != "D-Every variant"


def test_a_reading_re_proposed_under_a_new_name_is_not_carried_twice():
    """Matched on what the reading does, not on what it is called. Validating
    it twice would put two identical rows on the comparison table."""
    actions = [_set_power("VAR-01B")]
    previous = [_reading("Max only", actions)]
    fresh = [_reading("Apply to Northaven AP300 Max", list(actions))]

    assert _carry_forward(previous, fresh) == []


def test_a_reading_that_changes_nothing_is_not_carried_forward():
    assert _carry_forward([_reading("Empty", [])], []) == []


def test_two_previous_readings_that_do_the_same_thing_collapse():
    same = [_set_power("VAR-01B")]
    previous = [_reading("A", list(same)), _reading("B", list(same))]
    assert len(_carry_forward(previous, [])) == 1


# ---------------------------------------------------------------------------
# The diff the reviewer reads
# ---------------------------------------------------------------------------


def _ranked(name: str, ready: float, stale: float, fields: float = 4.0,
            feasible: bool = True) -> dict:
    return {
        "scenario_id": f"SC-{name}", "name": name, "feasible": feasible,
        "delta": {"id": f"D-{name}", "actions": [_set_power(f"VAR-{name}")]},
        "kpis": {"listings_ready_pct": ready, "assets_stale": stale,
                 "fields_affected": fields, "channels_blocked": 4.0,
                 "completeness_pct": 100.0, "safety_flags": 0.0,
                 "republish_steps": 42.0},
    }


def test_no_diff_without_a_previous_recommendation():
    """A first plan has nothing to have moved from."""
    assert _plan_diff({}, [_ranked("A", 65.38, 17.0)]) == {}


def test_the_diff_reports_the_moved_figures():
    was = _ranked("EveryVariant", 65.38, 17.0)
    now = _ranked("MaxOnly", 80.77, 32.0)
    state = {
        "revision": 1,
        "previous_recommendation": {"scenario_id": "SC-EveryVariant",
                                    "scenario_name": "EveryVariant",
                                    "signals_seen": [{"id": "SIG-1"}]},
        "previous_ranked": [was],
        "signals": [{"id": "SIG-1", "kind": "SPEC_CORRECTION", "summary": "65 W"},
                    {"id": "SIG-2", "kind": "SPEC_CORRECTION",
                     "summary": "44 dB, Max only"}],
    }

    diff = _plan_diff(state, [now, was])

    assert diff["held"] is False
    assert diff["previous"]["name"] == "EveryVariant"
    assert diff["current"]["name"] == "MaxOnly"
    # Arithmetic, not narrative.
    assert diff["moved"]["listings_ready_pct"] == pytest.approx(15.39)
    assert diff["moved"]["assets_stale"] == pytest.approx(15.0)
    assert diff["moved"]["fields_affected"] == pytest.approx(0.0)
    # Only the correction the superseded plan had not seen.
    assert [s["id"] for s in diff["new_signals"]] == ["SIG-2"]
    assert diff["revision"] == 1


def test_the_diff_says_where_the_superseded_reading_now_ranks():
    """The reviewer's first question about a moved recommendation."""
    was = _ranked("EveryVariant", 65.38, 17.0, feasible=False)
    now = _ranked("MaxOnly", 80.77, 32.0)
    state = {
        "revision": 1,
        "previous_recommendation": {"scenario_id": "SC-EveryVariant",
                                    "scenario_name": "EveryVariant"},
        "previous_ranked": [was],
        "signals": [],
    }

    diff = _plan_diff(state, [now, was])

    assert diff["previous_now_ranked"] == 2
    assert diff["previous_still_feasible"] is False


def test_the_diff_says_so_when_the_recommendation_holds():
    """Holding is a finding too, and has to be distinguishable from a move."""
    same = _ranked("EveryVariant", 65.38, 17.0)
    state = {
        "revision": 1,
        "previous_recommendation": {"scenario_id": "SC-EveryVariant",
                                    "scenario_name": "EveryVariant"},
        "previous_ranked": [same],
        "signals": [],
    }

    diff = _plan_diff(state, [same])

    assert diff["held"] is True
    assert "holds" in diff["headline"]


def test_the_diff_matches_the_superseded_reading_on_what_it_does():
    """A revision re-proposes the same reading under a new scenario id, so the
    plan has to be recognised by its actions or every revision reads as a move."""
    was = _ranked("EveryVariant", 65.38, 17.0)
    reproposed = {**was, "scenario_id": "SC-Fresh", "name": "EveryVariant"}
    state = {
        "revision": 2,
        "previous_recommendation": {"scenario_id": "SC-EveryVariant",
                                    "scenario_name": "EveryVariant"},
        "previous_ranked": [was],
        "signals": [],
    }

    diff = _plan_diff(state, [reproposed])

    assert diff["held"] is True
    assert diff["reason"] == ""
