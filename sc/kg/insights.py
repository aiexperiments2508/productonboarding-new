"""The six saved queries, and the allowlist that is the only way to run one.

``POST /api/kg/query`` takes an ``id`` from ``CATALOGUE`` and nothing else.
There is no free-text Cypher box, in v1 or otherwise: the closed set checked by
name is the same argument ``sc/graph/evidence.py`` already makes for its tool
table, and a graph endpoint that executed a supplied string would be the one
genuine injection surface in this platform.

Every spec states a ``question`` and a ``why``. That is not decoration - an
insight with no stated question is a chart, and a merchant looking at six rows
has no way to tell a finding from a coincidence unless the view says what it
asked. Two of the six need no invented data at all, and their ``why`` says so.

Each insight has two implementations: a builder in ``sc/kg/cypher.py`` and a
function here that walks ``sc/kg/project.Graph``. They are not independent
readings - both run over the same projection - but they are separate code, so
``tests/test_kg_insights.py`` checks the shapes agree rather than assuming it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sc.contracts import GraphDomain as D
from sc.contracts import GraphNodeLabel as L
from sc.contracts import InsightParam, InsightSpec
from sc.kg.project import Graph

#: How many rows any one insight will return. A view that answered with four
#: hundred rows would be a report, and the tab is not a reporting tool - it is
#: a way of noticing something worth opening a product for.
MAX_ROWS = 50


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _incoming(graph: Graph, node_id: str, rel: str) -> list[str]:
    """Node ids on the far end of every ``rel`` edge pointing at this node."""
    return [graph.edges[i].source for i in graph.adjacency.get(node_id, ())
            if graph.edges[i].type.value == rel
            and graph.edges[i].target == node_id]


def _outgoing(graph: Graph, node_id: str, rel: str) -> list[str]:
    return [graph.edges[i].target for i in graph.adjacency.get(node_id, ())
            if graph.edges[i].type.value == rel
            and graph.edges[i].source == node_id]


def _nodes(graph: Graph, label: L):
    return [n for n in graph.nodes.values() if n.label is label]


# ---------------------------------------------------------------------------
# 1 - certifications expiring


def certifications_expiring(graph: Graph, params: dict, as_of: datetime) -> list[dict]:
    """Certificates lapsing soon, and everything that stands on them.

    Measured against ``as_of`` - the replay clock - and never against the wall
    clock. Every other as-of read in this platform works that way, and a
    ninety-day window anchored to real time would pass on the day it was
    written and quietly stop finding anything a year later.
    """
    within = int(params.get("within_days", 90))
    today = as_of.date()
    horizon = today + timedelta(days=within)

    rows = []
    for certificate in _nodes(graph, L.CERTIFICATE):
        expires = _as_date(certificate.props.get("expiresOn"))
        if expires is None or not (today <= expires <= horizon):
            continue
        variants = _incoming(graph, certificate.id, "CERTIFIED_BY")
        if not variants:
            continue
        skus = sorted(str(graph.nodes[v].props.get("sku") or v.split(":", 1)[1])
                      for v in variants)
        rows.append({
            "certificate": certificate.props.get("ref"),
            "scheme": certificate.props.get("scheme"),
            "expires_on": str(expires),
            "days_remaining": (expires - today).days,
            "products": len(variants),
            "skus": ", ".join(skus),
        })
    rows.sort(key=lambda r: (r["days_remaining"], r["certificate"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# 2 - best sellers with no primary image


def bestsellers_missing_image(graph: Graph, params: dict,
                              as_of: datetime) -> list[dict]:
    """What sells best in its category, and has no picture of the kind it needs.

    The media gap is real - fifty-three variants lack a role their branch
    requires, and the record view already reports it. What the graph adds is
    the ranking: without sales figures, a best seller with no pack shot and a
    dead line with no pack shot are the same finding, and only one of them is
    worth somebody's morning.
    """
    rank_ceiling = int(params.get("rank", 1))

    best: dict[str, dict] = {}
    for fact in _nodes(graph, L.SALES_FACT):
        if int(fact.props.get("rankInCategory", 99)) > rank_ceiling:
            continue
        for variant_id in _outgoing(graph, fact.id, "FOR_VARIANT"):
            held = best.get(variant_id)
            if held is None or fact.props.get("units", 0) > held.get("units", 0):
                best[variant_id] = {
                    "units": fact.props.get("units", 0),
                    "revenue": fact.props.get("revenue", 0),
                    "market": fact.props.get("marketCode"),
                    "period": fact.props.get("period"),
                    "category": fact.props.get("category"),
                }

    rows = []
    for variant_id, sales in best.items():
        variant = graph.nodes.get(variant_id)
        if variant is None:
            continue
        missing = variant.props.get("missingMedia") or []
        if not missing:
            continue
        rows.append({
            "sku": variant.props.get("sku") or variant_id.split(":", 1)[1],
            "name": variant.name,
            "category": sales["category"],
            "market": sales["market"],
            "period": sales["period"],
            "units": sales["units"],
            "missing_media": ", ".join(missing),
        })
    rows.sort(key=lambda r: (-r["units"], r["sku"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# 3 - stocked where it cannot lawfully ship


def stock_cannot_ship(graph: Graph, params: dict, as_of: datetime) -> list[dict]:
    """Stock held in a depot that serves a market the product cannot enter.

    The failure this exists for: nobody did anything wrong. The depot is doing
    its job, the certificate is valid, the market rule is correct, and no
    single system in the estate can see all three at once. It stops a shipment
    anyway.

    Scoped to variants that *hold* a certificate. A variant with none is a
    different finding - an uncertified product - and the record view already
    makes it. Reporting both here would drown the one nothing else can see.
    """
    rows = []
    for level in _nodes(graph, L.STOCK_LEVEL):
        variants = _incoming(graph, level.id, "HAS_STOCK")
        depots = _outgoing(graph, level.id, "AT_WAREHOUSE")
        if not variants or not depots:
            continue
        variant = graph.nodes[variants[0]]
        branch = str(variant.props.get("branch", ""))

        certificates = [graph.nodes[c]
                        for c in _outgoing(graph, variant.id, "CERTIFIED_BY")]
        if not certificates:
            continue
        satisfied = {r for c in certificates
                     for r in _outgoing(graph, c.id, "SATISFIES")}

        for depot_id in depots:
            depot = graph.nodes[depot_id]
            # Markets are collected before a row is written. Rotterdam serves
            # Germany and France and both require CE, so a row per market would
            # report one problem twice and make the finding look larger than
            # the work it represents.
            blocked: dict[str, set[str]] = {}
            for market_id in _outgoing(graph, depot_id, "SERVES"):
                market = graph.nodes[market_id]
                for regulation_id in _outgoing(graph, market_id, "REQUIRES"):
                    regulation = graph.nodes[regulation_id]
                    reaches = regulation.props.get("appliesTo") or []
                    if reaches and branch not in reaches:
                        continue
                    if regulation_id in satisfied:
                        continue
                    blocked.setdefault(
                        str(regulation.props.get("code")), set()).add(market.name)

            for code, markets in sorted(blocked.items()):
                rows.append({
                    "sku": variant.props.get("sku")
                    or variant.id.split(":", 1)[1],
                    "name": variant.name,
                    "warehouse": depot.name,
                    "markets": ", ".join(sorted(markets)),
                    "regulation": code,
                    "holds": ", ".join(sorted(
                        str(c.props.get("scheme")) for c in certificates)),
                    "on_hand": level.props.get("onHandQty"),
                })
    rows.sort(key=lambda r: (r["warehouse"], r["sku"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# 4 - cross-sell candidates


def cross_sell_candidates(graph: Graph, params: dict,
                          as_of: datetime) -> list[dict]:
    """Products a campaign already treats as belonging together.

    Two shared campaigns and not one. A campaign with twenty members puts a
    great many unrelated pairs in a room together, so a single overlap is
    coincidence and an edge drawn from it would make this view a list of
    everything.
    """
    minimum = int(params.get("min_campaigns", 2))
    rows = []
    for edge in graph.edges:
        if edge.type.value != "COMPLEMENTS":
            continue
        shared = int(edge.props.get("campaigns", 0))
        if shared < minimum:
            continue
        left, right = graph.nodes[edge.source], graph.nodes[edge.target]
        rows.append({
            "product": left.name,
            "pairs_with": right.name,
            "shared_campaigns": shared,
            "category": left.props.get("category"),
            "pairs_with_category": right.props.get("category"),
            "cross_category": (str(left.props.get("category", "")).split(".")[0]
                               != str(right.props.get("category", "")).split(".")[0]),
        })
    rows.sort(key=lambda r: (-r["shared_campaigns"], r["product"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# 5 - weakest media coverage


def weakest_media_coverage(graph: Graph, params: dict,
                           as_of: datetime) -> list[dict]:
    """Category subtrees where the imagery is thinnest.

    Entirely real. The requirement comes from the retailer's own branch
    profile and what is held comes from the asset library; nothing here is
    invented, which is why it is the insight to open with when somebody asks
    whether the graph is telling the truth.
    """
    depth = int(params.get("level", 2))
    totals: dict[str, int] = defaultdict(int)
    gaps: dict[str, int] = defaultdict(int)

    for variant in _nodes(graph, L.VARIANT):
        category = str(variant.props.get("category", ""))
        if not category:
            continue
        subtree = ".".join(category.split(".")[:depth])
        required = variant.props.get("requiredMedia") or []
        if not required:
            continue
        totals[subtree] += 1
        if variant.props.get("missingMedia"):
            gaps[subtree] += 1

    rows = []
    for subtree, total in totals.items():
        missing = gaps.get(subtree, 0)
        if not missing:
            continue
        rows.append({
            "category": subtree,
            "variants": total,
            "missing_media": missing,
            "coverage_pct": round(100.0 * (total - missing) / total, 1),
        })
    rows.sort(key=lambda r: (r["coverage_pct"], r["category"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# 6 - supplier concentration


def supplier_concentration(graph: Graph, params: dict,
                           as_of: datetime) -> list[dict]:
    """Categories that depend on one supplier.

    Also entirely real - ``Product.supplier`` over twenty-eight suppliers, as
    the catalog has always held it. The graph's contribution is the grouping: a
    single-source dependency is invisible product by product and obvious the
    moment the category is the unit.
    """
    threshold = float(params.get("share_pct", 60))
    depth = int(params.get("level", 2))

    by_subtree: dict[str, list[str]] = defaultdict(list)
    for product in _nodes(graph, L.PRODUCT):
        category = str(product.props.get("category", ""))
        suppliers = _outgoing(graph, product.id, "SUPPLIED_BY")
        if not category or not suppliers:
            continue
        by_subtree[".".join(category.split(".")[:depth])].append(suppliers[0])

    rows = []
    for subtree, suppliers in by_subtree.items():
        tally: dict[str, int] = defaultdict(int)
        for supplier in suppliers:
            tally[supplier] += 1
        top, count = max(tally.items(), key=lambda kv: (kv[1], kv[0]))
        share = 100.0 * count / len(suppliers)
        if share < threshold:
            continue
        rows.append({
            "category": subtree,
            "supplier": graph.nodes[top].name,
            "products": count,
            "of_products": len(suppliers),
            "share_pct": round(share, 1),
            "suppliers_in_category": len(tally),
        })
    rows.sort(key=lambda r: (-r["share_pct"], -r["products"], r["category"]))
    return rows[:MAX_ROWS]


# ---------------------------------------------------------------------------
# The catalogue - and the allowlist

CATALOGUE: dict[str, InsightSpec] = {
    spec.id: spec for spec in (
        InsightSpec(
            id="certifications-expiring",
            title="Certifications expiring soon",
            question="Which products stand on a certificate that lapses within "
                     "the next ninety days?",
            why="A lapsed certificate withdraws a product from sale, and one "
                "certificate usually covers several. Product by product it is "
                "a date in a field nobody diaries; by certificate it is one "
                "piece of work with a deadline.",
            domains=[D.COMPLIANCE, D.CORE],
            columns=["certificate", "scheme", "expires_on", "days_remaining",
                     "products", "skus"],
            params=[InsightParam(name="within_days", kind="int", default=90,
                                 minimum=1, maximum=365)],
        ),
        InsightSpec(
            id="bestsellers-missing-image",
            title="Best sellers with no primary image",
            question="Which top-ranking products in their category are missing "
                     "a media role that category requires?",
            why="The missing image is a finding the record view already makes. "
                "What it cannot say is which of them matters this week - and a "
                "best seller with no pack shot is a different morning's work "
                "from a dead line with no pack shot.",
            domains=[D.MEDIA, D.SALES, D.CATEGORY],
            columns=["sku", "name", "category", "market", "period", "units",
                     "missing_media"],
            params=[InsightParam(name="rank", kind="int", default=1,
                                 minimum=1, maximum=10)],
        ),
        InsightSpec(
            id="stock-cannot-ship",
            title="Stocked where it cannot lawfully ship",
            question="Which stock sits in a depot that serves a market the "
                     "product is not certified for?",
            why="Nobody did anything wrong. The depot is doing its job, the "
                "certificate is valid, the market rule is right, and no single "
                "system can see all three at once. It stops a shipment anyway, "
                "and this is the only view in the platform that can find it.",
            domains=[D.WAREHOUSE, D.COMPLIANCE, D.CORE],
            columns=["sku", "name", "warehouse", "markets", "regulation",
                     "holds", "on_hand"],
        ),
        InsightSpec(
            id="cross-sell-candidates",
            title="Cross-sell candidates",
            question="Which products from different categories does marketing "
                     "already put in the same campaign?",
            why="The catalog never says two products belong together; a "
                "shopper reads that claim on every page. Where a campaign has "
                "made it more than once, somebody has already decided - and "
                "the merchandising has not caught up.",
            domains=[D.MARKETING, D.CORE],
            columns=["product", "pairs_with", "shared_campaigns", "category",
                     "pairs_with_category", "cross_category"],
            params=[InsightParam(name="min_campaigns", kind="int", default=2,
                                 minimum=1, maximum=10)],
        ),
        InsightSpec(
            id="weakest-media-coverage",
            title="Category subtrees with the weakest imagery",
            question="Which parts of the taxonomy are furthest from the media "
                     "their branch requires?",
            why="Photography is booked by category, not by SKU. Knowing that "
                "eleven variants are short of a picture is not a brief; "
                "knowing which shelf they are on is one. Nothing in this view "
                "is invented.",
            domains=[D.MEDIA, D.CATEGORY],
            columns=["category", "variants", "missing_media", "coverage_pct"],
            params=[InsightParam(name="level", kind="int", default=2,
                                 minimum=1, maximum=3)],
        ),
        InsightSpec(
            id="supplier-concentration",
            title="Supplier concentration risk",
            question="Which categories depend on a single supplier?",
            why="Invisible product by product and obvious the moment the "
                "category is the unit. One supplier failing an audit takes a "
                "shelf with it. Also entirely real - the supplier is the one "
                "the catalog has always carried.",
            domains=[D.CORE, D.CATEGORY],
            columns=["category", "supplier", "products", "of_products",
                     "share_pct", "suppliers_in_category"],
            params=[InsightParam(name="share_pct", kind="int", default=60,
                                 minimum=25, maximum=100),
                    InsightParam(name="level", kind="int", default=2,
                                 minimum=1, maximum=3)],
        ),
    )
}

#: id -> the function that answers it in process. Deliberately a second table
#: rather than a field on the spec: the spec is a contract the UI reads, and
#: hanging a callable off it would put an unserialisable object in a response.
RUNNERS = {
    "certifications-expiring": certifications_expiring,
    "bestsellers-missing-image": bestsellers_missing_image,
    "stock-cannot-ship": stock_cannot_ship,
    "cross-sell-candidates": cross_sell_candidates,
    "weakest-media-coverage": weakest_media_coverage,
    "supplier-concentration": supplier_concentration,
}


def bind(insight_id: str, params: dict | None) -> dict:
    """Check an id against the allowlist and coerce its parameters.

    Both halves refuse rather than guess. An unknown id never reaches a driver,
    and a parameter outside its declared bounds is a 400 rather than a query
    that scans the graph because somebody typed a large number.
    """
    from sc.kg import BadRequest

    spec = CATALOGUE.get(insight_id)
    if spec is None:
        raise BadRequest(
            f"unknown insight {insight_id!r} - "
            f"expected one of {', '.join(sorted(CATALOGUE))}")

    supplied = params or {}
    unknown = set(supplied) - {p.name for p in spec.params}
    if unknown:
        raise BadRequest(
            f"{insight_id} takes no parameter {', '.join(sorted(unknown))}")

    bound: dict[str, object] = {}
    for param in spec.params:
        value = supplied.get(param.name, param.default)
        if param.kind == "int":
            try:
                number = int(value)
            except (TypeError, ValueError) as exc:
                raise BadRequest(
                    f"{param.name} must be a whole number") from exc
            if param.minimum is not None and number < param.minimum:
                raise BadRequest(
                    f"{param.name} must be at least {param.minimum}")
            if param.maximum is not None and number > param.maximum:
                raise BadRequest(
                    f"{param.name} must be at most {param.maximum}")
            bound[param.name] = number
        elif param.kind == "enum":
            if param.options and str(value) not in param.options:
                raise BadRequest(
                    f"{param.name} must be one of {', '.join(param.options)}")
            bound[param.name] = str(value)
        else:
            bound[param.name] = str(value)
    return bound
