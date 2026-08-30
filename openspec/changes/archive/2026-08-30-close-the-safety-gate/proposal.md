## Why

The fail-closed safety gate had a hole in it, and the hole was invisible
because the arc that exercises it happened to walk around the edge.

`_check_safety` resolved the listings it was about to block by asking
`base.listings_of` - an index keyed by *variant*. A fact recorded against a
*product* resolved to an empty list, so the loop that writes the violations ran
zero times. The same evidence, recorded one level up, gave the opposite answer:

    recorded on VAR-02A  ->  5 violations, publishable = False
    recorded on PRD-02   ->  0 violations, publishable = True

The product path is live, not hypothetical. Both writers store whichever entity
the evidence named - `replay.ingest.record_attribute` for structured feeds and
the extraction node for what a model reads out of prose - and a supplier notice
saying "all formats" or "the Oatberry bar" names the product, not a variant. The
allergen arc passed because its extraction happened to land on variants. Nothing
made that true; it was where the seed pack put it.

The same variant-keyed assumption sat in three more places, each of which turned
a resolvable product-level fact into silence:

- **Readiness scoring.** `_listings_hit` resolved a violation's entity the same
  way, so a product-level block counted zero unready listings. A reviewer would
  have been shown 100% of listings ready beside `publishable = False` - the two
  headline numbers on the screen contradicting each other, with the reassuring
  one being the wrong one.
- **The republish-step count**, which is what the reviewer's cost estimate is
  built from.
- **The impacted-channel list on the reviewer's diff**, so the change summary
  named fewer channels than the correction actually reached.

Four more places where the code promised something it did not do, all found
while reading around the gate:

- **`Channel.freeze_days` was a comment, not a rule.** The field was declared,
  carried a comment promising that a correction landing inside a print freeze
  could not be published without a reprint decision, and no rule anywhere read
  it. INC-2026-002 in the corpus is that failure: the catalogue asset was
  regenerated, which cleared the only staleness signal there was, and 214,000
  catalogues went out carrying the superseded figure.
- **`rollback` said "unpublish" and did not unpublish.** It released the locks
  and marked the actions reversed, and left every COMMITTED fact standing, so an
  as-of read taken after a rollback still returned the value the channel had
  been told to stop showing. This was recorded as a known limitation of the
  change that introduced it rather than papered over; it is closed here.
- **`Listing.published_version` was maintained and read by nothing.** It was
  written on every commit and no rule consulted it - root cause three of
  INC-2026-002 almost verbatim, sitting in the code that postmortem is filed
  against.
- **A module docstring still routed the reader to a toolset deleted eight
  commits earlier**, and the source-precedence policy had drifted into two
  private copies, one on each side of the provenance split.

## What Changes

- **One resolver decides which listings an entity id reaches**, at whatever
  level the evidence named it: a listing is itself, a variant is its listings, a
  product is every one of its variants' listings, and an id the catalog does not
  know reaches nothing. Every one of the four sites - the safety gate, the scope
  walk, readiness and republish scoring, and the reviewer's diff - now resolves
  through it rather than restating the variant-keyed assumption.
- **The safety gate blocks on a product-level fact.** The regression test is
  parameterised over both levels, was confirmed failing on the product case
  before the fix, and asserts the violation's entity id and that readiness reads
  zero, so a partial resolution cannot pass it.
- **The freeze window becomes a rule.** On a channel that publishes something
  irreversible, a listing whose `published_version` has been overtaken by a
  value now in force is a blocking violation, and the detail names the version
  in print, the version in force and the channel's documented lead time.
  Regenerating the copy deliberately does **not** clear it, because that is the
  whole finding of INC-2026-002. Republishing the listing clears it, and so does
  withholding it - those are the two decisions that change what is in the world.
- **The rule is not "within N days of a press date."** There is no press date
  anywhere in the catalog. `freeze_days` marks a channel whose artefact cannot
  be recalled and carries the documented lead time into the explanation; the
  trigger is a superseded published version on such a channel. Inventing a press
  calendar to match the comment would have been fabricating evidence to satisfy
  a spec.
- **Rollback retracts what was published.** For every COMMITTED fact the
  scenario wrote and nothing has since superseded, a new fact is asserted from
  the rollback instant onwards restoring what the publish displaced. It is an
  insertion, not an edit: the published value *was* what the channel held
  between the commit and the rollback, and an as-of read inside that window has
  to keep saying so. Closing the interval with `valid_to` does not work in this
  store - the original row stays open and still wins the as-of read - so the
  retraction has to be a fresh assertion.
- **`Listing.published_version` is read.** It is moved forward by every commit,
  overlaid by a bitemporal `listing` fact, and consulted by the freeze-window
  rule. An empty value means the listing has never gone out, so there is no
  artefact in the world that can be stale.
- **The precedence policy becomes one function** in `state.baseline`, imported
  by both halves of the provenance split rather than copied into each. No
  behaviour changes; a test now asserts the two callers hold the same object.

## Capabilities

### New Capabilities

None. This change closes gaps in capabilities that already exist.

### Modified Capabilities

- `content-validation`: **Safety fails closed** is modified so that the gate
  resolves the listings it blocks at whatever level the fact was recorded
  against, and so that readiness reflects the block. A new requirement adds the
  freeze-window rule on channels that publish something irreversible.
- `review-and-publish`: **Rollback frees the batch and reverses the actions** is
  modified to also retract the facts the publish wrote, and a new requirement
  records the version each listing went to press on so the freeze-window rule
  has something to read.

## Impact

- `sc/sim/engine.py` - `_listings_for` as the single resolver, used by the scope
  walk, the safety gate, `_listings_hit` and the republish count;
  `_check_frozen_version` and `Overlay.published_version`.
- `sc/tools/planning.py` - the per-listing press version written on commit, and
  `rollback` retracting the COMMITTED facts it used to leave standing.
- `sc/state/overlay.py` - reads the `published_version` listing fact.
- `sc/state/baseline.py` - `precedence` promoted to one shared function.
- `sc/contracts.py` - `Channel.freeze_days` and `Listing.published_version`
  documented as what they now are rather than what they promised.
- `sc/graph/nodes.py` - the reviewer's diff and the violation-to-listing
  resolution share the validator's resolver; `precedence` imported rather than
  restated.
- `sc/replay/ingest.py`, `sc/tools/network.py` - the shared precedence function
  and the overlaid published version; a stale docstring corrected.
- `tests/test_validator.py` - the safety regression parameterised over product
  and variant, plus six freeze-window tests.
- `tests/test_orchestration.py` - retraction and repeated-rollback tests.
- `tests/test_ingest.py` - one policy, one function.
- No test is deleted and no KPI on the untouched catalog moves.
