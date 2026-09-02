## Context

Two of the decisions below are about *ordering* - which question is asked
first, and which refusal is checked first - and neither shows up in a data
model. They are the ones worth writing down, because an implementation that got
either backwards would still pass every test about what a proposal contains.

## Decisions

### The gate is a partition of an existing summary, not a second implementation

`readiness.assess` already runs every check and returns the findings. The gate
reads one summary it produced and splits its findings in two by the check that
raised each one. There is no query in the gate, no model, no clock and no rule
of its own.

The alternative - a gate that re-derived "unsaleable" from the record - is a
second answer to a question that already has one, and the reviewer would be
shown whichever ran. This is the same discipline `mandatory_information`
follows against the publish-time validator, for the same reason.

### The gate names checks; it does not read a severity

Three of the four gate checks produce `BLOCKING` findings, so making the gate
*be* `severity == BLOCKING` is one line shorter and wrong.

`checks.py` reserves `BLOCKING` for a regulation saying a thing may not be
sold. `policy_conformance` is deliberately `OPEN`: a breach of the retailer's
own policy stops onboarding without being a statement about legality. Reading
the severity would force a choice between dropping the policy check from the
gate and letting it claim an authority it does not have. Naming the checks -
`sale_permitted`, `forbidden_content`, `saleability`, `policy_conformance` -
keeps both true at once, and lets the refusal say *who* said so: a product
stopped by both a regulation and a policy is reported as stopped by the
regulation, because that is the sentence the supplier gets and the one that
decides whether the answer can be argued with.

### The score is composed, and the model's self-report is one discounted input

The single most important decision in the change, because this score is what
decides whether a value is written without a person looking at it.

A model's confidence in its own reading is uncalibrated between prompts and
moves with phrasing. So `CITED_TRUST` is how much of it survives: enough to
carry a proposal most of the way, never enough to carry it alone. Everything
else in the score is a count of things already on file - siblings, category
convention, past decisions - which is checkable, stable between runs, and is
what the reviewer is shown.

Disagreement is weighted heavier than agreement, sibling for sibling, because a
sibling holding a *different* value is stronger evidence that the proposal is
wrong than a category convention is that it is right.

Two consequences follow, and both are the point rather than a side effect:

- A safety-class attribute scores **zero**, not "low", and is never proposed
  autonomously whatever agrees with it.
- A single source can never reach autonomy - and not because the weights happen
  to fall short of the default threshold.

### The two structural refusals are checked before the number

`decide.route` takes the proposal object rather than a bare confidence, and
that signature is load bearing: two of the three refusals are properties of the
proposal rather than of its score, and a function that accepted a float would
make them unreachable.

The order is the order they are argued in - safety class, then too few
supporters, then the threshold. The score is consulted last because it is the
only one of the three an operator can move. A safety property that survives
only while nobody turns a knob is not a safety property, and the minimum source
count is therefore a constant and not a setting.

### An autonomous fill is INFERRED; a person's answer is DECIDED

Easy to get subtly wrong, and the failure is silent.

An autonomous fill goes through `ingest.record_attribute`, the same door
`enrich` writes through, and lands `INFERRED` with its confidence and its
citation. That provenance is what keeps the fail-closed safety gate in
`sim.engine` able to see it, and what stops a model's reading acquiring the
standing of a supplier's assertion.

A person's decision lands `DECIDED`, not INFERRED-with-a-note. `ProvenanceKind`
keeps "an LLM concluded it" and "a human chose it" apart on purpose, and the
publish-time safety check treats them differently *because they are different*.
A category manager approving a value is taking responsibility for it, which is
precisely the thing an inference cannot do.

Neither door publishes. "Pushed through" means a product now has no findings
left, which is arithmetic; publication needs `commit_plan`, a recorded approval
and a channel reservation, and a reviewer answering "yes, 65 W is right" has
not said "put it on sale".

### The queue is the one thing here that is stored

Almost nothing else in this schema stores a judgement - verdicts, stages and
readiness are recomputed on read so they cannot drift from the record. The
proposal queue is stored, and the reason is narrow: **a category manager
approves the exact value they were shown.** The proposal comes partly from a
model reading retrieved passages, so recomputing it on the next read can
legitimately produce a different number, and a queue that re-derived its rows
would let somebody approve 65 W and write 68 W.

What is stored is the proposal, not a conclusion about the product. The verdict
beside it is still computed from the facts every time.

The row is upserted on submission, entity and attribute together: re-assessing
a batch refreshes an open proposal rather than stacking a second one beside it,
and a proposal that has already been decided is left alone, because re-reading
a batch is not a reason to reopen a question somebody answered.

### `clear` is a separate verb from `reset`

`reset` is careful to be *only* a rewind - it unreleases the tape and leaves
the live lane alone, because retracting a supplier's submission because
somebody moved the clock would be a lie about history.

So the deliberate act is its own verb. It clears **both** ingest watermarks,
and the live one is not optional: live sequence numbers restart at their base
once the rows are gone, so a watermark left at the old high-water mark would
silently drop every subsequent submission as already-seen - ingestion would
stop and report success, which is the exact failure the lane column exists to
prevent.

Open questions go with the submission; records of decisions do not. A proposal
somebody *answered* survives, for the same reason the audit ledger does, and
because `history` reads it back as a prior. A proposal written *autonomously*
survives too - it was never a question, and the value it produced outlives the
clear, so removing its row would leave a fact in force with no account of why
it was trusted.

**What this leaves is a real inconsistency and is chosen rather than
overlooked.** A value a portal submission already recorded stays in force after
the event that carried it is gone. Clearing the tape and retracting a fact are
different acts, the second needs the supersession machinery in `sc.state`, and
a control that quietly did both would be a control nobody could reason about.
The UI says so where the button is.

### The map gets its own screen back

Three things had accumulated under the graph that are not about the graph: the
estate panel and the arrivals machinery, which belong to System Control; the
supplier bundle, which belongs to Supplier Intake; and the list of what is in
force, which belongs beside the map but not on top of it.

What is in force moves into a rail that is **shut by default, and shut is not
hidden**: the handle carries the open-case count and takes the severity of the
worst one, so a reader watching only the graph still knows there is something
to open. System Control becomes tabbed rather than a column of a dozen panels,
because a section that has grown a dozen panels is a section that has stopped
being navigable.

## Risks / Trade-offs

- **Parallel tests are distributed by file, and that is load bearing.** Each
  module owns its database; two workers sharing one would delete each other's
  fixtures mid-run. Distribution by file is therefore not a tuning choice. The
  suite is disk-bound rather than CPU-bound, so the gain is real but sublinear
  - eight workers beat four and neither approaches an eightfold speedup.
- **The accepted-lines extension has to be per-module** for the same reason,
  which also closes a leak that predates this change.
- **The offline path produces questions, not silence.** With no gateway nothing
  is read from a document, but `history` still answers, so proposals still
  exist - corroborated by definition or capped below any usable threshold. That
  is the path the suite exercises, since the gateway is pinned to a closed port
  throughout.
- **A category prior too thin to support a value must be too thin to refute
  one.** The asymmetric weights make the opposite tempting and it is a bug: a
  handful of rows disagreeing is not evidence, in either direction.
- **A fill built from priors alone carries no citation**, and every surface
  that renders the audit line has to survive that. A proposal is not required
  to have read a document; it is required to say what it read.

## Open Questions

- The gate reads four checks. A fifth authority - a marketplace's own
  admissions policy, say - would want a third value beside `REGULATION` and
  `POLICY`, and the sentence the supplier gets would need to rank it. Left
  until there is one.
