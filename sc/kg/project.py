"""Turning the catalog and the reference pack into one graph.

Pure. No database, no driver, no MCP - it takes a ``Baseline`` and a list of
``(system_id, event_type, payload)`` triples and returns nodes and edges. That
is the whole point of the file: **two sources feed it and they must not be able
to disagree.**

``sc/kg/source_db.py`` reads those triples out of SQLite for the in-process
backend. ``scripts/load_graph.py`` reads the identical triples over MCP for the
Neo4j loader. Both hand them here, so the graph a merchant explores with no
Neo4j running and the graph Cypher answers are the same graph derived by the
same code - not two implementations that happen to agree today.

**It dispatches on event type, never on system id.** ``sc/estate/manifest.py``
is where systems are named and ``tests/test_estate.py`` enforces that; this file
would fail that test the moment it hard-coded a carrier, and rightly - a
projection that knew which system sent a stock snapshot would break when the
manifest moved it.

**What is left out, and why.** Only the newest stock snapshot per depot becomes
a ``StockLevel``. Ten weeks of history is what the back-office console renders
and what the events hold; the graph answers "where is this stocked now", and
projecting six thousand historical counts would bury the picture under a
timeline nobody asked it for. Sales facts keep every period, because the
questions there are explicitly about a month.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sc.contracts import GraphDomain, GraphEdge, GraphNode, GraphNodeLabel
from sc.contracts import GraphRelType as R
from sc.kg import domains as dom
from sc.kg import model

L = GraphNodeLabel


@dataclass(frozen=True)
class Graph:
    """Nodes, edges, and the adjacency the traversals walk.

    ``adjacency`` maps a node id to the indices of every edge touching it, in
    *both* directions. A neighbourhood is not a hierarchy: somebody looking at
    a certificate wants the products under it as much as somebody looking at a
    product wants the certificate above it, and a directed walk would answer
    only one of those.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    adjacency: dict[str, list[int]] = field(default_factory=dict)

    def neighbours(self, node_id: str) -> list[tuple[str, int]]:
        """(other node id, edge index) for everything one hop away."""
        out = []
        for index in self.adjacency.get(node_id, ()):
            edge = self.edges[index]
            other = edge.target if edge.source == node_id else edge.source
            out.append((other, index))
        return out


def node_id(label: GraphNodeLabel, key: str) -> str:
    """The graph's own identifier for a node.

    Prefixed with the label because business keys are only unique *within* a
    label - a category code and a supplier id have no reason to stay apart on
    their own - and because a reader looking at ``Warehouse:WH-LEEDS`` in a
    payload knows what they are holding without a lookup.
    """
    return f"{label.value}:{key}"


class _Builder:
    """Accumulates nodes and edges, keeping both idempotent.

    Adding the same node twice merges properties rather than replacing, because
    a variant is named by the catalog and then mentioned again by a stock line,
    and the second mention knows less than the first.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._seen_edges: set[str] = set()

    def node(self, label: GraphNodeLabel, key: str, name: str,
             **props: object) -> str:
        identifier = node_id(label, key)
        existing = self.nodes.get(identifier)
        if existing is None:
            self.nodes[identifier] = GraphNode(
                id=identifier, label=label, domain=model.DOMAIN_OF[label],
                name=name, synthetic=model.is_synthetic(label),
                props={k: v for k, v in props.items() if v is not None})
        else:
            merged = dict(existing.props)
            merged.update({k: v for k, v in props.items() if v is not None})
            self.nodes[identifier] = existing.model_copy(
                update={"props": merged,
                        "name": existing.name or name})
        return identifier

    def edge(self, rel: R, source: str, target: str, **props: object) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        identifier = f"{source}|{rel.value}|{target}"
        if identifier in self._seen_edges:
            return
        self._seen_edges.add(identifier)
        self.edges.append(GraphEdge(
            id=identifier, source=source, target=target, type=rel,
            domain=model.edge_domain(rel),
            # An edge is invented when either end is. A real product joined to
            # an invented depot is not a real fact about that product.
            synthetic=(self.nodes[source].synthetic
                       or self.nodes[target].synthetic),
            props={k: v for k, v in props.items() if v is not None}))

    def finish(self) -> Graph:
        adjacency: dict[str, list[int]] = defaultdict(list)
        for index, edge in enumerate(self.edges):
            adjacency[edge.source].append(index)
            adjacency[edge.target].append(index)

        degree = {nid: len(indices) for nid, indices in adjacency.items()}
        nodes = {nid: n.model_copy(update={"degree": degree.get(nid, 0)})
                 for nid, n in self.nodes.items()}
        return Graph(nodes=nodes, edges=self.edges, adjacency=dict(adjacency))


# ---------------------------------------------------------------------------
# The catalog half - the retailer's own data


def _categories(builder: _Builder, base) -> None:
    """Every taxonomy node the catalog actually uses, and its ancestors.

    Built from the paths products carry rather than from the taxonomy map, so
    a branch nobody stocks does not appear as an empty category a merchant can
    click into and find nothing in.
    """
    labels = dict(base.catalog.taxonomy.get("internal", {}))
    paths: set[str] = set()
    for product in base.products.values():
        parts = product.category.split(".")
        for depth in range(1, len(parts) + 1):
            paths.add(".".join(parts[:depth]))

    for path in sorted(paths):
        parts = path.split(".")
        builder.node(L.CATEGORY, path,
                     labels.get(path) or parts[-1].replace("-", " ").title(),
                     code=path, path=path, level=len(parts))

    for path in sorted(paths):
        parts = path.split(".")
        if len(parts) < 2:
            continue
        parent = ".".join(parts[:-1])
        builder.edge(R.PARENT_OF,
                     node_id(L.CATEGORY, parent), node_id(L.CATEGORY, path))


def _hazmat(builder: _Builder, base, variant_id: str, product_node: str) -> None:
    """Classify from the battery the catalog says the product contains.

    Derived, not declared. Forty-three variants carry ``specs.battery_type``
    and the value says what the cell is; a lithium cell shipped inside
    equipment is UN3481 and a lithium-metal coin cell UN3091, both Class 9.
    That is a real constraint on which depots may hold the thing, which is
    exactly why it is worth an edge.
    """
    value = str(base.attr_values.get((variant_id, "specs.battery_type"), "")).lower()
    if not value:
        return
    if "lithium-ion" in value or "lithium polymer" in value or "li-ion" in value:
        code, name = "UN3481", "Lithium-ion cells in equipment (Class 9)"
    elif "coin cell" in value or "lithium metal" in value or "cr20" in value:
        code, name = "UN3091", "Lithium-metal cells in equipment (Class 9)"
    else:
        return  # An alkaline cell is not dangerous goods.
    builder.node(L.HAZMAT_CLASS, code, name, code=code, hazardClass="9")
    builder.edge(R.CLASSIFIED_AS, product_node, node_id(L.HAZMAT_CLASS, code))


def from_catalog(base) -> _Builder:
    """Products, variants, suppliers, categories, attributes, media, listings.

    All of it the retailer's own. Nothing projected here is stamped synthetic,
    and that boundary is the reason the flag exists.
    """
    builder = _Builder()
    _categories(builder, base)

    for path, definition in sorted(base.attr_defs.items()):
        builder.node(L.ATTRIBUTE, path,
                     getattr(definition, "label", None) or path,
                     path=path, dtype=str(getattr(definition, "dtype", "")),
                     safetyClass=bool(getattr(definition, "safety_class", False)))

    for product_id in sorted(base.products):
        product = base.products[product_id]
        product_node = builder.node(
            L.PRODUCT, product_id, product.name,
            id=product_id, category=product.category,
            branch=product.category.split(".")[0],
            regulated=product.regulated,
            updatedAt=str(base.horizon_start))

        supplier_node = builder.node(L.SUPPLIER, product.supplier,
                                     product.supplier, id=product.supplier)
        builder.edge(R.SUPPLIED_BY, product_node, supplier_node)
        builder.edge(R.IN_CATEGORY, product_node,
                     node_id(L.CATEGORY, product.category))

        for variant_id in base.variants_of.get(product_id, []):
            variant = base.variants[variant_id]
            variant_node = builder.node(
                L.VARIANT, variant_id, variant.name,
                id=variant_id, sku=getattr(variant, "sku", "") or "",
                isBase=variant.is_base, category=product.category,
                branch=product.category.split(".")[0],
                updatedAt=str(base.horizon_start))
            builder.edge(R.HAS_VARIANT, product_node, variant_node)
            _hazmat(builder, base, variant_id, product_node)

            required = set(
                (base.catalog.profile.get("branches", {})
                 .get(product.category.split(".")[0], {}) or {})
                .get("required_media", []))
            held = {asset.role for asset in base.media_by_entity.get(variant_id, [])}
            for asset in base.media_by_entity.get(variant_id, []):
                asset_node = builder.node(
                    L.MEDIA_ASSET, asset.id, asset.alt_text or asset.id,
                    assetId=asset.id, role=str(asset.role), uri=asset.uri,
                    system=asset.system, width=asset.width, height=asset.height,
                    # "Primary" means the first role the branch demands. A
                    # category that needs a pack front and an ingredient panel
                    # has a different primary from one that needs a hero.
                    primary=str(asset.role) in required,
                    updatedAt=str(base.horizon_start))
                builder.edge(R.HAS_MEDIA, variant_node, asset_node,
                             role=str(asset.role),
                             primary=str(asset.role) in required)

            # Recorded on the variant so a query can ask the question without
            # walking every asset: what the branch demands and what is absent.
            if required:
                builder.nodes[variant_node] = builder.nodes[variant_node].model_copy(
                    update={"props": {**builder.nodes[variant_node].props,
                                      "requiredMedia": sorted(required),
                                      "missingMedia": sorted(required - held)}})

            for listing_id in base.listings_of.get(variant_id, []):
                listing = base.listings[listing_id]
                listing_node = builder.node(
                    L.LISTING, listing_id, listing_id, id=listing_id,
                    status=str(listing.status),
                    publishedVersion=listing.published_version)
                builder.edge(R.LISTED_ON, variant_node, listing_node)
                channel = base.channels.get(listing.channel_id)
                channel_node = builder.node(
                    L.CHANNEL, listing.channel_id,
                    channel.name if channel else listing.channel_id,
                    id=listing.channel_id,
                    kind=str(channel.kind) if channel else "")
                builder.edge(R.ON_CHANNEL, listing_node, channel_node)

    for (entity_id, path), value in sorted(base.attr_values.items()):
        variant_node = node_id(L.VARIANT, entity_id)
        if variant_node not in builder.nodes or path not in base.attr_defs:
            continue
        source = base.attr_sources.get((entity_id, path))
        # Named for the attribute rather than for the value. A value can be a
        # list of claims or a paragraph of ingredients, and a node label that
        # is forty words of prose makes both the picture and a path narrative
        # unreadable. The value is still on the node, where a side panel reads
        # it in full.
        rendered = str(value)
        if len(rendered) > 40:
            rendered = rendered[:37] + "..."
        value_node = builder.node(
            L.ATTRIBUTE_VALUE, f"{entity_id}:{path}",
            f"{path.rsplit('.', 1)[-1]}: {rendered}",
            id=f"{entity_id}:{path}", path=path, value=str(value),
            system=getattr(source, "system", "") if source else "")
        builder.edge(R.HAS_ATTRIBUTE, variant_node, value_node,
                     path=path, value=str(value))
        builder.edge(R.OF_ATTRIBUTE, value_node, node_id(L.ATTRIBUTE, path))

    return builder


# ---------------------------------------------------------------------------
# The reference half - the four back-office systems


def _latest_stock(reference: list[tuple[str, str, dict]]) -> list[dict]:
    """The newest snapshot per depot.

    See the module docstring: the graph answers where a thing is stocked *now*.
    A depot's ten weeks of history is what the back-office console draws, and
    projecting all of it would put six thousand counts into a picture whose
    question is "which depots hold this".
    """
    newest: dict[str, dict] = {}
    for _, event_type, payload in reference:
        if event_type != "STOCK_SNAPSHOT":
            continue
        depot = payload["warehouse_id"]
        if (depot not in newest
                or payload["week_start"] > newest[depot]["week_start"]):
            newest[depot] = payload
    return [newest[depot] for depot in sorted(newest)]


def from_reference(builder: _Builder, base,
                   reference: list[tuple[str, str, dict]]) -> None:
    """Everything the four back-office systems delivered.

    Dispatches on ``event_type``. A carrier is never named here - see the
    module docstring - so a payload is projected the same way whichever system
    turns out to have sent it.
    """
    campaigns: list[dict] = []
    sales_rank: dict[str, int] = {}

    for _, event_type, payload in reference:
        if event_type == "MARKET_RULE":
            market = builder.node(
                L.MARKET, payload["market_id"], payload["market_name"],
                code=payload["market_id"], country=payload["country"],
                minAgeEnforced=payload["min_age_enforced"])
            for code in payload["requires_regulations"]:
                builder.node(L.REGULATION, code, code, code=code)
                builder.edge(R.REQUIRES, market, node_id(L.REGULATION, code))
            # A market that will not take a category at all. Recorded against
            # the products in it rather than the category, because it is the
            # product a merchant is looking at when they need to know.
            for prefix in payload["restricted_categories"]:
                for product_id, product in base.products.items():
                    if product.category.split(".")[0] == prefix:
                        builder.edge(R.RESTRICTED_IN,
                                     node_id(L.PRODUCT, product_id), market,
                                     reason=f"{prefix} may not be sold in "
                                            f"{payload['market_name']}")

        elif event_type == "REGULATION":
            builder.node(
                L.REGULATION, payload["regulation_id"], payload["title"],
                code=payload["regulation_id"], authority=payload["authority"],
                acceptedSchemes=payload["accepted_schemes"],
                appliesTo=payload["applies_to_categories"])

        elif event_type == "CERTIFICATE":
            certificate = builder.node(
                L.CERTIFICATE, payload["certificate_ref"],
                payload["certificate_ref"],
                ref=payload["certificate_ref"], scheme=payload["scheme"],
                issuer=payload["issuer"], issuedOn=payload["issued_on"],
                expiresOn=payload["expires_on"], status=payload["status"],
                updatedAt=payload["issued_on"])
            for code in payload["satisfies"]:
                builder.node(L.REGULATION, code, code, code=code)
                builder.edge(R.SATISFIES, certificate,
                             node_id(L.REGULATION, code))
            for variant_id in payload["scope"]:
                builder.edge(R.CERTIFIED_BY, node_id(L.VARIANT, variant_id),
                             certificate)

        elif event_type == "AUDIENCE":
            builder.node(
                L.PERSONA, payload["audience_id"], payload["name"],
                code=payload["audience_id"],
                description=payload["description"])
            for term in payload["affinity_keywords"]:
                builder.node(L.KEYWORD, term.lower(), term, term=term.lower())

        elif event_type == "CAMPAIGN":
            campaigns.append(payload)

        elif event_type == "PROMOTION":
            promotion = builder.node(
                L.PROMOTION, payload["promotion_id"], payload["mechanic"],
                id=payload["promotion_id"], mechanic=payload["mechanic"],
                depthPct=payload["depth_pct"], startsOn=payload["starts_on"],
                endsOn=payload["ends_on"], marketCode=payload["market_id"])
            for variant_id in payload["members"]:
                builder.edge(R.APPLIES_TO, promotion,
                             node_id(L.VARIANT, variant_id))

        elif event_type == "PRICE_LIST":
            market_code = payload["market_id"]
            for line in payload["lines"]:
                key = f"{line['variant_id']}:{market_code}"
                price = builder.node(
                    L.PRICE_RECORD, key,
                    f"{line['list_price']} {line['currency']}",
                    id=key, listPrice=line["list_price"],
                    currency=line["currency"], priceBand=line["price_band"],
                    effectiveFrom=line["effective_from"],
                    marketCode=market_code, updatedAt=line["effective_from"])
                builder.edge(R.PRICED_AT,
                             node_id(L.VARIANT, line["variant_id"]), price)
                builder.edge(R.IN_MARKET, price, node_id(L.MARKET, market_code))

        elif event_type == "SALES_PERIOD":
            market_code = payload["market_id"]
            period = str(payload["period_start"])[:7]
            for line in payload["lines"]:
                key = f"{line['variant_id']}:{market_code}:{period}"
                fact = builder.node(
                    L.SALES_FACT, key, f"{line['units']} units {period}",
                    id=key, period=period, units=line["units"],
                    revenue=line["revenue"],
                    rankInCategory=line["rank_in_category"],
                    category=line["category"], marketCode=market_code,
                    currency=payload["currency"],
                    updatedAt=str(payload["period_end"]))
                builder.edge(R.FOR_VARIANT, fact,
                             node_id(L.VARIANT, line["variant_id"]))
                builder.edge(R.IN_MARKET, fact, node_id(L.MARKET, market_code))
                best = sales_rank.get(line["variant_id"])
                if best is None or line["rank_in_category"] < best:
                    sales_rank[line["variant_id"]] = line["rank_in_category"]

    _warehouses(builder, reference)
    _campaigns(builder, base, campaigns, sales_rank)


def _warehouses(builder: _Builder,
                reference: list[tuple[str, str, dict]]) -> None:
    """Depots, their storage locations, the markets they serve, and stock."""
    for warehouse in dom.WAREHOUSES:
        node = builder.node(
            L.WAREHOUSE, warehouse.code, warehouse.name,
            code=warehouse.code, country=warehouse.country,
            region=warehouse.region,
            temperatureControlled=warehouse.temperature_controlled,
            hazmatLicensed=warehouse.hazmat_licensed)
        for kind, label in dom.LOCATION_KINDS:
            code = f"{warehouse.code}-{kind}"
            builder.node(L.STORAGE_LOCATION, code, f"{warehouse.name} {label}",
                         code=code, kind=kind)
            builder.edge(R.HAS_LOCATION, node, node_id(L.STORAGE_LOCATION, code))
        for market_code in warehouse.serves:
            builder.edge(R.SERVES, node, node_id(L.MARKET, market_code))

    for snapshot in _latest_stock(reference):
        depot = snapshot["warehouse_id"]
        for line in snapshot["lines"]:
            key = f"{line['variant_id']}:{depot}:{snapshot['week_start']}"
            level = builder.node(
                L.STOCK_LEVEL, key,
                f"{line['on_hand']} on hand at {depot}",
                id=key, onHandQty=line["on_hand"],
                allocated=line["allocated"],
                reorderPoint=line["reorder_point"],
                belowReorderPoint=line["on_hand"] < line["reorder_point"],
                weekStart=snapshot["week_start"], warehouseCode=depot,
                updatedAt=snapshot["week_start"])
            builder.edge(R.HAS_STOCK,
                         node_id(L.VARIANT, line["variant_id"]), level)
            builder.edge(R.AT_WAREHOUSE, level, node_id(L.WAREHOUSE, depot))


def _campaigns(builder: _Builder, base, campaigns: list[dict],
               sales_rank: dict[str, int]) -> None:
    """Campaigns, their keywords, and the two product-to-product edges.

    ``COMPLEMENTS`` cannot be derived one event at a time - it asks which
    products appear together in *more than one* campaign, which is a question
    about the whole set. That is why campaigns are collected first and joined
    here rather than projected as they arrive.

    Two campaigns rather than one because one is coincidence: a campaign with
    twenty members puts a great many unrelated pairs in a room together, and an
    edge drawn from that would make the cross-sell view a list of everything.
    """
    together: dict[tuple[str, str], int] = defaultdict(int)

    for payload in campaigns:
        campaign = builder.node(
            L.CAMPAIGN, payload["campaign_id"], payload["name"],
            id=payload["campaign_id"], startsOn=payload["starts_on"],
            endsOn=payload["ends_on"], objective=payload["objective"],
            marketCode=payload["market_id"], channels=payload["channels"],
            updatedAt=payload["starts_on"])
        builder.edge(R.TARGETS, campaign,
                     node_id(L.PERSONA, payload["audience_id"]))

        products: set[str] = set()
        for variant_id in payload["members"]:
            product_id = base.product_of_variant.get(variant_id)
            if product_id is None:
                continue
            products.add(product_id)
            builder.edge(R.PROMOTES, campaign, node_id(L.PRODUCT, product_id))
            for term in payload["keywords"]:
                builder.node(L.KEYWORD, term.lower(), term, term=term.lower())
                builder.edge(R.RANKS_FOR, node_id(L.VARIANT, variant_id),
                             node_id(L.KEYWORD, term.lower()),
                             # The position is the variant's own best sales
                             # rank, so a keyword edge carries something that
                             # was measured rather than a number invented to
                             # fill the field.
                             position=sales_rank.get(variant_id, 0))

        ordered = sorted(products)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                together[(left, right)] += 1

    for (left, right), shared in sorted(together.items()):
        if shared >= 2:
            builder.edge(R.COMPLEMENTS, node_id(L.PRODUCT, left),
                         node_id(L.PRODUCT, right), campaigns=shared)

    # Products in the same depth-2 subtree. **One partner each**, not three.
    #
    # Three was a clique: at two hops from a variant it pulled in sixty
    # sibling products and the picture became a blue mass with the six other
    # domains around the edge of it. The information was already there anyway -
    # two products sharing a Category node are visibly in the same category,
    # and SIMILAR_TO restates that with an invented score attached. One edge
    # keeps the relationship the model promises without letting it dominate
    # every neighbourhood it appears in.
    subtree: dict[str, list[str]] = defaultdict(list)
    for product_id, product in sorted(base.products.items()):
        subtree[".".join(product.category.split(".")[:2])].append(product_id)
    for members in subtree.values():
        for index, left in enumerate(members[:-1]):
            builder.edge(R.SIMILAR_TO, node_id(L.PRODUCT, left),
                         node_id(L.PRODUCT, members[index + 1]), score=0.5)


def build(base, reference: list[tuple[str, str, dict]] | None = None) -> Graph:
    """The whole graph, from the catalog and whatever reference data exists.

    ``reference`` empty is a supported state, not a degraded one. A checkout
    that has not generated the pack still gets products, variants, categories,
    media and channels - four of the seven domains - and the tab renders with
    three chips that filter to nothing rather than an error.
    """
    builder = from_catalog(base)
    if reference:
        from_reference(builder, base, reference)
    return builder.finish()


def domains_present(graph: Graph) -> dict[GraphDomain, int]:
    """How many nodes each domain contributed. What the legend counts."""
    tally: dict[GraphDomain, int] = {domain: 0 for domain in GraphDomain}
    for node in graph.nodes.values():
        tally[node.domain] += 1
    return tally
