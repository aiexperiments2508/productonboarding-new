// The knowledge graph's constraints and indexes.
//
// Applied statement by statement by `sc/kg/ingest.py` before any MERGE, and
// idempotent throughout: every statement is IF NOT EXISTS, so re-running this
// against a loaded graph is a no-op rather than an error. That is the same
// discipline `sc/schema.sql` keeps for SQLite, and this file sits beside the
// code that applies it for the same reason that one does.
//
// Three rules govern what is in here.
//
// 1. **A constraint on every business key, because MERGE is the loader.**
//    `sc/kg/model.py` names one key per label and the loader MERGEs on it. A
//    label whose key has no uniqueness constraint gets a second copy of every
//    node on the second load, and "idempotent" becomes a claim in a README
//    rather than a property of the database. `tests/test_kg_schema.py` reads
//    BUSINESS_KEY and ALTERNATE_KEY back and fails if either is unbacked.
//
// 2. **No range index on a constrained property.** A uniqueness constraint
//    creates its own backing index. Declaring one alongside it costs a second
//    index to maintain on every write and buys nothing.
//
// 3. **An index only where a query filters.** Every range index below names
//    the insight or lookup that reads it. An index nothing sorts or filters on
//    is write cost with no read to pay for it, which is why `updatedAt` is
//    indexed on the five high-volume labels a prune actually sweeps and not on
//    all twenty-three.

// ---------------------------------------------------------------------------
// Constraints - core
// ---------------------------------------------------------------------------

CREATE CONSTRAINT kg_product_id IF NOT EXISTS
FOR (n:Product) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT kg_variant_id IF NOT EXISTS
FOR (n:Variant) REQUIRE n.id IS UNIQUE;

// The alternate key, and it has to be a constraint of its own. The catalogue
// identifies a variant as VAR-01B and every merchant types NAV-AP300-MAX; both
// resolve to one node or a SKU lookup can return two. Products deliberately
// carry no SKU - see sc.contracts.Product - so there is no matching constraint
// for them and there should not be one.
CREATE CONSTRAINT kg_variant_sku IF NOT EXISTS
FOR (n:Variant) REQUIRE n.sku IS UNIQUE;

CREATE CONSTRAINT kg_supplier_id IF NOT EXISTS
FOR (n:Supplier) REQUIRE n.id IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - category
// ---------------------------------------------------------------------------

CREATE CONSTRAINT kg_category_code IF NOT EXISTS
FOR (n:Category) REQUIRE n.code IS UNIQUE;

CREATE CONSTRAINT kg_attribute_path IF NOT EXISTS
FOR (n:Attribute) REQUIRE n.path IS UNIQUE;

// Composed by the loader as "<variantId>:<attributePath>" - the pair that
// identifies one held value. See the BUSINESS_KEY note in sc/kg/model.py on
// why a composed key is still a business key and a surrogate would not be.
CREATE CONSTRAINT kg_attribute_value_id IF NOT EXISTS
FOR (n:AttributeValue) REQUIRE n.id IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - compliance
// ---------------------------------------------------------------------------

// The ref is the real one: compliance.certificate_ref, carried on seventy-four
// variants in the catalog. Two variants citing UKCA-2411 must reach the same
// certificate node or "products sharing a certification" has nothing to share.
CREATE CONSTRAINT kg_certificate_ref IF NOT EXISTS
FOR (n:Certificate) REQUIRE n.ref IS UNIQUE;

CREATE CONSTRAINT kg_regulation_code IF NOT EXISTS
FOR (n:Regulation) REQUIRE n.code IS UNIQUE;

CREATE CONSTRAINT kg_market_code IF NOT EXISTS
FOR (n:Market) REQUIRE n.code IS UNIQUE;

CREATE CONSTRAINT kg_hazmat_class_code IF NOT EXISTS
FOR (n:HazmatClass) REQUIRE n.code IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - warehouse
// ---------------------------------------------------------------------------

CREATE CONSTRAINT kg_warehouse_code IF NOT EXISTS
FOR (n:Warehouse) REQUIRE n.code IS UNIQUE;

CREATE CONSTRAINT kg_storage_location_code IF NOT EXISTS
FOR (n:StorageLocation) REQUIRE n.code IS UNIQUE;

// Composed as "<variantId>:<warehouseCode>:<weekStart>". One line of one
// depot's weekly snapshot, and the week is in the key because nine snapshots
// of the same pallet are nine facts and not one fact restated.
CREATE CONSTRAINT kg_stock_level_id IF NOT EXISTS
FOR (n:StockLevel) REQUIRE n.id IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - media
// ---------------------------------------------------------------------------

// Labelled MediaNode rather than MediaAsset: MediaAsset is already a model in
// sc/contracts.py, and a graph label shadowing a contract name makes every
// stack trace ambiguous about which of the two is in hand.
CREATE CONSTRAINT kg_media_node_asset_id IF NOT EXISTS
FOR (n:MediaNode) REQUIRE n.assetId IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - sales
// ---------------------------------------------------------------------------

CREATE CONSTRAINT kg_channel_id IF NOT EXISTS
FOR (n:Channel) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT kg_listing_id IF NOT EXISTS
FOR (n:Listing) REQUIRE n.id IS UNIQUE;

// Composed as "<variantId>:<marketCode>". A price is issued per market here,
// not per channel - the price list the trading system sends is a market's, and
// bending it into a per-channel shape would be modelling the diagram rather
// than the data.
CREATE CONSTRAINT kg_price_record_id IF NOT EXISTS
FOR (n:PriceRecord) REQUIRE n.id IS UNIQUE;

// Composed as "<variantId>:<marketCode>:<period>".
CREATE CONSTRAINT kg_sales_fact_id IF NOT EXISTS
FOR (n:SalesFact) REQUIRE n.id IS UNIQUE;

// ---------------------------------------------------------------------------
// Constraints - marketing
// ---------------------------------------------------------------------------

CREATE CONSTRAINT kg_campaign_id IF NOT EXISTS
FOR (n:Campaign) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT kg_promotion_id IF NOT EXISTS
FOR (n:Promotion) REQUIRE n.id IS UNIQUE;

// The term itself, lower-cased by the loader. Two products ranking for
// "lunchbox" must reach one keyword node or the cross-sell query has no edge
// to travel.
CREATE CONSTRAINT kg_keyword_term IF NOT EXISTS
FOR (n:Keyword) REQUIRE n.term IS UNIQUE;

CREATE CONSTRAINT kg_persona_code IF NOT EXISTS
FOR (n:Persona) REQUIRE n.code IS UNIQUE;

// ---------------------------------------------------------------------------
// Range indexes - lookup and filter
//
// Each one names what reads it. See rule 3 in the header.
// ---------------------------------------------------------------------------

// "top sellers in a category", "weakest subtrees", "supplier concentration" -
// all three group products by their taxonomy path.
CREATE INDEX kg_product_category IF NOT EXISTS
FOR (n:Product) ON (n.category);

// Regulated branches are the ones a market restriction can bite.
CREATE INDEX kg_product_regulated IF NOT EXISTS
FOR (n:Product) ON (n.regulated);

// Subtree queries walk down from a depth-2 node; both are read as a pair.
CREATE INDEX kg_category_level IF NOT EXISTS
FOR (n:Category) ON (n.level);

CREATE INDEX kg_category_path IF NOT EXISTS
FOR (n:Category) ON (n.path);

// "certifications expiring within ninety days" - the whole of insight one, and
// the reason this index exists at all.
CREATE INDEX kg_certificate_expires_on IF NOT EXISTS
FOR (n:Certificate) ON (n.expiresOn);

// "stocked where it cannot lawfully ship" separates UKCA from CE by scheme.
CREATE INDEX kg_certificate_scheme IF NOT EXISTS
FOR (n:Certificate) ON (n.scheme);

// Below-reorder queries compare the two, so both are indexed.
CREATE INDEX kg_stock_level_on_hand IF NOT EXISTS
FOR (n:StockLevel) ON (n.onHandQty);

CREATE INDEX kg_stock_level_reorder_point IF NOT EXISTS
FOR (n:StockLevel) ON (n.reorderPoint);

// A snapshot is per week; "the latest stock" filters on it before anything else.
CREATE INDEX kg_stock_level_week_start IF NOT EXISTS
FOR (n:StockLevel) ON (n.weekStart);

// "Top sellers in a month" filters by period then orders by units, which is
// what a composite index is for. The single-property index on period stays,
// because the supplier-concentration query filters on period alone.
CREATE INDEX kg_sales_fact_period_units IF NOT EXISTS
FOR (n:SalesFact) ON (n.period, n.units);

CREATE INDEX kg_sales_fact_period IF NOT EXISTS
FOR (n:SalesFact) ON (n.period);

// Insight two asks for rank 1 specifically rather than for an ordering.
CREATE INDEX kg_sales_fact_rank_in_category IF NOT EXISTS
FOR (n:SalesFact) ON (n.rankInCategory);

// "missing a primary image" and "weakest media coverage" both filter on role,
// and the first also filters on primary.
CREATE INDEX kg_media_node_role IF NOT EXISTS
FOR (n:MediaNode) ON (n.role);

CREATE INDEX kg_media_node_primary IF NOT EXISTS
FOR (n:MediaNode) ON (n.primary);

// Overlapping campaigns is an interval test against both ends.
CREATE INDEX kg_campaign_starts_on IF NOT EXISTS
FOR (n:Campaign) ON (n.startsOn);

CREATE INDEX kg_campaign_ends_on IF NOT EXISTS
FOR (n:Campaign) ON (n.endsOn);

CREATE INDEX kg_promotion_ends_on IF NOT EXISTS
FOR (n:Promotion) ON (n.endsOn);

// A withheld listing is not a sales channel; status is filtered, not displayed.
CREATE INDEX kg_listing_status IF NOT EXISTS
FOR (n:Listing) ON (n.status);

CREATE INDEX kg_price_record_effective_from IF NOT EXISTS
FOR (n:PriceRecord) ON (n.effectiveFrom);

// ---------------------------------------------------------------------------
// updatedAt - incremental refresh and prune
//
// Five labels, not twenty-three. `--since` filters at the source, so the only
// thing that reads updatedAt inside Neo4j is `--prune`, which sweeps nodes an
// ingest run did not touch. On the eighteen small labels a prune is a label
// scan over a few hundred nodes and an index would be write cost with no read
// to pay for it. These five are the ones that run to tens of thousands.
// ---------------------------------------------------------------------------

CREATE INDEX kg_variant_updated_at IF NOT EXISTS
FOR (n:Variant) ON (n.updatedAt);

CREATE INDEX kg_attribute_value_updated_at IF NOT EXISTS
FOR (n:AttributeValue) ON (n.updatedAt);

CREATE INDEX kg_media_node_updated_at IF NOT EXISTS
FOR (n:MediaNode) ON (n.updatedAt);

CREATE INDEX kg_stock_level_updated_at IF NOT EXISTS
FOR (n:StockLevel) ON (n.updatedAt);

CREATE INDEX kg_sales_fact_updated_at IF NOT EXISTS
FOR (n:SalesFact) ON (n.updatedAt);

// ---------------------------------------------------------------------------
// Full-text search
//
// Backs GET /api/kg/search. Nine labels, not twenty-three: these are the
// things a merchant names out loud. Offering StockLevel or AttributeValue in a
// type-ahead would bury the nine that anybody actually searches for under the
// tens of thousands that nobody does.
//
// The index name is also declared once in sc/kg/model.py as SEARCH_INDEX,
// because the builder that queries it and this statement have to agree and a
// typo between them is a runtime error on an otherwise healthy graph.
// ---------------------------------------------------------------------------

CREATE FULLTEXT INDEX kgSearch IF NOT EXISTS
FOR (n:Product|Variant|Category|Supplier|Warehouse|Campaign|Certificate|Keyword|Market)
ON EACH [n.name, n.code, n.sku, n.term, n.ref, n.id];
