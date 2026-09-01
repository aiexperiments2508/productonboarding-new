"""Building Cypher. Parameterised, and pure.

Every function here returns a ``GraphQuery`` - a name, a query string and a
parameter dict - and none of them touches a driver. That is what makes the
whole query surface testable with no Neo4j anywhere: a test asserts on the
string and the parameters, which is the thing that could be wrong, rather than
on a database round trip, which is the thing that could be slow.

**The one genuine injection risk, and how it is closed.**

Cypher has no syntax for a parameterised variable-length bound. ``*1..$depth``
is not a query - it fails to parse - so a depth taken from a request would have
to be pasted into the pattern, and *that* is an injection point rather than a
setting. It is closed here by a lookup table of literal patterns: a depth that
is not a key raises, so nothing derived from a request ever reaches the string.

The same reasoning covers the two other things Cypher will not bind - a label
and a property name. Both are taken from ``sc/kg/model.py`` and the enums in
``sc/contracts.py``, never from a caller. Anything a caller *can* supply - a
node id, a search term, a date, a threshold - is a bound parameter.

``tests/test_kg_cypher.py`` checks all of this the blunt way: it pulls every
``$name`` out of each built string and asserts the set matches the parameter
keys exactly, and it feeds a Cypher fragment in as a domain filter and asserts
the builder refuses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from sc.contracts import GraphDomain, GraphNodeLabel
from sc.kg import model

#: Depth is written into the pattern because it cannot be bound. Three keys,
#: and a request for anything else is refused rather than clamped - a caller
#: asking for six hops has misunderstood something, and quietly giving them
#: three would hide that.
_DEPTH_PATTERN: dict[int, str] = {1: "*1..1", 2: "*1..2", 3: "*1..3"}

#: How many rows a saved query returns. Mirrors ``insights.MAX_ROWS``; the two
#: are asserted equal by the tests so a Cypher run and an in-process run cannot
#: disagree about how much they answered.
MAX_ROWS = 50


@dataclass(frozen=True)
class GraphQuery:
    """One statement and its parameters, ready for a session.

    Frozen because a query that could be edited after it was built would let a
    caller reach past the builder that validated it.
    """

    name: str
    cypher: str
    params: dict[str, object] = field(default_factory=dict)

    def placeholders(self) -> set[str]:
        """Every ``$name`` in the statement. What the tests check against."""
        return set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", self.cypher))


def _labels_for(domains: list[GraphDomain] | None) -> list[str] | None:
    """The label names a domain filter admits, or None for everything.

    Returned as a **parameter value**, not spliced into the query. Cypher will
    bind a list and ``any(l IN labels(n) WHERE l IN $labels)`` reads it, so the
    domain filter never touches the string - which is why a domain carrying a
    Cypher fragment is simply a name that matches no label.
    """
    if not domains:
        return None
    admitted = {label.value for label, domain in model.DOMAIN_OF.items()
                if domain in set(domains)}
    return sorted(admitted)


def _validated_domains(names: list[str] | None) -> list[GraphDomain] | None:
    """Turn caller-supplied domain names into enum members, or refuse.

    Refusing is the point. A name that is not a domain cannot become one by
    being passed along, and silently dropping it would show the caller a graph
    filtered differently from the one they asked for.
    """
    from sc.kg import BadRequest

    if not names:
        return None
    known = {domain.value: domain for domain in GraphDomain}
    chosen = []
    for name in names:
        domain = known.get(str(name).strip().upper())
        if domain is None:
            raise BadRequest(
                f"unknown domain {name!r} - expected one of "
                f"{', '.join(sorted(known))}")
        chosen.append(domain)
    return chosen


def validated_depth(depth: int) -> int:
    """The depth, or a refusal. See the module docstring."""
    from sc.kg import BadRequest

    try:
        value = int(depth)
    except (TypeError, ValueError) as exc:
        raise BadRequest("depth must be a whole number") from exc
    if value not in _DEPTH_PATTERN:
        raise BadRequest(
            f"depth must be one of {sorted(_DEPTH_PATTERN)} - "
            "the traversal bound is written into the pattern, not bound as a "
            "parameter, so it comes from a closed set")
    return value


# ---------------------------------------------------------------------------
# Traversal


def neighbourhood_query(root: str, depth: int,
                        domains: list[str] | None = None,
                        limit: int = model.DEFAULT_MAX_NODES) -> GraphQuery:
    """The subgraph around one node.

    ``kgId`` is the graph's own prefixed identifier - ``Variant:VAR-01B`` - and
    it is bound, so a caller cannot reach past the pattern with it.

    Ordered by degree before the cap for the same reason the in-process backend
    is: a truncation that took whatever came first would drop a certificate and
    keep a ninth attribute value, and nothing on the screen would say so.
    """
    pattern = _DEPTH_PATTERN[validated_depth(depth)]
    labels = _labels_for(_validated_domains(domains))

    clause = ("  AND any(l IN labels(m) WHERE l IN $labels)\n" if labels
              else "")
    return GraphQuery(
        name="neighbourhood",
        cypher=(
            "MATCH (root {kgId: $root})\n"
            # OPTIONAL, because a node with no neighbours inside the filter is
            # an answer. A plain MATCH would return no rows at all, and the
            # caller could not tell "nothing connected" from "no such node".
            f"OPTIONAL MATCH (root)-[{pattern}]-(m)\n"
            "WHERE m.kgId IS NOT NULL\n"
            f"{clause}"
            "WITH root, m, size([(m)--() | 1]) AS degree\n"
            "ORDER BY degree DESC, m.kgId\n"
            "WITH root, [x IN collect(DISTINCT m)\n"
            "            WHERE x IS NOT NULL][0..$limit] AS reached\n"
            "WITH [root] + reached AS nodes\n"
            "UNWIND nodes AS a\n"
            "OPTIONAL MATCH (a)-[r]->(b)\n"
            "WHERE b IN nodes\n"
            "WITH nodes, collect(DISTINCT r) AS rels\n"
            "RETURN [n IN nodes | properties(n)] AS nodes,\n"
            "       [r IN rels WHERE r IS NOT NULL |\n"
            "         {id: r.kgId, source: startNode(r).kgId,\n"
            "          target: endNode(r).kgId, type: type(r),\n"
            "          props: properties(r)}] AS edges"),
        params={"root": root, "limit": int(limit),
                **({"labels": labels} if labels else {})})


def paths_query(source: str, target: str, limit: int = 3) -> GraphQuery:
    """Shortest routes between two nodes.

    ``allShortestPaths`` rather than a variable-length match with an ORDER BY:
    the planner has a purpose-built implementation and using it is the
    difference between a bounded walk and a search of the whole graph.

    The bound inside it is a literal for the same reason a depth is - it cannot
    be a parameter - and it is a constant here rather than caller-supplied,
    which is the strongest form of the same argument.
    """
    return GraphQuery(
        name="paths",
        cypher=(
            "MATCH (a {kgId: $source}), (b {kgId: $target})\n"
            "MATCH p = allShortestPaths((a)-[*..6]-(b))\n"
            "WITH p, length(p) AS length\n"
            "ORDER BY length, [n IN nodes(p) | n.kgId]\n"
            "LIMIT $limit\n"
            "RETURN length,\n"
            "       [n IN nodes(p) | n.kgId] AS nodes,\n"
            "       [r IN relationships(p) | r.kgId] AS edges,\n"
            "       [n IN nodes(p) | n.name] AS names"),
        params={"source": source, "target": target, "limit": int(limit)})


def search_query(term: str, limit: int = 20) -> GraphQuery:
    """Type-ahead over the searchable labels.

    Goes through the full-text index rather than a regex over every node, so
    the cost does not grow with the graph. The index name is
    ``model.SEARCH_INDEX``, declared once and read here and by
    ``schema.cypher`` - a typo between the two would be a runtime error on an
    otherwise healthy graph, which is what the schema test is for.

    The term is escaped and bound. Lucene syntax in a search box is not an
    injection into Cypher, but it is a way to make a query throw, and a
    type-ahead that errors on an apostrophe is a type-ahead nobody trusts.
    """
    cleaned = re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/]', " ", str(term)).strip()
    return GraphQuery(
        name="search",
        cypher=(
            "CALL db.index.fulltext.queryNodes($index, $term)\n"
            "YIELD node, score\n"
            "WHERE node.kgId IS NOT NULL\n"
            "RETURN node.kgId AS id, labels(node)[0] AS label,\n"
            "       node.name AS name, properties(node) AS props, score\n"
            "ORDER BY score DESC, node.kgId\n"
            "LIMIT $limit"),
        params={"index": model.SEARCH_INDEX,
                "term": f"{cleaned}~" if cleaned else "*",
                "limit": int(limit)})


def counts_query() -> GraphQuery:
    """What the graph holds, for ``/api/kg/status``."""
    return GraphQuery(
        name="counts",
        cypher=(
            "MATCH (n) WHERE n.kgId IS NOT NULL\n"
            "WITH labels(n)[0] AS label, count(*) AS nodes\n"
            "RETURN collect({label: label, nodes: nodes}) AS byLabel"))


# ---------------------------------------------------------------------------
# Ingestion
#
# A label and a property name cannot be bound in Cypher. Both come from the
# enums here, never from a caller, so the statement is built from a closed set
# and the *data* travels as $rows.


def node_upsert(label: GraphNodeLabel) -> GraphQuery:
    """MERGE every node of one label, from a bound list of rows.

    ``UNWIND $rows`` rather than a statement per node: a round trip per node
    across seven thousand of them is the difference between a load that takes
    a second and one that takes a minute.

    MERGE keys on the business key, which is why ``sc/kg/schema.cypher`` puts a
    uniqueness constraint on every one of them. Without the constraint this
    inserts a second copy of everything on the second run and reports success.
    """
    key = model.BUSINESS_KEY[label]
    return GraphQuery(
        name=f"upsert:{label.value}",
        cypher=(
            "UNWIND $rows AS row\n"
            f"MERGE (n:{label.value} {{{key}: row.key}})\n"
            "SET n += row.props, n.kgId = row.kgId, n.name = row.name,\n"
            "    n.synthetic = row.synthetic, n.updatedAt = row.updatedAt"),
        params={"rows": []})


def edge_upsert(rel_type: str) -> GraphQuery:
    """MERGE every relationship of one type, matching both ends by kgId.

    Matched on ``kgId`` rather than on each end's own business key because the
    projection already composed it, and looking a node up by the identifier the
    graph itself uses avoids the loader having to know which property is which
    label's key at edge time.
    """
    if rel_type not in {r.value for r in __import__(
            "sc.contracts", fromlist=["GraphRelType"]).GraphRelType}:
        raise ValueError(f"unknown relationship type {rel_type!r}")
    return GraphQuery(
        name=f"upsert:{rel_type}",
        cypher=(
            "UNWIND $rows AS row\n"
            "MATCH (a {kgId: row.source})\n"
            "MATCH (b {kgId: row.target})\n"
            f"MERGE (a)-[r:{rel_type}]->(b)\n"
            "SET r += row.props, r.kgId = row.id, r.synthetic = row.synthetic"),
        params={"rows": []})


def prune_query(label: GraphNodeLabel) -> GraphQuery:
    """Delete nodes of one label that this run did not touch.

    MERGE is idempotent but not convergent: a node that leaves the source stays
    in the graph for ever. This is how it leaves, and it is opt-in
    (``load_graph.py --prune``) because deleting on every load would make a
    partial harvest destructive.
    """
    return GraphQuery(
        name=f"prune:{label.value}",
        cypher=(
            f"MATCH (n:{label.value})\n"
            "WHERE n.kgId IS NOT NULL AND (n.loadedAt IS NULL "
            "OR n.loadedAt < $runStamp)\n"
            "DETACH DELETE n\n"
            "RETURN count(*) AS removed"),
        params={"runStamp": ""})


# ---------------------------------------------------------------------------
# The saved queries
#
# One builder per insight. They are the Cypher half of what
# ``sc/kg/insights.py`` also answers in process; the two run over the same
# projection, so they are two readings of one graph rather than two graphs.


def insight_query(insight_id: str, params: dict,
                  as_of: datetime) -> GraphQuery:
    """Build the Cypher for one saved query.

    The id has already been through ``insights.bind``, which checks it against
    the allowlist and bounds every parameter. This raises rather than falling
    back if it is handed something else, because a builder that quietly
    returned a default query would make the allowlist decorative.
    """
    from sc.kg import BadRequest

    builder = _INSIGHT_BUILDERS.get(insight_id)
    if builder is None:
        raise BadRequest(f"no Cypher builder for insight {insight_id!r}")
    return builder(params, as_of)


def _certifications_expiring(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="certifications-expiring",
        cypher=(
            "MATCH (v:Variant)-[:CERTIFIED_BY]->(c:Certificate)\n"
            "WHERE c.expiresOn >= $today AND c.expiresOn <= $horizon\n"
            "WITH c, collect(DISTINCT coalesce(v.sku, v.id)) AS skus\n"
            "RETURN c.ref AS certificate, c.scheme AS scheme,\n"
            "       c.expiresOn AS expires_on,\n"
            "       duration.inDays(date($today), date(c.expiresOn)).days\n"
            "           AS days_remaining,\n"
            "       size(skus) AS products,\n"
            "       skus AS skus\n"
            "ORDER BY days_remaining, certificate\n"
            "LIMIT $limit"),
        params={"today": as_of.date().isoformat(),
                "horizon": (as_of.date().toordinal()
                            and _plus_days(as_of, int(params["within_days"]))),
                "limit": MAX_ROWS})


def _plus_days(as_of: datetime, days: int) -> str:
    from datetime import timedelta

    return (as_of.date() + timedelta(days=days)).isoformat()


def _bestsellers_missing_image(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="bestsellers-missing-image",
        cypher=(
            "MATCH (f:SalesFact)-[:FOR_VARIANT]->(v:Variant)\n"
            "WHERE f.rankInCategory <= $rank\n"
            "  AND size(coalesce(v.missingMedia, [])) > 0\n"
            "WITH v, f ORDER BY f.units DESC\n"
            "WITH v, head(collect(f)) AS best\n"
            "RETURN coalesce(v.sku, v.id) AS sku, v.name AS name,\n"
            "       best.category AS category, best.marketCode AS market,\n"
            "       best.period AS period, best.units AS units,\n"
            "       v.missingMedia AS missing_media\n"
            "ORDER BY units DESC, sku\n"
            "LIMIT $limit"),
        params={"rank": int(params["rank"]), "limit": MAX_ROWS})


def _stock_cannot_ship(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="stock-cannot-ship",
        cypher=(
            "MATCH (v:Variant)-[:HAS_STOCK]->(s:StockLevel)\n"
            "            -[:AT_WAREHOUSE]->(w:Warehouse)-[:SERVES]->(m:Market)\n"
            "MATCH (m)-[:REQUIRES]->(reg:Regulation)\n"
            "WHERE v.branch IN reg.appliesTo\n"
            "  AND EXISTS { (v)-[:CERTIFIED_BY]->(:Certificate) }\n"
            "  AND NOT EXISTS {\n"
            "        (v)-[:CERTIFIED_BY]->(:Certificate)-[:SATISFIES]->(reg)\n"
            "      }\n"
            "MATCH (v)-[:CERTIFIED_BY]->(held:Certificate)\n"
            "WITH v, w, reg, s,\n"
            "     collect(DISTINCT m.name) AS markets,\n"
            "     collect(DISTINCT held.scheme) AS schemes\n"
            "RETURN coalesce(v.sku, v.id) AS sku, v.name AS name,\n"
            "       w.name AS warehouse,\n"
            "       markets AS markets,\n"
            "       reg.code AS regulation,\n"
            "       schemes AS holds,\n"
            "       s.onHandQty AS on_hand\n"
            "ORDER BY warehouse, sku\n"
            "LIMIT $limit"),
        params={"limit": MAX_ROWS})


def _cross_sell_candidates(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="cross-sell-candidates",
        cypher=(
            "MATCH (a:Product)-[r:COMPLEMENTS]->(b:Product)\n"
            "WHERE r.campaigns >= $minCampaigns\n"
            "RETURN a.name AS product, b.name AS pairs_with,\n"
            "       r.campaigns AS shared_campaigns,\n"
            "       a.category AS category,\n"
            "       b.category AS pairs_with_category,\n"
            "       split(a.category, '.')[0] <> split(b.category, '.')[0]\n"
            "           AS cross_category\n"
            "ORDER BY shared_campaigns DESC, product\n"
            "LIMIT $limit"),
        params={"minCampaigns": int(params["min_campaigns"]),
                "limit": MAX_ROWS})


def _weakest_media_coverage(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="weakest-media-coverage",
        cypher=(
            "MATCH (v:Variant)\n"
            "WHERE size(coalesce(v.requiredMedia, [])) > 0\n"
            "WITH reduce(acc = '', part IN\n"
            "            split(v.category, '.')[0..$level] |\n"
            "       CASE WHEN acc = '' THEN part\n"
            "            ELSE acc + '.' + part END)\n"
            "         AS category,\n"
            "     count(*) AS variants,\n"
            "     sum(CASE WHEN size(coalesce(v.missingMedia, [])) > 0\n"
            "              THEN 1 ELSE 0 END) AS missing_media\n"
            "WHERE missing_media > 0\n"
            "RETURN category, variants, missing_media,\n"
            "       round(100.0 * (variants - missing_media) / variants, 1)\n"
            "           AS coverage_pct\n"
            "ORDER BY coverage_pct, category\n"
            "LIMIT $limit"),
        params={"level": int(params["level"]), "limit": MAX_ROWS})


def _supplier_concentration(params: dict, as_of: datetime) -> GraphQuery:
    return GraphQuery(
        name="supplier-concentration",
        cypher=(
            "MATCH (p:Product)-[:SUPPLIED_BY]->(s:Supplier)\n"
            "WITH reduce(acc = '', part IN\n"
            "            split(p.category, '.')[0..$level] |\n"
            "       CASE WHEN acc = '' THEN part\n"
            "            ELSE acc + '.' + part END)\n"
            "         AS category, s, count(*) AS products\n"
            "WITH category, collect({supplier: s.name, products: products})\n"
            "         AS tallies,\n"
            "     sum(products) AS of_products\n"
            "WITH category, of_products, tallies,\n"
            "     reduce(best = null, t IN tallies |\n"
            "            CASE WHEN best IS NULL OR t.products > best.products\n"
            "                 THEN t ELSE best END) AS top\n"
            "WITH category, of_products, size(tallies)\n"
            "         AS suppliers_in_category,\n"
            "     top.supplier AS supplier, top.products AS products\n"
            "WHERE 100.0 * products / of_products >= $sharePct\n"
            "RETURN category, supplier, products, of_products,\n"
            "       round(100.0 * products / of_products, 1) AS share_pct,\n"
            "       suppliers_in_category\n"
            "ORDER BY share_pct DESC, products DESC, category\n"
            "LIMIT $limit"),
        params={"sharePct": float(params["share_pct"]),
                "level": int(params["level"]), "limit": MAX_ROWS})


_INSIGHT_BUILDERS = {
    "certifications-expiring": _certifications_expiring,
    "bestsellers-missing-image": _bestsellers_missing_image,
    "stock-cannot-ship": _stock_cannot_ship,
    "cross-sell-candidates": _cross_sell_candidates,
    "weakest-media-coverage": _weakest_media_coverage,
    "supplier-concentration": _supplier_concentration,
}
