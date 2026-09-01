"""The knowledge-graph routes.

Six endpoints, and the thing worth testing about most of them is what they
refuse. A traversal depth outside the closed set, a domain name that is really
a Cypher fragment, an insight id nobody declared - each has to come back as a
400 the caller can read, not as a 500, and certainly not as a query.

The last test in this file is the one that keeps the rest honest: it reads the
route handlers' own source and asserts none of them contains Cypher. The house
rule is that a route is a thin layer over the domain module, and the moment a
`MATCH` appears in `sc/main.py` there are two places that know how to ask the
graph a question.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_kg_api.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

# These tests are about the routes, not about which engine answers them, so the
# engine is pinned rather than left to whatever this machine has configured.
# Without it a developer with a Neo4j running gets four failures that say
# nothing about the routes - `tests/test_kg_neo4j.py` is where the other engine
# is exercised.
os.environ["KG_BACKEND"] = "memory"

from sc import db  # noqa: E402
from sc.kg import memory, synth  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

PURIFIER = "VAR-01B"
PURIFIER_SKU = "NAV-AP300-MAX"
HOSTILE = "'; MATCH (n) DETACH DELETE n //"

#: The same thing without the trailing comment slashes. A path segment cannot
#: carry a slash - encoded or not, the router decodes before matching, so the
#: request never reaches the handler at all - and a test that sent one would be
#: asserting on Starlette's routing rather than on this endpoint.
HOSTILE_KEY = "'; MATCH (n) DETACH DELETE n"


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


def client():
    from fastapi.testclient import TestClient

    from sc.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# The neighbourhood


def test_a_product_can_be_asked_for_by_every_name_it_has():
    """A SKU, a variant id and a product id all reach the same graph.

    All three get typed by somebody - a merchant reads the SKU off a purchase
    order, the product screen holds the variant id, a report names the product
    - so the route takes any of them and says which it turned out to be.
    """
    api = client()
    for key in (PURIFIER, PURIFIER_SKU, PURIFIER_SKU.lower()):
        body = api.get(f"/api/products/{key}/graph").json()
        assert body["resolved"]["entity_id"] == PURIFIER, key
        assert body["resolved"]["key"] == key
        assert body["nodes"]

    # A product widens to its base variant rather than 404ing.
    body = api.get("/api/products/PRD-01/graph").json()
    assert body["resolved"]["product_id"] == "PRD-01"
    assert body["resolved"]["entity_id"].startswith("VAR-01")


def test_an_unknown_key_is_a_404_and_not_an_empty_graph():
    """A typo'd SKU and a product with no connections look identical on screen.

    So they must not look identical in the response. One is a mistake the
    reader can fix; the other is a finding.
    """
    assert client().get("/api/products/NOT-A-SKU/graph").status_code == 404

    # Cypher in the key resolves to no variant, so it is a 404 like any other
    # name nothing answers to. See HOSTILE_KEY on why this one has no slashes.
    import urllib.parse

    encoded = urllib.parse.quote(HOSTILE_KEY, safe="")
    response = client().get(f"/api/products/{encoded}/graph")
    assert response.status_code == 404
    assert response.json()["detail"] == "no such product"


def test_depth_and_the_node_cap_both_bound_the_answer():
    """Two controls, and the response says when either one bit."""
    api = client()
    shallow = api.get(f"/api/products/{PURIFIER}/graph",
                      params={"depth": 1, "limit": 500}).json()
    deeper = api.get(f"/api/products/{PURIFIER}/graph",
                     params={"depth": 2, "limit": 500}).json()
    assert len(shallow["nodes"]) < len(deeper["nodes"])

    capped = api.get(f"/api/products/{PURIFIER}/graph",
                     params={"depth": 3, "limit": 30}).json()
    assert len(capped["nodes"]) <= 30
    assert capped["truncated"] is True
    assert capped["total_nodes"] > len(capped["nodes"])
    assert capped["dropped_domains"], "truncated without saying what was dropped"


def test_a_depth_outside_the_closed_set_is_a_400():
    """Not a 500, and not silently clamped.

    Depth is the one value Cypher will not bind, so it comes from a lookup
    table. A caller who asks for six has misunderstood the endpoint, and
    quietly giving them three would hide that.
    """
    api = client()
    for depth in (0, 4, 99, -1):
        response = api.get(f"/api/products/{PURIFIER}/graph",
                           params={"depth": depth})
        assert response.status_code == 400, depth
        assert "depth" in response.json()["detail"]

    for depth in (1, 2, 3):
        assert api.get(f"/api/products/{PURIFIER}/graph",
                       params={"depth": depth}).status_code == 200


def test_a_domain_filter_that_is_really_cypher_is_a_400():
    """The filter is an enum or it is a refusal.

    It travels as a bound list of label names, so this string could only ever
    match no label - but a blank screen with no explanation is a worse answer
    than a refusal that names the problem.
    """
    api = client()
    response = api.get(f"/api/products/{PURIFIER}/graph",
                       params={"domains": HOSTILE})
    assert response.status_code == 400
    assert "domain" in response.json()["detail"]

    ok = api.get(f"/api/products/{PURIFIER}/graph",
                 params={"domains": "COMPLIANCE,WAREHOUSE", "depth": 2})
    assert ok.status_code == 200
    assert {n["domain"] for n in ok.json()["nodes"]} <= {
        "COMPLIANCE", "WAREHOUSE", "CORE"}


def test_the_response_says_which_backend_answered():
    """A report, not a setting.

    With no Neo4j reachable this is the in-process walk, reading SQLite. A
    reader surprised by an answer can tell what produced it without having to
    reason about environment variables.
    """
    body = client().get(f"/api/products/{PURIFIER}/graph").json()
    assert body["backend"] == "memory"
    assert body["route"] == "sqlite"


# ---------------------------------------------------------------------------
# Paths, search, expand


def test_a_path_between_two_products_comes_back_said_in_words():
    api = client()
    body = api.get(f"/api/products/{PURIFIER}/graph/paths",
                   params={"target": "VAR-03A"}).json()
    assert body["source"]["entity_id"] == PURIFIER
    assert body["target"]["entity_id"] == "VAR-03A"
    assert body["paths"]
    for path in body["paths"]:
        assert path["narrative"]
        assert len(path["nodes"]) == path["length"] + 1

    assert api.get(f"/api/products/{PURIFIER}/graph/paths",
                   params={"target": "NOT-A-SKU"}).status_code == 404


def test_search_finds_a_product_by_sku_and_by_name():
    api = client()
    for term in (PURIFIER_SKU, "northaven", "WH-LEEDS"):
        body = api.get("/api/kg/search", params={"q": term}).json()
        assert body["hits"], term
        assert body["query"] == term

    assert client().get("/api/kg/search", params={"q": ""}).json()["hits"] == []


def test_expanding_a_node_skips_what_the_caller_already_has():
    """Double-click means "more of this", so the caller says what is on screen."""
    api = client()
    first = api.get("/api/kg/expand/Product:PRD-01").json()
    assert first["nodes"]

    shown = ",".join(n["id"] for n in first["nodes"])
    again = api.get("/api/kg/expand/Product:PRD-01",
                    params={"seen": shown}).json()
    assert again["nodes"] == []


# ---------------------------------------------------------------------------
# The saved queries


def test_every_saved_query_runs_and_returns_its_declared_columns():
    """Six buttons, six answers. A view that returns nothing reads as "fine"."""
    api = client()
    specs = api.get("/api/kg/insights").json()["insights"]
    assert len(specs) == 6

    for spec in specs:
        assert spec["question"] and spec["why"], spec["id"]
        body = api.post("/api/kg/query", json={"id": spec["id"]}).json()
        assert body["rows"], f"{spec['id']} returned nothing"
        assert body["columns"] == spec["columns"]
        assert body["as_of"], "an insight with no as-of is not answerable"
        for row in body["rows"]:
            assert set(row) == set(spec["columns"])


def test_the_saved_queries_are_the_only_ones_that_run():
    """There is no endpoint here that executes a statement a caller wrote.

    The id is checked against the catalogue before anything else happens, so
    an unknown one never reaches a driver - which is the whole of the injection
    posture for this feature, along with the closed depth set.
    """
    api = client()
    for identifier in ("drop-everything", HOSTILE, "MATCH (n) DETACH DELETE n"):
        response = api.post("/api/kg/query", json={"id": identifier})
        assert response.status_code == 400, identifier

    assert api.post("/api/kg/query", json={}).status_code == 400
    assert api.post("/api/kg/query",
                    json={"id": "certifications-expiring",
                          "params": {"within_days": 9999}}).status_code == 400


def test_the_as_of_is_the_replay_clock_and_not_the_wall_clock():
    """"Expiring within ninety days" of *when*.

    Every other as-of read in this platform runs on the simulated clock. One
    that read real time would answer a different question from the rest of the
    screen, and would work by coincidence until the coincidence expired.
    """
    body = client().post("/api/kg/query",
                         json={"id": "certifications-expiring"}).json()
    assert body["as_of"].startswith(str(tape.sim_now().date()))
    assert body["as_of"].startswith("2026-")


def test_status_reports_the_backend_and_what_it_holds():
    body = client().get("/api/kg/status").json()
    assert body["backend"] == "memory"
    assert body["available"] is False        # no NEO4J_URI in the suite
    assert body["uri"] is None
    assert body["reference_events"] == 220
    assert body["node_counts"]["Product"] > 100
    assert body["max_depth"] == 3


# ---------------------------------------------------------------------------
# The house rule


def test_the_graph_routes_delegate_and_hold_no_cypher():
    """The same guard `tests/test_product360.py` puts on the product reads.

    A route is a thin layer over the domain module. Cypher in `sc/main.py`
    would mean two places know how to ask the graph a question, and the second
    one is never the one that gets fixed.
    """
    import inspect

    from sc import main

    routes = ("product_graph", "product_graph_paths", "graph_expand",
              "graph_search", "graph_insights", "graph_query", "graph_status")
    for route in routes:
        body = inspect.getsource(getattr(main, route))
        assert "from sc import kg" in body, f"{route} does not delegate"
        for keyword in ("MATCH ", "MERGE ", "RETURN ", "DETACH DELETE"):
            assert keyword not in body, f"{route} contains Cypher: {keyword}"
        # Nor does it decide anything the domain module owns.
        assert "DEFAULT_MAX_NODES" not in body
        assert "_DEPTH_PATTERN" not in body
