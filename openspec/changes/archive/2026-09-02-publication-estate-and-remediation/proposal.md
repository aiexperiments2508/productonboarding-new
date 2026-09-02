## Why

The blast radius stops at the catalog edge. It says a correction reaches fifteen
content assets across five listings on four channels, which is true, precise,
and expressed entirely in identifiers only this system can read.

Everybody who has to *act* on one works in SKUs. A buyer asked "which products
are affected" cannot answer from `VAR-01B`; a marketplace account manager asked
"what do I have to reissue" cannot answer from `LST-07`. The most interesting
finding this system produces - that a correction scoped to the Max lands on the
base model's page too, because a comparison table there quotes both - is
currently expressed in a vocabulary that hides who it is about.

There is a second gap beside it. `commit_plan` publishes an approved resolution
and `rollback` retracts one, and both are whole-plan: one call, one outcome, all
channels together. That is the right shape for a *decision* and the wrong shape
for a *dispatch*, because the systems on the other side are independent and fail
independently. A caller told "failed" cannot tell whether nothing went out or
almost everything did.

And nothing named the publication systems at all. Six channels are declared,
each with its own schema, its own freeze window and its own idea of what a
listing is - and the thing that turns "this correction affects CH-PRINT" into
"the printed catalogue is inside its freeze window and cannot be changed" was
knowledge in the validator, not a system anybody could see.

## What Changes

- **The blast radius answers in SKUs**, alongside the identifiers it already
  answers in. Each affected SKU carries the listings and channels it is live on.
- **The publication estate is derived from the channels**, not configured
  beside them - a publication list that could disagree with the channel list is
  a second account of where content goes, and the first thing it would disagree
  about is the channel somebody just added.
- **The systems to tell are grouped with their SKUs.** "Eleven listings" is a
  number; "these four SKUs on these three systems" is a work list.
- **A dispatch plan that sends nothing**, so a reviewer sees that the print
  channel is frozen before deciding rather than from a report afterwards.
- **Dispatch and revert report per system**: sent, deferred, or refused, each
  with its reason. A channel inside its freeze window is deferred rather than
  attempted, because a printed artefact nobody can recall is worse than a
  decision not to print.
- **A channel never sent to is not reported as reverted.** That would be a lie
  about a printed page.

### What deliberately does not change

The three refusals - a recorded approval, evidence that has not moved, no open
safety violation - stay exactly where they are, at the planning boundary. This
change dispatches and reports; it decides nothing. A commit that refuses refuses
every system, because those refusals are properties of the resolution rather
than of any one channel, and publishing to four channels a resolution nobody
approved would be four problems instead of none.

## Capabilities

### New Capabilities

None. This is the existing blast radius answered in a second vocabulary, and the
existing publish and rollback reported at a finer grain.

### Modified Capabilities

- `blast-radius`: the walk resolves to affected SKUs and to the publication
  systems that carry them.
- `review-and-publish`: publishing and rollback report per system, and a
  channel whose artefact cannot be recalled is deferred rather than attempted.

## Impact

- `sc/estate/publication.py` - new: the publication systems, derived from the
  channels, and the SKU and system views of a trace.
- `sc/estate/remediation.py` - new: the dispatch plan, and per-system dispatch
  and revert over the existing commit and rollback.
- `sc/main.py` - the publication routes.
- `tests/test_publication.py` - new.
