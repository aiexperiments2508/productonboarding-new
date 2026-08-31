"""Blast-radius traversal.

The claim the whole demo rests on is "this correction touches these fields,
these listings and these channels - here is every hop". These tests guard the
three properties that make that claim worth anything: the walk reaches
everything that used the old value, it reaches nothing that did not, and it says
why in relations a reviewer can read.

The awkward case is deliberate and is tested hardest: a correction scoped to the
Max still lands on the base model's page, because the comparison table there
quotes the Max's wattage. A traversal that misses it would republish a page that
contradicts itself.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("DB_PATH", "data/test_propagation.db")

from sc import db  # noqa: E402
from sc import main  # noqa: E402 - the HTTP route, called as the function it is
from sc.contracts import (  # noqa: E402
    ChangeSet,
    Provenance,
    ProvenanceKind,
    SetAttributeAction,
    SourceRef,
)
from sc.sim.engine import simulate  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.state import store  # noqa: E402
from sc.tools import network  # noqa: E402

# Horizon day 14 and the main inject on day 28, per the seed pack.
CERTIFIED = datetime(2026, 9, 15, 9)
INJECT = datetime(2026, 9, 29, 9)
AS_OF = "2026-09-30T09:00:00"

POWER = "VAR-01B:specs.power_w"
ROOTS = ("DOC-01", "PRD-01", "VAR-01B", POWER, "AST-004", "LST-06", "CH-WEB")


@pytest.fixture(autouse=True)
def fresh_db():
    db.init_db(drop=True)
    yield
    db.close()


@pytest.fixture
def base():
    return baseline_mod.get()


def certify_base_at_45() -> None:
    """Day 14: the portal feed certifies the base model independently."""
    store.record(
        entity_type="variant", entity_id="VAR-01A", attr="specs.power_w",
        value=45, valid_from=CERTIFIED, recorded_at=CERTIFIED,
        provenance=Provenance(kind=ProvenanceKind.RECORDED, source_id="DOC-02:v1"))


def correct_the_max_to_65() -> None:
    """Day 28: DOC-01 v2 says 65 W, without naming which model it means."""
    store.record(
        entity_type="source_doc", entity_id="DOC-01", attr="version",
        value="v2", valid_from=INJECT, recorded_at=INJECT,
        provenance=Provenance(kind=ProvenanceKind.RECORDED, source_id="EVT-INJECT"))
    store.record(
        entity_type="variant", entity_id="VAR-01B", attr="specs.power_w",
        value=65, valid_from=INJECT, recorded_at=INJECT,
        provenance=Provenance(kind=ProvenanceKind.INFERRED, source_id="DOC-01:v2",
                              confidence=0.93))


def reject_the_multipack_feed() -> None:
    """Day 31: Marketplace B rejects the republish with MKB-2201."""
    store.record(
        entity_type="listing", entity_id="LST-11", attr="status",
        value="REJECTED", valid_from=INJECT, recorded_at=INJECT,
        provenance=Provenance(kind=ProvenanceKind.RECORDED, source_id="EVT-REJECT"))


def rows(diff: dict) -> dict:
    return {row["path"]: row for row in diff["attributes"]}


# ---------------------------------------------------------------------------
# The catalog map
# ---------------------------------------------------------------------------


def test_the_map_joins_every_tier_with_a_derived_edge(base):
    """Edges are derived from the listings rather than stored, so the map cannot
    drift from the catalog it claims to draw."""
    state = network.get_network_state()
    by_relation: dict[str, list[dict]] = {}
    for edge in state["edges"]:
        by_relation.setdefault(edge["relation"], []).append(edge)

    assert len(by_relation["supplies"]) == len(base.catalog.products)
    assert len(by_relation["contains"]) == len(base.catalog.variants)
    assert len(by_relation["lists_on"]) == len(base.listings)
    assert {e["listing"] for e in by_relation["lists_on"]} == set(base.listings)

    known = {n["id"] for n in state["nodes"]}
    assert known >= {e["from"] for e in state["edges"]}
    assert known >= {e["to"] for e in state["edges"]}
    assert state["horizon_days"] == base.horizon_days


def test_a_quiet_catalog_reports_no_corrections():
    assert network.get_network_state()["correction"] == {
        "docs": [], "attributes": {}, "listings": {}, "assets_stale": 0,
        "channels": {}, "summary": [],
    }


def test_corrections_in_force_show_on_the_map_with_their_source(base):
    certify_base_at_45()
    correct_the_max_to_65()
    reject_the_multipack_feed()

    state = network.get_network_state(as_of=AS_OF)
    correction = state["correction"]

    # DOC-01 is listed because v2 is in force over the v1 the copy was built on.
    assert correction["docs"] == ["DOC-01"]
    assert correction["attributes"][POWER] == {
        "value": 65, "version": "v2", "doc": "DOC-01",
        "provenance": "INFERRED", "confidence": 0.93}
    assert correction["listings"] == {"LST-11": "REJECTED"}
    assert any("45 -> 65" in line for line in correction["summary"])

    # Counted the way the validator counts it: copy standing on a version that
    # has since moved.
    assert correction["assets_stale"] == len(base.assets_derived_from[POWER])

    edge = [e for e in state["edges"] if e.get("listing") == "LST-11"][0]
    assert edge["status"] == "REJECTED", "a blocked listing is shown, not dropped"


def test_recorded_time_hides_a_correction_that_had_not_arrived_yet():
    """No silent overwrite: the baseline is still the answer for a question
    asked from before the correction landed."""
    correct_the_max_to_65()
    before = network.get_network_state(as_of=AS_OF,
                                       as_of_recorded="2026-09-20T09:00:00")
    assert before["correction"]["attributes"] == {}
    assert before["as_of_recorded"] == "2026-09-20T09:00:00"


# ---------------------------------------------------------------------------
# The blast radius
# ---------------------------------------------------------------------------


def test_the_correction_reaches_every_channel_that_used_the_old_value(base):
    trace = network.trace_dependencies(POWER)
    affected = trace["affected"]

    assert set(affected["assets"]) >= set(base.assets_derived_from[POWER])
    assert set(affected["listings"]) == {"LST-01", "LST-05", "LST-06",
                                         "LST-07", "LST-08"}
    assert set(affected["channels"]) == {"CH-MKT-A", "CH-PRINT", "CH-SHELF",
                                         "CH-WEB"}
    assert set(affected["channels"]) == {base.listings[l].channel_id
                                         for l in affected["listings"]}
    # The snack bar shares neither a document nor a page with an air purifier.
    assert "CH-SEARCH" not in affected["channels"]
    assert not any(v.startswith("VAR-02") for v in affected["variants"])


def test_a_variant_correction_reaches_the_base_page_through_the_comparison_table():
    """The deliberate cross-variant edge. A correction scoped to the Max lands
    on the Northaven AP300's own PDP because the table there quotes both models."""
    trace = network.trace_dependencies(POWER)

    assert "AST-004" in trace["affected"]["assets"]
    assert "LST-01" in trace["affected"]["listings"]
    assert "VAR-01A" in trace["affected"]["variants"]
    assert {"from": POWER, "to": "AST-004", "relation": "derives"} in trace["chain"]
    assert {"from": "AST-004", "to": "LST-01",
            "relation": "lists_on"} in trace["chain"]


def test_every_chain_link_is_drawn_with_a_relation_the_ui_can_label():
    certify_base_at_45()
    correct_the_max_to_65()
    for root in ROOTS:
        chain = network.trace_dependencies(root, as_of=AS_OF)["chain"]
        assert chain, root
        assert {link["relation"] for link in chain} <= set(network.RELATIONS), root
        assert all(link["from"] and link["to"] for link in chain), root


def test_a_document_revision_is_drawn_as_a_supersedes_hop():
    certify_base_at_45()
    correct_the_max_to_65()
    trace = network.trace_dependencies("DOC-01", as_of=AS_OF)

    assert {"from": "DOC-01:v2", "to": "DOC-01:v1",
            "relation": "supersedes"} in trace["chain"]
    assert {"from": "DOC-01:v2", "to": POWER, "relation": "defines"} in trace["chain"]
    # The base model's wattage stopped being DOC-01's to define on day 14.
    assert "VAR-01A:specs.power_w" not in trace["affected"]["attributes"]


def test_totals_agree_with_the_affected_lists(base):
    for root in ROOTS:
        trace = network.trace_dependencies(root)
        affected, totals = trace["affected"], trace["totals"]

        assert totals["fields"] == len(affected["attributes"]), root
        assert totals["assets"] == len(affected["assets"]), root
        assert totals["listings"] == len(affected["listings"]), root
        assert totals["channels"] == len(affected["channels"]), root
        assert totals["safety_flags"] == sum(
            base.attr_defs[ref.partition(":")[2]].safety_class
            for ref in affected["attributes"]), root
        assert totals["regulated"] == sum(
            base.products[p].regulated for p in affected["products"]), root


def test_a_regulated_product_is_counted_as_one():
    """The two numbers a reviewer reads first.

    Six safety flags, not four: both allergen paths on both variants, plus
    `compliance.sale_permitted` on each. That attribute is safety-class on
    purpose - it is what a withdrawal notice moves, and marking it so is what
    buys forced escalation and a fail-closed publish without new rule code.

    `regulated` stays one, because it counts products and not attributes."""
    totals = network.trace_dependencies("PRD-02")["totals"]
    assert totals["regulated"] == 1
    assert totals["safety_flags"] == 6


def test_depth_bounds_the_walk():
    shallow = network.trace_dependencies(POWER, depth=1)
    middle = network.trace_dependencies(POWER, depth=2)
    full = network.trace_dependencies(POWER, depth=3)

    assert shallow["affected"]["attributes"] == [POWER]
    assert shallow["affected"]["variants"] == ["VAR-01B"]
    assert shallow["affected"]["assets"] == []
    assert shallow["affected"]["listings"] == []

    assert middle["affected"]["assets"] and middle["affected"]["listings"]
    assert middle["affected"]["channels"] == []
    # The base page is reached at depth 2; the variant behind it only at 3.
    assert "LST-01" in middle["affected"]["listings"]
    assert "VAR-01A" not in middle["affected"]["variants"]

    assert full["affected"]["channels"]
    assert len(full["chain"]) > len(middle["chain"]) > len(shallow["chain"])


def test_an_unknown_root_returns_an_empty_scope_rather_than_raising():
    trace = network.trace_dependencies("VAR-99Z")
    assert trace["root"] == "VAR-99Z"
    assert trace["chain"] == []
    assert all(value == [] for value in trace["affected"].values())
    assert set(trace["totals"].values()) == {0}

    unknown_path = network.trace_dependencies("VAR-01B:specs.nonesuch")
    assert unknown_path["affected"]["attributes"] == []


def test_a_cyclic_catalog_terminates_and_never_redraws_a_hop(monkeypatch):
    """The base page already quotes the Max. Make the Max's page quote the base
    and the two variants reference each other - the walk must still finish."""
    fresh = baseline_mod.load()
    fresh.assets["AST-018"].derived_from.append("VAR-01A:specs.power_w")
    fresh.assets_derived_from.setdefault("VAR-01A:specs.power_w", []).append("AST-018")
    monkeypatch.setattr(baseline_mod, "get", lambda: fresh)

    trace = network.trace_dependencies(POWER)
    hops = [(l["from"], l["to"], l["relation"]) for l in trace["chain"]]

    assert len(hops) == len(set(hops)), "a cycle must not redraw the same hop"
    assert len(hops) <= network.MAX_CHAIN
    assert "AST-018" in trace["affected"]["assets"]


def test_the_chain_is_capped_without_truncating_the_scope(base):
    """Every variant has a website listing, so this root reaches the whole
    catalog. The cap shortens the explanation and never the answer."""
    trace = network.trace_dependencies("CH-WEB")

    assert len(trace["chain"]) == network.MAX_CHAIN
    assert trace["totals"]["listings"] == len(base.listings)
    assert trace["totals"]["channels"] == len(base.channels)
    assert set(trace["affected"]["assets"]) == {
        asset_id for assets in base.assets_derived_from.values()
        for asset_id in assets}


def test_every_listing_the_validator_flags_is_inside_the_blast_radius(base):
    """The reviewer is shown the traversal's count and the validator revalidates
    its own scope. If the two disagree the demo contradicts itself, so the
    traversal has to be a superset of everything the validator binds on."""
    correction = SetAttributeAction(
        id="a1", entity_id="VAR-01B", attribute_path="specs.power_w",
        old_value=45, new_value=65, unit="W", confidence=0.93,
        source=SourceRef(doc_id="DOC-01", version="v2"))
    result = simulate(base, ChangeSet(id="D", actions=[correction]))

    flagged = set()
    for violation in result.violations:
        head = violation.entity_id.partition(":")[0]
        if head in base.assets:
            flagged.add(base.assets[head].listing_id)
        elif head in base.listings:
            flagged.add(head)

    assert flagged
    assert flagged <= set(network.trace_dependencies(POWER)["affected"]["listings"])


def test_two_traces_of_the_same_root_are_identical():
    """Sorted iteration everywhere: the blast radius is part of the audit trail,
    so it has to hash the same on every run."""
    assert len({db.dumps(network.trace_dependencies(POWER)) for _ in range(20)}) == 1
    assert len({db.dumps(network.trace_dependencies("PRD-02")) for _ in range(20)}) == 1


# ---------------------------------------------------------------------------
# Base versus variant
# ---------------------------------------------------------------------------


def test_variant_diff_marks_exactly_the_attributes_that_differ():
    diff = network.variant_diff("PRD-01")

    assert [v["id"] for v in diff["variants"]] == ["VAR-01A", "VAR-01B"]
    assert {p for p, row in rows(diff).items() if row["differs"]} == {
        "identifiers.gtin", "specs.coverage_m2"}
    # The premise of scenario one: at baseline both models read 45 W, which is
    # internally consistent and wrong.
    assert rows(diff)["specs.power_w"]["values"]["VAR-01B"]["value"] == 45


def test_variant_diff_shows_the_document_each_value_stands_on():
    """This is the evidence for the scope decision: the base model was certified
    at 45 W by its own document a fortnight before the ambiguous correction."""
    certify_base_at_45()
    correct_the_max_to_65()
    row = rows(network.variant_diff("PRD-01", as_of=AS_OF))["specs.power_w"]

    assert row["differs"]
    assert row["values"]["VAR-01A"] == {
        "value": 45, "version": "v1", "doc": "DOC-02",
        "provenance": "RECORDED", "confidence": None}
    assert row["values"]["VAR-01B"] == {
        "value": 65, "version": "v2", "doc": "DOC-01",
        "provenance": "INFERRED", "confidence": 0.93}


def test_the_variants_endpoint_serves_the_document_the_value_stands_on(base):
    """The route and the MCP tool answer the same question and must answer it
    with the same cell.

    The whole argument for scoping the correction to the Max is that the base
    model was independently certified at 45 W by a named document. A cell
    flattened to its value cannot say that, and the panel that renders "stands
    on DOC-02 v1" under it has nothing to render.
    """
    certify_base_at_45()
    correct_the_max_to_65()

    answer = main.catalog_variants("PRD-01", as_of=AS_OF)
    power = answer["attributes"]["specs.power_w"]

    assert power["VAR-01A"] == {"value": 45, "version": "v1", "doc": "DOC-02",
                                "provenance": "RECORDED", "confidence": None}
    assert power["VAR-01B"] == {"value": 65, "version": "v2", "doc": "DOC-01",
                                "provenance": "INFERRED", "confidence": 0.93}
    # And the two things the route adds on top of the tool are untouched.
    assert "specs.power_w" in answer["differs"]
    assert answer["variants"][0]["listings"] == base.listings_of["VAR-01A"]


def test_a_value_only_one_variant_carries_is_a_difference_too(monkeypatch):
    fresh = baseline_mod.load()
    del fresh.attr_values[("VAR-01B", "specs.noise_db")]
    monkeypatch.setattr(baseline_mod, "get", lambda: fresh)

    row = rows(network.variant_diff("PRD-01"))["specs.noise_db"]
    assert row["differs"]
    assert set(row["values"]) == {"VAR-01A"}


def test_variant_diff_carries_the_label_and_the_safety_flag():
    row = rows(network.variant_diff("PRD-02"))["food.allergens.may_contain"]
    assert row["safety_class"] is True
    assert row["label"] == "Allergens - may contain"
    assert rows(network.variant_diff("PRD-01"))["specs.power_w"]["unit"] == "W"


def test_an_unknown_product_is_an_error_not_an_exception():
    assert "error" in network.variant_diff("PRD-99")


# ---------------------------------------------------------------------------
# Derivation and channel rules
# ---------------------------------------------------------------------------


def test_get_derivation_names_the_cross_variant_edge():
    derivation = network.get_derivation("AST-004")

    assert derivation["kind"] == "asset"
    assert derivation["listing"] == "LST-01"
    assert derivation["variant"] == "VAR-01A"
    assert {s["ref"] for s in derivation["derived_from"] if s["cross_variant"]} == {
        "VAR-01B:specs.coverage_m2", "VAR-01B:specs.filter_type",
        "VAR-01B:specs.noise_db", "VAR-01B:specs.power_w"}
    assert all(s["doc"] and s["version"] for s in derivation["derived_from"])


def test_get_derivation_of_a_listing_covers_every_asset_on_it(base):
    derivation = network.get_derivation("LST-06")

    assert derivation["kind"] == "listing"
    assert [a["asset"]["id"] for a in derivation["assets"]] == \
        base.assets_by_listing["LST-06"]
    assert POWER in derivation["sources"]


def test_get_derivation_of_an_unknown_id_is_an_error_not_an_exception():
    # Not "AST-999" - the catalog has thousands of assets now and that is a
    # real one. An unknown id has to be unknowable, not merely unlikely.
    assert "error" in network.get_derivation("AST-NO-SUCH-THING")


def test_channel_rules_returns_only_what_binds_on_the_named_field():
    rules = network.channel_rules("CH-MKT-A", "wattage")
    assert [r["id"] for r in rules["rules"]] == ["RUL-A02", "RUL-A03"]
    assert rules["attribute_paths"] == ["specs.power_w"]


def test_channel_rules_without_a_field_returns_the_whole_channel():
    rules = network.channel_rules("CH-MKT-A")
    assert [r["id"] for r in rules["rules"]] == [
        "RUL-A01", "RUL-A02", "RUL-A03", "RUL-A04", "RUL-A05", "RUL-A06",
        "RUL-A07"]
    assert "specs.power_w" in rules["required_attributes"]
    assert "wattage" in rules["fields"]


def test_the_print_freeze_window_is_visible_on_its_channel():
    assert network.channel_rules("CH-PRINT")["channel"]["freeze_days"] == 7
    assert "error" in network.channel_rules("CH-NOPE")


# ---------------------------------------------------------------------------
# One listing, as it stands
# ---------------------------------------------------------------------------


def test_a_listing_is_clean_until_something_moves_under_it():
    state = network.get_listing_state("LST-06")
    assert state["stale_assets"] == []
    assert state["status"] == "PREPARED"
    assert state["values"]["specs.power_w"]["value"] == 45
    assert state["channel"]["id"] == "CH-MKT-A"


def test_a_corrected_value_marks_the_copy_that_quoted_it_stale(base):
    correct_the_max_to_65()
    state = network.get_listing_state("LST-06", as_of=AS_OF)

    assert state["stale_assets"] == base.assets_by_listing["LST-06"]
    assert state["values"]["specs.power_w"] == {
        "value": 65, "version": "v2", "doc": "DOC-01",
        "provenance": "INFERRED", "confidence": 0.93}
    assert all(POWER in a["stale_refs"] for a in state["assets"])

    # And the base model's page is stale through the comparison table alone.
    assert network.get_listing_state("LST-01", as_of=AS_OF)["stale_assets"] \
        == ["AST-004"]


def test_a_rejected_feed_is_reported_on_the_listing_with_its_status():
    reject_the_multipack_feed()
    assert network.get_listing_state("LST-11", as_of=AS_OF)["status"] == "REJECTED"


def test_an_unknown_listing_is_an_error_not_an_exception():
    assert "error" in network.get_listing_state("LST-999")
