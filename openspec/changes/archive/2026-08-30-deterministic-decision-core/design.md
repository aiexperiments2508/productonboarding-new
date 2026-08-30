## Context

See proposal.md - Why. The record and the corpus are in place; what reads them
is not. The starting state is a decision layer built for a different question: a
Monte Carlo feasibility sampler, a supplier-and-lane dependency walk, an
ingestion path branching per event type in one conditional, and a tool layer
that reserved production capacity behind an approval gate.

Constraints that shape the approach:

- The whole suite runs with the model gateway pinned to a closed port. Nothing
  in this layer may need a model, and nothing here has one.
- Candidate resolutions are validated concurrently behind a live interface, so a
  pass has a sub-250ms budget and must be safe to run in parallel.
- The trace hash is part of the audit trail, so every iteration order must be
  deterministic and every tie broken by identifier.
- SQLite with no server: exclusivity is a partial unique index and atomicity is
  a transaction; there is nothing else to lean on.
- Graph state is plain JSON, so anything crossing into a run's state is
  primitives.

## Goals / Non-Goals

**Goals:**

- One place where "is this publishable" is decided, reproducibly, naming the
  rule behind every block.
- One place where "what does this correction touch" is answered from the
  catalog, with an auditable chain.
- An event plane that is exactly-once, that never invents structure it was not
  given, and that never lets a weaker source displace a stronger one.
- A publish boundary whose gates cannot be routed around by any later change to
  the orchestration above it.

**Non-Goals:**

- Reading corrected values out of prose, arguing base-versus-variant scope,
  rewriting copy, or narrating a decision. Those are the bounded model steps and
  belong to the pipeline change; this layer is the deterministic substrate they
  are bounded by.
- Unpublishing. Rollback here frees the batch and marks the actions reversed;
  retracting the published facts themselves is not part of this change.
- Any reprint or press-date gate. The catalog has no press date, and the
  freeze-window rule that eventually enforces reversibility is a later change.
- Scoring a resolution's business value. Ranking here is safety, then evidence,
  then scope width.

## Decisions

**Deterministic arithmetic, not sampling.** Product-data validation has no
stochastic quantity: the same change set against the same catalog has exactly
one answer. Monte Carlo was deleted rather than retargeted. What it used to earn
- separating candidates that the point estimate ties - is now done by the
evidence behind each candidate reading, which is a better discriminator because
it is the thing a reviewer would actually argue about.

*Alternative considered.* Keeping sampling for "confidence" in the result. It
would have manufactured an uncertainty band with no referent and invited the
reviewer to read noise as signal.

**One ordered pass, not a rule engine.** The pass runs in a fixed order: build
the effective attribute table, mark stale assets, catch stale literals, evaluate
channel rules, check claims, check allergen declarations, apply the safety gate,
check version currency, check citations. A fixed order plus sorted iteration is
what makes the trace hash meaningful.

**Stale literals are the deterministic half of contradiction detection.** A
bullet reading "Ultra-quiet 45W operation" is mechanically wrong once the value
is 65 W, and no model is needed to say so. The semantic half - that
"ultra-quiet" may now be untrue for reasons no rule encodes - is left to an
advisory model pass elsewhere. The split is where AI earns its place instead of
duplicating arithmetic.

*Trade-off.* Literal matching is bounded by a word-boundary pattern so 45 is not
found inside 145. That costs some recall on reworded copy, which is exactly the
recall the advisory pass exists to supply.

**Channel rules are data, not code.** Seven rule kinds cover presence, type,
length, format, enumeration, list order and taxonomy mapping. A channel is added
by adding rows. The tests exploit this directly: removing a channel's taxonomy
mapping is enough to make that rule bind, with no code change.

**Failing closed is a block, not a banner.** An inferred safety-class value
below the confidence threshold with no human decision behind it blocks every
channel carrying the product, and the violation names the attribute, the
confidence and the threshold missed. Degrading it to a warning would have made
the cheapest possible mistake - being slow about an allergen - the default.

*Alternative considered.* Blocking only the channels whose rules mention the
attribute. Rejected: the value is wrong everywhere it appears, and a gate that
has to understand each channel's schema to fail closed is a gate that will one
day not understand one.

**The blast radius keeps its shape and changes only its walk.** A root, affected
sets, a chain of relation-bearing hops, and totals. The shape was never about
supply chains. Because every content asset declares the attributes it was built
from, the walk has a correct answer rather than a judgement, which is what lets
the reviewer be shown a count rather than an opinion.

*Consequence worth stating.* The cross-variant case falls out of the data and
was not special-cased: a correction scoped to one variant reaches the other
variant's page because a comparison table there quotes it. A traversal that
missed it would republish a page that contradicts itself.

**The traversal is capped in explanation, never in scope.** The chain is capped
at a fixed number of hops so the drawn explanation stays readable; the affected
sets and totals are complete regardless. Visited hops are deduplicated, which is
also what makes a cyclic catalog terminate.

**Ingestion dispatches from a registry, keyed by event type.** Adding a feed or
a channel is a table entry. It also makes a handler substitutable, which is how
the partial-failure test injects a mid-batch crash.

**The RECORDED/INFERRED split is enforced at the boundary.** A structured feed
row is an observation and is recorded as one. A document's *arrival* is
structured; its *contents* are not, and are left to a model with a confidence.
Collapsing that here would make the provenance badge decorative and would let an
unread document masquerade as an observation.

**Materiality is asymmetric on purpose.** Five per cent for a numeric attribute;
any movement at all on a safety-class attribute. A threshold that filters
allergen changes has misunderstood its job.

**Source precedence is one function with three importers.** The policy - label
artwork over a signed specification over a portal feed over an email, with
recency never overriding precedence - is a policy decision, so it lives in a
document a person owns and is applied identically on both sides of the
provenance split. Two copies of a policy become two policies the moment one is
edited, so there is one function and every caller imports it. A document the
catalog does not know ranks below every document it does, so an unattributed
value never displaces an attributed one.

**The cursor advances inside the same transaction as the facts.** An interrupted
batch is redelivered rather than silently skipped. This is the only reason the
event plane can be treated as at-least-once by everything above it.

**The publish gates live at the tool boundary, not in the graph.** Approval,
version currency and safety are checked in the function that writes, so no
future change to the orchestration above can route around them. Version currency
is re-checked immediately before writing rather than at approval time, because
the interesting window is exactly between approval and write.

**Exclusivity is a partial unique index.** A conflicting concurrent publish
fails at the database and is surfaced as a conflict. Application-level checking
would make it merely unlikely.

**A refusal is a row, not an absence.** The reviewer's question at the end of a
run is "why did the print batch not go out?", and the answer has to be
retrievable.

**Safety is a pre-sort in ranking, not a weight.** A resolution with an open
safety flag can never outrank one without, whatever the reviewer sets the
sliders to, because that is not a trade-off anyone should be able to express.
Below the pre-sort, evidence confidence outranks scope narrowness: a narrower
reading is only better when the record actually supports it.

## Risks / Trade-offs

**Determinism is asserted, not enforced by the type system.** A future unsorted
iteration would break the trace hash quietly. → Repeat-run tests on the hash,
the measures and the violations, plus an action-order-invariance test, all run
on every commit.

**The 250ms budget is asserted on one machine's timing.** → It is asserted at
roughly an order of magnitude of headroom rather than at the wire, so ordinary
machine variance does not make it flaky, and a genuine regression still trips
it.

**The blast radius and the validator could disagree about scope,** which would
make the reviewer's count contradict the reasons shown beneath it. → A test
asserts the traversal is a superset of every listing the validator binds on.

**Safety-class resolution reads listings keyed by variant.** A fact recorded
against a product rather than a variant therefore resolves to fewer listings
than it should. → Known and not addressed here; the extraction paths this change
serves write variant-level facts. This is a real residual, not a hypothetical.

**Rollback frees the batch without retracting the published facts.** An as-of
read after a rollback still returns the published value. → Known limitation of
this change, called out in Non-Goals rather than papered over.

**Precedence ranking depends on the catalog knowing the document.** An unknown
document ranks zero, which is safe for displacement but means a genuinely
authoritative new document is treated as weak until it is in the catalog. →
Accepted: failing towards "do not displace" is the correct direction, and the
conflict signal makes it visible rather than silent.

## Migration Plan

1. Delete the Monte Carlo module and its tests; delete the simulator tests they
   shared fixtures with.
2. Rewrite the engine, the traversal, the ingestion path and the tool layer;
   land the four new test files.
3. Regenerate nothing - the seed pack is unchanged by this work, which is what
   lets the clean-baseline assertion carry over as a regression check.
4. Rollback is `git revert` of the four commits; there is no persisted state
   worth preserving.
