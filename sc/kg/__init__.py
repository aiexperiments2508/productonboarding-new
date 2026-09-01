"""The knowledge graph: a second reading of the catalog.

The record answers "what is wrong with this product and who has to fix it".
This answers "what is this product connected to" - its category lineage, the
obligations on it, where it physically sits, what it looks like, what it earns
and who is being told about it, plus the paths between any two of those.

Deliberately ``sc/kg/`` and not ``sc/graph/``. That package is the LangGraph
agent graph and ``GET /api/graph`` is its topology. Two things called "the
graph" in one codebase is how somebody ends up debugging the wrong one.

**This module stays light on purpose.** Python runs a package's ``__init__``
before anything inside it, so an import here is an import every consumer pays -
and one of the consumers is ``sc/kg/model.py``, which a schema test reads
without wanting a database, a Neo4j driver or a background event loop anywhere
near it. The public surface below therefore imports its implementation inside
the function, which is the same discipline the route handlers in ``sc/main.py``
keep and for the same reason.

What is here today is the model and the schema. Ingestion, the backends and the
query surface land next, and this docstring grows a paragraph when they do.
"""

from __future__ import annotations


class BadRequest(ValueError):
    """The caller asked for something the graph will not do.

    Its own class rather than a bare ``ValueError`` so a route can turn it into
    a 400 and let everything else become a 500. The distinction matters here
    more than usual: a depth outside the closed set and a domain name that is
    not a domain are both refusals the caller can act on, and both would
    otherwise be indistinguishable from a bug in the traversal.
    """


def neighbourhood(key: str, *, depth: int = 2, domains: list[str] | None = None,
                  limit: int | None = None) -> dict | None:
    """The subgraph around one product. None when the key names nothing.

    ``key`` is a SKU, a variant id or a product id - see
    ``sc.readiness.search.resolve``. The resolution comes back with the answer
    so the caller never has to guess which of the three it sent.
    """
    from sc.kg import backend, model, project
    from sc.readiness import search

    resolved = search.resolve(key)
    if resolved is None:
        return None

    root = project.node_id(_variant_label(), resolved["entity_id"])
    answer = backend.neighbourhood(
        root, depth=depth, domains=domains,
        limit=limit or model.DEFAULT_MAX_NODES)
    return {"resolved": resolved, "depth": depth,
            "domains": [d.upper() for d in (domains or [])],
            "root": root, **answer}


def expand(node_id: str, *, seen: list[str] | None = None,
           domains: list[str] | None = None, limit: int = 40) -> dict:
    """One node's own neighbours - what a double-click asks for.

    In process only, and deliberately. An expansion is bounded by the node the
    reader clicked rather than by a global budget, so there is nothing here for
    a query planner to improve on and a round trip would only add latency to a
    gesture that has to feel immediate.
    """
    from sc.kg import backend, memory

    answer = memory.expand(node_id, exclude=set(seen or []),
                           domains=backend._domains(domains), limit=limit)
    return {**answer, "backend": "memory", "route": "sqlite"}


def paths(key: str, target: str) -> dict | None:
    """Shortest routes between two products. None when either key is unknown."""
    from sc.kg import backend, project
    from sc.readiness import search

    left, right = search.resolve(key), search.resolve(target)
    if left is None or right is None:
        return None

    label = _variant_label()
    answer = backend.paths(project.node_id(label, left["entity_id"]),
                           project.node_id(label, right["entity_id"]))
    return {"source": left, "target": right, **answer}


def search_nodes(query: str, *, limit: int = 20) -> dict:
    """Type-ahead across the labels a merchant names out loud."""
    from sc.kg import backend

    return {"query": query, **backend.search(query, limit=limit)}


def catalogue() -> list[dict]:
    """The saved queries, as the tab renders its buttons from."""
    from sc.kg import insights

    return [spec.model_dump(mode="json")
            for spec in insights.CATALOGUE.values()]


def run_insight(insight_id: str, params: dict | None = None) -> dict:
    """Run one saved query, as of the replay clock.

    ``as_of`` comes from ``tape.sim_now`` and never from the wall clock. Every
    other as-of read in this platform works that way, and "expiring within
    ninety days" measured against real time would answer a different question
    from the one the rest of the screen is answering.
    """
    from sc.kg import backend, insights
    from sc.replay import tape

    as_of = tape.sim_now()
    spec = insights.CATALOGUE.get(insight_id)
    if spec is None:
        raise BadRequest(
            f"unknown insight {insight_id!r} - expected one of "
            f"{', '.join(sorted(insights.CATALOGUE))}")

    answer = backend.run_insight(insight_id, params, as_of)
    return {"id": spec.id, "title": spec.title, "columns": spec.columns,
            "as_of": as_of.isoformat(), **answer}


def status() -> dict:
    """Which backend is answering, what it holds, and how it was built."""
    from sc.kg import backend

    return backend.status()


def _variant_label():
    from sc.contracts import GraphNodeLabel

    return GraphNodeLabel.VARIANT
