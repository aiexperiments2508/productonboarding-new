"""The six saved queries, answered in process, and the traversal under them.

Every one of these has to return rows. An insight view that answers with an
empty table reads exactly like a correct answer - "nothing to worry about" -
and is the failure mode this whole feature is most likely to arrive in.

So the assertions are about **identity, not count**. Asserting "twelve rows"
breaks the day somebody adds a product and says nothing useful when it does;
asserting "the certificate two variants share is in the lapsing cohort" fails
only when the thing that made the view worth building has actually gone.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_kg_insights.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.contracts import GraphDomain, GraphNodeLabel  # noqa: E402
from sc.kg import insights, memory, model, synth  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402


@pytest.fixture(scope="module")
def pack_file(tmp_path_factory):
    target = tmp_path_factory.mktemp("kg") / "backoffice.jsonl"
    synth.write(target)
    return target


@pytest.fixture(autouse=True)
def fresh(pack_file):
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    memory.cache_clear()
    tape.load_tape(reset=True)
    tape.load_reference(pack_file, reset=True)
    yield
    db.close()


def run(insight_id: str, **params) -> list[dict]:
    return insights.RUNNERS[insight_id](
        memory.graph(), insights.bind(insight_id, params or None),
        tape.sim_now())


# ---------------------------------------------------------------------------
# The graph itself


def test_the_projection_covers_all_seven_domains():
    """Seven chips in the legend, seven domains with something behind them.

    A chip that filters to nothing is worse than a missing chip: the reader
    concludes the product has no compliance rather than that the tab has no
    compliance data.
    """
    from sc.kg import project

    tally = project.domains_present(memory.graph())
    for domain in GraphDomain:
        assert tally[domain] > 0, f"{domain.value} projected nothing"


def test_a_graph_with_no_reference_pack_still_has_the_catalog():
    """Four of the seven domains are the retailer's own and need no pack.

    A checkout that has not run the generator gets products, variants,
    categories, media and channels. The tab renders; three chips are empty and
    say so.
    """
    from sc.kg import project

    graph = project.build(baseline_mod.get(), [])
    tally = project.domains_present(graph)
    assert tally[GraphDomain.CORE] > 0
    assert tally[GraphDomain.CATEGORY] > 0
    assert tally[GraphDomain.MEDIA] > 0
    assert tally[GraphDomain.SALES] > 0      # channels and listings are real
    assert tally[GraphDomain.WAREHOUSE] == 0
    assert tally[GraphDomain.MARKETING] == 0


def test_every_edge_joins_two_labels_the_model_admits():
    """A projection bug that joined a campaign to a depot would load cleanly.

    `model.ENDPOINTS` says which two labels each relationship may connect, and
    this is the test that makes writing it down worth anything.
    """
    graph = memory.graph()
    for edge in graph.edges:
        sources, targets = model.ENDPOINTS[edge.type]
        assert graph.nodes[edge.source].label in sources, edge.id
        assert graph.nodes[edge.target].label in targets, edge.id


def test_only_the_invented_domains_are_marked_synthetic():
    """The dashed stroke has to mean something.

    A real product marked synthetic would undersell the catalog; an invented
    revenue figure marked real is the failure that matters.
    """
    graph = memory.graph()
    for node in graph.nodes.values():
        assert node.synthetic == model.is_synthetic(node.label), node.id


# ---------------------------------------------------------------------------
# The six


def test_certifications_expiring_finds_the_shared_ones():
    """The point of asking a graph rather than a spreadsheet.

    One certificate covers several products, and the two in this catalog that
    genuinely do are deliberately in the lapsing cohort. A view returning only
    single-product certificates would be truthful and would demonstrate
    nothing.
    """
    rows = run("certifications-expiring")
    assert rows

    shared = [r for r in rows if r["products"] > 1]
    assert shared, "no lapsing certificate covers more than one product"
    assert all(0 <= r["days_remaining"] <= 90 for r in rows)

    # The window is a parameter, and narrowing it narrows the answer.
    assert len(run("certifications-expiring", within_days=10)) <= len(rows)


def test_bestsellers_missing_image_names_a_real_gap():
    """Every row must be a variant the record view would also flag.

    The ranking is invented; the missing image is not. A row whose media is
    actually complete would mean the view had started inventing findings.
    """
    from sc.kg import project

    rows = run("bestsellers-missing-image")
    assert rows

    graph = memory.graph()
    by_sku = {n.props.get("sku"): n for n in graph.nodes.values()
              if n.label.value == "Variant"}
    for row in rows:
        variant = by_sku[row["sku"]]
        assert variant.props["missingMedia"], row["sku"]
        assert row["missing_media"]

    boosted = synth._bestsellers_without_media(synth._load(), synth.DEFAULT_SEED)
    found = {row["sku"] for row in rows}
    for variant_id in boosted:
        node = graph.nodes[
            project.node_id(GraphNodeLabel.VARIANT, variant_id)]
        assert node.props.get("sku") in found, variant_id


def test_stock_that_cannot_ship_is_found_at_the_depot_that_serves_the_eu():
    """The finding nothing else in this platform can make.

    A UKCA certificate does not satisfy CE. The depot serving Germany and
    France holds UKCA-certified stock. Neither the warehouse system nor the
    certificate register nor the market rules can see that on their own.
    """
    rows = run("stock-cannot-ship")
    assert rows

    rotterdam = [r for r in rows if r["warehouse"] == "Rotterdam EDC"]
    assert rotterdam, "the depot the condition was planted at reports nothing"
    assert any(r["regulation"] == "REG-CE-768-2008" for r in rotterdam)
    assert all("UKCA" in r["holds"] or "BS-EN" in r["holds"] or "EN71" in r["holds"]
               for r in rotterdam)

    # Markets are collapsed into one row per depot and regulation - Rotterdam
    # serves two CE markets and that is one piece of work, not two.
    keys = [(r["sku"], r["warehouse"], r["regulation"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_cross_sell_candidates_cross_a_category_boundary():
    """Two variants of one product in two sizes is not a cross-sell candidate.

    The pairs that matter come from different branches, which is why the
    occasion-basket campaigns draw members across them.
    """
    rows = run("cross-sell-candidates")
    assert rows
    assert all(r["shared_campaigns"] >= 2 for r in rows)
    assert any(r["cross_category"] for r in rows), \
        "every pair sits inside one branch, so nothing was learned"

    # Asking for a stronger overlap returns fewer rows, never more.
    assert len(run("cross-sell-candidates", min_campaigns=3)) <= len(rows)


def test_weakest_media_coverage_is_derived_from_real_imagery():
    """Nothing in this view is invented, which is why it is the one to open."""
    rows = run("weakest-media-coverage")
    assert rows
    assert all(0 <= r["coverage_pct"] < 100 for r in rows)
    assert rows == sorted(rows, key=lambda r: (r["coverage_pct"], r["category"]))
    assert all(r["missing_media"] <= r["variants"] for r in rows)

    # Level is the taxonomy depth the rollup groups at.
    deeper = run("weakest-media-coverage", level=3)
    assert all(r["category"].count(".") >= 1 for r in deeper)


def test_supplier_concentration_finds_the_single_source_categories():
    """Invisible product by product, obvious once the category is the unit."""
    rows = run("supplier-concentration")
    assert rows
    assert all(r["share_pct"] >= 60 for r in rows)
    assert any(r["share_pct"] == 100.0 for r in rows), \
        "no category depends on one supplier, so the risk view has no risk"
    assert all(r["products"] <= r["of_products"] for r in rows)

    # A stricter threshold cannot return more.
    assert len(run("supplier-concentration", share_pct=90)) <= len(rows)


def test_every_insight_answers_and_answers_within_its_cap():
    """All six, in one place, so a broken one cannot hide behind five good ones."""
    for insight_id, spec in insights.CATALOGUE.items():
        rows = run(insight_id)
        assert rows, f"{insight_id} returned nothing"
        assert len(rows) <= insights.MAX_ROWS
        for row in rows:
            assert set(row) == set(spec.columns), \
                f"{insight_id} row keys do not match its declared columns"


# ---------------------------------------------------------------------------
# Traversal


def test_a_neighbourhood_grows_with_depth_and_stops_at_the_cap():
    """Depth is the control that matters, and the cap is what keeps it usable."""
    root = "Variant:VAR-01B"
    one = memory.neighbourhood(root, depth=1, limit=500)
    two = memory.neighbourhood(root, depth=2, limit=500)
    assert 1 < len(one["nodes"]) < len(two["nodes"])

    capped = memory.neighbourhood(root, depth=3, limit=25)
    assert len(capped["nodes"]) <= 25
    assert capped["truncated"] is True
    assert capped["dropped_domains"], "truncated without saying what was dropped"
    assert capped["total_nodes"] > len(capped["nodes"])


def test_a_domain_filter_removes_a_domain_and_its_edges():
    """Turning a chip off must not leave lines going nowhere."""
    root = "Variant:VAR-01B"
    result = memory.neighbourhood(root, depth=2, domains=[GraphDomain.CORE],
                                  limit=500)
    kept = {n.id for n in result["nodes"]}
    assert kept
    for node in result["nodes"]:
        assert node.domain is GraphDomain.CORE or node.id == root
    for edge in result["edges"]:
        assert edge.source in kept and edge.target in kept


def test_expanding_a_node_skips_what_is_already_on_screen():
    """Double-click means "show me more of this", not "start again"."""
    root = "Variant:VAR-01B"
    first = memory.neighbourhood(root, depth=1, limit=500)
    shown = {n.id for n in first["nodes"]}

    product = next(n.id for n in first["nodes"] if n.label.value == "Product")
    more = memory.expand(product, exclude=shown, limit=40)
    assert all(n.id not in shown for n in more["nodes"])


def test_a_path_between_two_products_is_said_in_words():
    """Nine node ids is a result. "Both are stocked at Leeds RDC" is an answer."""
    found = memory.paths("Variant:VAR-01B", "Variant:VAR-03A")
    assert found
    for path in found:
        assert path["length"] == len(path["edges"])
        assert len(path["nodes"]) == path["length"] + 1
        assert path["narrative"]
        assert "None" not in path["narrative"]

    # Shortest first, and the alternates are genuinely different routes.
    assert found == sorted(found, key=lambda p: p["length"])
    assert len({tuple(p["nodes"]) for p in found}) == len(found)


def test_searching_finds_a_product_by_every_name_it_has():
    """A merchant types a SKU, an internal id, or the thing's actual name."""
    for term in ("NAV-AP300-MAX", "VAR-01B", "Northaven"):
        hits = memory.search(term)
        assert hits, term
        assert any("northaven" in h["name"].lower() for h in hits), term

    # And the exact match leads.
    assert memory.search("WH-LEEDS")[0]["name"] == "Leeds RDC"
    assert memory.search("")==[]
