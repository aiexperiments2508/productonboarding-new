## Why

The deterministic core could decide things, and nothing asked it to. A
supplier's corrected specification arrives as prose in a document; something has
to read it, work out which product and which variant it is about, offer readings
the record actually supports, rewrite every sentence built on the old figure,
and put the result in front of a reviewer who has to sign it. That loop is the
only place in this system where a model is invited in - so it is also the only
place the bounds on a model can be written down.

Four things were true before this change, and together they are what makes it
the size it is.

- **The loop was still recovering a disrupted plan.** Seventeen nodes went
  monitor, detect, triage, investigate, generate alternatives, simulate, rank,
  recommend, approve, commit. There was no content leg at all: nothing walked
  the lineage into actions, nothing rewrote the copy that quoted a superseded
  figure, nothing re-validated the copy it had just written. Propagation - the
  thing the brief is actually about - had no node.
- **The peers described the previous estate.** impact-analyst, recovery-planner,
  simulator and risk-analyst. risk-analyst had nothing left to assess once the
  sampler was deleted, and nobody at all was responsible for writing copy.
- **The dangerous surface was not one server.** Two toolsets declared mutating
  tools - `planning-execution` and `inventory-capacity`, whose `reserve_capacity`
  wrote from a server whose name promised a read. An operator handing out
  "everything except planning" was handing out a writer, which is the whole
  property the partition exists to provide.
- **A run swept every open correction into one recommendation.** Signals were
  derived from every fact in force, so an air-purifier wattage correction and a
  snack bar's net weight arrived at the reviewer as one approval. That was the
  visible half. The invisible half was worse: `_forced_escalation` measured the
  **union** blast radius, so an Northaven AP300 run came back CRITICAL with a
  `triage_reason` reading "escalated by policy: PRD-02, PRD-05 is regulated" -
  rendered verbatim on two screens and carried into the approval grounds. The
  purifier is not regulated and its rated power is not safety-class; the
  CRITICAL was borrowed from a trail mix bar. PRD-05 got in because a
  source-conflict signal names DOC-05 as an entity and tracing that document
  reaches the granola bar: correct as a document trace, wrong as grounds for
  escalating this case.

There is a fifth property, and it is not a defect - it is the claim the whole
change exists to make good on. **The pipeline reaches a recommendation and an
approval gate with no model available.** Every node that calls a model catches
gateway failure and has a deterministic answer behind it, and the graph suite
runs with the gateway pinned to a closed port so the fallbacks are what CI
actually exercises. There is no LLM mocking anywhere, because a mocked model
tests the mock.

## What Changes

**BREAKING** - the graph, the peer roster and the toolset partition are
replaced.

- **A correction pipeline of twenty-two nodes.** Read the record, read the
  unread documents, narrow to one case, classify, resolve scope, enumerate
  readings, validate them concurrently, rank, then the content leg the old graph
  had no equivalent of: turn the lineage walk into actions, flag the sentences
  no rule can settle, rewrite the affected copy, fill the gaps a channel demands,
  re-validate the whole thing including the proposed copy, and recommend. Four
  branch nodes handle the shapes a correction can take - a precedent to apply, a
  question for the supplier, nothing publishable, a publish that lost its race.
- **Bounded model touchpoints, each with a deterministic fallback.** A model
  reads a value out of prose, argues which variant a document meant, notices a
  claim has become untrue, rewrites copy, fills a required field from supplied
  text, and writes the narrative. It never originates a number, a severity, a
  ranking or a publish decision: triage's severity is overridden by measurement,
  the recommendation may only quote figures a validation pass produced and may
  only name a candidate that was actually validated, and the enrichment may only
  copy values out of chunks it was handed.
- **The scope fallback is the widest reading, not the narrowest.** With no model
  to argue it down, a correction naming a product and no variant applies to
  every variant, flagged low-confidence with a rationale that says why. Applied
  too widely, a reviewer sees it and rejects it; applied too narrowly, a wrong
  number stays live and nobody sees it at all.
- **An evidence desk** - a closed, read-only allowlist of seven catalog and
  corpus lookups, a bounded loop, refusals recorded as evidence rather than
  dropped, and a catalogue rendered from the tool table so the prompt cannot
  drift from the governance in force. Its most important property: the standing
  questions - how the variants actually differ, and which versions of the
  document exist - are answered from the catalog **before** the model is asked
  anything, because a retrieved postmortem will happily assert an answer the
  current catalog contradicts, and a model reading one believes it.
- **Re-planning on the same thread.** New evidence forces a revision rather than
  a restart: the checkpoint history stays continuous, the superseded readings are
  carried forward deduplicated by what they do rather than by what they are
  called, and the run reports which figures moved. A pending approval is
  withdrawn first, as a real REJECT delivered through the same interrupt a
  reviewer uses, so it lands in the ledger with a decision and an actor instead
  of vanishing.
- **Case scoping**, and the principle that came out of fixing it:
  **extraction is global, action is case-scoped.** A case is one product, because
  the publish lock is channel-and-product and the product is therefore what a
  reviewer commits. The first attempt at this filtered inside `monitor`, which
  runs before anything has been read - so it filtered an empty list and every
  correction extraction then read arrived behind the filter unscoped. The filter
  belongs after reading: a document is read once whatever case is running, its
  facts are recorded either way, and only the signals a run *acts on* are
  narrowed.
- **Four peers at real seams** - walk the lineage, enumerate the readings,
  validate one deterministically, rewrite the copy - each discoverable with a
  card and each falling back in-process when its peer does not answer. The
  approval gate is deliberately not among them, and neither is publishing.
- **Six toolsets partitioned by who would own them** in a retailer, with every
  mutating tool concentrated in one named server so an operator can hand out the
  other five. The one qualified exception is the event plane's tape control,
  which moves the clock and never the catalog.

## Capabilities

### New Capabilities

- `correction-pipeline`: the orchestrated run from an arriving correction to an
  approval gate - what each stage is allowed to conclude, what a model may never
  originate, and the guarantee that the whole run completes with no model
  reachable.
- `evidence-desk`: the closed read-only tool surface the scope investigation is
  allowed to use, its mandatory catalog lookups, its bounds, and the record it
  leaves behind including what it was refused.
- `replanning`: revising a live correction case against evidence that arrived
  after the plan, on the same thread, without losing what the reviewer had
  already seen.
- `protocol-surfaces`: the toolset partition and the peer roster exposed over
  MCP and A2A - which surface owns which tool, what may cross a wire, and the
  requirement that delegating never changes the answer.

### Modified Capabilities

- `blast-radius`: the traversal is unchanged, but what may be concluded from it
  is not. A union radius over several signals legitimately reaches products a run
  is not deciding about, so the regulated and safety totals are a measure of
  reach and are no longer sufficient grounds for escalating a case.

## Impact

- `sc/graph/build.py` - twenty-two nodes, four branch nodes, one bounded cycle,
  and a real `interrupt()` at the approval gate.
- `sc/graph/nodes.py` - the pipeline, the case grouping, the fallbacks.
- `sc/graph/branches.py` - the exception routes and the retry cycle.
- `sc/graph/state.py` - the reset marker, the signal merge, the case fields.
- `sc/graph/evidence.py` - the allowlist, the mandatory lookups, the budgets.
- `sc/graph/prompts.py` - seven prompts; every figure is supplied rather than
  recalled.
- `sc/a2a/agents.py`, `sc/a2a/server.py`, `sc/a2a/client.py` - the four peers,
  their cards, and the transport with its in-process fallback.
- `sc/mcp/registry.py` and the six server modules - the partition;
  `inventory-capacity`, `supplier-network`, `transport-lanes` and
  `planning-execution` are gone.
- `sc/main.py` - `/api/cases`, and `case_id` accepted on both run routes.
- `tests/test_graph.py`, `tests/test_branches.py`, `tests/test_replan.py`,
  `tests/test_protocols.py` - all four run with the gateway unreachable.
