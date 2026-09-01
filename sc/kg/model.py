"""The shape of the knowledge graph, declared as data.

Everything else in ``sc/kg/`` reads this file and nothing else decides what a
node is. The projection asks it which domain a label belongs to, the Cypher
builders ask it which property is a label's business key, and the schema test
asks it whether ``schema.cypher`` declares a constraint for every key named
here. One statement of the model, three readers - so a label added without a
key, or a key with no constraint behind it, is a test failure rather than a
subgraph that silently duplicates on the second load.

**Why the maps are exhaustive rather than defaulted.** ``DOMAIN_OF`` could have
returned ``CORE`` for anything it did not recognise, and a new label would then
render in the colour of the product spine and be filtered by the wrong chip. A
``KeyError`` at import is the cheaper failure: it happens once, on the machine
of the person who added the label.

**Why ``synthetic`` is per label rather than per node.** Four of the seven
domains have no source data anywhere in this estate. Which of them a node came
from is a property of its *kind*, not of the individual row, and recording it
here means the ingestion cannot forget to stamp it and the legend cannot
disagree with the graph.
"""

from __future__ import annotations

from sc.contracts import GraphDomain, GraphNodeLabel, GraphRelType

L = GraphNodeLabel
R = GraphRelType
D = GraphDomain


# ---------------------------------------------------------------------------
# Labels

#: Which domain each label belongs to. The UI colours by this and the domain
#: filter chips select by it, so every label needs an entry - see the module
#: docstring for why there is no default.
DOMAIN_OF: dict[GraphNodeLabel, GraphDomain] = {
    L.PRODUCT: D.CORE,
    L.VARIANT: D.CORE,
    L.SUPPLIER: D.CORE,

    L.CATEGORY: D.CATEGORY,
    L.ATTRIBUTE: D.CATEGORY,
    L.ATTRIBUTE_VALUE: D.CATEGORY,

    L.CERTIFICATE: D.COMPLIANCE,
    L.REGULATION: D.COMPLIANCE,
    L.MARKET: D.COMPLIANCE,
    # Derived from the catalog's own `specs.battery_type`, which forty-three
    # variants carry: a lithium cell is UN3481 and a coin cell UN3091, both
    # Class 9. Not declared anywhere, and not invented either.
    L.HAZMAT_CLASS: D.COMPLIANCE,

    L.WAREHOUSE: D.WAREHOUSE,
    L.STORAGE_LOCATION: D.WAREHOUSE,
    L.STOCK_LEVEL: D.WAREHOUSE,

    L.MEDIA_ASSET: D.MEDIA,

    L.CHANNEL: D.SALES,
    L.LISTING: D.SALES,
    L.PRICE_RECORD: D.SALES,
    L.SALES_FACT: D.SALES,

    L.CAMPAIGN: D.MARKETING,
    L.PROMOTION: D.MARKETING,
    L.KEYWORD: D.MARKETING,
    L.PERSONA: D.MARKETING,
}

#: The property that identifies one of these, uniquely, for a human.
#:
#: This is the MERGE key, which is why it is a business key and never a
#: generated id: MERGE on a surrogate would insert a second copy of the same
#: warehouse on every load, and "idempotent" would be a claim rather than a
#: property. Where the source has no natural key - a stock level, a price, a
#: month's sales - the ingestion composes a deterministic one from the parts
#: that identify it, and that composition is the key.
BUSINESS_KEY: dict[GraphNodeLabel, str] = {
    L.PRODUCT: "id",
    L.VARIANT: "id",
    L.SUPPLIER: "id",

    L.CATEGORY: "code",
    L.ATTRIBUTE: "path",
    L.ATTRIBUTE_VALUE: "id",

    L.CERTIFICATE: "ref",
    L.REGULATION: "code",
    L.MARKET: "code",
    L.HAZMAT_CLASS: "code",

    L.WAREHOUSE: "code",
    L.STORAGE_LOCATION: "code",
    L.STOCK_LEVEL: "id",

    L.MEDIA_ASSET: "assetId",

    L.CHANNEL: "id",
    L.LISTING: "id",
    L.PRICE_RECORD: "id",
    L.SALES_FACT: "id",

    L.CAMPAIGN: "id",
    L.PROMOTION: "id",
    L.KEYWORD: "term",
    L.PERSONA: "code",
}

#: A second uniqueness constraint, where a label has two names people use.
#:
#: Only ``Variant.sku`` qualifies today. It is a genuine alternate key - the
#: catalogue identifies a variant as ``VAR-01B`` and every merchant types
#: ``NAV-AP300-MAX`` - and both must be unique or a SKU lookup can return two
#: rows. Products deliberately have no SKU; see ``sc.contracts.Product``.
ALTERNATE_KEY: dict[GraphNodeLabel, str] = {
    L.VARIANT: "sku",
}

#: Labels whose nodes are generated from the seed rather than read from the
#: retailer's own data.
#:
#: ``Certificate`` is in here and the call is deliberate: the *reference* on it
#: is real - ``compliance.certificate_ref`` is carried on seventy-four variants
#: in the catalog - but the issuer and the expiry date are not, and the expiry
#: is the whole of what "expiring within ninety days" reads. A node whose
#: interesting property is invented is an invented node, whatever its key.
SYNTHETIC: frozenset[GraphNodeLabel] = frozenset({
    L.CERTIFICATE, L.REGULATION, L.MARKET, L.HAZMAT_CLASS,
    L.WAREHOUSE, L.STORAGE_LOCATION, L.STOCK_LEVEL,
    L.PRICE_RECORD, L.SALES_FACT,
    L.CAMPAIGN, L.PROMOTION, L.KEYWORD, L.PERSONA,
})


# ---------------------------------------------------------------------------
# Relationships

#: The domain an edge belongs to, and the two ends it is allowed to join.
#:
#: The endpoints are not decoration either. They are what lets a test read the
#: relationship list back and confirm that every pattern in ``schema.cypher``
#: and every edge the projection emits joins labels this model actually admits
#: - so a ``(:Campaign)-[:PROMOTES]->(:Warehouse)`` is caught by a test rather
#: than by a merchant wondering why a depot is in a campaign.
#:
#: An edge's domain is the domain of the thing it *reaches*, not of the thing it
#: leaves. Turning the Warehouse chip off has to remove the edges into the
#: depots as well as the depots, and both ends of a core-to-core edge are core
#: anyway, so this rule has no awkward cases.
ENDPOINTS: dict[GraphRelType, tuple[tuple[GraphNodeLabel, ...],
                                    tuple[GraphNodeLabel, ...]]] = {
    # Core
    R.HAS_VARIANT: ((L.PRODUCT,), (L.VARIANT,)),
    R.SUPPLIED_BY: ((L.PRODUCT,), (L.SUPPLIER,)),
    # Category
    R.IN_CATEGORY: ((L.PRODUCT,), (L.CATEGORY,)),
    R.PARENT_OF: ((L.CATEGORY,), (L.CATEGORY,)),
    R.HAS_ATTRIBUTE: ((L.VARIANT,), (L.ATTRIBUTE_VALUE,)),
    R.OF_ATTRIBUTE: ((L.ATTRIBUTE_VALUE,), (L.ATTRIBUTE,)),
    # Compliance
    R.CERTIFIED_BY: ((L.VARIANT,), (L.CERTIFICATE,)),
    R.SATISFIES: ((L.CERTIFICATE,), (L.REGULATION,)),
    R.REQUIRES: ((L.MARKET,), (L.REGULATION,)),
    R.RESTRICTED_IN: ((L.PRODUCT,), (L.MARKET,)),
    R.CLASSIFIED_AS: ((L.PRODUCT,), (L.HAZMAT_CLASS,)),
    # Warehouse
    R.HAS_STOCK: ((L.VARIANT,), (L.STOCK_LEVEL,)),
    R.AT_WAREHOUSE: ((L.STOCK_LEVEL,), (L.WAREHOUSE,)),
    R.SERVES: ((L.WAREHOUSE,), (L.MARKET,)),
    R.HAS_LOCATION: ((L.WAREHOUSE,), (L.STORAGE_LOCATION,)),
    # Media
    R.HAS_MEDIA: ((L.VARIANT,), (L.MEDIA_ASSET,)),
    # Sales
    R.LISTED_ON: ((L.VARIANT,), (L.LISTING,)),
    R.ON_CHANNEL: ((L.LISTING,), (L.CHANNEL,)),
    R.PRICED_AT: ((L.VARIANT,), (L.PRICE_RECORD,)),
    R.FOR_VARIANT: ((L.SALES_FACT,), (L.VARIANT,)),
    # Two sources, because a price and a month's takings are both facts about
    # a market. `edge_domain` reads the far end, so both still colour as
    # compliance-adjacent Market nodes rather than as two different things.
    R.IN_MARKET: ((L.SALES_FACT, L.PRICE_RECORD), (L.MARKET,)),
    # Marketing
    R.PROMOTES: ((L.CAMPAIGN,), (L.PRODUCT,)),
    R.TARGETS: ((L.CAMPAIGN,), (L.PERSONA,)),
    R.APPLIES_TO: ((L.PROMOTION,), (L.VARIANT,)),
    R.RANKS_FOR: ((L.VARIANT,), (L.KEYWORD,)),
    # Product to product
    R.COMPLEMENTS: ((L.PRODUCT,), (L.PRODUCT,)),
    R.SIMILAR_TO: ((L.PRODUCT,), (L.PRODUCT,)),
}


# ---------------------------------------------------------------------------
# Search and traversal

#: What the type-ahead looks at. Labels a merchant would name out loud, and the
#: properties they would name them by. Deliberately excludes the join nodes -
#: nobody searches for a StockLevel or an AttributeValue, and offering them
#: would bury the nine things somebody does search for.
SEARCHABLE: tuple[GraphNodeLabel, ...] = (
    L.PRODUCT, L.VARIANT, L.CATEGORY, L.SUPPLIER, L.WAREHOUSE,
    L.CAMPAIGN, L.CERTIFICATE, L.KEYWORD, L.MARKET,
)

#: The properties the full-text index covers, across all of ``SEARCHABLE``.
#:
#: ``id`` is in here because people type internal ids. ``sc/readiness/search.py``
#: already treats ``entity_id`` as an exact-match band for that reason, and a
#: type-ahead that could not find ``PRD-01`` or ``SUP-19`` would be a search
#: that fails on the name half the estate uses. Note that the standard analyser
#: breaks ``PRD-01`` on the hyphen, so the builder also matches an exact id
#: directly rather than relying on the index alone.
SEARCH_PROPERTIES: tuple[str, ...] = ("name", "code", "sku", "term", "ref", "id")

#: The name of the full-text index. Named once, here, because the builder that
#: queries it and the schema that creates it must agree and a typo between them
#: is a runtime error on an otherwise healthy graph.
SEARCH_INDEX = "kgSearch"

#: How far a neighbourhood may reach.
#:
#: Three, and not configurable. Cypher has no syntax for a parameterised
#: variable-length bound - ``*1..$depth`` does not parse - so a depth that came
#: from a request would have to be pasted into the pattern, and that is an
#: injection point rather than a setting. ``sc.kg.cypher`` turns this into a
#: closed set of literal patterns and refuses anything outside it.
#:
#: Three hops is also more graph than anybody reads: from a variant that is
#: already the market, the regulation and the certificate that satisfies it.
MAX_DEPTH = 3

#: The most nodes one view will draw before it says it truncated.
#:
#: Past this the picture stops being a picture. The response carries what was
#: dropped and from which domains, because a graph that quietly drew two
#: hundred of eight hundred would be read as a graph of two hundred.
DEFAULT_MAX_NODES = 200


def domain_of(label: GraphNodeLabel) -> GraphDomain:
    """Which domain a label belongs to. Raises on an unmapped label."""
    return DOMAIN_OF[label]


def edge_domain(rel: GraphRelType) -> GraphDomain:
    """The domain of the thing an edge reaches - see ``ENDPOINTS``."""
    return DOMAIN_OF[ENDPOINTS[rel][1][0]]


def is_synthetic(label: GraphNodeLabel) -> bool:
    """Whether nodes of this label are generated rather than the retailer's."""
    return label in SYNTHETIC


def keys_of(label: GraphNodeLabel) -> tuple[str, ...]:
    """Every property that must be unique for this label, business key first."""
    alt = ALTERNATE_KEY.get(label)
    return (BUSINESS_KEY[label],) if alt is None else (BUSINESS_KEY[label], alt)
