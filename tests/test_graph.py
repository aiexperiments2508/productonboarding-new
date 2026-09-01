"""The correction graph, end to end.

These tests run with the gateway unreachable, on purpose. Every LLM step has a
deterministic fallback, and the loop must reach a recommendation and an
approval gate without a model - otherwise a dead network at the venue ends the
demo rather than degrading it. That is an architectural assertion, not a
convenience: a node that cannot produce an answer without a model is a bug.

The properties under test are the ones the brief names directly: a correction
reaches a reviewer and nothing publishes before one decides, the run survives
the process dying, a resumed run does not publish twice, and the safety rules
that are policy rather than classification cannot be argued down.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_graph.db")
# Point the gateway at a closed port so the fallback paths are what runs.
# Pinned as the full URL rather than as LITELLM_PORT: gateway.base_url() prefers
# LITELLM_BASE_URL, and a developer's .env sets that to a live gateway - pinning
# only the port would silently send the whole suite to a real model.
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.contracts import (  # noqa: E402
    ActionKind,
    Event,
    LlmUsage,
    Provenance,
    ProvenanceKind,
    ScopeLevel,
)
from sc.graph import build as graph_build  # noqa: E402
from sc.graph import nodes  # noqa: E402
from sc.graph.state import _merge_dicts, merge_signals  # noqa: E402
from sc.llm import gateway  # noqa: E402
from sc.rag import index as rag_index  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.state import store  # noqa: E402

INCIDENT = "INC-GRAPH"
THREAD = "T-GRAPH"

# The purifier's two readings, and the food product whose allergen change makes
# the same run safety-critical. Named rather than spelled inline so a failure
# reads as a claim about the scenario.
PURIFIER = "PRD-01"
BASE_MODEL = "VAR-01A"
MAX_MODEL = "VAR-01B"
SNACK = "PRD-02"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    # Release the checkpoint file before deleting it - the saver holds an open
    # handle and Windows will not unlink underneath it.
    graph_build.reset_graph()
    for suffix in ("", "-wal", "-shm"):
        path = graph_build.checkpoint_path()
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            candidate.unlink()

    tape.load_tape(reset=True)
    rag_index.build(include_comms=True, embed=False)
    # Advance past the inject so there is a correction to propagate - as far as
    # the allergen change, which is what the signal assertions below rest on.
    released = tape.jump_to(_seq_of(doc_id="DOC-04", version="v2"))
    ingest.ingest(released)
    yield
    db.close()


def _seq_of(*, doc_id: str | None = None, version: str | None = None,
            code: str | None = None) -> int:
    """Where an arc sits on the tape, by what it carries rather than by count.

    The arcs are fixed points in the story; their sequence numbers are not,
    because ids are assigned after the tape is sorted and any change to routine
    traffic renumbers everything. A test that says "twelve events past the
    inject" is asserting a traffic density it does not care about.
    """
    from sc import db

    for row in db.query("SELECT seq, payload FROM events ORDER BY seq"):
        payload = db.loads(row["payload"])
        if doc_id and payload.get("doc_id") != doc_id:
            continue
        if version and payload.get("doc_version") != version:
            continue
        if code and payload.get("code") != code:
            continue
        return int(row["seq"])
    raise AssertionError(
        f"no event on the tape carries doc_id={doc_id} version={version} "
        f"code={code}")


def _run(thread: str = THREAD) -> dict:
    return graph_build.start_run(INCIDENT, thread)


def _release_the_clarification() -> list:
    """Let the supplier's correction-of-a-correction reach the tape.

    DOC-01 v3 says the 65 W is the Max only and gives the Max a measured noise
    level that has never been published. It lands four days after the notice
    this run was started on.
    """
    released = tape.jump_to(_seq_of(doc_id="DOC-01", version="v3"))
    ingest.ingest(released)
    assert any((e.payload or {}).get("doc_version") == "v3" for e in released), \
        "the finale revision is not in the released window"
    return released


def _record_the_corrections() -> None:
    """Read the supplier documents into the record, on a thread of its own.

    A fact only exists once a run has read the document asserting it, so on a
    fresh database there are no open cases to scope to and the first run reads
    everything. That is what the case list is a view over, which is why the
    scoped runs below are second runs.
    """
    graph_build.start_run(INCIDENT, "T-SEED")


# ---------------------------------------------------------------------------
# The loop reaches a decision point with no model available
# ---------------------------------------------------------------------------


def test_run_stops_at_the_approval_gate():
    result = _run()
    assert result["awaiting_approval"] is True
    assert result["next"] == ["request_approval"]
    assert result["status"] == "AWAITING_APPROVAL"


def test_the_correction_is_read_without_a_model():
    values = _run()["values"]
    kinds = {s["kind"] for s in values["signals"]}

    assert values["signals"], "corrections must be read out of the documents"
    assert {"SPEC_CORRECTION", "ALLERGEN_CHANGE"} <= kinds
    # And the run says out loud that it ran blind, rather than presenting a
    # fallback as a model's conclusion.
    assert any("cannot reach" in e or "unreachable" in e
               for e in values.get("errors") or [])


def test_every_leg_of_the_pipeline_runs():
    values = _run()["values"]
    seen = {t["node"] for t in values["trace"]}
    assert {"monitor", "extract", "triage", "resolve_scope", "plan_candidates",
            "validate", "rank", "propagate", "scan_claims", "regenerate",
            "enrich", "validate_final", "recommend"} <= seen


def test_the_recommendation_quotes_validated_figures():
    """The narrative may be templated; the numbers may not be invented."""
    values = _run()["values"]
    recommendation = values["recommendation"]
    chosen = next(r for r in values["ranked"]
                  if r["scenario_id"] == recommendation["scenario_id"])

    assert recommendation["kpis"] == chosen["kpis"]
    assert recommendation["feasible"] == bool(chosen.get("feasible"))


# ---------------------------------------------------------------------------
# Policy overrides classification
# ---------------------------------------------------------------------------


def test_the_safety_override_forces_critical():
    """A safety-class attribute or a regulated product is CRITICAL whether or
    not a model was available to say so. It is a rule, not a tie-break."""
    values = _run()["values"]

    assert values["severity"] == "CRITICAL"
    assert values["material"] is True
    assert "escalated by policy" in values["triage_reason"]
    assert "safety-class" in values["triage_reason"]


def _grounds(delta: dict, violations: list[dict] | None = None) -> list[str]:
    return nodes._review_grounds(baseline_mod.get(),
                                 {"delta": delta, "violations": violations or []},
                                 {})


def _set_attribute(entity_id: str, path: str, value) -> dict:
    return {"kind": str(ActionKind.SET_ATTRIBUTE), "id": f"SA-{entity_id}-{path}",
            "entity_id": entity_id, "attribute_path": path, "new_value": value}


# The three measured grounds the brief makes non-negotiable. Each is asserted
# on its own, because the bug this guards was one ground being read and the
# other two being missed - a run that withheld four channels under a safety
# hold and reported approval as optional.
REVIEW_GROUNDS = {
    "a safety attribute moved": (
        {"scope": {"entities": ["VAR-02A"]},
         "actions": [_set_attribute("VAR-02A", "food.allergens.may_contain",
                                    ["peanuts"])]},
        "safety-class"),
    "a regulated product is affected": (
        {"scope": {"entities": ["VAR-05A"]},
         "actions": [_set_attribute("VAR-05A", "food.net_weight_g", 280)]},
        "is regulated"),
    "a channel is withheld": (
        {"scope": {"entities": [MAX_MODEL]},
         "actions": [_set_attribute(MAX_MODEL, "specs.power_w", 65),
                     {"kind": str(ActionKind.WITHHOLD_CHANNEL), "id": "WC-LST-05",
                      "listing_id": "LST-05", "channel_id": "CH-WEB"}]},
        "held back under a safety hold"),
}


@pytest.mark.parametrize("ground,expected",
                         [(g, e) for g, (_, e) in REVIEW_GROUNDS.items()],
                         ids=list(REVIEW_GROUNDS))
def test_review_is_required_on_every_measured_ground(ground, expected):
    delta, _ = REVIEW_GROUNDS[ground]
    grounds = _grounds(delta)

    assert grounds, f"{ground} must require review"
    assert any(expected in g for g in grounds)
    governed = nodes._governed(baseline_mod.get(), {},
                               {"delta": delta, "violations": []})
    assert governed["requires_review"] is True


def test_an_open_safety_declaration_also_requires_review():
    delta = {"scope": {"entities": [MAX_MODEL]},
             "actions": [_set_attribute(MAX_MODEL, "specs.power_w", 65)]}
    grounds = _grounds(delta, [{"constraint": "allergen_declaration",
                                "severity": "HARD"}])
    assert any("allergen_declaration is open" in g for g in grounds)


def test_a_routine_correction_does_not_require_review():
    """The negative control. Without it the assertion above is satisfied by a
    function that always answers yes, which would be no governance at all."""
    delta = {"scope": {"entities": [MAX_MODEL]},
             "actions": [_set_attribute(MAX_MODEL, "specs.power_w", 65)]}

    assert _grounds(delta) == []
    assert nodes._governed(baseline_mod.get(), {},
                           {"delta": delta, "violations": []}
                           )["requires_review"] is False


def test_the_gate_recomputes_the_obligation_rather_than_trusting_it():
    """``requires_review`` is a function of the change set, so nothing upstream
    can lower it by writing the field."""
    delta = {"scope": {"entities": [MAX_MODEL]},
             "actions": [{"kind": str(ActionKind.WITHHOLD_CHANNEL), "id": "WC-1",
                          "listing_id": "LST-05", "channel_id": "CH-WEB"}]}
    tampered = {"delta": delta, "violations": [],
                "requires_review": False, "review_grounds": []}

    governed = nodes._governed(baseline_mod.get(), {}, tampered)

    assert governed["requires_review"] is True
    assert governed["review_grounds"]


def test_the_run_reaches_the_gate_carrying_its_review_obligation():
    result = _run()
    recommendation = result["values"]["recommendation"]

    assert recommendation["requires_review"] is True
    assert recommendation["review_grounds"]
    # The reviewer is shown it, not just the state.
    assert result["interrupt"]["requires_review"] is True
    assert result["interrupt"]["review_grounds"] == recommendation["review_grounds"]


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def test_the_scope_fallback_is_the_widest_reading_not_the_narrowest():
    """Fail safe, not fail silent.

    A correction applied too widely republishes a number on a page it does not
    belong on, which a reviewer can see and reject; one applied too narrowly
    leaves a wrong number live, which nobody sees at all. The purifier notice
    names the product and no variant, so with no model to argue it down every
    variant is in scope.
    """
    base = baseline_mod.get()
    values = _run()["values"]

    readings = [c for c in values["scope_candidates"]
                if MAX_MODEL in c["entities"] or BASE_MODEL in c["entities"]]
    assert readings, "the purifier correction produced no reading at all"
    widest = readings[0]

    assert set(widest["entities"]) == set(base.variants_of[PURIFIER])
    assert widest["level"] == str(ScopeLevel.ALL)
    assert len(widest["entities"]) > 1, "the narrowest reading was taken instead"
    assert "no model was available" in widest["rationale"]


def test_a_scope_never_holds_another_products_variants():
    base = baseline_mod.get()
    values = _run()["values"]

    for candidate in values["scope_candidates"]:
        products = {base.product_of_variant[e] for e in candidate["entities"]}
        assert len(products) == 1, f"{candidate['entities']} spans {products}"


def test_a_reading_spanning_two_products_is_refused_with_its_reason():
    """A correction to the purifier has nothing to say about the snack bar, and
    a refusal a reviewer can read beats a candidate that quietly vanished."""
    why = nodes._scope_problem(baseline_mod.get(),
                               {"level": str(ScopeLevel.ALL),
                                "entities": [BASE_MODEL, "VAR-02A"]})
    assert "cannot put another product's variants in scope" in why


# ---------------------------------------------------------------------------
# One run, one correction case
# ---------------------------------------------------------------------------
#
# A case is keyed by product: the publish lock is channel-and-product, so the
# product is the unit a reviewer actually commits. Before this, a run derived
# signals from every fact in force and swept the purifier's wattage and the
# snack bar's allergen into one recommendation - two unrelated decisions offered
# as one approval.


def test_a_scoped_run_decides_one_product_and_reports_the_rest():
    base = baseline_mod.get()
    _record_the_corrections()

    values = graph_build.start_run(INCIDENT, "T-CASE", case_id=PURIFIER)["values"]

    assert values["case_id"] == PURIFIER
    assert values["case"]["title"].startswith(PURIFIER)
    assert all(nodes.case_of(s, base) == PURIFIER for s in values["signals"])

    changed = {c["entity_id"] for c in values["recommendation"]["changes"]}
    assert changed, "the scoped run recommended no change at all"
    assert changed <= {PURIFIER, BASE_MODEL, MAX_MODEL}

    # The snack bar's correction does not vanish because this run is not about
    # it - it is reported as still open, without its signal bodies.
    snack = next(c for c in values["other_open_cases"] if c["case_id"] == SNACK)
    assert snack["safety"] is True
    assert snack["signal_ids"]
    assert "signals" not in snack


def test_a_scoped_run_is_not_contaminated_by_the_documents_it_reads():
    """The regression: a case filter ahead of extraction filters nothing.

    No seed run here, and that is the whole point. Every correction is still
    sitting in an unread supplier document, so the facts `monitor` derives its
    signals from do not exist yet - it finds no cases, filters an empty list,
    and `extract` then appends the snack bar's allergen behind the filter.
    Triage measured the union, escalated an air-purifier case on a regulated
    snack, and named that snack in the sentence two screens render verbatim.
    """
    base = baseline_mod.get()

    values = graph_build.start_run(INCIDENT, "T-CASE-FIRST",
                                   case_id=PURIFIER)["values"]

    assert values["case_id"] == PURIFIER
    assert all(nodes.case_of(s, base) == PURIFIER for s in values["signals"])
    assert not any(other in values["triage_reason"]
                   for other in (SNACK, "PRD-05", "VAR-02A", "VAR-02B")), \
        "another product's correction reached this case's severity sentence"

    # The other case does not vanish because this run is not about it.
    snack = next(c for c in values["other_open_cases"] if c["case_id"] == SNACK)
    assert snack["signal_ids"]

    # And extraction stayed global: the snack bar's allergen is on the record
    # even though nothing in this run acted on it. A document is read once, so a
    # run that skipped it would leave the case nobody has decided yet unreadable.
    assert db.one("SELECT 1 FROM facts WHERE entity_id = 'VAR-02A'"
                  " AND attr = 'food.allergens.may_contain'")


def test_a_run_with_no_case_named_takes_the_worst_one_open():
    """Existing callers keep working, and get one coherent case rather than
    every correction on file."""
    base = baseline_mod.get()
    _record_the_corrections()

    values = graph_build.start_run(INCIDENT, "T-CASE-AUTO")["values"]

    assert values["case_id"] == SNACK, "the allergen case is the worst one open"
    assert [c["case_id"] for c in values["other_open_cases"]] == [PURIFIER]
    assert all(nodes.case_of(s, base) == SNACK for s in values["signals"])
    # And the run says which case it took, rather than leaving it to be inferred
    # from the entities that happen to appear downstream.
    named = [t for t in values["trace"]
             if t["node"] == "monitor" and t["detail"].get("case_id")]
    assert len(named) == 1
    assert SNACK in named[0]["summary"]


# ---------------------------------------------------------------------------
# What is allowed to open a case
# ---------------------------------------------------------------------------
#
# The case list is what a reviewer picks from and what `monitor` takes when the
# caller names none, so a correction it cannot see is a correction the loop
# cannot be run against at all. It used to see two things: a value that moved,
# and a channel that refused a feed. These are the three it was blind to.
#
# All three arrive on the live lane rather than the recording, which is not a
# testing convenience - it is where they happen. A supplier typing into the
# portal is exactly what contradicts a pack label and exactly what leaves a
# mandatory field empty.


def _live_row(entity_id: str, path: str, value: object, doc_id: str,
              version: str = "v9"):
    """One attribute row, shaped the way the intake server shapes a portal
    submission."""
    from sc.contracts import EventType

    return tape.append_live(
        EventType.SUPPLIER_FEED, "VENDOR_PORTAL",
        {"doc_id": doc_id, "doc_version": version, "supplier": "SUP-01",
         "entity_id": entity_id, "path": path, "value": value,
         "kind": "ATTRIBUTE"},
        system_id="supplier-portal")


def test_a_feed_row_that_lost_a_precedence_contest_opens_a_case():
    """The disagreement `ingest` refuses to record is still a disagreement.

    POL-002 keeps the pack label and drops the spreadsheet row - correctly, or
    a portal upload could quietly beat approved artwork. But `ingest` returns
    before `store.record`, so the losing value leaves no fact, and a case list
    derived from facts alone could never see it. A supplier could contradict
    the artwork and be told nothing at all.
    """
    base = baseline_mod.get()
    entity, path = "VAR-02A", "food.fibre_g"
    standing = base.attr_sources[(entity, path)].doc_id
    loser = next(d.id for d in base.source_docs.values()
                 if d.precedence < base.source_docs[standing].precedence)

    # `append_live` ingests inline, under the same precedence rules a taped
    # row goes through, so the contest has already been decided here.
    _live_row(entity, path, 36.5, loser)

    signals = nodes._signals_in_force(tape.sim_now())
    conflict = next(s for s in signals if s["kind"] == "SOURCE_CONFLICT")

    assert conflict["attribute_paths"] == [path]
    # Both documents, because the pair is the argument. A case naming one of
    # them would hide what is actually in dispute.
    assert {standing, loser} <= set(conflict["entities"])
    assert conflict["entities"][0] == entity, "the subject is read first"
    assert nodes.case_of(conflict, base) == SNACK

    # And it is a case, in the list, and therefore runnable.
    assert SNACK in [c["case_id"] for c in nodes.open_cases(signals, base)]


def test_a_conflict_the_record_came_round_to_stops_being_open():
    """Derived, so it retires itself.

    Nothing stores this signal, which is what makes the resolution rule
    trustworthy: the contest is recomputed against what is in force *now*, so a
    value the record later adopted simply stops being reported. A stored
    conflict would need somebody to remember to close it.
    """
    base = baseline_mod.get()
    entity, path = "VAR-02A", "food.fibre_g"
    standing = base.attr_sources[(entity, path)].doc_id
    loser = next(d.id for d in base.source_docs.values()
                 if d.precedence < base.source_docs[standing].precedence)
    held = base.attr_values[(entity, path)]

    # The portal restates exactly what is already in force. It still loses the
    # precedence contest; there is simply nothing left to argue about.
    _live_row(entity, path, held, loser)

    signals = nodes._signals_in_force(tape.sim_now())
    assert not [s for s in signals if s["kind"] == "SOURCE_CONFLICT"]


def test_a_required_value_submitted_empty_opens_a_case_as_a_gap():
    """A mandatory field emptied is not a correction to what it used to say.

    Classified by `ingest.is_gap` rather than by attribute path, so the queue
    and the ingestion that recorded the row cannot disagree about what counts
    as missing - and so the row reads as "this is now absent" rather than as
    "this changed to nothing".
    """
    base = baseline_mod.get()
    entity, path = "VAR-01A", "identifiers.gtin"
    assert base.attr_defs[path].required_for, "the fixture attribute is mandatory"

    _live_row(entity, path, None, base.attr_sources[(entity, path)].doc_id)

    signals = nodes._signals_in_force(tape.sim_now())
    gap = next(s for s in signals if s["kind"] == "DATA_GAP")

    assert gap["attribute_paths"] == [path]
    assert "empty" in gap["summary"]
    assert "required on" in gap["summary"]
    assert nodes.case_of(gap, base) == PURIFIER


def test_withdrawing_a_revision_nothing_stands_on_opens_nothing():
    """The tape's own withdrawal, and why the rule is scoped to the revision.

    DOC-06 v2 was a provisional dimensional drawing retracted when the tooling
    audit closed. v1 stands, every value on the kettle is exactly as supported
    as it was, and reporting that as an open case would turn the one piece of
    good news on the tape into a critical incident.
    """
    kettle_doc = baseline_mod.get().source_docs["DOC-06"]
    assert kettle_doc.version == "v1", (
        "the version the kettle's values actually stand on")

    signals = nodes._signals_in_force(tape.sim_now())

    assert not [s for s in signals if s["kind"] == "DOC_WITHDRAWN"], (
        "a retracted revision nothing was recorded from is not an open case")


def test_a_correction_that_names_no_product_is_not_dropped():
    """A correction the system could not attribute to a product is exactly the
    kind of thing that must stay on a reviewer's list."""
    base = baseline_mod.get()
    orphan = {"id": "SIG-ORPHAN", "kind": "SPEC_CORRECTION",
              "entities": ["CH-WEB", "DOC-01"], "attribute_paths": [],
              "detected_at": "2026-09-29T07:00",
              "summary": "a channel and a document name no product"}

    assert nodes.case_of(orphan, base) is None

    cases = nodes.open_cases([orphan], base)
    assert [c["case_id"] for c in cases] == [nodes.UNSCOPED_CASE]
    assert cases[0]["signal_ids"] == ["SIG-ORPHAN"]
    assert cases[0]["product"] == ""


def test_cases_are_ordered_worst_first_and_deterministically():
    base = baseline_mod.get()
    power = {"id": "SIG-P", "kind": "SPEC_CORRECTION", "entities": [MAX_MODEL],
             "attribute_paths": ["specs.power_w"],
             "detected_at": "2026-09-29T07:00", "summary": "65 W"}
    allergen = {"id": "SIG-A", "kind": "ALLERGEN_CHANGE", "entities": ["VAR-02A"],
                "attribute_paths": ["food.allergens.may_contain"],
                "detected_at": "2026-10-02T09:00", "summary": "may contain peanuts"}
    # Names its listing first, so it resolves to a product the long way round.
    rejection = {"id": "SIG-R", "kind": "CHANNEL_REJECTION",
                 "entities": ["LST-11", "CH-MKT-B", "VAR-02A"],
                 "attribute_paths": [], "detected_at": "2026-10-01T08:00",
                 "summary": "CH-MKT-B has LST-11 as REJECTED"}

    cases = nodes.open_cases([power, allergen, rejection], base)

    assert [c["case_id"] for c in cases] == [SNACK, PURIFIER]
    assert cases[0]["safety"] is True, "the safety case must come first"
    assert cases[0]["severity_hint"] == "CRITICAL"
    # Safety outranks age: the purifier's correction is three days older.
    assert cases[1]["first_detected"] < cases[0]["first_detected"]
    assert cases[0]["signal_ids"] == ["SIG-A", "SIG-R"]
    # Order is a property of the cases, not of the order they arrived in.
    shuffled = nodes.open_cases([rejection, power, allergen], base)
    assert [c["case_id"] for c in shuffled] == [SNACK, PURIFIER]


def test_a_replan_stays_on_the_same_case():
    """Re-planning on the same thread exists so the decision stays the same one.
    A revision that re-picked would walk the incident onto another product."""
    _record_the_corrections()
    graph_build.start_run(INCIDENT, "T-CASE-REPLAN", case_id=PURIFIER)
    _release_the_clarification()

    values = graph_build.replan_run("T-CASE-REPLAN", reason="DOC-01 v3")["values"]

    assert values["revision"] == 1
    assert values["case_id"] == PURIFIER
    purifier = [c["entities"] for c in values["scope_candidates"]
                if MAX_MODEL in c["entities"] or BASE_MODEL in c["entities"]]
    assert purifier == [[MAX_MODEL]], "the revision lost the case it was on"


# ---------------------------------------------------------------------------
# Approval gates publication
# ---------------------------------------------------------------------------


def test_nothing_publishes_before_a_decision():
    _run()
    assert db.query("SELECT * FROM committed_actions") == []
    assert db.query("SELECT * FROM audit WHERE action = 'COMMIT'") == []
    assert db.query("SELECT * FROM facts WHERE attr LIKE 'published.%'") == []


def test_a_decision_is_recorded_with_decided_provenance():
    """A human choice must be distinguishable from a model's inference."""
    _run()
    graph_build.resume(THREAD, {"decision": "APPROVE", "actor": "a.reviewer"})

    rows = db.query("SELECT * FROM audit WHERE action = 'DECIDE'")
    assert len(rows) == 1
    assert db.loads(rows[0]["provenance"])["kind"] == "DECIDED"
    assert rows[0]["actor"] == "a.reviewer"


def test_a_publish_is_recorded_with_committed_provenance():
    _run()
    result = graph_build.resume(THREAD, {"decision": "APPROVE",
                                         "actor": "a.reviewer"})

    assert result["values"]["commit_result"]["committed"] is True
    rows = db.query("SELECT * FROM audit WHERE action = 'COMMIT'")
    assert len(rows) == 1
    assert db.loads(rows[0]["provenance"])["kind"] == "COMMITTED"


def test_rejection_closes_the_run_without_publishing():
    _run()
    result = graph_build.resume(THREAD, {"decision": "REJECT",
                                         "actor": "a.reviewer",
                                         "comment": "wait for the supplier"})

    assert result["values"]["approval"]["decision"] == "REJECT"
    assert db.query("SELECT * FROM committed_actions") == []


# ---------------------------------------------------------------------------
# Durability - "recover safely from partial execution"
# ---------------------------------------------------------------------------


def test_a_run_survives_the_process_being_lost():
    """Drop every in-memory object and rebuild from the checkpoint alone.

    A run waiting on a reviewer overnight must still be there in the morning.
    """
    _run()

    graph_build.reset_graph()          # as if the process had restarted
    nodes.baseline_mod.get.cache_clear()

    recovered = graph_build.snapshot(THREAD)
    assert recovered["awaiting_approval"] is True
    assert recovered["values"]["recommendation"]

    result = graph_build.resume(THREAD, {"decision": "APPROVE",
                                         "actor": "a.reviewer"})
    assert result["values"]["commit_result"]["committed"] is True


def test_resuming_twice_publishes_once():
    """A redelivered decision must not push the same content twice.

    The publish is idempotency-keyed on incident and scenario, so replaying the
    approval returns the original result rather than acting again. This is the
    at-least-once event plane's guarantee showing up at the far end.
    """
    _run()
    decision = {"decision": "APPROVE", "actor": "a.reviewer"}
    graph_build.resume(THREAD, decision)

    before = db.query("SELECT * FROM committed_actions")
    published = db.query("SELECT * FROM facts WHERE attr LIKE 'published.%'")
    assert before and published, "the first decision published nothing to replay"

    try:
        graph_build.resume(THREAD, decision)
    except Exception:
        pass  # a finished thread may refuse the resume outright; either is fine

    assert len(db.query("SELECT * FROM committed_actions")) == len(before)
    assert len(db.query("SELECT * FROM facts WHERE attr LIKE 'published.%'")) \
        == len(published)


def test_checkpoint_history_is_available_for_time_travel():
    _run()
    history = graph_build.history(THREAD)

    assert len(history) > 3
    assert any(h["status"] == "AWAITING_APPROVAL" for h in history)
    # Newest first, and every entry names the checkpoint it can be resumed from.
    assert all(h["checkpoint_id"] for h in history)


# ---------------------------------------------------------------------------
# What the run spent, and what it read
# ---------------------------------------------------------------------------


POWER_SIGNAL = {"id": "SIG-P", "kind": "SPEC_CORRECTION", "entities": [MAX_MODEL],
                "attribute_paths": ["specs.power_w"],
                "detected_at": "2026-09-29T07:00", "summary": "65 W"}


def _answering(reply: dict, **usage):
    """A reachable gateway, which the suite otherwise never has."""
    def complete_json(messages, **kwargs):
        return reply, LlmUsage(**usage)
    return complete_json


def test_a_node_records_what_its_model_calls_cost(monkeypatch):
    """Per-run cost is a SQL aggregate over llm_calls; the checkpointed state
    the UI renders has to carry it too, or the run cannot price itself."""
    monkeypatch.setattr(gateway, "complete_json",
                        _answering({"severity": "HIGH", "material": True,
                                    "reason": "applied the retrieved policy"},
                                   prompt_tokens=120, completion_tokens=30,
                                   total_tokens=150, cost_usd=0.0021, cached=True))

    update = nodes.triage({"run_id": "RUN-SPEND", "signals": [POWER_SIGNAL]})

    assert update["usage"] == {"triage": {
        "calls": 1, "prompt_tokens": 120, "completion_tokens": 30,
        "total_tokens": 150, "cost_usd": 0.0021, "cache_hits": 1}}


def test_a_node_that_fell_back_records_no_spend():
    """The negative control, and the path CI takes: a node that never reached a
    model has nothing to report, and reporting zeroes would suggest it did."""
    update = nodes.triage({"run_id": "RUN-SPEND", "signals": [POWER_SIGNAL]})

    assert update["usage"] == {}
    assert update["errors"], "a node running blind must say so"


def test_spend_is_keyed_by_node_so_one_writer_does_not_erase_another():
    """The reducer merges dicts by overwriting keys rather than summing them, so
    a flat accumulator would keep only the last node to write."""
    extract = nodes._spend("extract", LlmUsage(prompt_tokens=10, cost_usd=0.001),
                           LlmUsage(prompt_tokens=5, cost_usd=0.002, cached=True))
    triage = nodes._spend("triage", LlmUsage(completion_tokens=7))

    assert extract["extract"]["calls"] == 2
    assert extract["extract"]["prompt_tokens"] == 15
    assert extract["extract"]["cost_usd"] == 0.003
    assert extract["extract"]["cache_hits"] == 1
    assert set(_merge_dicts(extract, triage)) == {"extract", "triage"}


def test_every_trace_line_says_how_long_it_took():
    """"Which node is slow" has to be answerable from the run's own artefact."""
    trace = _run()["values"]["trace"]
    elapsed = [t["elapsed_ms"] for t in trace]

    assert len(elapsed) == len(trace)
    assert all(isinstance(ms, (int, float)) and ms >= 0 for ms in elapsed)
    assert sum(elapsed) > 0, "a whole run cannot have taken no time at all"


def test_a_document_with_no_inline_body_is_read_from_disk():
    """``SourceDoc.body_path`` is where the seed pack keeps a document's
    extracted text, so a notice that arrives as a reference is still read."""
    base = baseline_mod.get()
    event = Event(id="EVT-REF", seq=1, ts=nodes.tape.sim_now(),
                  type="SPEC_DOC", source="SUPPLIER_PORTAL",
                  payload={"doc_id": "DOC-01", "doc_version": "v1"}, body=None)

    text = nodes._document_text(base, event)

    assert "DOC-01" in text
    assert base.source_docs["DOC-01"].body_path == "docs/DOC-01-v1.txt"


def test_reading_from_disk_never_breaks_a_run(monkeypatch):
    """Three ways it can fail, and all three degrade to the body the event
    carries. A document that cannot be opened must not end a correction run.

    The version guard is not politeness: ``body_path`` names one revision of a
    document, and feeding v1's text to a v2 notice would have the run extract
    superseded values as though they were the correction.
    """
    base = baseline_mod.get()

    def event_for(payload: dict):
        return Event(id="EVT-REF", seq=1, ts=nodes.tape.sim_now(),
                     type="SPEC_DOC", source="SUPPLIER_PORTAL",
                     payload=payload, body=None)

    # A revision the file on disk is not.
    assert nodes._document_text(
        base, event_for({"doc_id": "DOC-01", "doc_version": "v2"})) == ""
    # A document with no extracted text, and one the catalog never heard of.
    assert nodes._document_text(base, event_for({"doc_id": "DOC-02"})) == ""
    assert nodes._document_text(base, event_for({"doc_id": "DOC-99"})) == ""
    # And the file simply not being there.
    monkeypatch.setattr(baseline_mod, "data_dir", lambda: Path("no/such/place"))
    assert nodes._document_text(base, event_for({"doc_id": "DOC-01"})) == ""


# ---------------------------------------------------------------------------
# The republish gate
# ---------------------------------------------------------------------------


def test_publish_is_refused_once_a_later_source_version_is_in_force():
    """The print batch prepared under DOC-01 v2 must not go out after v3 has
    landed, however good it looked when the reviewer approved it.

    The refusal is a race rather than a verdict, so the run re-plans against
    the version now in force and comes back to the gate instead of failing.
    """
    result = _run()
    as_of = nodes._iso(result["values"]["as_of"])
    for variant_id in baseline_mod.get().variants_of[PURIFIER]:
        store.record("variant", variant_id, "specs.power_w", 65,
                     valid_from=as_of, recorded_at=as_of,
                     provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                           source_id="DOC-01:v3"))

    after = graph_build.resume(THREAD, {"decision": "APPROVE",
                                        "actor": "a.reviewer"})

    assert after["values"]["commit_result"]["error"] == "stale_version"
    assert db.query("SELECT * FROM committed_actions") == []
    assert after["values"]["publish_retries"] == 1
    assert after["awaiting_approval"] is True, "the retry never reached the gate"


# ---------------------------------------------------------------------------
# Corrections that clear, and corrections of corrections
# ---------------------------------------------------------------------------


def test_a_withdrawn_notice_is_not_an_open_correction():
    """The kettle dimensions were flagged provisional and the audit closed
    three days later. Both are on the tape; only one of them is live."""
    values = _run()["values"]
    # The whole released window, not its last few hundred events. The tape
    # carries thousands now, and "the last 400" stopped reaching back as far as
    # the notice this test is about.
    released = tape.released(limit=100_000)

    assert any((e.payload or {}).get("withdraws") == "DOC-06:v2"
               for e in released), "the withdrawal is not in the released window"
    assert not any("VAR-04A" in (s.get("entities") or [])
                   for s in values["signals"])


def test_a_withdrawal_retires_what_it_clears():
    hold = {"id": "h", "kind": "SPEC_CORRECTION", "entities": ["VAR-04A"],
            "detected_at": "2026-09-11T08:00", "summary": "dimensions provisional"}
    withdrawal = {"id": "w", "kind": "DOC_WITHDRAWN", "entities": ["VAR-04A"],
                  "detected_at": "2026-09-14T10:00", "resolves_issue": True,
                  "summary": "revision withdrawn, nothing changes"}
    unrelated = {"id": "p", "kind": "SPEC_CORRECTION", "entities": ["PRD-01"],
                 "attribute_paths": ["specs.power_w"],
                 "detected_at": "2026-09-29T07:00", "summary": "65 W"}

    merged = merge_signals([hold, unrelated], [withdrawal])

    assert [s["id"] for s in merged] == ["p"]


def test_an_unwithdrawn_notice_still_stands():
    hold = {"id": "h", "kind": "SPEC_CORRECTION", "entities": ["VAR-04A"],
            "detected_at": "2026-09-11T08:00", "summary": "dimensions provisional"}
    assert merge_signals([hold], []) == [hold]


def test_a_revision_supersedes_but_does_not_resolve():
    """A second correction to the same field replaces the first; it does not
    mean the field is now right on the page."""
    first = {"id": "c1", "kind": "SPEC_CORRECTION", "entities": [MAX_MODEL],
             "attribute_paths": ["specs.power_w"],
             "detected_at": "2026-09-29T07:00", "summary": "65 W"}
    second = {"id": "c2", "kind": "SPEC_CORRECTION", "entities": [MAX_MODEL],
              "attribute_paths": ["specs.power_w"], "is_correction": True,
              "detected_at": "2026-10-03T09:00", "summary": "65 W, Max only"}

    merged = merge_signals([first], [second])

    assert [s["id"] for s in merged] == ["c2"]


def test_a_withdrawal_does_not_cancel_an_unrelated_correction():
    kettle = {"id": "k", "kind": "DOC_WITHDRAWN", "entities": ["VAR-04A"],
              "detected_at": "2026-09-14T10:00", "resolves_issue": True,
              "summary": "revision withdrawn"}
    purifier = {"id": "p", "kind": "SPEC_CORRECTION", "entities": [MAX_MODEL],
                "attribute_paths": ["specs.power_w"],
                "detected_at": "2026-09-29T07:00", "summary": "65 W"}

    assert [s["id"] for s in merge_signals([purifier], [kettle])] == ["p"]


def test_a_correction_of_a_correction_withdraws_the_pending_approval():
    """A recommendation whose evidence has moved is not one anybody may still
    approve, so the gate is closed as a real decision rather than cleared."""
    assert _run()["awaiting_approval"] is True
    _release_the_clarification()

    graph_build.replan_run(THREAD, reason="DOC-01 v3: the 65 W is the Max only")

    withdrawn = [a for a in db.query("SELECT * FROM approvals")
                 if a["actor"] == "system"]
    assert len(withdrawn) == 1
    assert withdrawn[0]["decision"] == "REJECT"
    assert "superseded before decision" in withdrawn[0]["comment"]

    decisions = db.query("SELECT * FROM audit WHERE action = 'DECIDE'")
    assert [d["actor"] for d in decisions] == ["system"]
    assert db.loads(decisions[0]["provenance"])["kind"] == "DECIDED"
    assert db.query("SELECT * FROM committed_actions") == []


def test_a_correction_of_a_correction_narrows_the_scope_and_reports_the_move():
    """The finale. v2 said "the Northaven AP300 draws 65 W" and could have meant
    either model; v3 says it is the Max, and certifies the base model at 45 W
    on a different document. The record now separates the two readings, so the
    revision must stop applying the correction to the base model - and say what
    that changed."""
    before = _run()
    assert before["values"]["chosen_scope"]["entities"] == [BASE_MODEL, MAX_MODEL]
    _release_the_clarification()

    after = graph_build.replan_run(THREAD, reason="DOC-01 v3")
    values = after["values"]

    assert values["revision"] == 1
    assert values["chosen_scope"]["entities"] == [MAX_MODEL]
    purifier = [c["entities"] for c in values["scope_candidates"]
                if MAX_MODEL in c["entities"] or BASE_MODEL in c["entities"]]
    assert purifier == [[MAX_MODEL]], "the base model is still in scope"

    diff = values["plan_diff"]
    assert diff, "a revision that cannot say what moved is a restart"
    assert diff["revision"] == 1
    assert diff["held"] is False
    assert diff["previous"]["scope"]["entities"] == [BASE_MODEL, MAX_MODEL]
    assert {"listings_ready_pct", "fields_affected"} <= set(diff["moved"])
    # The superseded plan is still on the table, re-scored against v3.
    assert any(r.get("carried_from") for r in values["ranked"])


# ---------------------------------------------------------------------------
# Doing independent model work at once does not change the answer
#
# These run with the gateway unreachable like everything else here, so what is
# concurrent is the fallback rather than a model call. That is enough to test
# the property that matters: the pool, the per-worker collections and the
# ordered reassembly are exercised either way, and it is the reassembly that
# could silently reorder a change set. The latency claim is verified by running
# the thing against a real gateway; the correctness claim is verified here.
# ---------------------------------------------------------------------------


def _reset_world() -> None:
    """Put the store back where the fixture found it.

    Needed by the tests that run the same correction twice and compare. A
    second run against a store the first one wrote to is reading a different
    world, so an equality between them would prove nothing.
    """
    db.init_db(drop=True)
    graph_build.reset_graph()
    for suffix in ("", "-wal", "-shm"):
        path = graph_build.checkpoint_path()
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            candidate.unlink()
    tape.load_tape(reset=True)
    rag_index.build(include_comms=True, embed=False)
    # The same window the fixture opened. It has to be the same one, or the
    # two runs this exists to compare are reading different worlds - which is
    # what "put the store back where the fixture found it" means.
    ingest.ingest(tape.jump_to(_seq_of(doc_id="DOC-04", version="v2")))


#: The fields of a rewrite record that describe *what was decided*, as opposed
#: to how long it took to decide it. Compared as a whole rather than field by
#: field so a newly added key is caught by this test rather than ignored by it.
def _rewrites(values: dict) -> list[tuple]:
    return [(r["asset_id"], r["listing_id"], r["channel_id"], r["field"],
             r["proposed_text"], r["status"], r["note"], tuple(r["citations"]),
             r["budget"], r["used"])
            for r in values.get("regenerated") or []]


def _appended(update: dict) -> list[tuple]:
    """The actions a regeneration pass added, reduced to what they say.

    Action identifiers are UUIDs minted per call, so they differ between any two
    passes and say nothing about whether the two agreed.
    """
    rows = []
    for row in update.get("ranked") or []:
        for action in (row.get("delta") or {}).get("actions") or []:
            rows.append((row.get("name"), row.get("trace_hash"), action["kind"],
                         action.get("asset_id"), action.get("field"),
                         action.get("proposed_text"), action.get("reason"),
                         action.get("listing_id")))
    return rows


def test_parallel_regeneration_matches_the_sequential_result(monkeypatch):
    """The whole point. Concurrency here is allowed to change the clock and
    nothing else - not the text, not the citations, not the order, and not the
    change set that reaches the reviewer.

    Compared at the node rather than across two whole runs, deliberately. A run
    pins its recorded instant from the wall clock and the validator folds that
    instant into the trace hash, so two runs legitimately disagree on the hash
    for reasons that have nothing to do with concurrency. Feeding one state to
    the node twice removes that difference and leaves only the one under test.
    """
    state = _run()["values"]

    monkeypatch.setattr(nodes, "MAX_REGEN_WORKERS", 1)
    serial = nodes.regenerate(copy.deepcopy(state))

    monkeypatch.setattr(nodes, "MAX_REGEN_WORKERS", 6)
    parallel = nodes.regenerate(copy.deepcopy(state))

    assert _rewrites(serial), "the pass rewrote nothing, so this proves nothing"
    assert _rewrites(serial) == _rewrites(parallel)
    assert _appended(serial) == _appended(parallel)
    assert serial["status"] == parallel["status"]

    # Errors are compared by shape, not verbatim, and that is not a weakening.
    # The gateway's outage message carries a live countdown to the circuit
    # breaker's next retry - "(retrying in 27s)" - so two passes seconds apart
    # legitimately disagree on the string while agreeing on everything the
    # reviewer acts on. Comparing the text would be a test of the clock.
    def outages(update: dict) -> list[str]:
        return sorted(e.split(":", 1)[0] for e in update["errors"])

    assert outages(serial) == outages(parallel)
    assert (serial["trace"][0]["summary"] == parallel["trace"][0]["summary"]),         "the node's own account of what it did must not depend on the pool"


def test_results_follow_the_targets_not_the_replies(monkeypatch):
    """Assembled in target order, never in completion order. Ordering by
    whichever reply landed first is not a tie-break that is usually right, it is
    a different change set on a fast network."""
    monkeypatch.setattr(nodes, "MAX_REGEN_WORKERS", 6)
    values = _run()["values"]
    written = values.get("regenerated") or []

    assert written, "the run rewrote nothing, so this proves nothing"
    # Unsettled fields first, then the ones already corrected deterministically
    # that still lean on a withdrawn claim - the order the node documents, and
    # the order a reviewer reads the cap in.
    settled_at = [i for i, r in enumerate(written) if r["status"] == "SETTLED"]
    unsettled_at = [i for i, r in enumerate(written) if r["status"] != "SETTLED"]
    assert not (settled_at and unsettled_at) or min(settled_at) > max(unsettled_at)
    # And no asset is rewritten twice, which a racing assembly could produce.
    assert len({r["asset_id"] for r in written}) == len(written)


def test_spend_within_a_stage_survives_concurrent_workers():
    """Six workers each returning their own usage must total what six calls made
    one after another would have totalled. The serial code appended to one
    shared list, which is correct under one thread and silently lossy under
    six."""
    per_worker = [[LlmUsage(prompt_tokens=10, completion_tokens=2, cost_usd=0.001)],
                  [LlmUsage(prompt_tokens=5, completion_tokens=1, cost_usd=0.002,
                            cached=True)],
                  [],
                  [LlmUsage(prompt_tokens=7, completion_tokens=3, cost_usd=0.004)]]
    merged: list[LlmUsage] = []
    for worker in per_worker:
        merged.extend(worker)

    folded = nodes._spend("regenerate", *merged)["regenerate"]
    assert folded["calls"] == 3
    assert folded["prompt_tokens"] == 22
    assert folded["completion_tokens"] == 6
    assert folded["cost_usd"] == pytest.approx(0.007)
    assert folded["cache_hits"] == 1


def test_a_gateway_outage_is_reported_once_however_many_workers_meet_it():
    """One outage is one fact about the run. The serial path deduplicated with a
    membership test against a shared list, which six workers racing on would
    turn into up to six identical lines."""
    values = _run()["values"]
    errors = values.get("errors") or []

    for stage in ("extract", "regenerate"):
        outages = [e for e in errors
                   if e.startswith(f"{stage}: ")
                   and ("cannot reach" in e or "unreachable" in e)]
        assert len(outages) <= 1, f"{stage} reported its outage {len(outages)} times"
    # And the run said out loud that it ran blind rather than presenting a
    # fallback as a model's conclusion.
    assert any("cannot reach" in e or "unreachable" in e for e in errors)


def test_extraction_persists_in_tape_order_however_its_readings_raced(monkeypatch):
    """Readings may be fetched at once; writes may not. The watermark advances
    as each document is persisted and the next is read against it, so a covering
    email restating its own specification sees what the specification wrote."""
    monkeypatch.setattr(nodes, "MAX_EXTRACT_WORKERS", 1)
    serial = _run("T-EXTRACT-SERIAL")["values"]

    _reset_world()
    monkeypatch.setattr(nodes, "MAX_EXTRACT_WORKERS", 6)
    parallel = _run("T-EXTRACT-PARALLEL")["values"]

    def signals(values: dict) -> list[tuple]:
        return [(s["kind"], s.get("entity_id"), tuple(s.get("attribute_paths") or []))
                for s in values.get("signals") or []]

    assert signals(serial), "nothing was extracted, so this proves nothing"
    assert signals(serial) == signals(parallel)

    # The trace still reads document by document in the order the tape
    # delivered them, which is what a reviewer follows.
    def documents(values: dict) -> list[str]:
        return [t["summary"].split()[0] for t in values["trace"]
                if t["node"] == "extract" and t["summary"].startswith("EVT-")]

    assert documents(serial) == documents(parallel)


# ---------------------------------------------------------------------------
# The cache, and what it is allowed to claim
#
# Every model call is cached in SQLite keyed on (model, temperature, messages),
# so a rehearsal populates it and the run a room watches reads it back. The
# point is not speed - the loop finishes in about twenty seconds cold - it is
# that the run is the same every time, independent of a venue's wifi.
#
# What the cache must never do is flatter the numbers. A served call is a hit,
# not work done, and a usage panel that reported otherwise would undermine the
# thing the cache exists to protect.
# ---------------------------------------------------------------------------


def test_a_served_call_is_recorded_as_a_hit_not_as_work():
    """Reported honestly or the audit view is telling a story about spend that
    did not happen."""
    from sc.contracts import LlmUsage

    served = LlmUsage(prompt_tokens=10, completion_tokens=2, cost_usd=0.001,
                      cached=True)
    live = LlmUsage(prompt_tokens=10, completion_tokens=2, cost_usd=0.001)

    folded = nodes._spend("extract", live, served)["extract"]

    assert folded["calls"] == 2
    assert folded["cache_hits"] == 1, "a served call must be countable as served"


def test_warming_the_cache_leaves_no_pending_decision():
    """A warmed run is thrown away on its own thread. A presenter opening the
    review screen must not find a half-worked case somebody else started."""
    import scripts.prepare_demo as prepare

    result = prepare.warm(thread="T-WARM-TEST")

    # With no gateway this warms nothing, which is the correct and honest
    # outcome - a venue with no network still gets a prepared demo.
    assert "warmed" in result and "calls" in result
    pending = graph_build.snapshot("T-WARM-TEST")
    assert pending.get("thread_id") == "T-WARM-TEST"
    # Whatever it did, it did on its own thread and not on the demo's.
    assert graph_build.snapshot(THREAD).get("values", {}).get("trace") in (None, [])


def test_two_validations_of_one_change_set_agree_on_the_trace_hash():
    """The reproducibility the audit trail rests on, checked at the boundary
    where it is actually true.

    Two whole *runs* legitimately disagree: a run pins its recorded instant from
    the wall clock and the validator folds that instant into the hash, so the
    difference is the clock rather than the concurrency. Pinning the instant
    removes it and leaves the property under test - that validating one change
    set twice, with the rewrites fanned out, produces one hash.
    """
    from sc.sim.engine import simulate
    from sc.contracts import ChangeSet

    state = _run()["values"]

    nodes.MAX_REGEN_WORKERS = 6
    produced = nodes.regenerate(copy.deepcopy(state))
    delta = (produced["ranked"][0].get("delta") or {}) if produced["ranked"] else {}
    assert delta.get("actions"), "the pass proposed nothing, so this proves nothing"

    base = baseline_mod.get()
    change_set = ChangeSet.model_validate(delta)
    hashes = {simulate(base, change_set).trace_hash for _ in range(5)}

    assert len(hashes) == 1, f"one change set produced {len(hashes)} hashes"
