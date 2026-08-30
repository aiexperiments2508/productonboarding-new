"""The staging page, and the one place a model writes for a shopper.

Everything else this system asks a model for is a candidate a rule then admits
or drops. The differentiator is prose, and no rule can check whether a sentence
is good - so it is fenced by construction instead: two grounds, both required,
and a forbidden-content check that runs on whatever came back rather than a
politely worded prompt.

The gateway is unreachable here, so the templated form is what these exercise.
That is the right thing to test hardest: it is what a venue with no network
sees, and it is the form that must carry the same grounding as the written one.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_preview.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

import sc.readiness as readiness  # noqa: E402
from sc import db  # noqa: E402
from sc.rag import index as rag_index  # noqa: E402
from sc.readiness import preview as preview_mod  # noqa: E402
from sc.readiness import record as record_mod  # noqa: E402
from sc.readiness import verdict as verdict_mod  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

READY_PRODUCT = "VAR-01A"
UNREADY_PRODUCT = "VAR-02B"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    rag_index.load.cache_clear()
    rag_index.build(include_comms=True, embed=False)
    ingest.ingest(tape.jump_to(tape.inject_seq()))
    yield
    db.close()


def _preview(entity_id: str) -> dict:
    summary = readiness.assess(entity_id, use_model=False)
    return preview_mod.build(entity_id, summary, use_model=False)


# ---------------------------------------------------------------------------
# Only a record that passed
# ---------------------------------------------------------------------------


def test_a_blocked_record_is_refused_not_rendered():
    """A page that renders a blocked product is a page somebody screenshots."""
    page = _preview(UNREADY_PRODUCT)

    assert page["rendered"] is False
    assert page["verdict"] != verdict_mod.READY
    assert page["findings"], "a refusal must say what is wrong"
    # Not a page with a warning across the top - no page.
    assert "specification" not in page
    assert "differentiator" not in page


def test_a_ready_record_renders_its_salient_information():
    page = _preview(READY_PRODUCT)

    assert page["rendered"] is True
    assert page["title"] and page["sku"]
    assert page["specification"], "a page with no specification is a stub"
    assert page["media"], "a ready record has its imagery by definition"
    for row in page["specification"]:
        assert row["label"] and row["value"] is not None


def test_the_preview_route_refuses_an_unready_product():
    from fastapi.testclient import TestClient

    from sc.main import app

    client = TestClient(app)
    response = client.get(
        f"/api/products/{UNREADY_PRODUCT}/preview?use_model=false")

    assert response.status_code == 200, "a refusal is an answer, not an error"
    body = response.json()
    assert body["rendered"] is False
    assert body["findings"]


# ---------------------------------------------------------------------------
# Nothing on the page that is not in the record
# ---------------------------------------------------------------------------


def test_every_figure_on_the_page_is_in_the_record():
    """The last surface before publication and the first one a reviewer trusts.
    A figure that appears here and nowhere in the record is untraceable."""
    page = _preview(READY_PRODUCT)
    record = record_mod.build(READY_PRODUCT)

    for row in page["specification"]:
        assert row["path"] in record.values, f"{row['path']} is not held"
        assert row["value"] == record.values[row["path"]], \
            f"{row['path']} was reworded or recomputed on the way to the page"


def test_an_unsubstantiated_claim_does_not_reach_the_page():
    """A claim on the preview that the validator would refuse at publish is a
    claim the reviewer approves and the channel rejects."""
    from sc.sim import engine

    page = _preview(READY_PRODUCT)
    record = record_mod.build(READY_PRODUCT)

    for claim in page["claims"]:
        rule = engine.CLAIM_RULES[claim]
        assert rule.holds(dict(record.values)), \
            f"{claim} reached the page unsupported"

    # And a claim the record no longer supports is dropped rather than shown.
    record.values["specs.power_w"] = 900
    kept = preview_mod._substantiated_claims(record, baseline_mod.get())
    assert "low-energy" not in kept


# ---------------------------------------------------------------------------
# The differentiator
# ---------------------------------------------------------------------------


def test_a_differentiator_names_attributes_and_cites_a_passage():
    """Two grounds, both required. "Comfortable in summer" needs a summer and a
    reason, and either alone is a sentence somebody made up."""
    page = _preview(READY_PRODUCT)
    differentiator = page["differentiator"]

    assert differentiator is not None
    assert differentiator["attributes"], "grounded on no attribute"
    assert differentiator["citation"], "grounded on no passage"

    record = record_mod.build(READY_PRODUCT)
    for path in differentiator["attributes"]:
        assert path in record.values, f"{path} is not held by this record"


def test_an_ungrounded_differentiator_is_withheld():
    """A page with no differentiator says less; a page with an ungrounded one is
    wrong."""
    base = baseline_mod.get()
    record = record_mod.build(READY_PRODUCT)
    # A record holding none of the attributes its category is bought on has
    # nothing to lean on, whatever context is available.
    record.values.clear()

    assert preview_mod.differentiator(record, base, use_model=False) is None


def test_a_forbidden_claim_is_rejected():
    """Checked, not requested. A prompt saying "no medical claims" is a
    preference; this is a control, and it runs on whatever came back."""
    assert preview_mod._forbidden("Clinically proven to treat hay fever")
    assert preview_mod._forbidden("Completely safe for children")
    assert preview_mod._forbidden("Guaranteed to remove every allergen")
    # And it does not fire on an innocent sentence that merely contains a
    # forbidden word inside a longer one.
    assert preview_mod._forbidden("A quiet purifier for bedrooms") is None
    assert preview_mod._forbidden("Ideal after manicures") is None


def test_the_differentiator_survives_having_no_model():
    """The surface degrades rather than disappearing: a venue with no network
    should still see the feature, resting on the same two grounds."""
    page = _preview(READY_PRODUCT)
    differentiator = page["differentiator"]

    assert differentiator["written_by_model"] is False
    assert differentiator["text"], "the templated form produced nothing"
    assert differentiator["note"] and "without a model" in differentiator["note"]
    assert differentiator["attributes"] and differentiator["citation"]
