"""Which engine answers, and the one rule it must obey.

``KG_BACKEND`` is ``auto`` (the default), ``neo4j`` or ``memory``. The precedent
is ``sc/mcp/client.py``, whose ``USE_MCP`` switch its own docstring calls a
transport decision rather than a behavioural one, and which falls back rather
than fails. The same two claims hold here:

**The answer is the same either way.** Both engines run over the projection
``sc/kg/project.py`` builds - Neo4j over a MERGEd copy of it, the in-process
backend over it directly. They are not two implementations of a graph; they are
one graph with two ways of walking it. That is what makes the switch safe to
flip mid-session, and it is why the projection is a separate pure module rather
than something each backend derives for itself.

**It falls back rather than fails.** ``auto`` uses Neo4j when it answers and
the in-process backend when it does not, and says which it used in every
response. A demo that will not open a tab because a database server nobody
started is not running has failed at the one thing it was for.

Every response carries ``backend`` and ``route``. Not a setting - a report. A
reader surprised by an answer can tell which engine produced it and whether the
data came over MCP or out of SQLite before they go looking for a bug.
"""

from __future__ import annotations

import logging
import os

from sc.contracts import GraphDomain
from sc.kg import cypher, driver, insights, memory, model

log = logging.getLogger(__name__)


def preference() -> str:
    """What the operator asked for. Read per call, so it can be changed live."""
    choice = os.environ.get("KG_BACKEND", "auto").strip().lower()
    return choice if choice in {"auto", "neo4j", "memory"} else "auto"


def chosen() -> tuple[str, str]:
    """The backend that will actually answer, and why if it is not the ask.

    ``memory`` is never refused - it needs nothing. ``neo4j`` asked for
    explicitly and unreachable is still a fallback rather than an error,
    because the alternative is a blank tab, but the reason travels with the
    answer so nobody has to guess.
    """
    want = preference()
    if want == "memory":
        return "memory", ""

    ready, reason = driver.available()
    if ready:
        return "neo4j", ""
    if want == "neo4j":
        return "memory", f"neo4j was asked for but is not answering: {reason}"
    return "memory", reason


def _domains(names: list[str] | None) -> list[GraphDomain] | None:
    return cypher._validated_domains(names)


# ---------------------------------------------------------------------------
# Reads
#
# Each of these builds the Cypher whether or not it runs it. That is
# deliberate: the builder is where the validation lives - the closed depth set,
# the domain allowlist, the parameter bounds - so a request that Neo4j would
# have refused is refused identically with Neo4j switched off. A validation
# that only ran on one path would be a validation that stopped running the day
# somebody set KG_BACKEND=memory.


def neighbourhood(root: str, *, depth: int, domains: list[str] | None,
                  limit: int) -> dict:
    query = cypher.neighbourhood_query(root, depth, domains, limit)
    backend, note = chosen()

    if backend == "neo4j":
        try:
            rows = driver.run(query)
            return {**_adapt_neighbourhood(rows), "backend": "neo4j",
                    "route": "mcp"}
        except Exception as exc:  # noqa: BLE001 - falls back, and says so
            log.warning("neo4j neighbourhood failed, falling back: %s", exc)
            note = f"neo4j failed mid-query: {type(exc).__name__}"

    answer = memory.neighbourhood(root, depth=cypher.validated_depth(depth),
                                  domains=_domains(domains), limit=limit)
    return {**answer, "backend": "memory", "route": "sqlite", "note": note or None}


def _adapt_neighbourhood(rows: list[dict]) -> dict:
    """Turn a Cypher result into the shape the in-process backend returns.

    One row, two lists. The adapter exists so the route handler cannot tell
    which engine answered - anything else and the switch would be visible in
    the response shape, which is exactly what it promises not to be.
    """
    from sc.contracts import GraphEdge, GraphNode, GraphNodeLabel, GraphRelType

    if not rows:
        return {"nodes": [], "edges": [], "truncated": False, "total_nodes": 0,
                "dropped_domains": {}}

    row = rows[0]
    nodes = []
    for props in row.get("nodes") or []:
        label = GraphNodeLabel(str(props.get("kgLabel") or props.get("label")))
        nodes.append(GraphNode(
            id=props["kgId"], label=label, domain=model.DOMAIN_OF[label],
            name=props.get("name") or props["kgId"],
            degree=int(props.get("kgDegree") or 0),
            synthetic=bool(props.get("synthetic")), props=props))

    edges = []
    for record in row.get("edges") or []:
        rel = GraphRelType(record["type"])
        edges.append(GraphEdge(
            id=record["id"], source=record["source"], target=record["target"],
            type=rel, domain=model.edge_domain(rel),
            synthetic=bool((record.get("props") or {}).get("synthetic")),
            props=record.get("props") or {}))

    return {"nodes": nodes, "edges": edges, "truncated": False,
            "total_nodes": len(nodes), "dropped_domains": {}}


def paths(source: str, target: str, *, limit: int = memory.MAX_PATHS) -> dict:
    query = cypher.paths_query(source, target, limit)
    backend, note = chosen()

    if backend == "neo4j":
        try:
            rows = driver.run(query)
            found = [{"length": r["length"], "nodes": r["nodes"],
                      "edges": [e for e in r["edges"] if e],
                      "narrative": _narrate_names(r.get("names") or [])}
                     for r in rows]
            return {"paths": found, "backend": "neo4j", "route": "mcp"}
        except Exception as exc:  # noqa: BLE001
            log.warning("neo4j paths failed, falling back: %s", exc)
            note = f"neo4j failed mid-query: {type(exc).__name__}"

    return {"paths": memory.paths(source, target, limit=limit),
            "backend": "memory", "route": "sqlite", "note": note or None}


def _narrate_names(names: list[str]) -> str:
    middles = [n for n in names[1:-1] if n]
    return f"via {', then '.join(middles)}" if middles else "directly connected"


def search(term: str, *, limit: int = 20) -> dict:
    backend, note = chosen()

    if backend == "neo4j":
        try:
            rows = driver.run(cypher.search_query(term, limit))
            hits = [{"id": r["id"], "label": r["label"], "name": r["name"],
                     "domain": model.DOMAIN_OF[r["label"]],
                     "detail": (r.get("props") or {}).get("code"),
                     "score": round(float(r.get("score") or 0), 2)}
                    for r in rows]
            return {"hits": hits, "backend": "neo4j", "route": "mcp"}
        except Exception as exc:  # noqa: BLE001
            log.warning("neo4j search failed, falling back: %s", exc)
            note = f"neo4j failed mid-query: {type(exc).__name__}"

    return {"hits": memory.search(term, limit=limit), "backend": "memory",
            "route": "sqlite", "note": note or None}


def run_insight(insight_id: str, params: dict | None, as_of) -> dict:
    """Run one saved query. The id has already been through the allowlist."""
    bound = insights.bind(insight_id, params)
    spec = insights.CATALOGUE[insight_id]
    backend, note = chosen()

    if backend == "neo4j":
        try:
            rows = driver.run(cypher.insight_query(insight_id, bound, as_of))
            return {"rows": [_join_lists(r) for r in rows], "params": bound,
                    "backend": "neo4j", "route": "mcp",
                    "truncated": len(rows) >= insights.MAX_ROWS}
        except Exception as exc:  # noqa: BLE001
            log.warning("neo4j insight %s failed, falling back: %s",
                        insight_id, exc)
            note = f"neo4j failed mid-query: {type(exc).__name__}"

    rows = insights.RUNNERS[insight_id](memory.graph(), bound, as_of)
    return {"rows": rows, "params": bound, "backend": "memory",
            "route": "sqlite", "truncated": len(rows) >= insights.MAX_ROWS,
            "note": note or None, "columns": spec.columns}


def _join_lists(row: dict) -> dict:
    """Cypher returns a list where the table wants a sentence.

    The builders return lists rather than calling ``apoc.text.join``, because
    a stock Neo4j has no plugins and a query that needs one turns "run
    Neo4j locally" into a support question. The joining happens here instead.
    """
    return {key: ", ".join(str(v) for v in value)
            if isinstance(value, list) else value
            for key, value in row.items()}


def status(as_of=None) -> dict:
    """What is holding the graph, and what it contains."""
    backend, note = chosen()
    ready, reason = driver.available()

    counts: dict[str, int] = {}
    if backend == "neo4j":
        try:
            rows = driver.run(cypher.counts_query())
            for entry in (rows[0]["byLabel"] if rows else []):
                counts[entry["label"]] = entry["nodes"]
        except Exception as exc:  # noqa: BLE001
            note = f"could not count: {type(exc).__name__}"
            backend = "memory"

    if backend == "memory":
        graph = memory.graph()
        for node in graph.nodes.values():
            counts[node.label.value] = counts.get(node.label.value, 0) + 1

    from sc.kg import source_db

    return {
        "backend": backend,
        "route": "mcp" if backend == "neo4j" else "sqlite",
        "available": ready,
        "uri": driver.safe_uri(),
        "node_counts": dict(sorted(counts.items())),
        "rel_counts": {},
        "ingested_at": None,
        "note": note or (reason if not ready else None),
        "reference_events": source_db.reference_count(),
        "preference": preference(),
        "max_depth": model.MAX_DEPTH,
        "max_nodes": model.DEFAULT_MAX_NODES,
    }
