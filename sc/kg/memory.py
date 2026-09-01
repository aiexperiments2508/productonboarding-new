"""The in-process backend: traversal over the projection, with no server.

This is what answers ``/api/kg/*`` when Neo4j is not reachable, and what the
tests exercise. It is not a second implementation of the graph - it walks the
identical structure ``sc/kg/project.py`` builds, which is also what the Neo4j
loader MERGEs. One graph, two execution engines.

The precedent is ``sc/mcp/client.py``, whose transport switch is documented as
a transport decision rather than a behavioural one, and which falls back rather
than fails. Same claim here: the answer is the same either way, and a demo that
needs a database server before a tab will open is a demo that does not open.

**Truncation happens twice, and the second time is the interesting one.**

The walk is breadth-first, and within a hop it reaches the better-connected
nodes first - so what a cap keeps is never whatever the dictionary happened to
iterate. But breadth-first order alone is still the wrong rule for *choosing*
what to draw: a well-connected product reaches fifty other products through two
shared campaigns, all of them nearer than the certificate that is about to
lapse, so the picture fills with one domain while the legend promises seven.
``_fair_share`` deals round-robin across the domains instead.

What was left out, and from which domain, comes back with the answer either
way - the doctrine ``NetworkMap`` states for its own row cap: a view that
quietly drew thirty of a hundred and fifty would be read as a graph of thirty.
"""

from __future__ import annotations

from collections import deque
from functools import lru_cache

from sc.contracts import GraphDomain
from sc.kg import model, project, source_db
from sc.kg.project import Graph

#: How many alternate routes between two products are worth showing. Past
#: three they stop being different explanations and start being the same
#: explanation with a different attribute value in the middle.
MAX_PATHS = 3


@lru_cache(maxsize=1)
def graph() -> Graph:
    """The projection, built once.

    Cached like ``sc.state.baseline.get`` and cleared the same way. Every test
    fixture that reseeds the database has to call ``cache_clear`` beside
    ``baseline_mod.get.cache_clear`` - a graph built from the previous seed is
    the kind of stale that looks like a wrong answer rather than an error.
    """
    from sc.state import baseline as baseline_mod

    return project.build(baseline_mod.get(), source_db.reference_events())


def cache_clear() -> None:
    graph.cache_clear()


def _allowed(domains: list[GraphDomain] | None) -> set[GraphDomain] | None:
    """None means everything. An empty selection also means everything.

    Turning every chip off and being shown nothing is technically consistent
    and practically a bug report: the reader has filtered themselves into an
    empty screen with no way to tell it from a failure.
    """
    return set(domains) if domains else None


def neighbourhood(root: str, *, depth: int = 2,
                  domains: list[GraphDomain] | None = None,
                  limit: int = model.DEFAULT_MAX_NODES) -> dict:
    """The subgraph around one node, out to ``depth`` hops.

    Breadth first, because the ordering is the whole of the truncation policy:
    everything one hop away is more relevant than anything two hops away, and
    within a hop the better-connected node is the one worth the space.
    """
    g = graph()
    if root not in g.nodes:
        return {}

    allowed = _allowed(domains)

    # --- reach everything first, in breadth-first order ------------------
    reached: list[str] = [root]
    seen = {root}
    frontier = deque([(root, 0)])

    while frontier:
        node_id, hop = frontier.popleft()
        if hop >= depth:
            continue

        candidates = []
        for other, _ in g.neighbours(node_id):
            if other in seen:
                continue
            node = g.nodes[other]
            if allowed is not None and node.domain not in allowed:
                continue
            candidates.append(node)

        # Best connected first *within a hop*. Everything one hop away is more
        # relevant than anything two hops away, and inside a hop the
        # better-connected node is the one worth the space.
        candidates.sort(key=lambda n: (-n.degree, n.id))
        for node in candidates:
            if node.id in seen:
                continue
            seen.add(node.id)
            reached.append(node.id)
            frontier.append((node.id, hop + 1))

    kept_ids = _fair_share(g, reached, limit)
    kept = set(kept_ids)

    dropped: dict[str, int] = {}
    for node_id in reached:
        if node_id not in kept:
            domain = g.nodes[node_id].domain.value
            dropped[domain] = dropped.get(domain, 0) + 1

    nodes = [g.nodes[nid] for nid in kept_ids]
    edges = [e for e in g.edges if e.source in kept and e.target in kept]
    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": bool(dropped),
        "total_nodes": len(reached),
        "dropped_domains": dropped,
    }


def _fair_share(g: Graph, reached: list[str], limit: int) -> list[str]:
    """Choose which of the reached nodes to draw, without letting one domain win.

    Straight breadth-first order would be the obvious rule and it is the wrong
    one. A well-connected product reaches fifty other products through two
    shared campaigns, and those fifty are all closer than the certificate that
    is about to lapse - so the picture fills with one domain and the legend
    promises seven that are not there.

    Round-robin across the domains instead, taking each domain's own
    breadth-first order. Every domain present gets a turn before any domain
    gets a second helping, and a domain that runs out simply stops being dealt
    to, so no capacity is wasted. The root is always first: it is what the
    reader asked about.
    """
    if len(reached) <= limit:
        return reached

    root = reached[0]
    queues: dict[str, deque] = {}
    for node_id in reached[1:]:
        queues.setdefault(g.nodes[node_id].domain.value, deque()).append(node_id)

    chosen = [root]
    order = sorted(queues)
    while len(chosen) < limit and any(queues[d] for d in order):
        for domain in order:
            if not queues[domain]:
                continue
            chosen.append(queues[domain].popleft())
            if len(chosen) >= limit:
                break
    return chosen


def expand(node_id: str, *, exclude: set[str] | None = None,
           domains: list[GraphDomain] | None = None, limit: int = 40) -> dict:
    """One node's own neighbours - what a double-click asks for.

    Separate from ``neighbourhood`` because the question is different. This is
    "show me more of *this*", so it is bounded by what the reader clicked
    rather than by a global budget, and it skips what is already on screen.
    """
    g = graph()
    if node_id not in g.nodes:
        return {"nodes": [], "edges": [], "truncated": False, "total_nodes": 0}

    allowed = _allowed(domains)
    seen = exclude or set()
    candidates = []
    for other, _ in g.neighbours(node_id):
        if other in seen:
            continue
        node = g.nodes[other]
        if allowed is not None and node.domain not in allowed:
            continue
        candidates.append(node)

    candidates.sort(key=lambda n: (-n.degree, n.id))
    kept = candidates[:limit]
    ids = {n.id for n in kept} | {node_id} | seen
    edges = [e for e in g.edges
             if (e.source == node_id and e.target in ids)
             or (e.target == node_id and e.source in ids)]
    return {
        "nodes": kept, "edges": edges,
        "truncated": len(candidates) > limit,
        "total_nodes": len(candidates),
    }


def _narrate(g: Graph, node_ids: list[str], edge_ids: list[str]) -> str:
    """Say a path in the reader's own words.

    A list of nine node ids is a result, not an answer. "Both are stocked at
    Leeds RDC" is what somebody came to find out, and it is the difference
    between a graph that explains a connection and one that merely proves there
    is one.
    """
    if len(node_ids) < 3:
        return "directly connected"
    middles = [g.nodes[nid] for nid in node_ids[1:-1]]
    said = []
    for node in middles:
        noun = node.label.value.lower()
        said.append(f"the {noun} {node.name}")
    joined = ", then ".join(said)
    return f"via {joined}"


def paths(source: str, target: str, *, limit: int = MAX_PATHS) -> list[dict]:
    """Shortest routes between two nodes.

    Breadth first for the shortest, then alternates that avoid an intermediate
    the previous route used. Alternates that differ only by which attribute
    value they pass through are the same explanation twice, and this is the
    cheapest way to keep them out.
    """
    g = graph()
    if source not in g.nodes or target not in g.nodes or source == target:
        return []

    found: list[dict] = []
    banned: set[str] = set()

    for _ in range(limit):
        previous: dict[str, tuple[str, int]] = {source: ("", -1)}
        queue = deque([source])
        while queue and target not in previous:
            current = queue.popleft()
            for other, edge_index in g.neighbours(current):
                if other in previous or other in banned:
                    continue
                previous[other] = (current, edge_index)
                queue.append(other)

        if target not in previous:
            break

        node_ids, edge_ids, cursor = [target], [], target
        while cursor != source:
            parent, edge_index = previous[cursor]
            edge_ids.append(g.edges[edge_index].id)
            node_ids.append(parent)
            cursor = parent
        node_ids.reverse()
        edge_ids.reverse()

        found.append({
            "length": len(edge_ids),
            "nodes": node_ids,
            "edges": edge_ids,
            "narrative": _narrate(g, node_ids, edge_ids),
        })
        # Ban one intermediate so the next route has to go somewhere else.
        middles = node_ids[1:-1]
        if not middles:
            break
        banned.add(middles[len(middles) // 2])

    return found


def search(query: str, *, limit: int = 20) -> list[dict]:
    """Type-ahead over the labels a merchant names out loud.

    Exact key match first, then prefix, then substring. That order is what
    makes typing a SKU feel like a lookup rather than a search: the thing you
    named is the first row, not the fourth.

    Restricted to ``model.SEARCHABLE``. Offering the fourteen thousand join
    nodes would bury the nine kinds anybody actually looks for.
    """
    needle = query.strip().lower()
    if not needle:
        return []

    g = graph()
    searchable = set(model.SEARCHABLE)
    hits: list[tuple[int, int, str, dict]] = []

    for node in g.nodes.values():
        if node.label not in searchable:
            continue
        keys = [str(node.props.get(k, "")) for k in model.keys_of(node.label)]
        haystacks = [node.name] + keys
        best = None
        for text in haystacks:
            lowered = text.lower()
            if not lowered:
                continue
            if lowered == needle:
                best = 0
            elif lowered.startswith(needle) and (best is None or best > 1):
                best = 1
            elif needle in lowered and best is None:
                best = 2
        if best is None:
            continue
        detail = keys[0] if keys and keys[0] != node.name else node.label.value
        hits.append((best, -node.degree, node.id, {
            "id": node.id, "label": node.label, "domain": node.domain,
            "name": node.name, "detail": detail,
            "score": round(1.0 - best * 0.3, 2),
        }))

    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    return [hit[3] for hit in hits[:limit]]
