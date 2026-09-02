## Why

Every surface in this system answers a question about *one thing* - one
correction, one product, one batch. Nothing answers one about the estate: this
supplier sent forty rows on the fourth of July, where are they now, and what
did it cost.

The data is there and nothing reads it together. Two state spines exist and
neither meets the other. `estate/submissions` walks a submission through nine
stages and stops at `verdict` - it knows what arrived and what the system made
of it, and nothing about what happened next. `lifecycle/stages` places a
product in one of six lanes from its *current* state - it knows a product is on
sale, and nothing about which archive delivered it. A category manager's actual
question falls exactly between them.

The cost question is worse than unanswered; it is answerable wrongly.
`llm_calls` is being asked to be a cache and a ledger at once and cannot be
both. Its primary key is the cache key, so asking the same question twice
leaves one row and a counter. `created_at` is the *first* time that prompt was
ever seen, so a window over it answers a question nobody asked. There is one
row per distinct prompt, so "what did July cost" cannot be computed at all. And
no column names the feed, so spend cannot be attributed to the archive that
caused it. Embedding spend is invisible entirely.

There is no control over any of it either. An operator can watch a reindex
consume tokens and has nothing to stop it with.

## What Changes

- **A control tower**: where every feed's rows have got to, what arrived over a
  window, the KPIs across it, and what the models spent reaching them. Nothing
  on it decides anything - every verdict, gate outcome, stage and lane is read
  from the module that already owns it.
- **Seven states from received to on sale**, joining the two spines, derived on
  read, with a pure `state_of` in the same shape `stage_of` already has.
- **The grain is the row a supplier sent**, and the screen says so. Product
  Lifecycle places a *product*, and a product is as blocked as its worst
  variant, so a pack whose 500ml is fit to sell and whose 1L is not appears
  there as one product and here as one row cleared and one not. Both are right
  and they will disagree, so the caption names which question was answered.
- **`RETURN_TO_SOURCE` is deliberately not blocked.** Blocked is the gate
  stopping it or a finding blocking it - the two things a supplier has to fix. A
  record with a gap the gate let through is mid-flight, and filing it as a
  failure would count the whole AI-correction lane as one.
- **An append-only spend ledger beside the cache.** One row per invocation,
  written at the two choke points completion already had, plus embedding -
  which is how embedding spend stops being invisible.
- **A cache hit is recorded, not skipped**, with its tokens intact and no cost,
  so spend and spend avoided are two sums over one table rather than one number
  with a footnote. What a hit would have cost is read off the cache's own
  record and never re-estimated.
- **Two clocks, and each answers only what it can.** Windows filter the
  simulated clock; durations measure the real one. Subtracting across them would
  say a feed that arrived in simulated August and published this morning took
  four weeks.
- **A cost of zero is not a fact about the price.** A model the gateway's price
  map does not know returns no figure, so the ledger carries whether a call was
  priced and a window nothing priced says so rather than reporting a confident
  $0.0000.
- **The cap is two caps.** A money cap on a gateway that prices nothing is a
  control that can never fire, so a token cap sits beside it and either trips
  alone. Past it the gateway raises the same error an unreachable gateway
  raises, so every deterministic fallback already written runs and the work
  continues with narrower answers.
- **Six personas, and the screen calls them a lens.** A persona changes which
  figures lead and nothing else; the API says so in its own contract.
- **Every rate is null rather than zero when its denominator is empty**, and a
  truncated window says every figure below it is a sample.
- **A read-only control-tower toolset** over MCP. The spend cap is deliberately
  not a tool on it.

## Capabilities

### New Capabilities

- `control-tower`: the join across submissions, readiness, onboarding and
  lifecycle - feed flow, the arrival register, the KPIs over a window, and the
  personas that choose which of them lead.
- `model-spend`: the append-only ledger of model invocations, the two sums over
  it, and the caps that stop unattended spend.

### Modified Capabilities

- `model-gateway`: every invocation appends to the ledger, embedding included,
  and a breached cap refuses the way an unreachable gateway refuses.
- `protocol-surfaces`: the control tower is a toolset this platform implements,
  distinct from the estate systems it talks to, and it declares no mutating
  tool.

## Impact

- `sc/tower/flow.py`, `register.py`, `kpis.py`, `spend.py`, `personas.py` -
  new; all read-only, all derived.
- `sc/llm/gateway.py` - the ledger append at the completion and embedding choke
  points, the two caps, and the refusal past them.
- `sc/schema.sql` - `llm_ledger`, and an index on arrivals so a window is not a
  full scan.
- `sc/mcp/control_tower.py`, `sc/mcp/registry.py` - the read-only toolset.
- `sc/main.py` - the tower routes and the cap, which demands a name.
- `frontend/src/components/tower/*` - the four tabs; `ControlTower.tsx`
  rendered the Ingest Fabric and is renamed to say so, freeing the section id
  for the thing that is one.
- `tests/test_tower.py` - the states, the two clocks, the ledger, the caps and
  the personas.
- `README.md` and two docstrings - the estate is fifteen systems and the prose
  said ten or eleven. The test asserted at least ten and passed, so only the
  prose was wrong.
