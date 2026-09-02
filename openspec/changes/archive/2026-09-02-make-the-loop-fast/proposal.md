## Why

A correction run takes three to four minutes against a live gateway, and
nothing in the repository noticed. The whole test suite runs with the gateway
pinned to a closed port, so what CI exercises is the deterministic fallback in
every node - which returns instantly. The suite measures correctness and has
never measured latency, so a sequential loop over a reasoning-tier model looked
exactly like a fast one.

The shape of the cost is not subtle once it is looked for. `regenerate` rewrites
one content field per iteration of a plain Python `for` loop, each iteration a
blocking round-trip to the reasoning tier, capped at twelve. `extract` reads one
supplier document per iteration of another. A cold run is roughly twenty
sequential round-trips, and the two loops are most of it. Nothing about the work
is sequential - twelve fields on five listings have nothing to say to each
other - it was simply written in the order it was thought of.

There is a second cost that is not latency. Every stage already streams its own
result to the reader as it completes, carrying the whole update the stage
produced. The client uses the stage's *name* to highlight a step and discards
its *content*, then re-fetches the entire run state at the end. So a reviewer
watches an inert progress indicator for the full duration and everything arrives
at once, which makes a slow run feel slower than it is and a fast one feel no
faster.

## What Changes

- **The per-field rewrites run concurrently** on a bounded pool, and the results
  are reassembled in target order rather than completion order. The change set,
  the trace line and the `trace_hash` are identical to what the sequential loop
  produced - that equality is the test, not a hope.
- **The per-document model reads run concurrently, and the writes stay
  sequential.** This split is not an optimisation detail, it is the whole
  correctness argument: extraction carries a watermark that advances as each
  document is persisted, and the next document is read against it, so that a
  covering email restating its own specification sees what the specification
  already wrote. Parallelising the reads is safe because a read depends only on
  the catalog and the event. Parallelising the writes would assert the same
  correction twice.
- **Spend and errors merge deterministically within a stage.** Spend is already
  keyed per stage so concurrent stages cannot erase one another; concurrency
  *inside* a stage puts the same pressure on the same accumulator one level
  down. Each worker accumulates its own, and the merge is ordered by target.
- **A gateway outage still reports as one line, not twelve.** The existing
  deduplication is a membership test against a shared list, which is exactly the
  thing concurrency breaks.
- **Nothing about what the model is asked changes.** No prompt is edited, no cap
  is raised, no step is skipped. This change makes the same calls at the same
  time as each other rather than one after another.

### What it measured

A correction run to the approval gate, against a live gateway, on a cold cache:

- **21.4 seconds**, down from the three to four minutes the sequential loops
  produced. Sixteen fresh model calls, no cache hits on any pipeline stage.
- `extract` made nine of those sixteen concurrently. That stage was the longest
  serial chain in this particular correction, and it is the one whose *writes*
  had to stay sequential - so the split between reading and persisting is
  carrying most of the saving.
- `regenerate` made none. The deterministic propagation settled every affected
  field on this run, so the fan-out had nothing to fan out. Worth recording
  rather than glossing: the twelve-call worst case is real and is not what every
  correction hits, and a figure quoted from a run that avoided it would be a
  figure quoted from the easy case.

## Capabilities

### New Capabilities

None. Nothing new is asked of the pipeline; the work it already does is
rearranged in time.

### Modified Capabilities

- `correction-pipeline`: independent model work inside a stage may run
  concurrently, and doing so is required not to change the stage's answer.

The streaming contract is deliberately **not** modified. Each stage message
already carries that stage's own result, which is everything a reader needs to
render it on arrival; what changes is that the client stops throwing it away.
Writing a requirement for behaviour the API already has would report progress
that was made in 2026 as though it were made here.

## Impact

- `sc/graph/nodes.py` - `regenerate` fans its rewrites across a bounded pool;
  `extract` prefetches its readings concurrently and persists them in tape
  order; both merge spend and errors deterministically.
- `frontend/src/app/App.tsx` - the streamed stage result is merged into view
  state as it lands instead of being discarded.
- `scripts/prepare_demo.py` - warms the response cache so a rehearsed run pays
  no first-call latency.
- `tests/test_graph.py` - the equality test, and the spend-merge test extended
  to concurrency within a stage.
