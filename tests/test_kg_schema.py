"""The graph model and the schema that has to back it.

These tests read `sc/kg/schema.cypher` as text and check it against
`sc/kg/model.py`. Nothing here needs Neo4j, a driver, or a database - which is
the point. The model is declared in one place and the schema is written in
another, and the failure mode when they drift is not an exception: it is a
second copy of every warehouse appearing on the second load, or a search index
that answers nothing because the builder and the schema disagree about its
name by one character.

The expensive version of this test is noticing in a demo. The cheap version is
here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("DB_PATH", "data/test_kg_schema.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc.contracts import GraphDomain, GraphNodeLabel, GraphRelType  # noqa: E402
from sc.kg import model  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[1] / "sc" / "kg" / "schema.cypher"


def statements() -> list[str]:
    """The schema as executable statements, with the commentary stripped.

    The loader splits this file the same way, so a statement this helper cannot
    see is a statement that never reaches the database.
    """
    lines = [line for line in SCHEMA.read_text(encoding="utf-8").splitlines()
             if not line.strip().startswith("//")]
    return [s.strip() for s in " ".join(lines).split(";") if s.strip()]


def constrained() -> set[tuple[str, str]]:
    """(label, property) for every uniqueness constraint declared."""
    found = set()
    for statement in statements():
        match = re.search(
            r"CREATE CONSTRAINT .*? FOR \(n:(\w+)\) REQUIRE n\.(\w+) IS UNIQUE",
            statement)
        if match:
            found.add((match.group(1), match.group(2)))
    return found


def range_indexed() -> set[tuple[str, str]]:
    """(label, property) for every property named by a range index."""
    found = set()
    for statement in statements():
        match = re.search(r"CREATE INDEX .*? FOR \(n:(\w+)\) ON \(([^)]+)\)",
                          statement)
        if match:
            for prop in match.group(2).split(","):
                found.add((match.group(1), prop.strip().removeprefix("n.")))
    return found


# ---------------------------------------------------------------------------
# The model is complete


def test_every_label_belongs_to_a_domain():
    """The UI colours nodes by domain and filters by it.

    A label with no domain would render in whichever colour the lookup happened
    to default to and be hidden by the wrong chip - a wrong picture rather than
    a missing one, which is the harder kind to notice.
    """
    missing = [label for label in GraphNodeLabel if label not in model.DOMAIN_OF]
    assert missing == [], f"no domain declared for {missing}"


def test_every_domain_has_at_least_one_label():
    """A legend entry with nothing behind it is a chip that filters to nothing.

    Seven domains were promised; a domain that survives as an enum member after
    its labels are gone is a control that does nothing and says nothing.
    """
    covered = set(model.DOMAIN_OF.values())
    assert covered == set(GraphDomain), f"no labels in {set(GraphDomain) - covered}"


def test_every_label_has_a_business_key():
    """MERGE is the loader, and it MERGEs on this key.

    A label without one cannot be loaded idempotently at all - there is nothing
    to match on, so every run inserts.
    """
    missing = [label for label in GraphNodeLabel
               if label not in model.BUSINESS_KEY]
    assert missing == [], f"no business key for {missing}"


def test_every_relationship_declares_both_of_its_ends():
    """The endpoints are what let a later test reject an impossible edge.

    Without them a projection bug that joined a campaign to a warehouse would
    load cleanly and be found by somebody reading the picture.
    """
    missing = [rel for rel in GraphRelType if rel not in model.ENDPOINTS]
    assert missing == [], f"no endpoints for {missing}"

    for rel, (sources, targets) in model.ENDPOINTS.items():
        assert sources and targets, f"{rel} has an empty end"
        for label in (*sources, *targets):
            assert label in model.DOMAIN_OF, f"{rel} names unmapped {label}"


def test_an_edge_takes_the_domain_of_what_it_reaches():
    """Turning a domain off has to remove the edges into it as well.

    A Warehouse chip that hid the depots and left their edges dangling would
    draw lines to nothing, so `edge_domain` reads the far end and this pins it.
    """
    assert model.edge_domain(GraphRelType.AT_WAREHOUSE) is GraphDomain.WAREHOUSE
    assert model.edge_domain(GraphRelType.CERTIFIED_BY) is GraphDomain.COMPLIANCE
    assert model.edge_domain(GraphRelType.HAS_VARIANT) is GraphDomain.CORE


# ---------------------------------------------------------------------------
# The schema backs the model


def test_the_schema_is_idempotent_statement_by_statement():
    """It is applied before every load, including loads onto a loaded graph.

    One statement without IF NOT EXISTS turns the second ingest into a failure
    at the point where nothing has been written yet and everything looks fine.
    """
    for statement in statements():
        assert "IF NOT EXISTS" in statement, f"not idempotent: {statement[:70]}"


def test_every_key_the_model_names_has_a_constraint_behind_it():
    """This is the test that keeps MERGE honest.

    An unconstrained key does not error. It inserts a second copy of every node
    of that label on the second load, and the graph doubles quietly while every
    count still looks plausible.
    """
    declared = constrained()
    for label in GraphNodeLabel:
        for key in model.keys_of(label):
            assert (label.value, key) in declared, \
                f"{label.value}.{key} is a key with no uniqueness constraint"


def test_the_alternate_key_is_constrained_and_products_have_none():
    """A SKU lookup must return one variant, and a product has no SKU at all.

    Both halves matter: a constraint on Product.sku would be a constraint on a
    property that is never written, which reads as though products have SKUs.
    """
    assert ("Variant", "sku") in constrained()
    assert ("Product", "sku") not in constrained()


def test_no_range_index_repeats_a_constraint():
    """A uniqueness constraint already creates its backing index.

    A second index on the same property is maintained on every write and read
    by nothing.
    """
    overlap = constrained() & range_indexed()
    assert overlap == set(), f"redundant index on constrained {sorted(overlap)}"


def test_the_search_index_is_named_the_same_in_both_places():
    """The builder queries it by name and this statement creates it by name.

    Disagreeing by one character is a runtime error on an otherwise healthy
    graph, and the query returns nothing rather than failing loudly.
    """
    fulltext = [s for s in statements() if "FULLTEXT INDEX" in s]
    assert len(fulltext) == 1, "expected exactly one full-text index"
    assert model.SEARCH_INDEX in fulltext[0]


def test_the_search_index_covers_exactly_the_searchable_labels():
    """SEARCHABLE is what the type-ahead offers; the index is what it can find.

    A label in one and not the other is a search that silently omits a kind of
    thing, which a reader experiences as "the graph does not know about that".
    """
    fulltext = next(s for s in statements() if "FULLTEXT INDEX" in s)
    labels = set(re.search(r"FOR \(n:([\w|]+)\)", fulltext).group(1).split("|"))
    assert labels == {label.value for label in model.SEARCHABLE}

    properties = set(re.search(r"ON EACH \[([^\]]+)\]", fulltext).group(1)
                     .replace("n.", "").replace(" ", "").split(","))
    assert properties == set(model.SEARCH_PROPERTIES)


def test_every_searchable_label_can_be_found_by_its_own_key():
    """Searching for a warehouse by its code has to reach the warehouse.

    The full-text index covers a fixed property list, so a searchable label
    whose business key is not in that list is one nobody can look up by the
    only name they know it by.
    """
    for label in model.SEARCHABLE:
        keys = set(model.keys_of(label))
        assert keys & set(model.SEARCH_PROPERTIES), \
            f"{label.value} is searchable but none of {keys} is indexed"


def test_the_depth_bound_is_small_and_stated():
    """Depth cannot be a parameter, so it has to be a closed set.

    Cypher has no syntax for a parameterised variable-length bound, which means
    a depth from a request would be pasted into the pattern. Three is the whole
    range, and it is written here so the builder can refuse anything else.
    """
    assert model.MAX_DEPTH == 3
    assert model.DEFAULT_MAX_NODES == 200


def test_the_synthetic_labels_are_the_ones_with_no_source_data():
    """The dashed stroke and the legend's caveat are driven by this set.

    Four domains are generated from the seed, and marking one of their labels
    as real would put an invented revenue figure on the screen with nothing to
    say that it was invented - beside a genuine regulatory finding.
    """
    generated = {model.DOMAIN_OF[label] for label in model.SYNTHETIC}
    assert GraphDomain.WAREHOUSE in generated
    assert GraphDomain.MARKETING in generated
    assert GraphDomain.COMPLIANCE in generated

    # The spine and the things the retailer actually holds are not invented.
    for label in (GraphNodeLabel.PRODUCT, GraphNodeLabel.VARIANT,
                  GraphNodeLabel.SUPPLIER, GraphNodeLabel.CATEGORY,
                  GraphNodeLabel.MEDIA_ASSET, GraphNodeLabel.CHANNEL,
                  GraphNodeLabel.LISTING):
        assert not model.is_synthetic(label), f"{label.value} is real data"
