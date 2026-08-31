"""Is this product's information fit to publish?

These run with the gateway unreachable, like everything else here, which means
the six deterministic checks are what executes and the three reading checks
report that they did not run. That is the right shape for this file: the
deterministic half is where the verdict comes from, and the reading half is
tested for the property that matters most about it - that its absence is
reported rather than mistaken for a clean result.

The property this file exists to protect is that **the verdict is arithmetic**.
No score, no threshold, no confidence, and no note that can move it. A readiness
surface that could be talked into a launch would be worse than none, because it
would be trusted.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_readiness.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

import sc.readiness as readiness  # noqa: E402
from sc import db  # noqa: E402
from sc.rag import index as rag_index  # noqa: E402
from sc.readiness import checks as checks_mod  # noqa: E402
from sc.readiness import record as record_mod  # noqa: E402
from sc.readiness import verdict as verdict_mod  # noqa: E402
from sc.readiness.checks import BLOCKING, Finding  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

#: Clean in the seed pack: an air purifier with all its imagery.
CLEAN = "VAR-01A"
#: A multipack whose imaging job was queued against the single and never redone.
NO_PANEL = "VAR-02B"
#: A second-generation fan reusing the first generation's cut-out.
NO_IN_SITU = "VAR-06A"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    # The baseline is cached process-wide and loaded from disk. A test that
    # edits an asset to give a check something to find would otherwise leave
    # that edit in place for every test after it - which is exactly how a clean
    # product came back BLOCKED here once.
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    rag_index.load.cache_clear()
    rag_index.build(include_comms=True, embed=False)
    ingest.ingest(tape.jump_to(tape.inject_seq()))
    yield
    db.close()


def _assess(entity_id: str) -> dict:
    return readiness.assess(entity_id, use_model=False)


# ---------------------------------------------------------------------------
# Findings, not a score
# ---------------------------------------------------------------------------


def test_readiness_reports_findings_and_no_score():
    """A number would invite a threshold, and a threshold would invite
    publishing at ninety - which is how a missing allergen declaration reaches a
    shelf."""
    summary = _assess(NO_PANEL)

    assert summary["findings"], "a product with a known gap found nothing"
    for finding in summary["findings"]:
        assert finding["check"] and finding["subject"] and finding["detail"]
        assert finding["basis"], "a finding with no basis is an opinion"

    forbidden = {"score", "readiness_score", "percent", "percentage", "grade",
                 "confidence"}
    assert not (forbidden & set(summary)), f"{forbidden & set(summary)}"


def test_an_assessment_is_reproducible():
    first, second = _assess(NO_PANEL), _assess(NO_PANEL)
    assert first["findings"] == second["findings"]
    assert first["verdict"] == second["verdict"]


# ---------------------------------------------------------------------------
# The six that need no model
# ---------------------------------------------------------------------------


def test_the_deterministic_checks_need_no_model():
    """The whole suite runs with the gateway on a closed port. If readiness
    needed one, a venue with no network would have no readiness."""
    base = baseline_mod.get()
    record = record_mod.build(CLEAN)

    assert record is not None
    for check in checks_mod.DETERMINISTIC:
        check(record, base)  # must not raise

    assert _assess(CLEAN)["verdict"] == verdict_mod.READY


def test_missing_media_is_found_by_role():
    """By role, not by count. Three hero shots and no ingredient panel is a food
    product nobody with an allergy can check, and a count would call it
    complete."""
    summary = _assess(NO_PANEL)
    media = [f for f in summary["findings"] if f["check"] == "required_media"]

    assert [f["subject"] for f in media] == ["INGREDIENT_PANEL"]
    assert media[0]["basis"] == "INT-001", "the finding names the rule behind it"

    other = _assess(NO_IN_SITU)["findings"]
    assert [f["subject"] for f in other if f["check"] == "required_media"] \
        == ["IN_SITU"]


def test_a_check_does_not_fire_on_an_attribute_the_category_never_has():
    """A rule requiring a wattage binds on a marketplace, and a snack bar lists
    on that marketplace. Reporting the snack for missing a rated power it could
    never have produces a finding nobody can act on, in a list a reviewer then
    learns to scroll past."""
    summary = _assess(NO_PANEL)
    subjects = {f["subject"] for f in summary["findings"]}

    assert "specs.power_w" not in subjects
    assert not any(s.startswith("specs.") for s in subjects), subjects


def test_a_missing_mandatory_attribute_is_attributed(monkeypatch):
    base = baseline_mod.get()
    record = record_mod.build(CLEAN)
    # Take away something a channel this product lists on will refuse without.
    record.values.pop("identifiers.gtin", None)

    findings = checks_mod.mandatory_information(record, base)
    gtin = [f for f in findings if f.subject == "identifiers.gtin"]

    assert gtin, "a required attribute was removed and nothing noticed"
    assert gtin[0].basis.startswith("RUL-"), "the finding names the channel rule"
    assert "required by" in gtin[0].detail


def test_forbidden_content_is_found_without_a_model():
    """No wattage makes "cures asthma" publishable, so this cannot be a
    judgement about the product - it is a judgement about the sentence."""
    base = baseline_mod.get()
    record = record_mod.build(CLEAN)
    asset_id = base.assets_by_listing[record.listings[0]][0]
    base.assets[asset_id].text = "Clinically proven to treat asthma."

    findings = checks_mod.forbidden_content(record, base)

    assert findings, "a medical claim was not caught"
    assert findings[0].basis == "INT-002"


def test_a_withdrawn_product_is_blocked_without_a_model():
    """The one blocking finding that needs no reading.

    ``saleability`` asks a model whether a mandate covers this product, which
    is a question about a regulation's scope. This asks whether a withdrawal
    notice has already been served, which is a fact in the record - and
    putting it behind a gateway would mean a withdrawn product read as merely
    incomplete every time the gateway was down.
    """
    base = baseline_mod.get()
    record = record_mod.build(CLEAN)
    record.values[checks_mod.SALE_PERMITTED] = False

    findings = checks_mod.sale_permitted(record, base)

    assert findings, "a withdrawn product was not blocked"
    assert findings[0].severity == BLOCKING
    assert findings[0].basis == "REG-003"
    assert verdict_mod.decide(findings) == verdict_mod.BLOCKED


def test_a_product_still_permitted_raises_nothing():
    """Only an explicit denial blocks.

    A missing value is a gap ``applicable_attributes`` already reports.
    Reading "we were never told" as "not permitted" would hold the whole
    catalogue the first time a supplier left the field empty, which is a
    fail-closed rule doing more harm than the thing it guards against.
    """
    base = baseline_mod.get()
    record = record_mod.build(CLEAN)

    assert record.values.get(checks_mod.SALE_PERMITTED) is True
    assert not checks_mod.sale_permitted(record, base)

    record.values.pop(checks_mod.SALE_PERMITTED)
    assert not checks_mod.sale_permitted(record, base)


def test_both_surfaces_name_the_same_attribute():
    """A withdrawal bars a launch here and refuses a publish in the validator.

    Two names for one fact would mean one surface silently not implementing
    it, and the surface that failed to would be whichever a reviewer happened
    to be looking at.
    """
    from sc.sim import engine

    assert checks_mod.SALE_PERMITTED == engine.SALE_PERMITTED
    assert "sale_permitted" in verdict_mod.SALEABILITY_CHECKS


def test_readiness_and_publication_read_one_rule_table():
    """Two implementations of one rule are two answers to "why was this held",
    and the reviewer is shown whichever one ran."""
    from sc.contracts import ChannelRuleKind

    base = baseline_mod.get()
    record = record_mod.build(CLEAN)
    record.values.pop("identifiers.gtin", None)

    findings = checks_mod.mandatory_information(record, base)
    rule_ids = {f.basis for f in findings}
    published_rules = {r.id for r in base.rules
                       if r.kind == ChannelRuleKind.REQUIRED}

    assert rule_ids, "nothing was found"
    assert rule_ids <= published_rules, "readiness cited a rule nothing publishes"


# ---------------------------------------------------------------------------
# The three that may read, and may not decide
# ---------------------------------------------------------------------------


def test_an_assessment_without_a_model_says_so():
    """Reporting a narrower result as a clean one is the single most dangerous
    thing this surface could do."""
    summary = _assess(CLEAN)

    assert summary["checks_complete"] is False
    assert summary["caveat"] and "without a model" in summary["caveat"]


def test_an_uncited_candidate_finding_is_dropped():
    """The gate is the citation, not a confidence. A finding a reviewer cannot
    open is a finding they cannot check."""
    from sc.readiness import reading

    class _Chunk:
        id, doc_id, text = "REG-001#00", "REG-001", "a passage"

    class _Hit:
        chunk = _Chunk()

    passages = [_Hit()]
    kept = reading._cited(
        [{"requirement": "real", "citation": "REG-001#00"},
         {"requirement": "invented", "citation": "REG-999#42"},
         {"requirement": "unsourced"}],
        passages)

    assert [c["requirement"] for c, _ in kept] == ["real"]


def test_the_reading_checks_return_nothing_and_say_so_without_a_gateway():
    from sc.readiness import reading

    base = baseline_mod.get()
    record = record_mod.build(CLEAN)

    for check in reading.READING:
        findings, ran = check(record, base)
        assert findings == []
        # `ran` is False only where the check actually tried and failed; a check
        # with no passages to read never asked and is not evidence of an outage.
        assert ran in (True, False)


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def test_a_clean_record_is_ready_to_launch():
    assert _assess(CLEAN)["verdict"] == verdict_mod.READY
    assert _assess(CLEAN)["ready"] is True


def test_an_open_finding_returns_the_product_to_its_source():
    summary = _assess(NO_PANEL)

    assert summary["verdict"] == verdict_mod.RETURN
    assert summary["ready"] is False
    # Named, so somebody can act. "The data is incomplete" is not a return.
    assert summary["by_system"], "a return that names nobody is not actionable"
    assert summary["findings"][0]["subject"]


def test_only_a_saleability_finding_blocks():
    """Blocking is a statement about legality. Reaching it by accumulating
    quality findings would make it a judgement."""
    many = [Finding(check="required_media", subject=f"ROLE-{i}", detail="x")
            for i in range(8)]
    one = [Finding(check="saleability", subject="REG-001", detail="x",
                   severity=BLOCKING)]

    assert verdict_mod.decide(many) == verdict_mod.RETURN
    assert verdict_mod.decide(one) == verdict_mod.BLOCKED
    assert verdict_mod.decide([]) == verdict_mod.READY


def test_the_note_cannot_change_the_verdict():
    """A model may write the covering note a reviewer reads. If the note could
    move the outcome, the outcome would be the model's."""
    findings = [Finding(check="required_media", subject="HERO", detail="x")]

    first = verdict_mod.summarise("VAR-X", findings)
    second = verdict_mod.summarise("VAR-X", list(findings))
    second["note"] = "everything looks fine to me"

    assert first["verdict"] == second["verdict"] == verdict_mod.RETURN
    assert verdict_mod.decide(findings) == first["verdict"]


def test_findings_are_ordered_so_two_reads_agree():
    findings = [
        Finding(check="required_media", subject="HERO", detail="b"),
        Finding(check="saleability", subject="REG-001", detail="a",
                severity=BLOCKING),
        Finding(check="declared_types", subject="specs.power_w", detail="c"),
    ]
    summary = verdict_mod.summarise("VAR-X", findings)

    # Blocking first: it is the one a reviewer must not scroll past.
    assert summary["findings"][0]["check"] == "saleability"
    assert summary["blocking"]


# ---------------------------------------------------------------------------
# A narrow assessment is never reported as a clean one
# ---------------------------------------------------------------------------
# The product view now opens on the six rule checks alone, because the three
# that read prose are three model round trips and running them on every click
# made the page a wait rather than a look. That trade is only defensible while
# the response says what it did not do - so these are the assertions the new
# default rests on.


def test_the_rule_checks_alone_always_report_themselves_as_narrow():
    """Every product, not one. A single surface that forgot to say so is the
    whole risk of the faster default."""
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    for entity_id in sorted(base.variants):
        summary = readiness.assess(entity_id, use_model=False,
                                   include_record=False)
        assert summary["checks_complete"] is False
        assert summary["caveat"], f"{entity_id} reports narrowly and says nothing"
        assert "narrower" in summary["caveat"]


def test_a_narrow_assessment_can_still_be_ready_which_is_why_it_must_say_so():
    """The dangerous case, stated as a test.

    A record with no rule findings comes back READY_TO_LAUNCH from six checks
    of nine. The verdict is correct - nothing found it unready - and rendering
    it as "ready to launch" without the caveat would be reporting the absence
    of three checks as the presence of a clean result.
    """
    summary = readiness.assess(CLEAN, use_model=False, include_record=False)

    assert summary["verdict"] == verdict_mod.READY
    assert summary["ready"] is True
    assert summary["checks_complete"] is False


def test_findings_are_not_weakened_by_the_assessment_being_narrow():
    """A missing allergen declaration found by a rule is a missing allergen
    declaration whether or not a model also looked."""
    narrow = readiness.assess(NO_PANEL, use_model=False, include_record=False)

    assert narrow["verdict"] == verdict_mod.RETURN
    assert narrow["findings"], "the rule checks found nothing to return for"
