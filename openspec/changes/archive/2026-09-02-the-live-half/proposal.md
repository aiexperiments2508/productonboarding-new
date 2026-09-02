## Why

Up to here this system is a replay. Five thousand events recorded once and
released on a clock, which is convincing and entirely in the past tense:
nothing outside the process can put a fact in, and nothing outside it can see
what comes out.

Two consequences follow, and both are about credibility rather than features.

**There is no way to show that the boundary holds.** The architectural claim is
that a supplier cannot write a value into the catalog - that a submission
becomes a document version, and what it asserts becomes a fact only when the
graph reads the document and writes it back inferred, under the fail-closed
safety gate. With no supplier able to submit anything, that claim is untested
in both senses.

**There is a hole between knowing a value is wrong and having a replacement.**
Correcting a published value takes a run, a reviewer and a republish. Until
that finishes, the wrong value is still on sale. Nothing in the system can
*hide* it in the meantime, so the only available options are to leave a known
error facing shoppers or to let the correction publish without review - which
is the gate the whole architecture exists to hold.

And a product's state is scattered. Whether a product is with its supplier,
awaiting review, on sale or held back is derivable, and nothing derives it, so
the two halves of the system - the recorded flight and whatever is happening
now - never meet on one screen.

## What Changes

- **Three connected applications**, in `apps/`, each its own process on its own
  port, each reaching the platform over MCP and by no other route. They hold no
  database and no access to the API.

  ```
  Vendor Portal  :8110  suppliers push specs, documents, images, new lines
  Storefront     :8120  the web page and the two marketplace listings
  Ops Console    :8130  print, shelf, search - freeze windows and errata
  ```

- **The boundary is asserted, not asserted-to.** A test walks their imports and
  their fetches, because that boundary is one convenient line away from being
  false at any moment and nothing would visibly break when it was.
- **A live lane on the event tape.** A submission is a real event the platform's
  own ingestion judges under the same precedence policy, materiality threshold
  and safety override as the recording - but it is not part of the recording, so
  the transport cannot rewind it and the clock cannot walk into it.
- **The lanes are told apart by a column and never by a sequence range.** Two
  failures made that necessary: `advance` had no upper bound and would walk the
  cursor into the high band, and the single ingest watermark would be pushed
  past every remaining taped event and silently stop recording facts. Both
  report success.
- **A supplier cannot write a value.** A submission is recorded as a document
  version; what it asserts becomes a fact only when the graph reads the document
  and writes it back inferred, under the fail-closed safety gate. The provenance
  taxonomy does the enforcing - there is no permission check to route around,
  and the intake's imports are asserted so there cannot be one.
- **Redaction, and a second gate.** Hiding a value known to be wrong is
  authorised by the approval that already agreed it was wrong and happens at
  once. Republishing needs its own release decision, enforced as a fourth
  refusal in the publish path and recorded in its own table - never in the
  approvals table, where it would satisfy the first gate by itself.
- **What "hide" means is derived from what the channel can do**, and one
  correction gets five different right answers: a web listing withheld, a
  marketplace withdrawn (its own rules make a placeholder a hard violation), a
  search facet dropped, a shelf label queued for reprint, and a print run that
  cannot be recalled at all - which opens an erratum and is never reported as
  redacted.
- **Copy is redacted with the value it quotes**, through the same lineage the
  blast radius already uses. A bullet reading "may contain milk" above a spec
  row saying the allergen statement is being checked would make the page worse
  than before it was corrected.
- **Product Lifecycle joins the halves** - every product in the lane its own
  state puts it in, derived and never stored, for the reason the publication
  estate is derived from the channels. The three applications open from it.
- The manifest gains `accepts`, so each intake endpoint's tools are derived
  rather than written down; a media overlay, so an uploaded pack shot actually
  clears the missing-media finding instead of being theatre; accepted supplier
  lines, so a proposed product can become a real one by a reviewer's decision.

## Capabilities

### New Capabilities

- `vendor-intake`: what a supplier may submit, what it may see, and the
  provenance that stops a submission becoming a value.
- `redaction`: hiding a value known to be wrong, per channel, and the second
  gate that republishing has to pass.
- `product-lifecycle`: every product in exactly one lane, derived from its own
  state.

### Modified Capabilities

- `event-ingestion`: a second lane the transport cannot rewind and the clock
  cannot walk into, told apart by a column and never by a sequence range.
- `protocol-surfaces`: three applications reach the platform over the protocol
  and by no other route; an intake endpoint exposes what its system accepts and
  cannot reach the fact store.
- `review-and-publish`: a release decision is a fourth refusal, recorded in its
  own table.

## Impact

- `apps/vendor/`, `apps/storefront/`, `apps/ops/`, `apps/_mcp.py` - three
  processes and the endpoint they share.
- `sc/estate/intake.py`, `submissions.py` - the intake surface and the nine
  stages a submission walks.
- `sc/estate/manifest.py` - `accepts`, from which intake tools are derived.
- `sc/redaction/` - the per-channel derivation, the obligations, the ledger.
- `sc/lifecycle/stages.py`, `board.py` - the lanes and the signals behind them.
- `sc/replay/tape.py`, `ingest.py` - the lane column, the bounded advance, the
  per-lane watermark.
- `sc/tools/planning.py` - the fourth refusal in the publish path.
- `sc/schema.sql` - submissions, redactions, obligations, release decisions.
- `tests/test_app_boundary.py`, `test_intake.py`, `test_lifecycle.py`,
  `test_live_lane.py`, `test_redaction.py`, `test_protocols.py`.
