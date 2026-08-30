## Why

The day-0 contract module described a supply-chain disruption: a plan that had
become infeasible, a network of plants and lanes, a bill of materials, SKUs, and
a corpus of SOPs about expediting shipments and reallocating production. The
problem the system now has to solve is not a disrupted plan but a corrected
specification - a supplier revises a figure after content has already been
prepared for several channels, and the system has to work out what the
correction says, which product or variant it applies to, and every derived field
and channel built on the old value.

The interesting question was not whether the domain half could be replaced. It
was whether the *other* half - provenance, bitemporal facts, events, approvals,
audit, retrieval - was genuinely problem-independent or had merely looked that
way while only one problem was in the room. This change is the experiment. The
supply-chain half was replaced wholesale; the provenance half was kept whole,
including its tests, which did not need editing. That is the evidence those were
the right abstractions and the argument for having separated them in the first
place.

Two gaps motivated additions rather than replacements. Nothing in the day-0
contracts obliged a proposed change to say where it had been read from, so a
reviewer could be shown a new value with no way back to the sentence that
asserted it. And nothing marked an attribute as one a shopper could be harmed
by, so there was no switch a fail-closed rule could read.

## What Changes

**BREAKING** - the domain contracts are replaced, not extended. Persisted seed
data, the corpus and the retrieval index are all regenerated.

- **Kept whole, untouched:** the five provenance kinds (RECORDED, INFERRED,
  DECIDED, SIMULATED, COMMITTED), the bitemporal `Fact` and its store, the event
  envelope, approvals, the audit entry, retrieval chunks and replay control.
  `tests/test_bitemporal.py` passes unedited across the domain change.
- **Replaced:** network / lane / BOM / SKU become catalog entities - Product,
  Variant, Channel, ChannelRule, Listing, ContentAsset, SourceDoc, AttributeDef.
  `PlanDelta` becomes `ChangeSet` over six action kinds. KPIs are measured in
  fields affected, stale assets, blocked channels and listing readiness rather
  than OTIF and cost.
- **Added:** `SourceRef`, so every proposed change and regenerated sentence
  cites the document, version and excerpt it was read from;
  `ChangeSummaryLine`, assembled deterministically as source → old value → new
  value → impacted outputs so no consumer has to parse prose; and
  `AttributeDef.safety_class`, the switch a fail-closed rule reads.
- **Reframed:** capacity reservations become publish locks keyed
  channel + product for a batch date. The partial unique index that made
  duplicate reallocation impossible now makes two runs republishing the same
  product to the same channel impossible.
- **Seed pack:** a retailer onboarding an air purifier (two variants) and a
  packaged snack across six channels - its own site, two marketplaces with
  incompatible schemas, the printed catalogue, shelf labels and search facets -
  plus a six-arc, 56-day correction tape. The generator keeps the properties
  that made the old one work: a local mulberry32 PRNG so the pack is
  byte-identical per `DATA_SEED`, hardcoded entity ids so a hand-authored corpus
  can name `PRD-01` and `VAR-01B` literally, and self-validating assertions that
  exit non-zero rather than emit a pack that only looks right. The strongest of
  those: **the untouched catalog must validate with zero violations.**
- **Corpus:** fifteen authored documents in four types the retrieval layer now
  knows - STANDARD, CHANNEL, POLICY, POSTMORTEM - replace the SOP set. Two are
  load-bearing: STD-001 carries the claim-substantiation table that the
  validation engine enforces in code, and POL-002 carries the source-precedence
  order that settles a disagreement between two suppliers' documents.
- **Retrieval:** unchanged. The identifier-preserving tokenizer needed nothing -
  it already keeps `VAR-01B` and `MKA-4102` whole while indexing their parts,
  and it matters more here than it did before, because embeddings put `VAR-01A`
  and `VAR-01B` almost on top of each other while they hold opposite answers to
  the only question that matters about them. Only the corpus behind it changed.

## Capabilities

### New Capabilities

- `bitemporal-record`: the record of what is true about a product, what the
  system believed at any past instant, and on whose authority - with
  corrections that supersede rather than overwrite.
- `standards-retrieval`: the governance corpus the system cites - content
  standards, channel specifications, policies and postmortems - and the
  retrieval that finds the right passage and hands back a citation an editor can
  follow.

### Modified Capabilities

None. This is the first change; no capability specs exist yet to modify.

## Impact

- `sc/contracts.py` - the domain half rewritten, the provenance half untouched.
- `sc/schema.sql`, `sc/db.py`, `sc/state/store.py` - the reservation index
  reframed as a publish lock; the fact table shape unchanged.
- `sc/state/baseline.py`, `scripts/generate_data.py` - catalog and tape
  generation.
- `corpus/**` - fifteen documents replace the SOP, contract and incident sets.
- `sc/rag/bm25.py`, `sc/rag/chunk.py`, `sc/rag/retrieve.py` - document types and
  wording only; the algorithms are unchanged.
- `tests/test_rag.py` - retargeted at the new corpus and its golden sets.
- `tests/test_bitemporal.py` - unchanged, and that is the point.
