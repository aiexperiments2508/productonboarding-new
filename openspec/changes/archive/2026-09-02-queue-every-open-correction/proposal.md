## Why

The Ingest Fabric is a map with a shut rail beside it, and three things are
wrong with that.

Nothing on it says what suppliers have sent. The live event feed sits in System
Control next to the transport, on the argument that the tape releases those
rows - true, and the smaller half, because the question a person has on reading
one is *what does this touch*, and the answer is the picture, not the transport.
And the map draws every listing at full weight, so ten products against six
channels is a hairball in which the motion that means "this is publishing" has
stopped meaning anything.

The sequential pass over a bundle is already built and has no caller. The
impact layer exports the working and clearing helpers, the map renders both, and
the streaming assessment endpoint has served one product at a time with its
entities resolved server-side since it was written. Nothing walks it.

And the loop works exactly one case per click - which is the smaller of two
problems. The larger is that the case list cannot see most kinds of correction
at all. It derives signals from attribute values in force and channel
rejections, and three sorts the estate detects perfectly well never reach a
reviewer:

- **A source conflict.** Ingestion returns before recording when an incoming row
  ranks below the document in force, and it is right to - recording the loser
  would let a portal spreadsheet quietly beat approved artwork. But the losing
  value then leaves no fact behind, and a view derived from facts alone cannot
  see it, though the graph has a whole leg for one.
- **A data gap.** Classified by path, so a mandatory field asserted empty reads
  as a correction to whatever it used to say rather than as missing information.
- **A withdrawn document.** The overlay has carried document status the whole
  time and only the summariser reads it.

## What Changes

- **The Fabric reads left to right**, the way the map itself reads: what is
  arriving, the graph it arrives into, what is still in force. The live feed
  moves next to the picture it is about.
- **Processing a bundle walks it.** The working product breathes, the one before
  keeps a verdict-coloured ring, and the map pins to that supplier for the walk
  so nothing is assessed off-page.
- **The pacing is on the client, and that is not a preference.** The streaming
  endpoint takes a pace and sleeps between products, which works until something
  between the two buffers the response - a proxy without buffering disabled, a
  dev server, an embedded webview. Then every frame lands in one chunk, the
  renderer batches four updates into one, and the walk the whole feature exists
  to show is skipped in silence. Buffering cannot reorder or drop frames, so a
  client that paces its own reading is correct on every transport.
- **The map holds detail where the reader is looking.** A listing is drawn at
  full weight when it is traced, in the blast radius, being worked, or stopped;
  otherwise it is a hairline and its count rides on the variant as a chip that
  traces it. Nothing is hidden and the picture stops shouting. The systems tier
  is off behind a toggle: that is the estate rather than the catalog, and System
  Control is the section about it.
- **Three more kinds of open correction, all derived.** Source conflicts
  recomputed from the event that carried the losing value against what is in
  force *now*; gaps classified by ingestion's own predicate rather than by path;
  withdrawals read off the document status the overlay already carries.
- **Scoping the withdrawal is the sharp edge, and the obvious version is
  inverted.** Retracting a revision is usually the *opposite* of bad news - a
  provisional drawing pulled after the audit closed, the earlier version
  standing, which the merge already treats as a resolver. Keying by document
  would turn the one piece of good news on the tape into a critical incident. A
  case opens only where a fact in force *pins* the retracted document version: a
  value that revision asserted and nothing has replaced. An unpinned fact merely
  inherits the version and is still supported.
- **All three stay derived.** Nothing is stored, so nothing has to be retired: a
  conflict the record later adopted, a gap later filled and a document later
  reinstated stop being reported because the record stopped saying them. That is
  the only resolution rule that cannot drift out of step with the facts.
- **The header button works every open case in turn** rather than the worst one,
  each as its own run stopping at its own approval gate - a success for the
  sweep, not a reason to stop, because the queue of decisions is the point.
  Between runs it re-reads the list, so a case a run *opened* by reading an
  unexamined document is picked up instead of waiting for somebody to notice the
  scoping step reporting it.

## Capabilities

### Modified Capabilities

- `correction-pipeline`: the open-correction queue covers source conflicts, data
  gaps and withdrawn documents, all derived rather than stored; a document
  withdrawal that leaves values unsupported opens a case without becoming a
  resolver.
- `run-and-review-api`: the case list is re-derived on every read, so a case a
  run opened is visible immediately and one the record resolved retires itself.

## Impact

- `sc/graph/nodes.py` - the three derived signal passes and the pinned-version
  scoping.
- `sc/replay/ingest.py` - the gap predicate made public, so the queue and the
  ingestion that recorded the row cannot disagree about what counts as missing.
- `frontend/src/components/IngestFabric.tsx` - the three-column reading, the two
  sweeps, the client pacing.
- `frontend/src/components/NetworkMap.tsx`, `MapControls.tsx` - weight where the
  reader is looking; the systems tier behind a toggle.
- `frontend/src/components/EventFeed.tsx`, `SystemControl.tsx` - the feed moves
  to the picture it is about.
- `frontend/src/app/App.tsx` - a run may finish without taking the reader off
  the screen they started the sweep on.
- `tests/test_graph.py` - the three kinds, and the withdrawal that opens nothing.
