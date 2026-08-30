## Why

With the record and the corpus recast, the layer that decides things was still
the supply-chain one, and it decided the wrong questions. A Monte Carlo
simulator sampled whether a materials plan was feasible. A dependency walk
traversed suppliers, lanes and bills of materials. Event ingestion branched per
event type inside one growing conditional. The tool layer reserved production
capacity. None of that answers "is this corrected product record publishable,
and what does correcting it drag with it".

Recasting was the occasion; four real defects and gaps are what make this change
worth its size.

- **Nothing sampled.** Monte Carlo was applied to a quantity with no stochastic
  component. Product-data validation is arithmetic against a catalog: the same
  change set against the same catalog has exactly one answer. Sampling it was
  decoration that cost runtime and implied an uncertainty that did not exist.
- **A lower-ranked source silently overwrote a higher-ranked one.** Ingestion
  took the newer value. A portal spreadsheet arriving after a signed pack label
  simply replaced it, with no signal raised. That is the single most plausible
  route to publishing a wrong net weight, and it is the reason the
  source-precedence policy exists as a document a person owns.
- **An approved resolution could publish against evidence that had moved.**
  Approval was checked; currency was not. A print batch prepared and approved
  under a supplier document at v2 would go out unchanged after v3 landed and
  narrowed the correction to a different model - the exact shape of a
  postmortem already in the corpus.
- **Nothing stopped an unsafe publish that a reviewer had approved.** A
  low-confidence inference on a safety-class attribute, or an allergen that no
  prepared page declared, could reach a channel because the only gate was human
  sign-off. Approval is consent, not evidence.

There is a fifth property this change is really about, which is not a defect:
**no model is invoked anywhere in any of it.** Four modules and four test files -
validation, propagation, ingestion, publishing - contain no gateway call. What
publishes is decided by ordinary software, and that is what makes the decisions
reproducible, explainable and defensible after the fact.

## What Changes

**BREAKING** - the validation, propagation, ingestion and publishing surfaces
are replaced, and the Monte Carlo module and its tests are deleted.

- **Validation** becomes one deterministic pass over the catalog, in a fixed
  order: build the effective attribute table from baseline, facts in force and
  the change set; mark content assets whose source version has moved; catch a
  superseded literal still sitting in the prose; evaluate every channel rule;
  check claims against the substantiation table; check allergen declarations in
  each channel's required format; fail closed on a low-confidence safety value;
  and refuse anything validated against a version that has since been
  superseded. Kept from the old engine: the trace hash, sorted iteration with
  ties broken by id, one violation row per binding rule, and a sub-250ms budget
  so candidate resolutions can be validated concurrently.
- **Stale literals** are introduced as the deterministic half of contradiction
  detection. A bullet reading "Ultra-quiet 45W operation" is mechanically wrong
  the moment the value becomes 65 W and needs no model to say so. The semantic
  half - that "ultra-quiet" may now be untrue for reasons no rule encodes - is
  left to an advisory pass elsewhere, which is where a model earns its place
  rather than duplicating arithmetic.
- **Failing closed** becomes a block, not a banner. A safety-class attribute
  inferred below the confidence threshold with no human decision behind it
  blocks publication on every channel carrying that product, and the violation
  names the attribute, the confidence and the threshold it missed.
- **Blast radius** keeps its shape - a root, the affected sets, a chain of hops
  each carrying a relation, and totals - because that shape was never about
  supply chains. Only the walk changes: a source document defines an attribute,
  which derives content assets, which list on channels, with variants held by
  products and document versions superseding each other. It is derived entirely
  from the catalog, never from a model, because every content asset declares the
  attributes it was built from - which makes "what does this correction touch" a
  graph walk with a correct answer rather than a judgement call.
- **The cross-variant case** falls out of that structure and is the finding a
  person would miss: a correction scoped to the Max still lands on the base
  model's own web page, because a comparison table there quotes both variants.
- **Supplier-facing tools** are replaced. Alternate-supplier lookup and bill-of
  -materials expansion become a variant attribute diff and a derivation read.
  The variant diff is the important one: the attribute table across a product's
  variants, each value carrying the document and version it stands on. It is
  what makes a base-versus-variant argument decidable rather than rhetorical.
- **Ingestion** becomes a handler registry keyed by event type, so adding a feed
  or a channel is a table entry rather than another branch. Three properties are
  preserved deliberately: the cursor advances inside the same transaction as the
  facts it writes, so an interrupted batch is redelivered rather than silently
  skipped; structured feed rows become observed facts while documents and email
  write no attribute facts at all, because the arrival of a document is
  structured and its contents are not; and materiality carries one deliberate
  asymmetry - a numeric attribute needs a 5% move, but **any** change to a
  safety-class attribute is material regardless of size.
- **Source precedence** is added: a lower-ranked source contradicting a value
  already in force from a higher-ranked document raises a source conflict naming
  both documents and the policy that settles it, rather than overwriting.
- **Publishing** replaces planning as the mutating surface: validate a change
  set, rank the readings, take a lock, publish, roll back. Every governance
  property of the old tool layer survives because they were about the shape of a
  decision rather than its subject - idempotency keys, refusal without a
  recorded approval, database-enforced exclusivity of publish locks, and a
  rollback that genuinely frees the batch.
- **Two new publish gates**, both failing closed: version currency, re-checked
  immediately before writing rather than at approval time; and safety, refusing
  while any safety-confidence or allergen-declaration violation is open on an
  affected listing.
- **Ranking puts safety first as a pre-sort, not a weight.** A resolution with
  an open safety flag can never outrank one without, whatever a reviewer sets
  the sliders to, because that is not a trade-off anyone should be able to
  express. Below that, evidence confidence outranks scope narrowness - a
  narrower reading is only better when the record actually supports it.

## Capabilities

### New Capabilities

- `content-validation`: the deterministic, reproducible pass that decides
  whether a corrected product record is publishable on each channel, and names
  the rule behind every block.
- `blast-radius`: the catalog-derived traversal from a corrected value to every
  field, asset, listing and channel built on it, with a readable relation on
  every hop.
- `event-ingestion`: turning arriving feed rows, documents, correspondence and
  channel responses into facts and correction signals, exactly once, without
  guessing at anything unstructured.
- `review-and-publish`: the gates a resolution must pass to reach a channel -
  approval, version currency, safety - plus exclusive publish locks,
  idempotency, ranking and rollback.

### Modified Capabilities

None. This change is the first substantial consumer of `bitemporal-record` and
`standards-retrieval`, but it reads and writes through their existing contracts
without altering a requirement of either.

## Impact

- `sc/sim/engine.py` - rewritten as the validation pass.
- `sc/sim/monte_carlo.py` and `tests/test_monte_carlo.py` - deleted.
- `tests/test_simulator.py` - replaced by `tests/test_validator.py`.
- `sc/state/overlay.py` - the in-force layer the validator reads.
- `sc/tools/network.py` - the catalog map, blast-radius walk, variant diff,
  derivation read and channel-rule lookup.
- `sc/replay/ingest.py` - handler registry, materiality, source precedence,
  cursor.
- `sc/tools/planning.py` - propose, rank, reserve, commit, roll back.
- New test files: `tests/test_validator.py`, `tests/test_propagation.py`,
  `tests/test_ingest.py`; `tests/test_orchestration.py` retargeted.
- No model gateway is called from any of the above.
