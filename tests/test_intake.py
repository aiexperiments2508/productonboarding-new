"""What a supplier can send in.

The estate has always been read-only into the catalog, and that rule is not
relaxed here: an intake appends *events*, and the platform's own ingestion
judges them under the same precedence policy, the same materiality threshold
and the same safety override as the recorded flight.

The properties under test are the ones that keep that true. A supplier sees
only its own products. A submission is recorded as a document version and never
as a value. A new version of the supplier's own document inherits its
precedence, so a correction can actually win - and a document nobody has heard
of still cannot. And every refusal is a reason rather than a silent drop.
"""

from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_intake.db")

from sc import db  # noqa: E402
from sc.estate import intake, intake_server, submissions  # noqa: E402
from sc.estate.manifest import SYSTEMS  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

PORTAL = "supplier-portal"
SUPPLIER = "SUP-02"
PRODUCT = "PRD-05"
VARIANT = "VAR-05A"
SAFETY = "food.allergens.may_contain"

SVG = base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>').decode()


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(tape.inject_seq() + 12))
    yield
    db.close()


def _submit(**overrides):
    body = {
        "supplier": SUPPLIER, "system_id": PORTAL, "entity_id": VARIANT,
        "attribute_path": SAFETY, "new_value": ["milk", "peanuts"],
        "note": "Peanut handling introduced on the packing line.",
    }
    body.update(overrides)
    return intake.submit_specification_change(**body)


# ---------------------------------------------------------------------------
# The surface is derived from the manifest
# ---------------------------------------------------------------------------


def test_only_the_systems_the_manifest_marks_as_accepting_have_an_intake():
    """Three of the eleven. The other eight carry traffic outward only, and an
    intake endpoint they never use would be an address somebody could find."""
    facing = {s.id for s in intake_server.vendor_facing()}
    assert facing == {s.id for s in SYSTEMS if s.accepts}
    assert len(facing) == 3


def test_every_intake_tool_is_derived_from_what_its_system_accepts():
    """The manifest is the configuration. A data pool that syndicates attribute
    rows and nothing else does not get a document upload, and narrowing it in
    the manifest is the whole of how that is expressed."""
    for system in intake_server.vendor_facing():
        tools = set(intake_server.tools_for(system))
        assert set(intake_server.ALWAYS) <= tools
        if "CATALOG_UPDATE" not in system.accepts:
            assert "upload_image" not in tools
        if "SPEC_DOC" not in system.accepts:
            assert "upload_document" not in tools


def test_an_intake_endpoint_ends_in_a_slash():
    """Starlette's Mount strips the prefix, so a sub-app whose only route is
    "/" answers 405 without it - and an address that is wrong by one character
    reads as a broken server rather than a wrong address."""
    for system in intake_server.vendor_facing():
        assert intake_server.endpoint(system.id, "http://x").endswith("/")


def test_the_intake_declares_which_of_its_tools_can_act():
    for system in intake_server.vendor_facing():
        described = intake_server._describe(system)
        assert set(described["mutating"]) <= set(described["tools"])
        assert "submit_specification_change" in described["mutating"]


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


def test_a_supplier_sees_only_its_own_products():
    listed = intake.list_my_products(SUPPLIER, PORTAL)
    base = baseline_mod.get()
    assert listed["products"]
    for product in listed["products"]:
        assert base.products[product["product_id"]].supplier == SUPPLIER


def test_a_supplier_cannot_read_another_suppliers_specification():
    """The analogue of a system refusing to hand over another system's payload.
    A portal where every supplier can read every other one's specifications is
    one catalog with eighteen front doors."""
    refused = intake.get_product_spec("SUP-01", PRODUCT)
    assert refused["error"]
    assert "does not belong" in refused["error"]


def test_a_supplier_cannot_change_another_suppliers_product():
    refused = _submit(supplier="SUP-01", entity_id=VARIANT)
    assert refused["accepted"] is False


def test_an_unknown_supplier_is_refused_rather_than_served_nothing():
    """An empty list would read as "you have no products", which is a different
    and much more alarming statement than "we have never heard of you"."""
    refused = intake.list_my_products("SUP-999", PORTAL)
    assert "no supplier" in refused["error"]


def test_the_specification_read_agrees_with_the_catalog_route():
    """Two implementations of one read become two accounts of the same product
    the first time either is edited - and a supplier arguing about a number
    they did not send is the worst place for that to happen."""
    from sc.tools import network as network_tools

    mine = intake.get_product_spec(SUPPLIER, PRODUCT)
    theirs = network_tools.variant_diff(PRODUCT)

    assert [a["path"] for a in mine["attributes"]] == \
           [a["path"] for a in theirs["attributes"]]
    for row_a, row_b in zip(mine["attributes"], theirs["attributes"]):
        for variant_id, cell in row_b["values"].items():
            assert mine_cell(row_a, variant_id)["value"] == cell["value"]


def mine_cell(row, variant_id):
    return row["values"][variant_id]


def test_a_supplier_is_told_which_values_it_asserted():
    """The column that makes the screen worth opening: "what you told us" and
    "what we currently believe" are different things precisely when somebody is
    about to complain."""
    spec = intake.get_product_spec(SUPPLIER, PRODUCT)
    allergens = next(a for a in spec["attributes"] if a["path"] == SAFETY)
    assert any(cell["mine"] for cell in allergens["values"].values())


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


def test_a_submission_is_recorded_as_a_document_version_and_not_as_a_value():
    """The invariant the whole surface rests on. Ingestion records which
    version is in force; the value it asserts becomes a fact only when the
    graph reads the document, stamped INFERRED and under the safety gate."""
    from sc.state import overlay as overlay_mod
    from sc.state import store

    before = db.one(
        "SELECT COUNT(*) AS n FROM facts WHERE entity_type = 'variant'"
        " AND entity_id = ? AND attr = ?", (VARIANT, SAFETY))["n"]

    result = _submit()
    assert result["accepted"] is True

    after = db.one(
        "SELECT COUNT(*) AS n FROM facts WHERE entity_type = 'variant'"
        " AND entity_id = ? AND attr = ?", (VARIANT, SAFETY))["n"]
    assert after == before, "the intake wrote a value into the catalog"

    doc_id = result["doc_ref"].split(":")[0]
    version = store.get("source_doc", doc_id, overlay_mod.ATTR_VERSION,
                        tape.sim_now(), tape.sim_now())
    assert version is not None and version.value == result["doc_ref"].split(":")[1]


def test_a_correction_revises_the_document_the_value_came_off():
    """A supplier correcting a figure is reissuing the sheet that figure came
    from, not writing an unrelated one - and a document the seed pack does not
    know carries precedence zero and would lose every contest it entered."""
    base = baseline_mod.get()
    result = _submit()
    doc_id = result["doc_ref"].split(":")[0]

    assert doc_id in base.docs_by_supplier[SUPPLIER]
    assert base.source_docs[doc_id].precedence > 0


def test_a_second_submission_does_not_re_mint_the_same_version():
    first = _submit()
    second = _submit(new_value=["milk", "peanuts", "soya"])
    assert first["doc_ref"] != second["doc_ref"]


def test_the_submission_lands_on_the_live_lane_and_is_visible_at_once():
    result = _submit()
    row = db.one("SELECT lane, released_at FROM events WHERE id = ?",
                 (result["event_id"],))
    assert row["lane"] == tape.LANE_LIVE
    assert row["released_at"] is not None
    assert result["event_id"] in {e.id for e in tape.released(limit=30)}


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_safety_declaration_cannot_be_changed_without_saying_why():
    refused = _submit(note="")
    assert "safety-class" in refused["error"]


def test_a_value_of_the_wrong_type_is_refused_with_the_type_it_wanted():
    refused = _submit(entity_id="VAR-04A", supplier="SUP-04",
                      attribute_path="specs.power_w", new_value="quite a lot")
    assert "expected int" in refused["error"]


def test_an_attribute_nobody_has_defined_is_refused():
    refused = _submit(attribute_path="food.vibes")
    assert "no attribute" in refused["error"]


def test_a_correction_cannot_take_effect_before_it_was_sent():
    refused = _submit(effective_from="2026-01-01")
    assert "in the past" in refused["error"]


def test_an_unreadable_date_is_refused_rather_than_guessed_at():
    refused = _submit(effective_from="next Tuesday")
    assert "cannot read" in refused["error"]


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_an_uploaded_image_reaches_the_record_and_the_checks():
    """Otherwise the button is theatre: the supplier fixes the finding, and the
    system goes on reporting it in detail."""
    import sc.readiness as readiness

    before = readiness.assess("VAR-02B", use_model=False)
    assert any(f["check"] == "required_media" for f in before["findings"])

    result = intake.upload_image(
        supplier=SUPPLIER, system_id=PORTAL, entity_id="VAR-02B",
        role="INGREDIENT_PANEL", filename="panel.svg", content_base64=SVG,
        alt_text="Ingredient panel")
    assert result["accepted"] is True

    after = readiness.assess("VAR-02B", use_model=False)
    assert not any(f["check"] == "required_media" for f in after["findings"])


def test_an_uploaded_image_is_attributed_to_the_system_that_carried_it():
    """Media has an owner, and it is not the supplier who sent the specs."""
    from sc.readiness import record as record_mod

    intake.upload_image(
        supplier=SUPPLIER, system_id=PORTAL, entity_id="VAR-02B",
        role="INGREDIENT_PANEL", filename="panel.svg", content_base64=SVG)
    record = record_mod.build("VAR-02B")
    panel = next(a for a in record.media if str(a.role) == "INGREDIENT_PANEL")
    assert panel.system == PORTAL


def test_an_image_role_nobody_declared_is_refused():
    refused = intake.upload_image(
        supplier=SUPPLIER, system_id=PORTAL, entity_id=VARIANT,
        role="LIFESTYLE", filename="x.svg", content_base64=SVG)
    assert "is not an image role" in refused["error"]


def test_an_upload_over_the_limit_is_refused_with_a_named_reason():
    oversized = base64.b64encode(b"x" * (intake.MAX_UPLOAD_BYTES + 1)).decode()
    refused = intake.upload_document(
        supplier=SUPPLIER, system_id=PORTAL, product_id=PRODUCT,
        filename="big.pdf", content_base64=oversized)
    assert "accepts up to" in refused["error"]


def test_a_document_with_no_text_says_it_has_not_been_read():
    """Recording that a document arrived is true and useful. Implying its
    contents were understood is neither."""
    result = intake.upload_document(
        supplier=SUPPLIER, system_id=PORTAL, product_id=PRODUCT,
        filename="spec.pdf", content_base64=SVG)
    assert result["extractable"] is False
    assert "has not guessed" in result["reason"]


def test_a_document_with_a_text_rendition_can_be_read():
    result = intake.upload_document(
        supplier=SUPPLIER, system_id=PORTAL, product_id=PRODUCT,
        filename="spec.pdf", content_base64=SVG,
        text="May contain peanuts from the next production run.")
    assert result["extractable"] is True


def test_uploaded_bytes_land_outside_the_seed_pack():
    """``data/media`` is rewritten wholesale by the generator, so an upload
    written there would survive until the next regeneration."""
    result = intake.upload_image(
        supplier=SUPPLIER, system_id=PORTAL, entity_id=VARIANT,
        role="PACK_FRONT", filename="pack.svg", content_base64=SVG)
    assert result["stored"]["path"].startswith("inbox/")


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def test_a_draft_says_plainly_that_it_is_not_in_the_catalog():
    """The catalog is loaded from the seed pack and ingestion drops any entity
    that pack does not name, so a draft claiming otherwise is a claim the very
    next screen disproves."""
    result = intake.create_product_draft(
        supplier=SUPPLIER, system_id=PORTAL, name="Harrowfield Oat Bites",
        category="food.snacks.bars", note="New line for spring.")
    assert result["accepted"] is True
    assert result["in_catalog"] is False
    assert result["status"] == "DRAFT_RECEIVED"


def test_a_draft_without_a_category_is_refused():
    refused = intake.create_product_draft(
        supplier=SUPPLIER, system_id=PORTAL, name="Nameless", category="")
    assert refused["error"]


# ---------------------------------------------------------------------------
# The relay back
# ---------------------------------------------------------------------------


def test_a_submission_reports_every_stage_it_reached():
    result = _submit()
    status = submissions.status(SUPPLIER, result["submission_id"])
    reached = set(status["reached"])

    assert {"received", "carried", "ingested", "recorded"} <= reached
    stages = {s["stage"]: s for s in status["stages"]}
    assert stages["carried"]["system"] == PORTAL
    assert stages["carried"]["defects"] == []


def test_a_document_version_reports_awaiting_extraction_not_nothing_wrong():
    """Ingestion raises no signal for a document, by design. Reporting that as
    "nothing wrong" would be the most misleading thing this screen could say to
    a supplier who has just corrected an allergen."""
    result = _submit()
    status = submissions.status(SUPPLIER, result["submission_id"])
    judged = next(s for s in status["stages"] if s["stage"] == "judged")
    assert judged["done"] is False
    assert judged.get("awaiting_extraction") is True


def test_a_verdict_carries_its_caveat_when_the_reading_checks_did_not_run():
    result = _submit()
    status = submissions.status(SUPPLIER, result["submission_id"])
    verdict = next(s for s in status["stages"] if s["stage"] == "verdict")
    for row in verdict.get("verdicts", []):
        assert row["checks_complete"] is False
        assert row["caveat"]


def test_a_supplier_cannot_read_another_suppliers_submission():
    result = _submit()
    refused = submissions.status("SUP-01", result["submission_id"])
    assert "does not belong" in refused["error"]


def test_a_repeated_submission_acts_once():
    key = "same-key"
    first = _submit(idempotency_key=key)
    second = _submit(idempotency_key=key)
    assert second.get("idempotent_replay") is True
    assert first["event_id"] == second["event_id"]
    assert db.one("SELECT COUNT(*) AS n FROM submissions")["n"] == 1
