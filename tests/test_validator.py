"""Deterministic validation and propagation engine.

These tests guard the property the whole recommendation rests on: the numbers
are reproducible and the reasons are named. If determinism breaks, every
rehearsal diverges and no resolution can be defended. If a rule stops naming
what bound it, the Investigation tab has nothing to explain and a blocked
channel becomes an unexplained absence.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_validator.db")

from sc.contracts import (  # noqa: E402
    ChangeSet,
    RegenerateCopyAction,
    SetAttributeAction,
    SourceRef,
    ViolationSeverity,
    WithholdChannelAction,
)
from sc.sim.engine import (  # noqa: E402
    CLAIM_RULES,
    SAFETY_CONFIDENCE,
    AttrState,
    Overlay,
    baseline_readiness,
    simulate,
)
from sc.state import baseline as baseline_mod  # noqa: E402

DOC01_V2 = SourceRef(doc_id="DOC-01", version="v2",
                     excerpt="The rated power of the Northaven AP300 is 65 W.")
DOC01_V3 = SourceRef(doc_id="DOC-01", version="v3",
                     excerpt="The Max is measured at 44 dB.")
DOC04_V2 = SourceRef(doc_id="DOC-04", version="v2",
                     excerpt="Shared line: may contain peanuts.")

REORDERED = ["oats", "honey", "almonds", "sugar", "sunflower oil"]


@pytest.fixture(scope="module")
def base():
    return baseline_mod.get()


def power(action_id: str = "a1", value: int = 65) -> SetAttributeAction:
    """The main inject: the Max is 65 W, not the 45 W v1 asserted."""
    return SetAttributeAction(
        id=action_id, entity_id="VAR-01B", attribute_path="specs.power_w",
        old_value=45, new_value=value, unit="W", confidence=0.93,
        source=DOC01_V2)


def allergen(action_id: str = "a1") -> SetAttributeAction:
    return SetAttributeAction(
        id=action_id, entity_id="VAR-02A",
        attribute_path="food.allergens.may_contain",
        old_value=[], new_value=["peanuts"], confidence=0.95, source=DOC04_V2)


def constraints(result, name: str) -> list:
    return [v for v in result.violations if v.constraint == name]


# ---------------------------------------------------------------------------
# Determinism - the property everything else depends on
# ---------------------------------------------------------------------------


def test_identical_change_set_produces_identical_trace(base):
    delta = ChangeSet(id="D", actions=[power()])
    hashes = {simulate(base, delta).trace_hash for _ in range(50)}
    assert len(hashes) == 1, "the validator must be reproducible run to run"


def test_action_order_does_not_change_the_result(base):
    """Two change sets holding the same actions in a different order are the
    same resolution, and must score identically - otherwise ranking is
    unstable and the reviewer sees a different winner each refresh."""
    regenerate = RegenerateCopyAction(
        id="a2", listing_id="LST-06", asset_id="AST-020", field="title",
        proposed_text="Northaven AP300 Max Air Purifier — HEPA H13, 65 m², 65W",
        source=DOC01_V2)

    forward = simulate(base, ChangeSet(id="X", actions=[power(), regenerate]))
    reverse = simulate(base, ChangeSet(id="X", actions=[regenerate, power()]))

    assert forward.trace_hash == reverse.trace_hash
    assert forward.kpis == reverse.kpis
    assert forward.violations == reverse.violations


def test_kpis_are_stable_across_repeat_runs(base):
    delta = ChangeSet(id="D", actions=[allergen()])
    results = [simulate(base, delta).kpis for _ in range(10)]
    assert all(k == results[0] for k in results)


def test_overlay_digest_is_stable(base):
    overlay = Overlay(attr_values={
        ("VAR-01B", "specs.power_w"): AttrState(65, "v2", "F-1", None,
                                                "INFERRED", 0.93)})
    assert overlay.digest() == overlay.digest()
    assert len({simulate(base, ChangeSet(id="D"), overlay).trace_hash
                for _ in range(20)}) == 1


# ---------------------------------------------------------------------------
# The catalog must be clean before anything breaks it
# ---------------------------------------------------------------------------


def test_untouched_catalog_validates_clean(base):
    """The seed generator asserts this. Every violation a run reports
    afterwards is therefore attributable to the correction under
    investigation, which is the whole basis of the blast-radius claim."""
    result = baseline_readiness(base)
    assert result.violations == [], [v.detail for v in result.violations[:5]]
    assert result.feasible
    assert result.kpis.listings_ready_pct == 100.0
    assert result.kpis.completeness_pct == 100.0
    assert result.kpis.fields_affected == 0
    assert result.kpis.channels_blocked == 0


def test_baseline_readiness_is_an_empty_change_set(base):
    assert (baseline_readiness(base).trace_hash
            == simulate(base, ChangeSet(id="BASELINE")).trace_hash)


# ---------------------------------------------------------------------------
# Propagation - what a corrected value drags with it
# ---------------------------------------------------------------------------


def test_corrected_attribute_marks_every_derived_asset_stale(base):
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    stale = {v.entity_id for v in constraints(result, "stale_asset")}

    assert "AST-023" in stale, "the Marketplace A feed row quotes the wattage"
    assert "AST-027" in stale, "the print catalogue copy quotes the wattage"
    assert result.kpis.assets_stale == len(
        {v.entity_id for v in result.violations
         if v.constraint in ("stale_asset", "stale_literal")})
    for v in constraints(result, "stale_asset"):
        assert base.assets[v.entity_id].id in v.detail


def test_correction_reaches_the_base_variant_comparison_table(base):
    """The deliberate cross-variant edge: the Northaven AP300's own page carries a
    table quoting the Max's wattage, so a correction scoped to the Max still
    lands on the base variant's listing."""
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    assert "AST-004" in {v.entity_id for v in constraints(result, "stale_asset")}
    assert any(v.channel_id == "CH-WEB" and v.entity_id == "AST-004"
               for v in result.violations)


def test_regenerating_the_copy_clears_the_stale_asset(base):
    fixed = simulate(base, ChangeSet(id="D", actions=[
        power(),
        RegenerateCopyAction(
            id="a2", listing_id="LST-08", asset_id="AST-031", field="shelf_text",
            proposed_text="Northaven AP300 Max · 65W · HEPA H13", source=DOC01_V2),
    ]))
    assert "AST-031" not in {v.entity_id for v in fixed.violations}


def test_stale_literal_is_hard_on_the_marketplace_and_print(base):
    """A superseded number left in the copy is a rejected feed on a
    marketplace and an un-recallable page in print; elsewhere it is a
    blemish."""
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    by_channel = {}
    for v in constraints(result, "stale_literal"):
        by_channel.setdefault(v.channel_id, set()).add(v.severity)

    assert by_channel["CH-MKT-A"] == {ViolationSeverity.HARD}
    assert by_channel["CH-PRINT"] == {ViolationSeverity.HARD}
    assert by_channel["CH-SHELF"] == {ViolationSeverity.SOFT}
    assert by_channel["CH-WEB"] == {ViolationSeverity.SOFT}
    assert all("45 W" in v.detail for v in constraints(result, "stale_literal"))


def test_stale_literal_does_not_match_inside_a_longer_number():
    """``45`` must not be found inside ``145``, or every dimension and price on
    the page becomes a false positive."""
    fresh = baseline_mod.load()
    fresh.assets["AST-031"].text = "Northaven AP300 Max · 145 W · HEPA H13"

    result = simulate(fresh, ChangeSet(id="D", actions=[power()]))
    literals = {v.entity_id for v in constraints(result, "stale_literal")}
    assert "AST-031" not in literals
    # The asset is still stale - it was built against the old version.
    assert "AST-031" in {v.entity_id for v in constraints(result, "stale_asset")}


def test_scope_stays_inside_the_corrected_product(base):
    """Candidate resolutions fan out concurrently, so a change set touching one
    variant must not walk the whole catalog."""
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    touched = {v.entity_id for v in result.violations}
    assert not any(t.startswith("VAR-02") or t.startswith("LST-1")
                   for t in touched)


# ---------------------------------------------------------------------------
# Channel rules - one test per rule kind, because each is a different failure
# ---------------------------------------------------------------------------


def test_max_len_reports_the_budget_and_the_overrun(base):
    over = "Northaven AP300 Max Air Purifier with True HEPA H13 " \
           "Filtration for Open-Plan Rooms up to 65 Square Metres, 65W"
    result = simulate(base, ChangeSet(id="D", actions=[RegenerateCopyAction(
        id="a1", listing_id="LST-06", asset_id="AST-020", field="title",
        proposed_text=over, source=DOC01_V2)]))

    breach = constraints(result, "channel_schema")[0]
    assert breach.entity_id == "LST-06:title"
    assert breach.channel_id == "CH-MKT-A"
    assert breach.required == 80.0
    assert breach.available == float(len(over))
    assert "RUL-A01" in breach.detail


def test_required_field_missing_names_the_rule_and_the_attribute(base):
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-01B", attribute_path="specs.power_w",
        old_value=45, new_value=None, source=DOC01_V2)]))

    fields = {v.entity_id: v for v in constraints(result, "channel_schema")}
    assert "RUL-A02" in fields["LST-06:wattage"].detail
    assert "RUL-P01" in fields["LST-07:specs.power_w"].detail
    assert fields["LST-06:wattage"].required == 1.0
    assert fields["LST-06:wattage"].available == 0.0


def test_dtype_rejects_a_value_of_the_wrong_type(base):
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-01B", attribute_path="specs.power_w",
        old_value=45, new_value="65 W", source=DOC01_V2)]))

    breach = [v for v in constraints(result, "channel_schema")
              if v.entity_id == "LST-06:wattage"][0]
    assert "RUL-A03" in breach.detail and "int" in breach.detail


def test_format_rejects_a_malformed_allergen_statement(base):
    """MKA-4102: the statement has to read the way Marketplace A parses it."""
    row = json.loads(base.assets["AST-038"].text) | {"allergen_statement": "almonds"}
    result = simulate(base, ChangeSet(id="D", actions=[RegenerateCopyAction(
        id="a1", listing_id="LST-10", asset_id="AST-038", field="feed_row",
        proposed_text=json.dumps(row, sort_keys=True), source=DOC04_V2)]))

    breach = [v for v in constraints(result, "channel_schema")
              if v.entity_id == "LST-10:allergen_statement"][0]
    assert "RUL-A05" in breach.detail
    assert breach.severity == ViolationSeverity.HARD


def test_enum_rejects_a_code_outside_the_channel_vocabulary(base):
    """AL-KIWI is not one of the regulated allergens, so no assortment can
    declare it and no marketplace vocabulary contains it. Deliberately not a
    code that merely happens to be unused today - the allowlist is built from
    the catalog's own map, so a code this test relied on being absent could
    become valid the moment a retailer started selling sesame."""
    row = json.loads(base.assets["AST-042"].text) | {"allergenCodes": ["AL-KIWI"]}
    result = simulate(base, ChangeSet(id="D", actions=[RegenerateCopyAction(
        id="a1", listing_id="LST-11", asset_id="AST-042", field="feed_row",
        proposed_text=json.dumps(row, sort_keys=True), source=DOC04_V2)]))

    breach = [v for v in constraints(result, "channel_schema")
              if v.entity_id == "LST-11:allergenCodes"][0]
    assert "RUL-B03" in breach.detail and "AL-KIWI" in breach.detail


def test_ordered_match_rejects_a_reordered_ingredient_list(base):
    """MKB-2208: ingredient order carries meaning, so a reordered declaration
    is a different declaration."""
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-02A", attribute_path="food.ingredients",
        old_value=list(base.attr_values[("VAR-02A", "food.ingredients")]),
        new_value=REORDERED, source=DOC04_V2)]))

    breach = [v for v in constraints(result, "channel_schema")
              if v.entity_id == "LST-11:ingredientList"][0]
    assert "RUL-B04" in breach.detail
    assert "oats, honey, almonds, sugar" in breach.detail


def test_regenerating_the_feed_row_satisfies_ordered_match(base):
    row = json.loads(base.assets["AST-042"].text) | {"ingredientList": REORDERED}
    result = simulate(base, ChangeSet(id="D", actions=[
        SetAttributeAction(
            id="a1", entity_id="VAR-02A", attribute_path="food.ingredients",
            new_value=REORDERED, source=DOC04_V2),
        RegenerateCopyAction(
            id="a2", listing_id="LST-11", asset_id="AST-042", field="feed_row",
            proposed_text=json.dumps(row, sort_keys=True), source=DOC04_V2),
    ]))
    assert not [v for v in constraints(result, "channel_schema")
                if v.entity_id == "LST-11:ingredientList"]


def test_category_mapped_names_the_unmapped_taxonomy_node(base):
    """Rules are data: dropping the mapping is enough to make the rule bind."""
    fresh = baseline_mod.load()
    fresh.channels["CH-MKT-A"].category_map.pop("home.air-treatment.purifiers")

    result = simulate(fresh, ChangeSet(id="D", actions=[power()]))
    breach = [v for v in constraints(result, "channel_schema")
              if v.entity_id == "LST-06:category"][0]
    assert "RUL-A07" in breach.detail
    assert "home.air-treatment.purifiers" in breach.detail


# ---------------------------------------------------------------------------
# Claim substantiation
# ---------------------------------------------------------------------------


def test_claim_table_covers_the_documented_claims():
    assert set(CLAIM_RULES) == {"gluten-free", "high-fibre", "low-energy",
                                "peanut-free", "ultra-quiet"}


def test_a_higher_wattage_unsubstantiates_low_energy(base):
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    claims = constraints(result, "claim_consistency")

    assert claims, "65 W cannot carry a claim capped at 50 W"
    assert all(v.severity == ViolationSeverity.HARD for v in claims)
    assert all(v.entity_id == "VAR-01B:claims" for v in claims)
    assert all("low-energy" in v.detail and "specs.power_w" in v.detail
               for v in claims)
    assert {v.channel_id for v in claims} == {"CH-WEB", "CH-MKT-A",
                                             "CH-PRINT", "CH-SHELF"}


def test_a_louder_measurement_unsubstantiates_ultra_quiet(base):
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-01B", attribute_path="specs.noise_db",
        old_value=38, new_value=44, unit="dB", source=DOC01_V3)]))
    assert any("ultra-quiet" in v.detail
               for v in constraints(result, "claim_consistency"))


def test_may_contain_peanuts_unsubstantiates_peanut_free(base):
    result = simulate(base, ChangeSet(id="D", actions=[allergen()]))
    claims = constraints(result, "claim_consistency")
    assert claims and all("peanut-free" in v.detail for v in claims)


def test_a_claim_that_holds_raises_nothing(base):
    """45 W and 38 dB carry both appliance claims - the point of a clean
    baseline is that the table is not simply always angry."""
    assert not constraints(baseline_readiness(base), "claim_consistency")


# ---------------------------------------------------------------------------
# Allergen declarations
# ---------------------------------------------------------------------------


def test_each_food_channel_demands_its_own_allergen_format(base):
    result = simulate(base, ChangeSet(id="D", actions=[allergen()]))
    by_entity = {v.entity_id: v for v in constraints(result,
                                                     "allergen_declaration")}

    marketplace_a = by_entity["LST-10:allergen_statement"]
    assert "Contains: almonds. May contain: peanuts." in marketplace_a.detail

    marketplace_b = by_entity["LST-11:allergenCodes"]
    assert "AL-PEANUT" in marketplace_b.detail
    assert marketplace_b.severity == ViolationSeverity.HARD


def test_an_undeclared_allergen_is_named_on_every_listing(base):
    result = simulate(base, ChangeSet(id="D", actions=[allergen()]))
    missing = [v for v in constraints(result, "allergen_declaration")
               if v.entity_id.endswith(":food.allergens")]

    assert {v.entity_id.split(":")[0] for v in missing} == {
        "LST-09", "LST-10", "LST-11", "LST-12", "LST-13"}
    assert all("peanuts" in v.detail for v in missing)


def test_derived_ingredient_order_must_match_the_source(base):
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-02A", attribute_path="food.ingredients",
        new_value=REORDERED, source=DOC04_V2)]))
    order = [v for v in constraints(result, "allergen_declaration")
             if v.entity_id.endswith(":food.ingredients")]

    assert order, "prose and feed rows both declare an ingredient order"
    assert all(v.severity == ViolationSeverity.HARD for v in order)
    assert all("food.ingredients" in v.detail for v in order)


def test_allergens_are_quiet_on_an_untouched_catalog(base):
    assert not constraints(baseline_readiness(base), "allergen_declaration")


# ---------------------------------------------------------------------------
# The fail-closed safety gate
# ---------------------------------------------------------------------------


def _inferred(confidence: float, kind: str = "INFERRED",
              entity_id: str = "VAR-02A") -> Overlay:
    return Overlay(attr_values={
        (entity_id, "food.allergens.may_contain"): AttrState(
            ["peanuts"], "v2", "F-1", None, kind, confidence)})


@pytest.mark.parametrize("entity_id", ["VAR-02A", "PRD-02"])
def test_low_confidence_on_a_safety_attribute_blocks_every_listing(base, entity_id):
    """Fail closed at whichever level the fact was recorded against.

    ``replay.ingest.record_attribute`` stores the entity the evidence named,
    and a document that says "the Oatberry bar" names the product. A gate that
    only understands variant ids passes that value through untouched, which is
    the single outcome fail-closed exists to prevent.
    """
    result = simulate(base, ChangeSet(id="D"), _inferred(0.62, entity_id=entity_id))
    gate = constraints(result, "safety_confidence")

    assert {v.channel_id for v in gate} == {"CH-WEB", "CH-MKT-A", "CH-MKT-B",
                                            "CH-SEARCH", "CH-SHELF"}
    assert all(v.severity == ViolationSeverity.HARD for v in gate)
    assert all(v.required == SAFETY_CONFIDENCE and v.available == 0.62
               for v in gate)
    assert all(v.entity_id == f"{entity_id}:food.allergens.may_contain"
               for v in gate)
    assert not result.feasible
    assert result.kpis.safety_flags > 0
    # Every listing the value reaches, not merely the ones a variant id happens
    # to index: a product-level fact reaches both variants of PRD-02.
    assert result.kpis.listings_ready_pct == 0.0


def test_a_confident_inference_passes_the_gate(base):
    result = simulate(base, ChangeSet(id="D"), _inferred(0.95))
    assert not constraints(result, "safety_confidence")


def test_a_human_decision_clears_the_gate(base):
    result = simulate(base, ChangeSet(id="D"), _inferred(0.62, kind="DECIDED"))
    assert not constraints(result, "safety_confidence")


def test_the_gate_ignores_attributes_that_are_not_safety_class(base):
    overlay = Overlay(attr_values={
        ("VAR-01B", "specs.power_w"): AttrState(65, "v2", "F-1", None,
                                                "INFERRED", 0.40)})
    assert not constraints(simulate(base, ChangeSet(id="D"), overlay),
                           "safety_confidence")


# ---------------------------------------------------------------------------
# The sale gate
#
# A different question from every other check here. The rest ask whether a
# listing is fit to publish; this asks whether the product may be sold at all,
# and the answer can be no while the record is perfect.
# ---------------------------------------------------------------------------


def _withdrawn(entity_id: str = "VAR-01B", kind: str = "RECORDED") -> Overlay:
    return Overlay(attr_values={
        (entity_id, "compliance.sale_permitted"): AttrState(
            False, "v2", "F-9", None, kind, 1.0)})


@pytest.mark.parametrize("entity_id", ["VAR-01B", "PRD-01"])
def test_a_withdrawal_blocks_every_listing_the_product_reaches(base, entity_id):
    """An authority has said no. Recorded with full confidence, and blocking.

    The safety gate would not fire on this: it only ever looks at inferences
    below the threshold, and a withdrawal notice is a fact somebody recorded,
    not a reading somebody was unsure about. Without its own constraint a
    takedown would escalate loudly and publish anyway.
    """
    result = simulate(base, ChangeSet(id="D"), _withdrawn(entity_id))
    gate = constraints(result, "sale_prohibited")

    assert gate, "a withdrawn product published"
    assert all(v.severity == ViolationSeverity.HARD for v in gate)
    assert all(v.entity_id == f"{entity_id}:compliance.sale_permitted"
               for v in gate)
    assert not result.feasible
    assert result.kpis.listings_ready_pct == 0.0


def test_the_sale_gate_is_part_of_the_publish_refusal(base):
    """It is in ``SAFETY_CONSTRAINTS``, which ``planning`` imports as its gate.

    That one tuple is what makes a violation refuse the commit rather than
    merely be reported, so membership is the whole mechanism and worth
    asserting rather than assuming.
    """
    from sc.tools import planning

    assert "sale_prohibited" in planning.SAFETY_GATE


def test_a_product_still_permitted_is_not_gated(base):
    """Only an explicit denial blocks.

    A missing value is a gap the readiness checks report. Reading "we were
    never told" as "not permitted" would hold the entire catalog the first
    time a supplier left the field empty, which is a fail-closed rule doing
    more harm than the thing it guards against.
    """
    permitted = Overlay(attr_values={
        ("VAR-01B", "compliance.sale_permitted"): AttrState(
            True, "v2", "F-9", None, "RECORDED", 1.0)})
    assert not constraints(simulate(base, ChangeSet(id="D"), permitted),
                           "sale_prohibited")
    assert not constraints(baseline_readiness(base), "sale_prohibited")


def test_a_withdrawal_is_not_something_copy_can_fix(base):
    """The leg must not spend a model call rewording a listing coming down."""
    from sc.graph import nodes
    from sc.graph import branches

    assert "sale_prohibited" in nodes.UNFIXABLE_BY_COPY
    assert "sale_prohibited" in branches.BEYOND_CONTENT


# ---------------------------------------------------------------------------
# The republish gate
#
# Two rules raise ``stale_version``, so both are selected by the entity they
# name: this gate names the attribute a standing decision was taken on, and the
# freeze-window rule below names the listing already in print.
# ---------------------------------------------------------------------------


def _on(result, name: str, entity_id: str) -> list:
    return [v for v in constraints(result, name) if v.entity_id == entity_id]


def test_a_decision_taken_against_an_older_version_blocks_republishing(base):
    overlay = Overlay(
        attr_values={("VAR-01B", "specs.power_w"): AttrState(
            65, "v2", "F-1", None, "RECORDED", None)},
        decision_version={"VAR-01B:specs.power_w": "v1"})

    breach = _on(simulate(base, ChangeSet(id="D"), overlay),
                 "stale_version", "VAR-01B:specs.power_w")[0]
    assert breach.severity == ViolationSeverity.HARD
    assert breach.required == 2.0 and breach.available == 1.0
    assert "revalidated" in breach.detail


def test_a_current_decision_does_not_block_republishing(base):
    overlay = Overlay(
        attr_values={("VAR-01B", "specs.power_w"): AttrState(
            65, "v2", "F-1", None, "RECORDED", None)},
        decision_version={"VAR-01B:specs.power_w": "v2"})
    assert not _on(simulate(base, ChangeSet(id="D"), overlay),
                   "stale_version", "VAR-01B:specs.power_w")


# ---------------------------------------------------------------------------
# The freeze window - what is already printed cannot be regenerated
# ---------------------------------------------------------------------------


def test_a_frozen_channel_reports_the_artefact_left_on_a_superseded_version(base):
    """INC-2026-002: the catalogue asset was rebuilt, stopped looking stale,
    and 214,000 copies still carried the old figure."""
    breach = _on(simulate(base, ChangeSet(id="D", actions=[power()])),
                 "stale_version", "LST-07")[0]

    assert breach.severity == ViolationSeverity.HARD
    assert breach.channel_id == "CH-PRINT"
    assert breach.required == 2.0 and breach.available == 1.0
    assert "7 days" in breach.detail and "reprint decision" in breach.detail


def test_regenerating_the_copy_does_not_clear_the_freeze_window(base):
    """The distinction the freeze window exists for: a stale asset is content
    that can be rebuilt, a stale version is a physical object in the world."""
    result = simulate(base, ChangeSet(id="D", actions=[
        power(),
        RegenerateCopyAction(
            id="a2", listing_id="LST-07", asset_id="AST-027",
            field="catalogue_copy",
            proposed_text="Northaven AP300 Max — HEPA H13, 65 m², 65 W",
            source=DOC01_V2),
    ]))
    assert "AST-027" not in {v.entity_id for v in constraints(result, "stale_asset")}
    assert _on(result, "stale_version", "LST-07")


def test_a_reversible_channel_is_not_held_to_the_freeze_window(base):
    """Raising it on CH-WEB would block every correction with its own arrival:
    a web page answers a moved value by republishing."""
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    frozen = {v.entity_id for v in constraints(result, "stale_version")}

    assert frozen == {"LST-07"}, "only the Max's print listing quotes the wattage"
    assert not _on(result, "stale_version", "LST-05")


def test_withholding_the_listing_is_the_reprint_decision(base):
    result = simulate(base, ChangeSet(id="D", actions=[
        power(),
        WithholdChannelAction(id="a2", listing_id="LST-07", channel_id="CH-PRINT",
                              reason="inside the print freeze", source=DOC01_V2),
    ]))
    assert not constraints(result, "stale_version")


def test_a_listing_that_has_never_gone_to_press_has_nothing_to_be_stale(base):
    """An empty ``published_version`` is no artefact, not a version of zero."""
    fresh = baseline_mod.load()
    fresh.listings["LST-07"].published_version = ""

    result = simulate(fresh, ChangeSet(id="D", actions=[power()]))
    assert not constraints(result, "stale_version")


def test_republishing_the_listing_clears_the_freeze_window(base):
    """The press decision, recorded: the artefact now carries v2."""
    overlay = Overlay(published_version={"LST-07": "v2"})
    result = simulate(base, ChangeSet(id="D", actions=[power()]), overlay)
    assert not constraints(result, "stale_version")


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------


def test_an_uncited_change_is_not_publishable(base):
    result = simulate(base, ChangeSet(id="D", actions=[SetAttributeAction(
        id="a1", entity_id="VAR-01B", attribute_path="specs.power_w",
        new_value=65)]))
    breach = constraints(result, "citation_missing")[0]

    assert breach.entity_id == "VAR-01B:specs.power_w"
    assert breach.severity == ViolationSeverity.HARD
    assert "a1" in breach.detail
    assert not result.feasible


def test_an_uncited_regeneration_is_not_publishable(base):
    result = simulate(base, ChangeSet(id="D", actions=[RegenerateCopyAction(
        id="a1", listing_id="LST-08", asset_id="AST-031", field="shelf_text",
        proposed_text="Northaven AP300 Max · 65W · HEPA H13")]))
    assert [v.entity_id for v in constraints(result, "citation_missing")] \
        == ["AST-031"]


def test_a_cited_change_raises_nothing(base):
    assert not constraints(simulate(base, ChangeSet(id="D", actions=[power()])),
                           "citation_missing")


# ---------------------------------------------------------------------------
# Reporting - a blocked channel is shown with its reason, never dropped
# ---------------------------------------------------------------------------


def test_every_violation_names_the_binding_rule_and_the_entity(base):
    result = simulate(base, ChangeSet(id="D", actions=[power(), allergen("a2")]))
    assert result.violations

    for v in result.violations:
        assert v.constraint and v.entity_id and v.detail
        head = v.entity_id.split(":")[0]
        assert head in base.assets or head in base.listings \
            or head in base.variants, v.entity_id
        if v.constraint == "channel_schema":
            assert "RUL-" in v.detail, v.detail


def test_violations_are_collapsed_to_one_row_per_binding_rule(base):
    result = simulate(base, ChangeSet(id="D", actions=[power()]))
    keys = [(v.constraint, v.entity_id, v.channel_id) for v in result.violations]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys, key=lambda k: (k[0], k[1], k[2] or ""))


def test_withholding_a_channel_costs_a_step_and_still_shows_the_block(base):
    """Withholding is a decision with consequences, so it appears in the diff
    and in the KPIs rather than as a silently absent channel."""
    plain = simulate(base, ChangeSet(id="D", actions=[power()]))
    held = simulate(base, ChangeSet(id="D", actions=[
        power(),
        WithholdChannelAction(id="a2", listing_id="LST-07", channel_id="CH-PRINT",
                              reason="print freeze", source=DOC01_V2),
    ]))

    assert "CH-PRINT" not in {v.channel_id for v in held.violations}
    assert held.kpis.channels_blocked == plain.kpis.channels_blocked
    assert held.kpis.republish_steps > plain.kpis.republish_steps


def test_feasibility_is_exactly_the_absence_of_hard_violations(base):
    for delta in (ChangeSet(id="BASELINE"),
                  ChangeSet(id="D", actions=[power()]),
                  ChangeSet(id="D", actions=[allergen()])):
        result = simulate(base, delta)
        assert result.feasible == (not any(v.severity == ViolationSeverity.HARD
                                           for v in result.violations))


# ---------------------------------------------------------------------------
# Speed - resolutions are validated in parallel behind a live UI
# ---------------------------------------------------------------------------


def test_validation_is_fast_enough_to_fan_out(base):
    """A slow validator turns the Resolutions tab into a spinner."""
    assert simulate(base, ChangeSet(id="D", actions=[power()])).runtime_ms < 250
    assert baseline_readiness(base).runtime_ms < 250
