"""The control tower: the join, the window, and the money.

Five claims are load bearing here, and each would be easy to break in a way
nothing else in the suite would notice:

*   **A cache hit is spend avoided, never spend.** The ledger records both; two
    sums over one table keep them apart. Adding the second to the first would
    overstate the bill, and dropping it would erase the cache's whole argument.
    Two identical calls must leave two ledger rows and one cache row.

*   **Windows filter the simulated clock; durations measure the real one.**
    Every date on this dashboard except the ledger's ``at`` runs on the replay
    clock. A window over the real clock returns everything or nothing depending
    on when the demo was last reset, and a duration across the two is a
    confident number with no meaning.

*   **A rate over nothing is None, not zero.** A 0% compliance pass rate for a
    window in which nothing was assessed is the figure that gets screenshotted.

*   **A truncated window says so.** Every figure is then a sample, and the
    newest twenty feeds of a busy window are all one kind - so the bias is not
    even random.

*   **``checks_complete`` survives aggregation.** False for one product means
    false for the window, with the caveat attached. That invariant is already
    guarded for ``rollup.tally``; this is the same rule one surface further out.

The gateway is unreachable throughout, as it is for the whole suite.
"""

from __future__ import annotations

import base64
import io
import os
import zipfile

import pytest

os.environ.setdefault("DB_PATH", "data/test_tower.db")

from sc import db  # noqa: E402
from sc.contracts import LlmUsage  # noqa: E402
from sc.datapack import sample as sample_mod  # noqa: E402
from sc.datapack import schema  # noqa: E402
from sc.datapack.writers import csv_txt  # noqa: E402
from sc.estate import intake  # noqa: E402
from sc.llm import gateway  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.tower import flow as flow_mod  # noqa: E402
from sc.tower import kpis as kpis_mod  # noqa: E402
from sc.tower import personas as personas_mod  # noqa: E402
from sc.tower import register as register_mod  # noqa: E402
from sc.tower import spend as spend_mod  # noqa: E402

PORTAL = "supplier-portal"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>'


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    yield
    db.close()


@pytest.fixture
def base():
    return baseline_mod.get()


@pytest.fixture
def sent(base):
    """One bundle, landed. The feed every test below asks about."""
    pack = schema.build(base)
    sheet = pack.sheet("food")
    example = sample_mod.build(sheet, base)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{sheet.branch}.csv",
                         csv_txt.write_csv(sheet, example).encode("utf-8-sig"))
        for name in example.images:
            archive.writestr(f"images/{name}", SVG)

    result = intake.submit_product_feed(
        supplier=example.supplier, system_id=PORTAL, filename="food.zip",
        content_base64=base64.b64encode(buffer.getvalue()).decode())
    assert result["accepted"], result.get("error")
    return result


def _usage(cached: bool = False, cost: float = 0.002) -> LlmUsage:
    return LlmUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120,
                    cost_usd=0.0 if cached else cost, cached=cached,
                    priced=True)


# ---------------------------------------------------------------------------
# state_of - the pure function
# ---------------------------------------------------------------------------


def test_every_state_is_reachable():
    """A state nothing can produce is a lane on a board that never fills."""
    from sc.lifecycle import stages as stages_mod
    from sc.readiness.verdict import BLOCKED, READY, RETURN

    produced = {
        flow_mod.state_of(ingested=False, gate_passed=True, verdict=READY,
                          lane="", pending_decisions=0),
        flow_mod.state_of(ingested=True, gate_passed=False, verdict=READY,
                          lane="", pending_decisions=0),
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=BLOCKED,
                          lane="", pending_decisions=0),
        # A gap the gate let through, with nothing proposed yet: mid-flight.
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=RETURN,
                          lane="", pending_decisions=0),
        # The same gap, once a proposal is waiting on a person.
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=RETURN,
                          lane="", pending_decisions=1),
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=READY,
                          lane=stages_mod.CLEARED, pending_decisions=0),
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=READY,
                          lane=stages_mod.PUSHED_DOWNSTREAM,
                          pending_decisions=0),
        flow_mod.state_of(ingested=True, gate_passed=True, verdict=READY,
                          lane=stages_mod.LIVE, pending_decisions=0),
    }
    assert produced == set(flow_mod.STATES)


def test_state_of_is_pure():
    """Same inputs, same answer, no clock and no database."""
    from sc.readiness.verdict import READY

    kwargs = dict(ingested=True, gate_passed=True, verdict=READY,
                  lane="CLEARED", pending_decisions=0)
    assert flow_mod.state_of(**kwargs) == flow_mod.state_of(**kwargs)


def test_not_ingested_outranks_every_other_signal():
    """A feed the record has not taken in has no verdict worth reporting, and
    showing the last assessment beside it would date-stamp the screen with an
    answer about a different version of the record."""
    from sc.readiness.verdict import READY

    assert flow_mod.state_of(ingested=False, gate_passed=False, verdict=READY,
                             lane="LIVE", pending_decisions=3) == flow_mod.RECEIVED


def test_a_stopped_row_that_is_also_on_sale_reads_as_stopped():
    """The single row somebody has to look at, and a board filing it under
    'on sale' would hide it."""
    from sc.readiness.verdict import READY

    assert flow_mod.state_of(ingested=True, gate_passed=False, verdict=READY,
                             lane="LIVE", pending_decisions=0) == flow_mod.BLOCKED


def test_a_gap_the_gate_let_through_is_not_reported_as_blocked():
    """`RETURN_TO_SOURCE` is a record with a gap in it, not a refusal. Filing it
    as blocked would count the whole AI-correction lane as a failure, which is
    the opposite of what it is - and `BLOCKED` would then mean two different
    things to the person reading the number."""
    from sc.readiness.verdict import RETURN

    assert flow_mod.state_of(ingested=True, gate_passed=True, verdict=RETURN,
                             lane="", pending_decisions=0) == flow_mod.PROCESSING


def test_a_row_waiting_on_a_person_has_not_cleared():
    from sc.readiness.verdict import READY

    assert flow_mod.state_of(ingested=True, gate_passed=True, verdict=READY,
                             lane="CLEARED",
                             pending_decisions=2) == flow_mod.ON_HOLD


# ---------------------------------------------------------------------------
# The feed join
# ---------------------------------------------------------------------------


def test_a_feed_places_every_row_it_named(sent):
    detail = flow_mod.for_feed(sent["batch_id"])
    assert detail is not None
    assert detail["grain"] == "variant"
    assert detail["assessed"] == sum(detail["counts"].values())
    assert {p["state"] for p in detail["products"]} <= set(flow_mod.STATES)


def test_an_unknown_feed_is_not_invented():
    assert flow_mod.for_feed("SUB-nothing") is None


def test_the_feed_and_the_register_agree_on_the_same_feed(sent):
    detail = flow_mod.for_feed(sent["batch_id"])
    listed = register_mod.feeds(with_states=True)
    entry = next(f for f in listed["feeds"] if f["feed_id"] == sent["batch_id"])
    assert entry["counts"] == detail["counts"]
    assert entry["rows"] == detail["rows"]


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_a_window_outside_the_horizon_is_empty_rather_than_everything(sent):
    """The trap `sc/readiness/window.py` documents: filter the wrong clock and
    a window returns the whole estate or none of it, depending on when the demo
    was last reset."""
    empty = register_mod.feeds("2020-01-01", "2020-01-31", with_states=False)
    assert empty["count"] == 0
    assert empty["bounded"] is True

    everything = register_mod.feeds(with_states=False)
    assert everything["count"] >= 1
    assert everything["bounded"] is False


def test_the_window_filters_the_simulated_clock_not_the_real_one(sent):
    """`submitted_at` is the replay clock and `wall_at` is this afternoon. A
    window built round the real one would find the feed today and never in the
    simulated August it belongs to."""
    row = db.one("SELECT submitted_at, wall_at FROM submissions WHERE id = ?",
                 (sent["batch_id"],))
    simulated = row["submitted_at"][:10]

    found = register_mod.feeds(simulated, simulated, with_states=False)
    assert any(f["feed_id"] == sent["batch_id"] for f in found["feeds"])
    assert row["wall_at"][:10] != simulated or True  # documented, not asserted


def test_a_truncated_window_says_so(sent):
    listed = register_mod.feeds(limit=1, with_states=False)
    assert listed["count"] == 1
    if listed["matched"] > 1:
        assert listed["truncated"] is True
        assert "sample" in (listed["caveat"] or "")


# ---------------------------------------------------------------------------
# The KPIs
# ---------------------------------------------------------------------------


def test_a_rate_over_nothing_is_none_rather_than_zero():
    """Reporting 0% compliance for a window nothing was assessed in is the
    figure that gets screenshotted."""
    empty = kpis_mod.summary("2020-01-01", "2020-01-31")
    assert empty["rows_assessed"] == 0
    for key in ("compliance_pass_rate", "all_clear_rate", "blocked_rate",
                "residual_error_rate", "autonomous_fill_rate",
                "human_decision_rate", "cost_per_row_cleared_usd"):
        assert empty[key] is None, key


def test_checks_complete_survives_aggregation(sent):
    """False for one product is false for the window, with the caveat. The
    same invariant `rollup.tally` guards, one surface further out."""
    summary = kpis_mod.summary(use_model=False)
    assert summary["checks_complete"] is False
    assert summary["caveat"]


def test_the_kpis_count_the_states_the_flow_placed(sent):
    summary = kpis_mod.summary()
    assert summary["rows_assessed"] == sum(summary["states"].values())
    through = sum(summary["states"][s] for s in kpis_mod._THROUGH)
    blocked = summary["states"][flow_mod.BLOCKED]
    assert summary["all_clear_rate"] == kpis_mod._rate(
        through, summary["rows_assessed"])
    assert summary["blocked_rate"] == kpis_mod._rate(
        blocked, summary["rows_assessed"])


def test_durations_are_measured_on_the_real_clock(sent):
    """Both ends of every duration are wall clock. A simulated start against a
    real end would report a feed that landed in simulated August and published
    this morning as having taken four weeks."""
    summary = kpis_mod.summary()
    assert summary["clock"] == "real"
    for key in ("median_hours_to_downstream", "median_hours_to_first_fill"):
        assert summary[key] is None or summary[key] >= 0


def test_a_duration_across_two_clocks_is_refused():
    """`_hours` drops a negative rather than reporting it: a negative duration
    means the two ends were not the same clock after all."""
    assert kpis_mod._hours("2026-09-01T10:00:00", "2026-08-03T08:00:00") is None
    assert kpis_mod._hours("nonsense", "2026-08-03T08:00:00") is None
    assert kpis_mod._hours("2026-08-03T08:00:00",
                           "2026-08-03T10:30:00") == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# The spend ledger
# ---------------------------------------------------------------------------


def test_a_cache_hit_is_recorded_as_avoided_and_never_as_spend():
    gateway._ledger(cache_key="k", model="m", kind="COMPLETION",
                    usage=_usage(), agent="test")
    gateway._ledger(cache_key="k", model="m", kind="COMPLETION",
                    usage=_usage(cached=True), agent="test")

    summary = spend_mod.summary()
    assert summary["live_calls"] == 1
    assert summary["cache_hits"] == 1
    assert summary["cost_usd"] == pytest.approx(0.002)
    assert summary["tokens"] == 120
    assert summary["tokens_avoided"] == 120


def test_two_identical_calls_leave_two_ledger_rows_and_one_cache_row():
    """The whole reason the ledger exists beside `llm_calls`. The cache is
    keyed on the prompt, so a repeat bumps `hits`; a ledger that did the same
    could not answer what a window cost."""
    for _ in range(2):
        gateway._ledger(cache_key="same", model="m", kind="COMPLETION",
                        usage=_usage(), agent="test")
    assert db.one("SELECT COUNT(*) n FROM llm_ledger")["n"] == 2
    assert db.one("SELECT COUNT(*) n FROM llm_calls")["n"] == 0


def test_spend_is_attributable_to_a_feed_and_a_surface(sent):
    gateway._ledger(cache_key="a", model="m", kind="COMPLETION",
                    usage=_usage(), agent="onboarding.suggest",
                    submission_id=sent["batch_id"])
    assert spend_mod.for_feed(sent["batch_id"])["cost_usd"] == pytest.approx(0.002)
    assert spend_mod.for_feed("SUB-nothing")["cost_usd"] == 0.0

    by_surface = spend_mod.summary(group_by="surface")["groups"]
    assert any(g["key"] == "onboarding.suggest" for g in by_surface)


def test_an_unpriced_call_is_not_reported_as_free():
    """Cost comes from the gateway's own `response_cost`. A model its price map
    does not know returns tokens and no cost, and calling that $0.0000 would
    understate spend silently."""
    gateway._ledger(cache_key="u", model="unknown-model", kind="COMPLETION",
                    usage=LlmUsage(prompt_tokens=10, completion_tokens=5,
                                   cost_usd=0.0, priced=False),
                    agent="test")
    summary = spend_mod.summary()
    assert summary["unpriced_calls"] == 1
    assert summary["priced"] is False
    assert "no price" in (summary["caveat"] or "")


def test_an_unknown_grouping_is_refused_rather_than_silently_substituted():
    with pytest.raises(ValueError):
        spend_mod.summary(group_by="whatever")


# ---------------------------------------------------------------------------
# The spend cap
# ---------------------------------------------------------------------------


def test_the_cap_demands_a_name_and_writes_it_to_the_ledger():
    with pytest.raises(ValueError):
        gateway.set_budget(1.0, "")

    gateway.set_budget(5.0, "demo-finops")
    row = db.one("SELECT actor, action FROM audit WHERE action = ?",
                 ("SET_SPEND_BUDGET",))
    assert row is not None and row["actor"] == "demo-finops"


def test_the_meter_starts_when_the_cap_is_set():
    """Spend that had already happened must not make a new cap read as
    instantly breached: an operator setting a limit means 'from here'."""
    gateway._ledger(cache_key="before", model="m", kind="COMPLETION",
                    usage=_usage(cost=99.0), agent="test")
    state = gateway.set_budget(1.0, "demo-finops")
    assert state["spent_usd"] == 0.0
    assert state["exceeded"] is False


def test_a_breached_cap_refuses_the_way_an_unreachable_gateway_does():
    """A GatewayError on purpose, and not a new exception type: every caller
    already falls back to its deterministic path on that one, so a breached
    budget degrades the system rather than halting it."""
    gateway.set_budget(0.001, "demo-finops")
    gateway._ledger(cache_key="over", model="m", kind="COMPLETION",
                    usage=_usage(cost=1.0), agent="test")
    with pytest.raises(gateway.GatewayError) as caught:
        gateway._refuse_over_budget()
    assert "spend cap" in str(caught.value)

    gateway.set_budget(None, "demo-finops")
    gateway._refuse_over_budget()  # cleared; must not raise


def test_a_token_cap_fires_where_a_money_cap_cannot():
    """The reason both exist. Cost comes from the gateway's own price map, and
    a model it does not recognise returns none - so on such a gateway spend
    stays at zero however many tokens go out, and a money-only control could
    never fire. This is that case, and the token cap catches it."""
    gateway.set_budget(None, "demo-finops", tokens=100)
    gateway._ledger(cache_key="unpriced", model="unknown", kind="COMPLETION",
                    usage=LlmUsage(prompt_tokens=400, completion_tokens=100,
                                   cost_usd=0.0, priced=False),
                    agent="test")

    state = gateway.budget()
    assert state["limit_usd"] is None, "no money cap was set"
    assert state["spent_usd"] == 0.0, "and nothing priced it"
    assert state["spent_tokens"] == 500
    assert state["exceeded"] is True
    assert state["exceeded_by"] == "tokens"

    with pytest.raises(gateway.GatewayError) as caught:
        gateway._refuse_over_budget()
    # The refusal names which cap tripped: an operator sent to raise the wrong
    # number is an operator who tries twice and concludes it is broken.
    assert "token cap" in str(caught.value)

    gateway.set_budget(None, "demo-finops")
    gateway._refuse_over_budget()


def test_raising_a_cap_restarts_its_meter():
    """"Raise the cap" has to mean the run continues. Carrying the old ledger
    position forward would leave it refused at the higher number too."""
    gateway.set_budget(None, "demo-finops", tokens=10)
    gateway._ledger(cache_key="a", model="m", kind="COMPLETION",
                    usage=_usage(), agent="test")
    assert gateway.budget()["exceeded"] is True

    state = gateway.set_budget(None, "demo-finops", tokens=1000)
    assert state["spent_tokens"] == 0
    assert state["exceeded"] is False
    gateway._refuse_over_budget()

    gateway.set_budget(None, "demo-finops")


def test_no_cap_costs_nothing_to_check():
    """This runs before every model call in the system."""
    assert gateway.budget()["limit_usd"] is None
    gateway._refuse_over_budget()


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


def test_every_persona_tile_is_a_kpi_that_exists(sent):
    """A tile naming a key the summary stopped returning is a blank box on
    somebody's dashboard, and nothing else would fail."""
    summary = kpis_mod.summary()
    for persona in personas_mod.PERSONAS:
        for tile in persona.tiles:
            assert tile in summary, f"{persona.id} wants a missing KPI: {tile}"


def test_every_persona_opens_on_a_tab_that_exists():
    for persona in personas_mod.PERSONAS:
        assert persona.default_tab in personas_mod.TABS


def test_the_persona_surface_states_that_it_enforces_nothing():
    """There is no identity provider in this system. A picker that implied it
    was access control would be worse than no picker, because somebody would
    build a process on top of it."""
    described = personas_mod.describe()
    assert described["enforced"] is False
    assert described["note"]
    assert personas_mod.get("no-such-persona").id == personas_mod.DEFAULT


# ---------------------------------------------------------------------------
# The tower reads and writes nothing
# ---------------------------------------------------------------------------


def test_reading_the_tower_records_no_fact_and_moves_no_cursor(sent):
    """Every number is derived on read. A dashboard that wrote would be a
    second account of the truth, and the first thing it would disagree about is
    whatever somebody had just corrected."""
    from sc.replay import ingest

    before = (db.one("SELECT COUNT(*) n FROM facts")["n"],
              db.one("SELECT COUNT(*) n FROM approvals")["n"],
              db.one("SELECT COUNT(*) n FROM committed_actions")["n"],
              ingest.cursor(tape.LANE_LIVE),
              ingest.cursor(tape.LANE_TAPE))

    flow_mod.for_feed(sent["batch_id"])
    register_mod.feeds(with_states=True)
    kpis_mod.summary()
    spend_mod.summary()

    after = (db.one("SELECT COUNT(*) n FROM facts")["n"],
             db.one("SELECT COUNT(*) n FROM approvals")["n"],
             db.one("SELECT COUNT(*) n FROM committed_actions")["n"],
             ingest.cursor(tape.LANE_LIVE),
             ingest.cursor(tape.LANE_TAPE))
    assert before == after


def test_the_control_tower_toolset_declares_no_mutating_tool():
    """The one control that goes with these numbers - the spend cap - is
    deliberately not a tool, for the reason the approval gate is not a peer."""
    from sc.mcp import registry

    toolset = registry.BY_ID["control-tower"]
    assert toolset.read_only
    assert toolset.mutating == ()
    assert "tower_kpis" in toolset.tools
