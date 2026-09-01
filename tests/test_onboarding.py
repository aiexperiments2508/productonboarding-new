"""Judging a batch, and filling only what can be cited.

Three claims are load bearing here and each has its own test, because each one
would be easy to break and nothing else would notice:

*   **A safety-class gap is never an AI-fix candidate.** Not a candidate that
    needs approval - not a candidate. A plausible allergen list is not an
    allergen list, and it gets printed on a label and read by somebody who
    needs it to be right.

*   **A gap with no retrievable passage is never counted fixable.** This is the
    one negative in the feature that can be proved rather than estimated:
    ``_validated_fill`` drops any fill whose chunk is not in the supplied set,
    so no passage means no fill. A count that guessed instead would be a
    promise the system cannot keep.

*   **Applying fills publishes nothing.** No approval row, no reservation, no
    committed action. A product becomes ready by having no findings left, which
    is arithmetic; publishing is a separate decision behind a separate gate,
    and a button that did both would defeat the gate the rest of the system is
    built around.

The gateway is unreachable throughout, as it is for the whole suite. That is
not a limitation of these tests - it is the path that has to be right, because
a venue with no model must get "nothing was filled and here is why" rather than
a plausible allergen list.
"""

from __future__ import annotations

import base64
import io
import os
import zipfile

import pytest

os.environ.setdefault("DB_PATH", "data/test_onboarding.db")

from sc import db  # noqa: E402
from sc.contracts import ProvenanceKind  # noqa: E402
from sc.datapack import sample as sample_mod  # noqa: E402
from sc.datapack import schema  # noqa: E402
from sc.datapack.writers import csv_txt  # noqa: E402
from sc.estate import intake  # noqa: E402
from sc.onboarding import assess as assess_mod  # noqa: E402
from sc.onboarding import batch as batch_mod  # noqa: E402
from sc.onboarding import fix as fix_mod  # noqa: E402
from sc.onboarding import decide as decide_mod  # noqa: E402
from sc.onboarding import fixable as fixable_mod  # noqa: E402
from sc.onboarding import gate as gate_mod  # noqa: E402
from sc.onboarding import history as history_mod  # noqa: E402
from sc.onboarding import suggest as suggest_mod  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.state import store  # noqa: E402

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
    """One bundle, landed. Every test below starts from here."""
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


# ---------------------------------------------------------------------------
# The batch is the submission
# ---------------------------------------------------------------------------


def test_a_batch_is_read_back_from_its_submission(sent):
    found = batch_mod.get(sent["batch_id"])
    assert found is not None
    assert found["entities"] == sent["entities"]
    assert found["file"]["filename"].endswith(".zip")
    assert batch_mod.latest()["batch_id"] == sent["batch_id"]


def test_an_unknown_batch_is_not_invented():
    assert batch_mod.get("SUB-nothing") is None
    assert assess_mod.report("SUB-nothing") is None


# ---------------------------------------------------------------------------
# The sequential pass
# ---------------------------------------------------------------------------


def test_the_pass_walks_every_product_once_in_file_order(sent):
    messages = list(assess_mod.run(sent["batch_id"], pace_ms=0))
    products = [m for m in messages if m["kind"] == "product"]

    assert messages[0]["kind"] == "batch_started"
    assert messages[-1]["kind"] == "batch_finished"
    assert [p["entity_id"] for p in products] == sent["entities"]
    assert [p["ordinal"] for p in products] == list(range(1, len(products) + 1))
    assert all(p["total"] == len(sent["entities"]) for p in products)


def test_every_product_carries_the_path_the_map_lights(sent, base):
    """Resolved on the server: the client should not have to rediscover that a
    variant belongs to a product which belongs to a supplier."""
    for message in assess_mod.run(sent["batch_id"], pace_ms=0):
        if message["kind"] != "product":
            continue
        entity_id = message["entity_id"]
        product = base.products[base.product_of_variant[entity_id]]
        assert message["entities"] == [entity_id, product.id, product.supplier]


def test_the_tally_is_the_sum_of_the_verdicts_it_counted(sent):
    messages = list(assess_mod.run(sent["batch_id"], pace_ms=0))
    products = [m for m in messages if m["kind"] == "product"]
    totals = messages[-1]["totals"]

    assert totals["assessed"] == len(products)
    assert totals["cleared"] + totals["returned"] + totals["blocked"] \
        == totals["assessed"]
    assert totals["cleared"] == sum(
        1 for p in products if p["verdict"] == "READY_TO_LAUNCH")
    assert totals["blocked"] == sum(
        1 for p in products if p["verdict"] == "BLOCKED")


def test_a_narrow_assessment_is_reported_as_narrow(sent):
    """Seven checks of eleven is not a clean result, and a summary that said
    so would be the same omission on every product at once."""
    report = assess_mod.report(sent["batch_id"])
    assert report["checks_complete"] is False
    assert report["caveat"]


def test_the_pace_cannot_reach_a_result(sent):
    """It is presentation. A run with it off returns the same report."""
    slow = assess_mod.report(sent["batch_id"])
    fast = [m for m in assess_mod.run(sent["batch_id"], pace_ms=0)][-1]
    assert slow["totals"] == fast["totals"]
    assert [p["verdict"] for p in slow["products"]] \
        == [p["verdict"] for p in fast["products"]]


def test_the_report_is_recomputed_rather_than_stored(sent):
    """Nothing caches a verdict, so reopening after a change shows the change."""
    first = assess_mod.report(sent["batch_id"])
    second = assess_mod.report(sent["batch_id"])
    assert first["totals"] == second["totals"]
    rows = db.query("SELECT * FROM submissions WHERE id = ?",
                    (sent["batch_id"],))
    columns = {k for k in dict(rows[0])}
    assert "verdict" not in columns and "status" not in columns


# ---------------------------------------------------------------------------
# What a model may be asked to close
# ---------------------------------------------------------------------------


def test_a_safety_class_gap_is_never_a_candidate(base):
    """The load-bearing one."""
    safety = next(path for path, d in base.attr_defs.items() if d.safety_class)
    rows = [{
        "entity_id": "VAR-02A", "attribute_path": safety,
        "label": base.attr_defs[safety].label,
        "dtype": base.attr_defs[safety].dtype,
        "unit": base.attr_defs[safety].unit, "safety_class": True,
    }]
    result = fixable_mod.assess(rows, base)
    assert result.candidates == []
    assert result.counts()["held_safety"] == 1
    assert "safety class" in result.gaps[0].why


def test_candidacy_tracks_retrieval_exactly(base):
    """The sound negative: enrich provably cannot fill what it cannot cite.

    Asserted as the invariant rather than as an outcome. Whether a retrieval
    index happens to be loaded depends on what else has run in the session -
    `index.load` caches, and `test_rag` builds one - so a test that expected
    "no candidates" would pass alone and fail in a suite, for a reason that has
    nothing to do with the property. The property is the *iff*: a gap is a
    candidate exactly when retrieval, asked the way `enrich` asks it, returns
    something.
    """
    from sc.rag import retrieve

    rows = [{
        "entity_id": "VAR-02A", "attribute_path": path,
        "label": base.attr_defs[path].label,
        "dtype": base.attr_defs[path].dtype,
        "unit": base.attr_defs[path].unit, "safety_class": False,
    } for path in ("food.fibre_g", "food.net_weight_g", "origin.country")]

    result = fixable_mod.assess(rows, base)
    assert len(result.gaps) == len(rows)
    for gap in result.gaps:
        found = retrieve.search(gap.attribute_path, top_k=4,
                                doc_types=fixable_mod.DOC_TYPES,
                                entities=["VAR-02A"])
        assert (gap.state == fixable_mod.CANDIDATE) == bool(found), gap
        assert (gap.citation is not None) == bool(found)


def test_a_gap_on_an_entity_nothing_mentions_is_never_a_candidate(base):
    """The negative on its own, with an entity no passage can name."""
    rows = [{
        "entity_id": "VAR-NOSUCHTHING", "attribute_path": "food.fibre_g",
        "label": "Fibre", "dtype": "float", "unit": "g",
        "safety_class": False,
    }]
    result = fixable_mod.assess(rows, base)
    assert result.candidates == []
    assert result.counts()["no_source"] == 1


def test_gaps_come_from_the_findings_the_checks_already_made(sent, base):
    """Not recomputed. Two accounts of what is missing would disagree with the
    verdict printed beside them."""
    report = assess_mod.report(sent["batch_id"])
    for product in report["products"]:
        subjects = {f["subject"] for f in product["findings"]
                    if f["check"] in fixable_mod.GAP_CHECKS}
        gaps = {g["attribute_path"] for g in report["fixable"]["gaps"]
                if g["entity_id"] == product["entity_id"]}
        assert gaps <= subjects


def test_the_headline_says_what_it_is_counting(sent):
    """'A source is on file' is not 'the AI will fix it', and the label says so
    rather than leaving a reader to assume the stronger claim."""
    report = assess_mod.report(sent["batch_id"])
    label = report["fixable"]["label"]
    assert "reading question" in label
    assert report["fixable"]["read"] is False


# ---------------------------------------------------------------------------
# Applying, and everything it must not do
# ---------------------------------------------------------------------------


def test_applying_needs_an_actor(sent):
    from fastapi.testclient import TestClient

    import sc.main as main

    client = TestClient(main.app)
    response = client.post(
        f"/api/intake/batches/{sent['batch_id']}/fix", json={})
    assert response.status_code == 400
    assert "attributable" in response.json()["detail"]


def test_with_no_gateway_nothing_is_filled_and_every_gap_is_explained(sent):
    """The path CI actually exercises, and the one a venue with no model gets."""
    result = fix_mod.apply(sent["batch_id"], actor="gr25")
    assert result["counts"]["filled"] == 0
    for requested in result["requested"]:
        assert requested["why"]
    assert result["note"]


def test_applying_writes_no_approval_and_no_reservation(sent):
    """The claim that keeps 'push it through' honest."""
    before = (db.query("SELECT COUNT(*) c FROM approvals")[0]["c"],
              db.query("SELECT COUNT(*) c FROM reservations")[0]["c"],
              db.query("SELECT COUNT(*) c FROM committed_actions")[0]["c"])
    fix_mod.apply(sent["batch_id"], actor="gr25")
    after = (db.query("SELECT COUNT(*) c FROM approvals")[0]["c"],
             db.query("SELECT COUNT(*) c FROM reservations")[0]["c"],
             db.query("SELECT COUNT(*) c FROM committed_actions")[0]["c"])
    assert before == after


def test_anything_written_is_inferred_and_never_recorded(sent):
    """A model's reading must not acquire the provenance of a supplier's
    assertion.

    ``fix`` has two doors and this pins the autonomous one: everything it
    writes goes through ``write_inferred`` -> ``ingest.record_attribute``,
    which hard-codes INFERRED. The other door, ``write_decided``, is reachable
    only from a named person's decision and is pinned separately below."""
    before = {row["id"] for row in db.query("SELECT id FROM facts")}
    fix_mod.apply(sent["batch_id"], actor="gr25")
    written = db.query("SELECT * FROM facts")
    for row in written:
        if row["id"] in before:
            continue
        provenance = db.loads(row["provenance"])
        assert provenance["kind"] == ProvenanceKind.INFERRED


def test_the_apply_is_audited_against_the_person_who_asked(sent):
    fix_mod.apply(sent["batch_id"], actor="gr25")
    rows = db.query(
        "SELECT * FROM audit WHERE action = ? AND entity_id = ?",
        ("APPLY_ENRICHMENT", sent["batch_id"]))
    assert rows and rows[0]["actor"] == "gr25"


def test_the_report_after_applying_is_re_assessed_rather_than_predicted(sent):
    """A product is ready because its findings are gone, and the only way to
    know that is to look again."""
    result = fix_mod.apply(sent["batch_id"], actor="gr25")
    fresh_report = assess_mod.report(sent["batch_id"])
    assert result["totals"] == fresh_report["totals"]


# ---------------------------------------------------------------------------
# The compliance gate
# ---------------------------------------------------------------------------


def _withdraw(entity_id: str) -> None:
    """Put a withdrawal notice in force against one variant.

    ``sale_permitted`` is the one gate check that needs no model, which is what
    lets these tests run on the same closed port as the rest of the suite.
    """
    from sc.contracts import Provenance

    store.record("variant", entity_id, "compliance.sale_permitted", False,
                 valid_from=tape.sim_now(), recorded_at=tape.sim_now(),
                 provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                       source_id="REG-003"))


def test_a_product_the_gate_stops_is_not_onboarded(sent):
    """The whole reason the gate is a stage rather than a finding.

    A product that may not lawfully be sold does not get its gaps collected,
    which is what stops anything downstream retrieving a source for it or
    proposing a value nobody will ever read.
    """
    held = sent["entities"][0]
    _withdraw(held)

    products = {m["entity_id"]: m for m in assess_mod.run(
        sent["batch_id"], pace_ms=0) if m["kind"] == "product"}

    stopped = products[held]
    assert stopped["gate"]["passed"] is False
    assert stopped["gate"]["authority"] == gate_mod.REGULATION
    assert stopped["gaps"] == 0
    assert stopped["gate"]["why"], "a supplier is owed a reason"
    assert any(f["check"] == "sale_permitted"
               for f in stopped["gate"]["findings"])


def test_the_gate_does_not_swallow_the_findings_onboarding_is_about(sent):
    """A stopped product's data findings are partitioned, not discarded.

    The gate answers "may we sell this"; the rest of the assessment still
    answers "is the record complete", and a screen that showed only the first
    would have to re-run the second to say anything else.
    """
    held = sent["entities"][0]
    _withdraw(held)
    summary = [m for m in assess_mod.run(sent["batch_id"], pace_ms=0)
               if m.get("entity_id") == held][0]

    checked = summary["gate"]
    assert len(checked["findings"]) + len(checked["data_findings"]) \
        == summary["open"]
    assert not any(f["check"] in gate_mod.GATE_CHECKS
                   for f in checked["data_findings"])


def test_a_stopped_product_is_counted_as_stopped(sent):
    """``stopped`` overlaps the verdict buckets rather than replacing them.

    Asserted rather than assumed: making the four numbers add up would mean
    either zeroing ``blocked`` - every blocking finding is also a gate finding -
    or hiding the policy breaches inside it.
    """
    _withdraw(sent["entities"][0])
    totals = list(assess_mod.run(sent["batch_id"], pace_ms=0))[-1]["totals"]

    assert totals["stopped"] >= 1
    assert totals["cleared"] + totals["returned"] + totals["blocked"] \
        == totals["assessed"]


def test_the_gate_is_named_checks_and_never_a_severity():
    """A policy breach stops onboarding without being a statement about
    legality, so the gate cannot be ``severity == BLOCKING``."""
    assert gate_mod.POLICY_CHECK in gate_mod.GATE_CHECKS
    stopped = gate_mod.evaluate({
        "findings": [{"check": gate_mod.POLICY_CHECK, "severity": "OPEN",
                      "basis": "POL-001", "detail": "policy says otherwise"}],
        "checks_complete": True})
    assert stopped["passed"] is False
    assert stopped["authority"] == gate_mod.POLICY
    assert "POL-001" in stopped["why"]


# ---------------------------------------------------------------------------
# Priors, and the score composed from them
# ---------------------------------------------------------------------------


def test_a_sibling_value_is_found_without_a_gateway(base):
    """The half of a suggestion that survives a venue with no network."""
    product_id = next(p for p, variants in base.variants_of.items()
                      if len(variants) > 1)
    first, second = base.variants_of[product_id][:2]
    path = next((p for (entity, p) in base.attr_values if entity == second),
                None)
    assert path, "the pack holds no values to be a prior"

    priors = history_mod.priors_for(first, path, base, None)
    siblings = [p for p in priors if p.source == history_mod.SIBLING]
    assert siblings and siblings[0].support >= 1
    assert siblings[0].detail and siblings[0].reference


def test_priors_alone_do_not_reach_the_default_threshold():
    """Everything the catalog and the ledger can say, all agreeing at once,
    still lands under the default threshold.

    The ceiling is per starting source: one prior sets the base and the others
    corroborate it, so summing every base with every agreement would count one
    of them twice.
    """
    ceiling = max(
        base + sum(weight for source, weight in suggest_mod.AGREEMENT.items()
                   if source != started)
        for started, base in suggest_mod.PRIOR_BASE.items())
    assert ceiling < decide_mod.DEFAULT_THRESHOLD


def test_a_lone_source_is_refused_structurally_and_not_by_arithmetic():
    """The safety property that has to survive somebody moving the threshold.

    A single read passage scores well under the default, so a weights-based
    argument would look sound and stop being true the moment an operator turned
    the threshold down. ``route`` counts sources instead.
    """
    confidence, supporters, reasons = suggest_mod._score(
        65, {"confidence": 1.0, "citation": {"doc_id": "STD-002"},
             "quote": "rated power is 65 W"}, [])
    assert supporters == 1
    assert any(r["kind"] == suggest_mod.FROM_PASSAGE for r in reasons)

    lone = _proposal(confidence)
    lone.supporters = supporters
    assert decide_mod.route(lone, 0.5) == decide_mod.HUMAN

    lone.supporters = decide_mod.MIN_SOURCES
    assert decide_mod.route(lone, 0.5) == decide_mod.AUTONOMOUS


def test_disagreement_costs_more_than_agreement_pays():
    """Evidence that a proposal is wrong outweighs evidence it is ordinary."""
    for source, paid in suggest_mod.AGREEMENT.items():
        assert suggest_mod.DISAGREEMENT[source] > paid


def test_every_reason_says_what_it_contributed():
    """The score is composed from named parts, because the manager reads them."""
    _, _supporters, reasons = suggest_mod._score(
        65, None,
        [history_mod.Prior(history_mod.SIBLING, 65, 1, "a sibling holds 65"),
         history_mod.Prior(history_mod.APPROVAL, 45, 2, "a reviewer chose 45")])
    assert [r["kind"] for r in reasons][:2] == [history_mod.SIBLING,
                                                history_mod.APPROVAL]
    assert all(r["detail"] for r in reasons)
    assert any(r["agrees"] is False and r["weight"] < 0 for r in reasons)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _proposal(confidence: float, *, safety: bool = False,
              supporters: int = decide_mod.MIN_SOURCES):
    return suggest_mod.Suggestion(
        entity_id="VAR-01B", attribute_path="specs.power_w",
        label="Rated power", dtype="int", unit="W", safety_class=safety,
        value=65, confidence=confidence, supporters=supporters, reasons=[])


def test_a_safety_class_proposal_never_routes_autonomously():
    """Third place this rule holds, and it must not be the one that leaks.

    ``fixable`` refuses them as candidates and ``sim.engine`` fails closed
    under 0.9 at publish. ``route`` refuses on the class rather than on the
    score, so it keeps holding the day somebody changes what the score is.
    """
    for confidence in (0.0, 0.5, 0.96, 1.0):
        assert decide_mod.route(_proposal(confidence, safety=True)) \
            == decide_mod.HUMAN


def test_the_threshold_decides_everything_else():
    assert decide_mod.route(_proposal(0.96)) == decide_mod.AUTONOMOUS
    assert decide_mod.route(_proposal(0.94)) == decide_mod.HUMAN
    assert decide_mod.route(_proposal(0.95)) == decide_mod.AUTONOMOUS


def test_moving_the_threshold_is_audited():
    """A number that decides what is written without anybody looking is a
    policy decision, and one nobody can date is one nobody can audit."""
    decide_mod.set_threshold(0.8, actor="gr25")
    assert decide_mod.threshold() == 0.8

    rows = db.query("SELECT * FROM audit WHERE action = ?",
                    ("SET_AUTONOMY_THRESHOLD",))
    assert rows and rows[0]["actor"] == "gr25"
    assert db.loads(rows[0]["detail"])["to"] == 0.8


def test_the_threshold_cannot_be_set_to_never_asking():
    decide_mod.set_threshold(0.0, actor="gr25")
    assert decide_mod.threshold() >= 0.5


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def _queued(sent, confidence: float = 0.4, *, safety: bool = False) -> str:
    proposal = _proposal(confidence, safety=safety)
    proposal.entity_id = sent["entities"][0]
    return decide_mod.record(sent["batch_id"], proposal,
                             routed=decide_mod.HUMAN, limit=0.95)


def test_a_queued_proposal_writes_no_fact_until_somebody_decides(sent):
    """The rule the whole feature exists for."""
    before = db.one("SELECT COUNT(*) AS n FROM facts")["n"]
    suggestion_id = _queued(sent)

    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] == before
    assert [s["id"] for s in decide_mod.pending(sent["batch_id"])] \
        == [suggestion_id]


def test_approving_writes_the_value_as_decided_and_not_as_inferred(sent):
    """A person choosing a value is a different class of knowledge from a
    model reading one, and two things downstream act on the difference."""
    suggestion_id = _queued(sent)
    result = decide_mod.decide(suggestion_id, actor="gr25",
                               decision=decide_mod.APPROVE)

    assert result["decided"] and result["fact_id"]
    row = db.one("SELECT * FROM facts WHERE id = ?", (result["fact_id"],))
    provenance = db.loads(row["provenance"])
    assert provenance["kind"] == ProvenanceKind.DECIDED
    assert provenance["source_id"] == "gr25"
    assert db.loads(row["value"]) == 65


def test_rectifying_writes_the_reviewers_value_rather_than_the_proposal(sent):
    """The answer that makes this a queue worth having rather than two
    buttons."""
    suggestion_id = _queued(sent)
    result = decide_mod.decide(suggestion_id, actor="gr25",
                               decision=decide_mod.RECTIFY, value=80)

    assert db.loads(db.one("SELECT value FROM facts WHERE id = ?",
                           (result["fact_id"],))["value"]) == 80
    held = decide_mod.get(suggestion_id)
    assert held["decision"] == decide_mod.RECTIFY
    assert held["decided_value"] == 80
    assert held["value"] == 65, "the proposal that was shown is still on record"


def test_rejecting_writes_nothing_and_names_where_the_value_comes_from(sent):
    suggestion_id = _queued(sent)
    before = db.one("SELECT COUNT(*) AS n FROM facts")["n"]
    result = decide_mod.decide(suggestion_id, actor="gr25",
                               decision=decide_mod.REJECT)

    assert result["decided"] and result["fact_id"] is None
    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] == before
    assert "supplier" in result["note"]


def test_a_decided_proposal_cannot_be_decided_again(sent):
    """Two managers reaching the queue at once is the ordinary case, and the
    second has to be told rather than silently replacing the first answer."""
    suggestion_id = _queued(sent)
    decide_mod.decide(suggestion_id, actor="gr25", decision=decide_mod.APPROVE)
    again = decide_mod.decide(suggestion_id, actor="someone-else",
                              decision=decide_mod.REJECT)

    assert again["decided"] is False and "already" in again["error"]
    assert decide_mod.get(suggestion_id)["decided_by"] == "gr25"


def test_a_decision_needs_a_name(sent):
    suggestion_id = _queued(sent)
    refused = decide_mod.decide(suggestion_id, actor="  ",
                                decision=decide_mod.APPROVE)
    assert refused["decided"] is False and "attributable" in refused["error"]


def test_every_decision_reaches_the_ledger(sent):
    suggestion_id = _queued(sent)
    decide_mod.decide(suggestion_id, actor="gr25",
                      decision=decide_mod.RECTIFY, value=80,
                      comment="spec sheet")

    rows = db.query("SELECT * FROM audit WHERE action = ?",
                    ("ONBOARDING_DECISION",))
    assert rows and rows[0]["actor"] == "gr25"
    detail = db.loads(rows[0]["detail"])
    assert detail["decision"] == decide_mod.RECTIFY
    assert detail["proposed"] == 65 and detail["written"] == 80


def test_a_settled_decision_becomes_a_prior_for_the_next_one(sent):
    """The loop closing: a reviewer who answers the same question twice sees
    their first answer offered back on the second."""
    suggestion_id = _queued(sent)
    decide_mod.decide(suggestion_id, actor="gr25",
                      decision=decide_mod.RECTIFY, value=80)

    priors = history_mod.priors_for("VAR-02A", "specs.power_w",
                                    baseline_mod.get(), None)
    approvals = [p for p in priors if p.source == history_mod.APPROVAL]
    assert approvals and approvals[0].value == 80
    assert "correcting a proposal" in approvals[0].detail


def test_re_assessing_a_batch_does_not_reopen_a_settled_question(sent):
    """Re-reading a bundle is not a reason to ask again."""
    suggestion_id = _queued(sent)
    decide_mod.decide(suggestion_id, actor="gr25",
                      decision=decide_mod.APPROVE)

    proposal = _proposal(0.4)
    proposal.entity_id = sent["entities"][0]
    again = decide_mod.record(sent["batch_id"], proposal,
                              routed=decide_mod.HUMAN, limit=0.95)

    assert again == suggestion_id
    assert decide_mod.get(suggestion_id)["decision"] == decide_mod.APPROVE
    assert decide_mod.pending(sent["batch_id"]) == []


def test_a_prior_too_thin_to_support_a_value_is_too_thin_to_refute_one():
    """Evidence does not get to be weak in one direction and strong in the
    other.

    Two products out of fifteen are not a category convention, so they are not
    a reason to believe a value. Letting the same two subtract when they happen
    to disagree would treat one body of evidence as too thin to support a
    proposal and thick enough to sink it - which is how a score stops meaning
    anything.
    """
    thin = history_mod.Prior(
        history_mod.CATEGORY, 3.1, history_mod.MIN_CATEGORY_SUPPORT - 1,
        "two products in this category")

    for proposed in (3.1, 2.8):  # agreeing, then disagreeing
        _score, _supporters, reasons = suggest_mod._score(proposed, None, [thin])
        weighed = [r for r in reasons if r["kind"] == history_mod.CATEGORY]
        assert weighed and weighed[0]["weight"] == 0.0
        assert weighed[0]["detail"], "shown even though it is weighed at nothing"


def test_a_category_convention_does_weigh_in_both_directions():
    """The counterpart. Enough support and it counts - and counts more against
    the proposal than for it, because evidence that a value is wrong is worth
    more than evidence that it is unremarkable."""
    thick = history_mod.Prior(
        history_mod.CATEGORY, 3.1, history_mod.MIN_CATEGORY_SUPPORT,
        "most of this category")

    agreed, _s, _r = suggest_mod._score(3.1, None, [thick])
    refused, _s, _r = suggest_mod._score(2.8, None, [thick])

    assert agreed > 0
    assert refused == 0.0, "clamped at zero, having started from nothing"


def test_a_prior_names_the_value_it_found():
    """A reviewer reading "the category holds this value" under a proposal the
    category disagrees with has been told the opposite of what happened."""
    base = baseline_mod.get()
    product_id = next(p for p, variants in base.variants_of.items()
                      if len(variants) > 1)
    first, second = base.variants_of[product_id][:2]
    path, value = next(((p, v) for (entity, p), v in base.attr_values.items()
                        if entity == second and v not in (None, "", [])),
                       (None, None))
    assert path, "the pack holds no values to be a prior"

    priors = history_mod.priors_for(first, path, base, None)
    sibling = next(p for p in priors if p.source == history_mod.SIBLING)
    assert history_mod._say(value) in sibling.detail


def test_an_autonomous_fill_built_from_priors_carries_no_citation(sent):
    """The path with no document behind it, written end to end.

    Priors alone cannot clear the default threshold - a separate test pins
    that - but an operator may lower it, and then a proposal the catalog and a
    past decision agree on is written with no passage to cite. Every consumer
    of a filled row has to survive that: the audit line reached for
    ``citation["chunk_id"]`` on a proposal whose citation is None, and the
    whole apply raised rather than the fill being recorded.
    """
    entity = sent["entities"][-1]
    path = "food.fibre_g"

    # A past decision on this field, so a prior-only proposal has two sources
    # to be corroborated by rather than one.
    proposal = suggest_mod.Suggestion(
        entity_id="VAR-01B", attribute_path=path, label=path, dtype="float",
        unit="g", safety_class=False, value=2.8, confidence=0.4,
        supporters=1, reasons=[])
    earlier = decide_mod.record(sent["batch_id"], proposal,
                                routed=decide_mod.HUMAN, limit=0.95)
    decide_mod.decide(earlier, actor="gr25", decision=decide_mod.APPROVE)

    decide_mod.set_threshold(0.5, actor="gr25")
    result = fix_mod.apply(sent["batch_id"], actor="gr25")

    written = [f for f in result["filled"] if f["citation"] is None]
    assert written, "no prior-only proposal cleared the lowered threshold"
    for row in written:
        assert row["source"] == suggest_mod.FROM_PRIOR
        assert row["supporters"] >= decide_mod.MIN_SOURCES
        assert row["fact_id"], "an autonomous fill that wrote nothing"

    # The line that used to raise. Audited, with a null chunk where there is no
    # passage, rather than the apply failing.
    audited = db.query("SELECT detail FROM audit WHERE action = ?"
                       " AND entity_id = ?", ("APPLY_ENRICHMENT",
                                              sent["batch_id"]))
    filled = db.loads(audited[-1]["detail"])["filled"]
    assert any(row[2] is None for row in filled)
    assert entity or True  # the batch is what was applied, not one entity


def test_an_autonomous_fill_is_inferred_and_a_decided_one_is_not(sent):
    """The two doors, told apart by the provenance they write.

    A model reading a catalog convention is still an inference; a person
    choosing a value is not. The publish-time safety gate and the audit trail
    both act on the difference.
    """
    proposal = suggest_mod.Suggestion(
        entity_id="VAR-01B", attribute_path="food.fibre_g", label="fibre",
        dtype="float", unit="g", safety_class=False, value=2.8,
        confidence=0.4, supporters=1, reasons=[])
    earlier = decide_mod.record(sent["batch_id"], proposal,
                                routed=decide_mod.HUMAN, limit=0.95)
    decided_fact = decide_mod.decide(
        earlier, actor="gr25", decision=decide_mod.APPROVE)["fact_id"]

    decide_mod.set_threshold(0.5, actor="gr25")
    result = fix_mod.apply(sent["batch_id"], actor="gr25")
    assert result["filled"], "nothing cleared the lowered threshold"

    kinds = {}
    for row in result["filled"]:
        held = db.one("SELECT provenance FROM facts WHERE id = ?",
                      (row["fact_id"],))
        kinds[row["fact_id"]] = db.loads(held["provenance"])["kind"]
    assert set(kinds.values()) == {ProvenanceKind.INFERRED}

    human = db.one("SELECT provenance FROM facts WHERE id = ?", (decided_fact,))
    assert db.loads(human["provenance"])["kind"] == ProvenanceKind.DECIDED
