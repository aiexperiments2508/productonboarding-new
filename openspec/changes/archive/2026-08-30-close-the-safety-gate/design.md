## Context

See proposal.md - Why. The starting state is a validation pass and a publish
boundary that both work, and four sites inside them that resolve an entity id to
listings by looking it up in an index keyed by variant. Two of the residuals
this change closes were recorded openly at the time they were introduced, in
`deterministic-decision-core`'s own Risks section and in its two unchecked
verification tasks; this is that debt being paid rather than discovered.

Constraints that shape the approach:

- A fact is recorded against whichever entity the evidence named. Both writers -
  the structured feed path and the extraction node - store the id they were
  given, and the catalog holds products, variants and listings as three
  separate tiers. Nothing normalises them on the way in, and normalising them on
  the way in would throw away the ambiguity the scope node exists to resolve.
- The KPIs are load-bearing and reproducible. Anything that changes what the
  untouched catalog reports is a regression in the demo's headline numbers, so a
  fix has to be exactly as wide as the defect.
- The fact store never updates in place. A retraction is therefore an
  assertion, and it has to be an assertion the as-of read will actually find.
- The catalog holds no press calendar. Not "not yet" - there is no field, no
  seed value and no event carrying one.

## Goals / Non-Goals

**Goals:**

- One resolver, used by every site that turns an entity id into listings, so the
  next rule written cannot reintroduce the assumption by accident.
- A freeze-window rule that fires on evidence the catalog actually holds.
- A rollback that an as-of read agrees with.

**Non-Goals:**

- Product-to-variant attribute inheritance. See the first decision below; this
  is the deliberate residual, not an oversight.
- A press calendar, a reprint workflow, or any notion of days-until-press. The
  lead time is carried into the explanation and decides nothing.
- Changing what the untouched catalog validates to. Nothing here moves a
  baseline KPI.

## Decisions

**One resolver, and only the gate is taught to fail closed across levels.**
`_listings_for` answers "which listings does this entity id reach" at whatever
level it was given: a listing is itself, a variant is its listings, a product is
every variant's listings, an unknown id is nothing. The four sites that had
restated the variant-keyed lookup - the scope walk, the safety gate, the
violation-to-listing resolution readiness is computed from, and the reviewer's
change summary - now call it.

*The residual, deliberately.* The rule, claim and allergen checks still read
values at **variant** level and were left alone. Giving them product-to-variant
inheritance needs a layer precedence rule - what happens when a product says one
thing and a variant says another - and inventing one here would move the KPIs
the engine exists to produce. It is also the wrong place for the question:
*which* variants an ambiguous product-level correction applies to is exactly
what scope resolution decides, and after it runs the change sets it emits always
name variants. The safety gate is different precisely because it fails closed -
it does not need to know which variant, only that it must not let this through.

*What that costs, stated plainly:* a **high**-confidence product-level allergen
is not declaration-checked until scope resolution has run. It is not gated by
the confidence rule, because it is confident; and the declaration check will not
see it, because it is looking at variants. The window is one node wide and it is
real.

**The freeze window triggers on a superseded published version, not on a date.**
`Channel.freeze_days` was documented as "days before a press date during which
content is frozen" and nothing enforced it. The literal reading needs a press
date; there is none in the catalog. The available evidence is: which channels
publish something that cannot be recalled (non-zero `freeze_days`), and what
version each listing last went out on (`Listing.published_version`, overlaid by
a `listing` fact). So the rule reads: on an irreversible channel, a listing
whose published version has been overtaken is blocking. The declared number of
days is carried into the detail as the lead time the channel documents, and
decides nothing.

*Alternative considered.* Adding a press date to the catalog so the comment
could be implemented as written. Rejected: that is fabricating evidence to
satisfy a sentence, and the resulting rule would be tested against data invented
for the test.

**Regenerating the copy deliberately does not clear it.** This is the entire
finding of INC-2026-002: rebuilding the catalogue asset cleared the only
staleness signal in the system, and 214,000 catalogues went out carrying the
superseded figure. A stale asset is content that can be rebuilt; a stale
published version is an object in the world. Only republishing - a press
decision - or withholding clears it, because only those change what is in the
world.

*Trade-off.* The rule is blind to whether the printed copy actually quoted the
moved value; it fires on any attribute the listing's assets were derived from
moving past the printed version. That is deliberately wider than necessary in
the direction of "ask a human", which is the direction an irreversible channel
should fail in.

**Retraction is a new assertion, not a closed interval.** The obvious
implementation is to close the published fact's `valid_to` at the rollback
instant. It does not work in this store: the original row stays open on the
valid axis and still wins the as-of read. So the rollback asserts a fresh fact
per published row, valid from the rollback onwards, carrying whatever the
attribute held immediately before the publish - read as of just before the
publish's own recording instant so the run does not find its own write. A
publish that was the first assertion of its kind falls back to the seed pack,
which is what the prepared content stands on; an attribute the pack never
carried has nothing to restore and gets nothing.

*Why insertion is the right answer anyway.* The published value **was** what the
channel held between the commit and the rollback. A read as of that window has
to keep saying so - that is what a bitemporal record is for - while a read taken
now must not return a value that has been pulled. Deleting the row would answer
the second question by destroying the answer to the first.

*One sharp edge.* Under the replay clock a rollback can land on the same tick as
the publish it reverses, and two rows sharing an instant tie on the store's
ordering, so the retraction can lose and be invisible. The rollback instant is
therefore pushed to one microsecond after the latest row it retracts. It says
something true - the publish was retracted after it happened - rather than
something merely convenient.

**Rows already superseded are skipped**, so a repeated rollback retracts nothing
twice and a later correction that has already moved the value is not undone by a
rollback of the publish underneath it.

**The precedence policy becomes one function.** It had drifted into two private
copies, one in the feed path and one in the extraction path. They agreed, which
is the point: two copies of a policy are two policies from the moment one of
them is edited. It moves to `state.baseline` beside the catalog it reads and
both callers import it. No behaviour changes, and a test asserts the two names
are the same object rather than merely equal.

## Risks / Trade-offs

**A high-confidence product-level allergen is not declaration-checked until
scope resolution runs.** → Recorded above and in the proposal rather than
softened. It is bounded: the confidence gate still fails closed below the
threshold, and the scope node emits variant-level change sets, after which every
check sees it. Closing it properly means layer precedence, which is its own
change.

**The freeze-window rule has no test through the publish path.** The rule is
covered six ways at validation time - against the catalog's own value and
against an injected overlay - but nothing asserts that committing a publish
writes the `published_version` listing fact, or that the overlay reads it back.
The round trip is therefore implemented and unevidenced. → Left as a gap and
named here rather than written up as a requirement no test supports.

**The resolver makes a product-level fact block more listings than a variant-
level one would.** That is the intended behaviour and it is also a blast radius
a reviewer will notice. → It is the failing-closed direction, and the scope node
narrows an ambiguous product-level correction to variants before a resolution is
proposed, so the wide block is what a reviewer sees only when scope genuinely
could not be resolved.

**Retraction depends on identifying the publish's own rows by provenance.** A
future writer stamping the same agent and run id would have its facts retracted
by a rollback that did not mean them. → The query is narrow (COMMITTED
provenance, the scenario's run id, the commit agent) and the rollback reports
the count it retracted, so an unexpected number is visible in the audit entry
rather than silent.

## Migration Plan

1. Land `_listings_for` and repoint the four call sites; confirm the untouched
   catalog's KPIs are unchanged.
2. Land the freeze-window rule and the overlay field it reads.
3. Land the retraction inside the existing rollback transaction.
4. Rollback is `git revert`; nothing here changes a schema or a stored shape,
   and the new `listing` facts are additive rows an older reader ignores.
