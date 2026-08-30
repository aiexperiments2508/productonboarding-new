## Why

The factory could run and nobody could watch it run. A correction reached an
approval gate inside a Python process, and the only way to see the case, its
blast radius, the readings that were considered or the decision that was taken
was to read a checkpoint database. There was also no way to point the system at
a model gateway other than the one it assumed, which mattered the first time it
was pointed at a real one.

Both halves had real defects, and none of them was domain work.

**The API still described the previous system, in two places that had never
run.** `/api/health` read a supply-chain network and an order book that no
longer existed, and `/api/plan/commit` passed a keyword that had been renamed.
Both would have failed the first time they were called. `/api/network/alternates`
and `/api/network/bom` answered questions about suppliers and bills of
materials; `/api/scenarios/risk` served a sampling layer that had been deleted.

**The variant table endpoint discarded the argument it existed to carry.** It
flattened each cell to a bare value, dropping the document and the version behind
it. That is not cosmetic: the base-versus-variant case rests entirely on the base
model having been independently certified at 45 W by a named document a fortnight
before an ambiguous correction named the product and not the variant. A reviewer
cannot check that against a number on its own, and the evidence line that carries
the whole argument was silently disabled. It also made the route and the tool
that serves it disagree about the same table.

**A run could not price itself.** Model spend is written per stage so that
concurrent writers do not erase one another, and the run-state route returned the
raw checkpoint with no total, so the cost of a run existed in the database and
nowhere a reader could see it.

**The launcher started a second gateway it then ignored.** With an existing
gateway named in the environment, the launcher still started its own proxy: the
application talked to one address while an unused child process was nursed on
another. The child was doomed regardless, because the provider credentials live
in the gateway you attach to and not in this repository.

**Only one door read the configuration.** The launcher read `.env`; the MCP
server, LangGraph Studio, the index builder and the demo script all ran on
whatever environment they happened to inherit. That is why building the retrieval
index reported the gateway unreachable on the default port while the application
three metres away was talking to it happily. The index builder was also missing
the import shim its sibling script has, so it could not be run directly at all.
`python-dotenv` was declared as a dependency and imported by nothing, which told
the next reader that configuration loading worked in a way it did not.

**Tier resolution could not read the names it was given.** Tiers are inferred
from model identifiers, and a gateway serving five flash-class models genuinely
has no readable reasoning tier - so everything collapsed onto whichever alias
looked newest. The test suite made this worse by asserting that a reasoning tier
existed, which is a claim about one deployment rather than about the code.

**The launcher rebuilt the seed pack on every boot** because its check was keyed
on a supply-chain file the current generator deletes, so the condition was always
true. It also started the API without checking whether the port was already in
use, which produces the most confusing five minutes available: the server fails
to bind, the browser opens anyway, and whatever was already listening answers.

**The console narrated past its own story.** A finished run navigated straight to
the review screen - and since suspending at the approval gate is the normal
terminal state, pressing "run" teleported past the blast radius and the
resolutions, the two views the system exists to show. The only feedback during
the minute a run takes was a twelve-pixel phrase in the footer. A tape-jump
parameter was typed through the client, the shell and the panel and supported by
the backend, and nothing ever sent it. The navigation described the resolutions
view as placed against a frontier, while that view's own header argues there
should not be one.

## What Changes

- **An HTTP surface over the same functions the pipeline calls.** The catalog,
  the blast radius, the variant table, the derivation, the corpus, the change-set
  validators, the correction cases, the runs, the approvals, the publish locks,
  the audit ledger and the bitemporal fact read. Nothing gets a second
  implementation, which is what keeps the console and the pipeline from drifting
  into two accounts of the same state.
- **The supply-chain routes are replaced**: alternate suppliers and bill of
  materials become the variant table and the derivation read, the sampling route
  is gone, and the change-set routes take change sets. `/api/health` and
  `/api/plan/commit` are made to work.
- **The variant table carries the document behind every value** - the cell the
  tool itself produces, with its value, version, source document, provenance and
  confidence - so the route and the tool say the same thing about the same table
  and the evidence line has something to render.
- **A run reports what it spent.** The run-state route sums the per-stage spend
  it was already carrying, rather than storing a second figure to keep in step
  with the first.
- **Runs stream node by node** over server-sent events, so what a reader watches
  is the pipeline's own progress rather than a progress bar imitating it. The
  same for a revision.
- **The graph diagram is read out of the compiled pipeline**, so it cannot drift
  from what actually executes and does not need an external service to render.
- **The evidence allowlist is served from the allowlist itself**, so the
  governance claim on screen cannot drift from the governance in force.
- **The model gateway becomes a thing you can point somewhere.** Tiers are
  classified on whole tokens rather than substrings - "gemini" contains "mini",
  and matching substrings files every Gemini model including the Pro tier as a
  small model, silently routing the reasoning work to the cheap tier. A tier the
  gateway does not serve degrades to the strongest model it does serve rather
  than raising from inside a run. A deployment can pin a tier by name, and the
  pin is validated against the gateway's own list so a retired alias surfaces at
  startup instead of as a 404 mid-run. The fallback model list is parsed from the
  shipped gateway configuration rather than duplicated in code.
- **Selection is hot-loaded and persisted**, and the write-back preserves the
  file: existing comments and ordering survive, values are updated on their own
  lines, and a credential is never created into a file that does not have one.
  A model the gateway does not serve, or an embedding model asked to do chat, is
  refused before it can fail inside a run.
- **Configuration is read at entry, by whichever door.** Loading `.env` moves to
  the bootstrap whose stated job is making the process usable however it was
  entered. Attaching to an already-running gateway becomes the default when one
  is named. `python-dotenv` is dropped.
- **The launcher** keys its seed-data check on the file the generator actually
  writes, and refuses to start when the API port is held, naming the process that
  holds it.
- **The console** lands a finished run on the blast radius and offers the pending
  decision as an action rather than a redirect, gives the live node stream the
  middle of the screen while a run is in flight, sends the tape-jump parameter it
  was already typed for, and stops the navigation promising a chart the screen
  argues against.

## Capabilities

### New Capabilities

- `run-and-review-api`: the HTTP contract over the correction factory - reading
  the catalog and the blast radius, listing correction cases, starting and
  streaming a run, delivering a reviewer's decision, revising a plan, driving the
  replay clock, and reading the audit trail and the bitemporal record.
- `model-gateway`: the single egress to a model - discovering what a deployment
  actually serves, classifying it into tiers, degrading when a tier is absent,
  and persisting a selection without damaging the file it is written to.

### Modified Capabilities

None. The variant-table regression belongs to `run-and-review-api`, which this
change introduces, so it is an ADDED requirement like the rest of that spec -
there is no earlier version of it to modify. The defect is the more useful half
and is kept where it can survive: written into the requirement itself, which
says what flattening the cell cost rather than only what the cell now contains.

## Impact

- `sc/main.py` - the routes, the broadcaster, the streaming, the spend total,
  and the static mount kept last.
- `sc/llm/models.py` - classification, discovery, tier resolution, selection.
- `sc/llm/env_file.py` - the write-back that preserves the file.
- `sc/llm/gateway.py` - the pinned-tier accessors and the gateway address.
- `sc/bootstrap.py` - configuration loading moved to entry.
- `run.py`, `startup.bat`, `scripts/build_index.py`, `scripts/prepare_demo.py` -
  attaching, port checking, seed-data keying, the import shim.
- `litellm/config.yaml`, `.env.example`, `requirements.txt` - the shipped
  aliases the fallback is parsed from; `python-dotenv` removed.
- `README.md` - how to run against either kind of gateway, the six demo arcs,
  and the reasoning behind the choices that are not obvious.
- `frontend/**` - the console; no test in the repository covers it.
- `tests/test_models.py` - stops asserting a reasoning tier exists and asserts
  the documented degradation instead.
