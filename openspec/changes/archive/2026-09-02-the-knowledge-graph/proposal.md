## Why

Product 360 can say what is wrong with a product and who has to fix it. It
cannot say what the product is **connected to** - which supplier concentration
sits behind it, which certificates its category shares, which depot holds stock
that cannot lawfully ship, which campaigns it appears in beside what else.

Those are graph questions, and the catalog is stored as a relational record.
Answering them by joining tables per question means a new query per question,
each one a second reading of a structure nobody has written down.

Four of the seven domains a retailer would want in such a graph have **no source
data at all**: warehouse, trading, marketing, and compliance as entities rather
than as attribute values. Nothing in the system has ever carried a stock
snapshot, a campaign, or a certificate register.

There is a real risk in inventing them. A stock snapshot that reached the
readiness pass could move a verdict, and a verdict moved by simulated warehouse
data would be indefensible - it is exactly the kind of contamination the fact
store's provenance rules exist to prevent.

Two smaller faults sit alongside. The estate server reads the newest few hundred
arrivals estate-wide and filters afterwards, so any quiet system reports having
delivered nothing. And a segmented control promises arrow keys in its docstring
and has no key handling at all.

## What Changes

- **A graph over seven domains**, on its own segment of Product 360, backed by
  Neo4j where one is running.
- **Neo4j is real but never required.** The backend selection uses it when it
  answers and walks the identical projection in process when it does not, and
  every response says which engine ran - the posture the MCP client already
  takes. A test checks that claim rather than arguing it: identical node sets
  and identical rows from both engines.
- **No Docker**, in keeping with the startup script's own header. Neo4j
  Community is a zip with a batch file in it, fetched on request and run from a
  local directory, stepping aside quietly when it is not there.
- **The four missing domains arrive the way every other fact arrives** - as
  events from simulated systems declared in the estate manifest, on a third lane
  that the transport does not count, the live feed does not announce, and the
  ingestion handlers skip by construction. **A stock snapshot cannot move a
  readiness verdict, and there is a test that says so.** A fourth back-office
  console reads them over MCP.
- **Where the catalog already knows something, it is derived rather than
  invented**: certificate schemes are parsed out of the references variants
  already carry, hazmat class comes from the battery specification, and two of
  the six insight views are built entirely on real media gaps and real supplier
  concentration. Everything generated is stamped synthetic and drawn dashed.
- **Parameterised Cypher throughout.** Depth is the one value Cypher will not
  bind, so it comes from a closed set of literal patterns; domains are an enum;
  saved queries are an allowlist checked by name. **There is no free-text
  Cypher.**
- The estate's arrival read is scoped per system rather than filtered after the
  fact, so a quiet system stops reporting nothing.

## Capabilities

### New Capabilities

- `knowledge-graph`: a second reading of the same catalog as a graph - the
  schema, the projection, the two interchangeable backends, the bounded
  traversal, and the saved insight queries.

### Modified Capabilities

- `event-ingestion`: a third lane carries reference data that the transport does
  not count and the fact store never sees.
- `source-estate`: arrivals are read per system rather than estate-wide and
  filtered afterwards.

## Impact

- `sc/kg/schema.py` - labels, relationships, business keys, constraints and the
  search index.
- `sc/kg/cypher.py` - every statement, parameterised, with depth from a closed
  set.
- `sc/kg/driver.py` - Neo4j imported inside a function, so a checkout without it
  still imports and serves.
- `sc/kg/memory.py` - the identical projection walked in process.
- `sc/kg/insights.py` - six saved views, two of them on real data.
- `sc/estate/manifest.py` - the four reference systems.
- `sc/replay/` - the reference lane, skipped by the ingestion handlers.
- `apps/backoffice/` - the fourth console, reading over MCP.
- `startup.bat` - fetching and running Neo4j without Docker.
- `tests/test_kg_schema.py`, `test_kg_cypher.py`, `test_kg_data.py`,
  `test_kg_insights.py`, `test_kg_api.py`, `test_kg_neo4j.py`,
  `tests/test_estate.py`.
