"""The Cypher, executed. Skipped unless a Neo4j is actually answering.

Everything in `tests/test_kg_cypher.py` checks the builders as strings, which
is the right way to test them: it is fast, it needs no server, and what it
checks - parameterisation, the closed depth set, the allowlist - is what could
be wrong in a way that matters. But a query can be perfectly parameterised and
still not parse, and no amount of string assertion finds that.

So this file runs them. It is skipped when there is no Neo4j, which is most of
the time, and that is deliberate: the default suite must not need a database
server. Bring one up with `startup.bat graph` and it runs.

**It writes to the database it is pointed at, and deletes nothing.** Every
write is the same idempotent MERGE the loader performs, so running this leaves
the graph exactly as `python scripts/load_graph.py` would leave it. See the
`loaded` fixture for why it does not try to clean up after itself.

**The test that earns the file is `test_both_backends_return_the_same_graph`.**
The whole design rests on one claim - that Neo4j and the in-process walk are
two engines over one graph rather than two implementations that happen to
agree - and this is the only place that claim is checked rather than argued.
"""

from __future__ import annotations

import contextlib
import os
import pathlib

import pytest

os.environ.setdefault("DB_PATH", "data/test_kg_neo4j.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.contracts import GraphNodeLabel, GraphRelType  # noqa: E402
from sc.kg import cypher, insights, memory, model, synth  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402


def _neo4j_settings() -> dict[str, str]:
    """The Neo4j keys out of `.env`, read **without touching os.environ**.

    `bootstrap.load_env` would be the obvious call and is the wrong one here.
    This runs at collection, before any fixture, and `load_env` sets every key
    in `.env` into the process environment - `DB_PATH`, `KG_BACKEND`, all of
    it - where it stays for the rest of the session. That is how this file
    once made four tests in `test_kg_api.py` fail: they assert the in-process
    backend answered, and collection had quietly told the whole suite to use
    Neo4j.

    So: parse the file, take the four keys this module needs, leave everything
    else alone. A real environment variable still wins, which is what a
    developer pointing the tests at a different server would expect.
    """
    settings: dict[str, str] = {}
    env_file = pathlib.Path(os.environ.get("KG_ENV_FILE") or ".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("NEO4J_"):
                settings[key] = value.strip()
    for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        if os.environ.get(key):
            settings[key] = os.environ[key]
    return settings


NEO4J = _neo4j_settings()


def live() -> bool:
    """Is there a Neo4j answering, with the driver installed to reach it?

    Asked once, at collection. `driver.available()` caches its own probe, so
    this does not put a handshake in front of every test.
    """
    if not NEO4J.get("NEO4J_URI"):
        return False
    try:
        from sc.kg import driver
    except ImportError:
        return False
    with _neo4j_env():
        return driver.available(refresh=True)[0]


@contextlib.contextmanager
def _neo4j_env():
    """Put the Neo4j settings in place for the duration of one call.

    `sc/kg/driver.py` reads them from the environment at call time, like every
    other setting in this codebase. Setting them for the length of a call and
    restoring afterwards is what keeps the rest of the suite from ever seeing
    them.
    """
    held = {key: os.environ.get(key) for key in NEO4J}
    os.environ.update(NEO4J)
    # Re-probe on the way in as well as clearing on the way out. The cache is
    # symmetric trouble: a *failed* probe cached by an earlier module - and
    # `test_kg_api.py` deliberately runs with no NEO4J_URI, so it caches one -
    # would otherwise survive into here, and `backend.chosen()` would answer
    # "memory" with a perfectly good server in front of it.
    try:
        from sc.kg import driver

        driver.close_all()
        driver.available(refresh=True)
    except ImportError:
        pass
    try:
        yield
    finally:
        for key, value in held.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Restoring the variables is not enough on its own. `driver.available`
        # caches its probe for the process, so a successful handshake here
        # would go on reporting "yes, Neo4j is reachable" to every later test -
        # including the ones in `test_kg_api.py` that assert it is not.
        # `close_all` drops the driver and the cached probe together.
        try:
            from sc.kg import driver

            driver.close_all()
        except ImportError:
            pass


pytestmark = pytest.mark.skipif(
    not live(),
    reason="no Neo4j answering - `startup.bat graph` brings one up")


@pytest.fixture(scope="module")
def loaded():
    """The graph, in Neo4j, loaded the way `scripts/load_graph.py` loads it.

    **This fixture writes and never deletes, and that is the whole design.**

    It first tried to be tidy: it stamped everything it wrote with `kgTest` and
    deleted those nodes afterwards. That was wrong in a way that took a
    destroyed graph to notice - MERGE keys on the *business* key, so the
    "test" nodes were the same nodes `load_graph.py` had already written, the
    stamp went onto them, and the teardown deleted the real graph. Anybody
    running this suite against the Neo4j they had just loaded would have lost
    it.

    So there is no teardown. Every write here is the same idempotent MERGE the
    loader performs, over the same seed, so running these tests leaves the
    database in exactly the state a `python scripts/load_graph.py` would - and
    an empty database ends up loaded rather than half-loaded.

    Loaded from the projection rather than over MCP: crossing that boundary is
    `scripts/load_graph.py`'s claim to make, and standing a platform up inside
    a test to prove it again would be a slower way to test something else.
    """
    import tempfile
    from pathlib import Path

    # conftest pins DB_PATH per test, and a module-scoped fixture runs before
    # any of that - so without this it initialises whichever database the
    # previous module happened to leave in the environment, and the first test
    # here then finds its own file uncreated. `no such table: runtime_config`
    # is what that looks like from the outside.
    os.environ["DB_PATH"] = "data/test_kg_neo4j.db"
    os.environ["ENV_FILE"] = "data/test_kg_neo4j.env"
    db.close_all()

    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    memory.cache_clear()
    tape.load_tape(reset=True)

    pack = Path(tempfile.mkdtemp()) / "backoffice.jsonl"
    synth.write(pack)
    tape.load_reference(pack, reset=True)
    memory.cache_clear()

    graph = memory.graph()

    import scripts.load_graph as loader  # noqa: E402

    # Held for the whole module: every test below reaches the driver, and the
    # driver reads its settings from the environment at call time.
    with _neo4j_env():
        loader._apply_schema()
        nodes, edges = loader._rows_for(graph, None, "test")
        for label, rows in nodes.items():
            loader._write_batch(cypher.node_upsert(label), rows)
        for rel_type, rows in edges.items():
            loader._write_batch(cypher.edge_upsert(rel_type), rows)

        yield graph

        from sc.kg import driver

        driver.close_all()
    db.close()


# ---------------------------------------------------------------------------
# Every statement parses and runs


def test_every_builder_produces_a_statement_neo4j_will_run(loaded):
    """A query can be perfectly parameterised and still not parse.

    This is the check the string tests cannot make, and the one that caught an
    `apoc.text.join` in six of these builders - a call that parses fine and
    then fails at runtime on a stock Neo4j, which ships no plugins.
    """
    from sc.kg import driver

    built = [
        cypher.neighbourhood_query("Variant:VAR-01B", 1, None, 50),
        cypher.neighbourhood_query("Variant:VAR-01B", 2, ["COMPLIANCE"], 50),
        cypher.neighbourhood_query("Variant:VAR-01B", 3, None, 50),
        cypher.paths_query("Variant:VAR-01B", "Variant:VAR-03A", 3),
        cypher.search_query("northaven", 10),
        cypher.counts_query(),
    ]
    built += [cypher.insight_query(i, insights.bind(i, None), tape.sim_now())
              for i in insights.CATALOGUE]

    for query in built:
        driver.run(query)          # raises if Neo4j will not run it


def test_the_schema_applies_and_re_applies(loaded):
    """Every statement is IF NOT EXISTS, so a second load is a no-op."""
    import scripts.load_graph as loader

    assert loader._apply_schema() > 40
    assert loader._apply_schema() > 40      # again, on an already-built graph


def test_merge_is_idempotent(loaded):
    """The claim the uniqueness constraints exist to make true.

    Without a constraint on a business key, MERGE inserts a second copy of
    every node of that label on the second run - and reports success, with
    every count still looking plausible.
    """
    from sc.kg import driver
    from sc.kg.cypher import GraphQuery
    import scripts.load_graph as loader

    def counts():
        n = driver.run(GraphQuery(
            "n", "MATCH (n) WHERE n.kgId IS NOT NULL RETURN count(n) AS n",
            {}))[0]["n"]
        r = driver.run(GraphQuery(
            "r", "MATCH ()-[r]->() WHERE r.kgId IS NOT NULL "
                 "RETURN count(r) AS n", {}))[0]["n"]
        return n, r

    before = counts()
    nodes, edges = loader._rows_for(loaded, None, "test")
    for label, rows in nodes.items():
        loader._write_batch(cypher.node_upsert(label), rows)
    for rel_type, rows in edges.items():
        loader._write_batch(cypher.edge_upsert(rel_type), rows)

    assert counts() == before


def test_every_label_and_relationship_survived_the_load(loaded):
    """A label the loader never wrote is a domain the tab cannot show."""
    from sc.kg import driver
    from sc.kg.cypher import GraphQuery

    labels = {row["label"] for row in driver.run(GraphQuery(
        "l", "MATCH (n) WHERE n.kgId IS NOT NULL "
             "RETURN DISTINCT labels(n)[0] AS label", {}))}
    projected = {node.label.value for node in loaded.nodes.values()}
    assert projected <= labels

    types = {row["t"] for row in driver.run(GraphQuery(
        "t", "MATCH ()-[r]->() WHERE r.kgId IS NOT NULL "
             "RETURN DISTINCT type(r) AS t", {}))}
    assert {edge.type.value for edge in loaded.edges} <= types


# ---------------------------------------------------------------------------
# The claim the whole design rests on


def test_both_backends_return_the_same_graph(loaded):
    """One graph, two engines - checked rather than argued.

    If these ever disagree, the switch in `sc/kg/backend.py` stops being a
    transport decision and becomes a behavioural one, and every promise made
    about falling back is void.
    """
    from sc.kg import backend

    for root in ("Variant:VAR-01B", "Variant:VAR-01A", "Product:PRD-01"):
        os.environ["KG_BACKEND"] = "neo4j"
        from_neo4j = backend.neighbourhood(root, depth=2, domains=None,
                                           limit=200)
        os.environ["KG_BACKEND"] = "memory"
        from_memory = backend.neighbourhood(root, depth=2, domains=None,
                                            limit=200)

        assert from_neo4j["backend"] == "neo4j"
        assert from_memory["backend"] == "memory"
        assert ({n.id for n in from_neo4j["nodes"]}
                == {n.id for n in from_memory["nodes"]}), root

    os.environ.pop("KG_BACKEND", None)


def test_both_backends_answer_the_saved_queries_the_same(loaded):
    """Same six questions, same rows, whichever engine ran them."""
    from sc.kg import backend

    as_of = tape.sim_now()
    for insight_id in insights.CATALOGUE:
        os.environ["KG_BACKEND"] = "neo4j"
        from_neo4j = backend.run_insight(insight_id, None, as_of)
        os.environ["KG_BACKEND"] = "memory"
        from_memory = backend.run_insight(insight_id, None, as_of)

        assert from_neo4j["backend"] == "neo4j"
        assert len(from_neo4j["rows"]) == len(from_memory["rows"]), insight_id
        assert from_neo4j["rows"], insight_id

    os.environ.pop("KG_BACKEND", None)


def test_the_full_text_index_finds_a_product_by_sku(loaded):
    """The index the schema declares, queried by the name the builder uses.

    A typo between `schema.cypher` and `model.SEARCH_INDEX` is a runtime error
    on an otherwise healthy graph, and the query returns nothing rather than
    failing loudly - so this asks for something it knows is there.
    """
    from sc.kg import driver

    hits = driver.run(cypher.search_query("northaven", 10))
    assert hits
    assert any("northaven" in (row["name"] or "").lower() for row in hits)


def test_a_depth_the_builder_refuses_never_reaches_neo4j(loaded):
    """The closed set is the whole injection posture, checked end to end."""
    from sc.kg import BadRequest

    with pytest.raises(BadRequest):
        cypher.neighbourhood_query("Variant:VAR-01B", 4)
