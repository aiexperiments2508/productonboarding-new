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
from sc.onboarding import fixable as fixable_mod  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

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
    """Seven checks of ten is not a clean result, and a summary that said so
    would be the same omission on every product at once."""
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
    assertion. `ingest.record_attribute` is the only door, and it hard-codes
    INFERRED - so this fails the moment somebody reaches for `store.record`."""
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
