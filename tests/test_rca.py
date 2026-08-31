"""Root-cause suggestions, and the two things that keep them honest.

A finding says what is wrong and names the system that carried it. This joins
that to what the estate declares about the system - what it is for, who owns
it, how it is known to misbehave - so that a reviewer holding eleven findings
knows which supplier to email first.

The bound is the one the whole package works under, and it is not relaxed here
because the output happens to be prose: **a model produces a candidate with a
citation; a rule decides.** An account citing nothing retrievable is dropped
and the deterministic one is used instead - so the surface works identically
with the gateway off, which is what these run against.

The other property is the one that would be easiest to lose in a refactor:
**this runs after the verdict and cannot reach it.** If an explanation could
change an outcome, the outcome would be the model's.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_rca.db")
# Deliberately dead: everything below asserts what the surface does with no
# model available, which is the state a venue with no network is in.
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

import sc.readiness as readiness  # noqa: E402
from sc import db  # noqa: E402
from sc.estate.manifest import BY_ID  # noqa: E402
from sc.readiness import rca as rca_mod  # noqa: E402
from sc.readiness import record as record_mod  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

#: The multipack: its ingredient panel was never delivered, and the finding
#: names the imaging system.
NO_PANEL = "VAR-02B"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(tape.inject_seq()))
    yield
    db.close()


def _explain(entity_id: str = NO_PANEL, **kwargs) -> dict:
    record = record_mod.build(entity_id)
    summary = readiness.assess(entity_id, use_model=False, include_record=False,
                               record=record)
    return rca_mod.explain(entity_id, summary, record, use_model=True, **kwargs)


def test_a_cause_is_produced_with_no_model_and_says_so():
    """The manifest alone answers "why, and who fixes it". The model only
    writes it better, and the grounding is identical either way."""
    report = _explain()

    assert report["causes"], "a product with an open finding got no explanation"
    for cause in report["causes"]:
        assert cause["written_by_model"] is False
        assert cause["note"], "a template that does not admit it is a template"
        assert cause["narrative"].strip()
        assert cause["remedy"].strip()


def test_a_cause_names_the_system_and_the_team_that_owns_it():
    """"The data is incomplete" is not actionable. "Digital asset management
    has not delivered an ingredient panel" is."""
    cause = _explain()["causes"][0]

    assert cause["system"] in BY_ID, "the cause names no system the estate has"
    assert cause["owner"] == BY_ID[cause["system"]].owner
    assert cause["owner"] in cause["remedy"], \
        "the remedy does not say who has to act"


def test_the_defect_named_is_one_that_system_actually_declares():
    """A guess constrained to a closed set. It may be wrong about which of a
    system's known failure modes fired; it may not invent a new one."""
    for cause in _explain()["causes"]:
        if not cause["likely_defect"]:
            continue
        declared = {str(d) for d in BY_ID[cause["system"]].defects}
        assert cause["likely_defect"] in declared
        assert cause["defect_explanation"], \
            "a defect named without an explanation is a code, not a cause"


def test_explaining_a_product_cannot_change_its_verdict():
    """The load-bearing one. `verdict.decide` counts findings; nothing here is
    a finding. If an explanation could reach the outcome, the outcome would be
    the model's - and the argument this system makes about bounded AI would be
    untrue at the one point somebody acts on it."""
    before = readiness.assess(NO_PANEL, use_model=False, include_record=False)
    _explain()
    after = readiness.assess(NO_PANEL, use_model=False, include_record=False)

    assert before["verdict"] == after["verdict"]
    assert before["findings"] == after["findings"]
    assert before["blocking"] == after["blocking"]


def test_a_clean_product_is_offered_no_explanation():
    """A page offering to explain a record with nothing open is offering to
    explain nothing."""
    base = baseline_mod.get()
    clean = next(
        (vid for vid in sorted(base.variants)
         if not readiness.assess(vid, use_model=False,
                                 include_record=False)["findings"]),
        None)
    if clean is None:
        pytest.skip("no clean product in the catalog at this instant")

    assert _explain(clean)["causes"] == []


def test_the_findings_it_leaves_out_are_counted_rather_than_dropped():
    """A panel that quietly stops at three reads as a product with three
    problems."""
    base = baseline_mod.get()
    worst = max(
        sorted(base.variants),
        key=lambda vid: len(readiness.assess(vid, use_model=False,
                                             include_record=False)["findings"]))
    total = len(readiness.assess(worst, use_model=False,
                                 include_record=False)["findings"])
    if total < 2:
        pytest.skip("no product with more than one finding at this instant")

    report = _explain(worst, limit=1)

    assert len(report["causes"]) == 1
    assert report["not_explained"] == total - 1


def test_the_worst_finding_is_explained_first():
    """Findings arrive sorted worst first, and the limit takes the top of that
    list rather than an arbitrary slice."""
    base = baseline_mod.get()
    blocked = next(
        (vid for vid in sorted(base.variants)
         if readiness.assess(vid, use_model=False,
                             include_record=False)["blocking"]),
        None)
    if blocked is None:
        pytest.skip("nothing is blocked at this instant")

    report = _explain(blocked, limit=1)
    assert report["causes"][0]["severity"] == "BLOCKING" or \
        report["causes"][0]["check"] in ("saleability", "forbidden_content")
