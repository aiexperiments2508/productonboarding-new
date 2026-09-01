"""The Cypher builders, and the one place this feature could be injected.

No database anywhere in this file. The builders are pure and return a query
string with its parameters, so what can be wrong - a value spliced into a
pattern, a parameter named in the string and never bound, a closed set that
turned out not to be closed - is exactly what is checked here, at the speed of
a string comparison.

The important test is `test_a_depth_outside_the_closed_set_is_refused`. Cypher
has no syntax for a parameterised variable-length bound, so a depth from a
request has to be written into the pattern. Every other value in this feature
is bound; that one is a lookup, and if the lookup ever stops raising, this
becomes an endpoint that runs caller-supplied Cypher.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import pytest

os.environ.setdefault("DB_PATH", "data/test_kg_cypher.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc.contracts import GraphNodeLabel, GraphRelType  # noqa: E402
from sc.kg import BadRequest, cypher, insights, model  # noqa: E402

AS_OF = datetime(2026, 7, 1)

#: A value that is valid Cypher and would be catastrophic if it were ever
#: concatenated into a statement. Used as a domain, a depth and a node id.
HOSTILE = "'; MATCH (n) DETACH DELETE n //"


def every_query() -> list:
    """One of everything the feature can build."""
    built = [
        cypher.neighbourhood_query("Variant:VAR-01B", 2, ["COMPLIANCE"], 200),
        cypher.neighbourhood_query("Variant:VAR-01B", 1),
        cypher.paths_query("Variant:VAR-01B", "Variant:VAR-03A"),
        cypher.search_query("northaven"),
        cypher.counts_query(),
    ]
    built += [cypher.insight_query(i, insights.bind(i, None), AS_OF)
              for i in insights.CATALOGUE]
    built += [cypher.node_upsert(label) for label in GraphNodeLabel]
    built += [cypher.edge_upsert(rel.value) for rel in GraphRelType]
    built += [cypher.prune_query(label) for label in GraphNodeLabel]
    return built


# ---------------------------------------------------------------------------
# Every value that can be bound, is


def test_every_placeholder_is_bound_and_every_parameter_is_used():
    """A named parameter with nothing behind it is a runtime error.

    And a bound parameter the query never mentions is worse: it is usually the
    remains of a value that used to be interpolated, and it says the statement
    is no longer taking the thing the caller supplied.
    """
    for query in every_query():
        assert query.placeholders() == set(query.params), (
            f"{query.name}: placeholders {sorted(query.placeholders())} "
            f"!= params {sorted(query.params)}")


def test_no_caller_value_is_written_into_a_statement():
    """The values a request can carry never appear in the string.

    Node ids, search terms, thresholds and dates all travel as parameters. If
    any of them turns up as a literal, something has started building Cypher by
    concatenation and the next value along will not be so harmless.
    """
    node_id = "Variant:VAR-01B"
    for query in (cypher.neighbourhood_query(node_id, 3, ["SALES"], 75),
                  cypher.paths_query(node_id, "Product:PRD-01"),
                  cypher.search_query("northaven ap300")):
        assert node_id not in query.cypher, query.name
        assert "northaven" not in query.cypher.lower(), query.name
        assert "75" not in query.cypher, query.name


def test_a_depth_outside_the_closed_set_is_refused():
    """The one bound Cypher will not take, so the one that must be a lookup.

    Refused rather than clamped. A caller asking for six hops has misunderstood
    the endpoint, and silently giving them three would hide that while looking
    like it worked.
    """
    for depth in (1, 2, 3):
        assert f"*1..{depth}" in cypher.neighbourhood_query("x", depth).cypher

    for bad in (0, 4, 99, -1, "2; MATCH (n) DETACH DELETE n"):
        with pytest.raises(BadRequest):
            cypher.neighbourhood_query("x", bad)

    assert set(cypher._DEPTH_PATTERN) == {1, 2, 3}
    assert max(cypher._DEPTH_PATTERN) == model.MAX_DEPTH


def test_a_domain_filter_carrying_cypher_is_refused():
    """Domains are enum members or they are nothing.

    The filter travels as a bound list of label names, so a hostile string
    could only ever match no label - but refusing is better than filtering to
    an empty graph, because the caller then knows why the screen is blank.
    """
    with pytest.raises(BadRequest):
        cypher.neighbourhood_query("x", 2, [HOSTILE])
    with pytest.raises(BadRequest):
        cypher.neighbourhood_query("x", 2, ["COMPLIANCE", "not-a-domain"])

    query = cypher.neighbourhood_query("x", 2, ["compliance", "SALES"])
    assert HOSTILE not in query.cypher
    assert set(query.params["labels"]) < {label.value
                                          for label in GraphNodeLabel}


def test_a_hostile_node_id_stays_a_parameter():
    """Even a node id that is valid Cypher only ever gets bound."""
    query = cypher.neighbourhood_query(HOSTILE, 2)
    assert "DETACH DELETE" not in query.cypher
    assert query.params["root"] == HOSTILE


# ---------------------------------------------------------------------------
# The allowlist


def test_an_unknown_insight_never_reaches_a_builder():
    """`bind` refuses first, so nothing downstream has to be careful.

    Two gates on purpose: `bind` checks the id against the catalogue and
    `insight_query` checks it against the builder table. Either alone would be
    enough today, and neither alone stays enough after somebody adds a spec and
    forgets its query.
    """
    for unknown in ("", "drop-everything", "certifications_expiring", HOSTILE):
        with pytest.raises(BadRequest):
            insights.bind(unknown, None)
        with pytest.raises(BadRequest):
            cypher.insight_query(unknown, {}, AS_OF)


def test_every_insight_in_the_catalogue_has_both_implementations():
    """A spec the UI can offer and nothing can answer is a broken button."""
    assert set(insights.CATALOGUE) == set(insights.RUNNERS)
    assert set(insights.CATALOGUE) == set(cypher._INSIGHT_BUILDERS)


def test_an_out_of_range_parameter_is_refused_not_clamped():
    """A caller asking for a thousand days has misunderstood the question.

    Clamping would answer a question they did not ask and report it as though
    they had.
    """
    with pytest.raises(BadRequest):
        insights.bind("certifications-expiring", {"within_days": 4000})
    with pytest.raises(BadRequest):
        insights.bind("certifications-expiring", {"within_days": 0})
    with pytest.raises(BadRequest):
        insights.bind("certifications-expiring", {"within_days": "ninety"})
    with pytest.raises(BadRequest):
        insights.bind("certifications-expiring", {"unknown_knob": 1})

    assert insights.bind("certifications-expiring", None) == {"within_days": 90}
    assert insights.bind(
        "certifications-expiring", {"within_days": 30}) == {"within_days": 30}


# ---------------------------------------------------------------------------
# The statements are runnable against a plain Neo4j


def test_no_builder_needs_a_plugin():
    """A stock Neo4j ships no plugins, and this repository ships one as a zip.

    An APOC call would turn one line of setup into a support question the
    README cannot answer, and the failure would arrive as a cryptic
    `Unknown function` in the one place a reader has no context to debug.
    """
    for query in every_query():
        lowered = query.cypher.lower()
        for plugin in ("apoc.", "gds.", "n10s."):
            assert plugin not in lowered, f"{query.name} calls {plugin}"


def test_the_row_cap_is_the_same_in_both_implementations():
    """A Cypher run and an in-process run must answer the same amount.

    Two caps that drifted would make the backend switch visible in the data,
    which is exactly what the dual-backend design promises it is not.
    """
    assert cypher.MAX_ROWS == insights.MAX_ROWS
    for insight_id in insights.CATALOGUE:
        query = cypher.insight_query(
            insight_id, insights.bind(insight_id, None), AS_OF)
        assert query.params.get("limit") == insights.MAX_ROWS


def test_every_saved_query_returns_the_columns_its_spec_declares():
    """The spec is what the UI builds a table header from.

    A column in the spec and not in the RETURN is an empty column; one in the
    RETURN and not the spec is data the reader never sees.
    """
    for insight_id, spec in insights.CATALOGUE.items():
        query = cypher.insight_query(insight_id, insights.bind(insight_id, None),
                                     AS_OF)
        returned = set(re.findall(r"AS (\w+)", query.cypher))
        missing = set(spec.columns) - returned
        assert not missing, f"{insight_id} never returns {sorted(missing)}"


def test_the_loader_only_builds_statements_for_known_labels_and_types():
    """A label or a relationship type cannot be bound, so it is enumerated.

    These are the two places the loader writes an identifier into a statement,
    and both read it out of the enums rather than off a payload.
    """
    for label in GraphNodeLabel:
        query = cypher.node_upsert(label)
        assert f"MERGE (n:{label.value} " in query.cypher
        assert model.BUSINESS_KEY[label] in query.cypher

    for rel in GraphRelType:
        assert f"[r:{rel.value}]" in cypher.edge_upsert(rel.value).cypher

    with pytest.raises(ValueError):
        cypher.edge_upsert("DROP_DATABASE")
    with pytest.raises(ValueError):
        cypher.edge_upsert(HOSTILE)
