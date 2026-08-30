# Autonomous Product Intelligence Factory

TCS Use Case 05. A supplier sends a corrected specification after content has
already been prepared for several channels. The system closes the loop:

`Supplier data received → Content parsed → Attributes extracted → Conflicts resolved → Taxonomy mapped → Rules validated → Gaps enriched → Reviewer approved → Product published`

Re-publishing is a real loop, not a second run. A correction that is itself
corrected revises the resolution on the same thread: the superseded
recommendation and the readings it beat are carried forward and re-validated,
and the UI reports what moved and why.

**The LLM interprets; deterministic code decides.** A model reads a corrected
value out of a supplier PDF, argues which variant it applies to, flags copy
whose meaning has gone stale, and rewrites the affected sentences. Everything
that determines what publishes — identity, lineage, taxonomy, channel rules,
effective dating, propagation, approval gates, audit — is ordinary software.
Same input, same output, always.

## Run it

```bash
pip install -r requirements.txt
copy .env.example .env
python scripts/generate_data.py
python run.py
```

Open http://127.0.0.1:8000. No database server, no message broker, no
containers of our own — SQLite is a file, the vector index is a numpy array,
and the event plane is a table.

Useful flags: `--reset` (drop the database and reload the seed pack),
`--no-gateway` (work offline from the LLM response cache), `--port`.

### The model gateway

Every model and embedding call leaves through one LiteLLM gateway. There are
two ways to have one, and `.env` decides which.

**Attach to a gateway that is already running** — a shared instance, a
container, one started by hand:

```
LITELLM_BASE_URL=http://127.0.0.1:5000
LITELLM_API_KEY=<the gateway master key>
```

`run.py` then starts nothing of its own. The provider credentials live in that
gateway, so no `GEMINI_API_KEY` is needed here. Models are read from its
`/v1/models` at runtime, so whatever it serves is what the UI offers and what
the graph uses. **Nothing names a model alias in code.**

**Or start one** from `litellm/config.yaml` by leaving `LITELLM_BASE_URL` unset
and supplying `GEMINI_API_KEY` instead.

The graph asks for a *tier* — the fast model for extraction, triage, claim
scanning and enrichment; the reasoning model for scope resolution, copy
regeneration and the reviewer write-up. Which model fills each tier is normally
inferred from the model names, but that only works when the names say
something: a gateway serving five flash-class models has no readable reasoning
tier and everything collapses onto whichever is newest. Pin them when the names
cannot carry the distinction:

```
LITELLM_FAST_MODEL=gemini-3.5-flash-lite
LITELLM_REASONING_MODEL=gemini-3.7-flash
```

Both are checked against the gateway's own list at startup, so a retired alias
surfaces there rather than as a 404 from inside a run.

### Python version

**3.12 is required to run the gateway locally.** The LiteLLM proxy cannot
install on 3.14 — `orjson` has no wheel and its Rust build fails against the
3.14 ABI. Everything else in the stack runs on 3.14, so attaching to an
existing gateway works on either.

## What V2 added

The MVP resolved corrections to products that were already live. V2 puts an
estate in front of that and a product surface beside it.

**Ten external systems, each reached over MCP.** A supplier portal, the
supplier's own PIM, the artwork library, the ERP, an industry data pool, a
regulatory feed, a marketplace connector, a translation service, an imaging
system and a market feed. Each is its own server at `/mcp/{system}`, dialled at
startup by a real `initialize` and `tools/list`; each declares what it emits and
how badly it behaves. Connect another by pasting a URL, and the dependency map
redraws from a topology message without a reload.

Deliveries are asynchronous, batched and irregularly timed. Ingestion is
sequenced. That split is the whole correctness argument and it is not a
detail - the consumer cursor is a single watermark, so feeding interleaved
batches straight to ingest would advance it past an event still in flight and
drop that event silently, on a run reporting success.

**Product 360.** Search by SKU, identifier or name; read the merged record with
the system that carried each value and the values that lost; assess it against
nine checks; and, for a record that passes, open the staging page it would
become. Six checks are rules. Three read prose no rule encodes - whether a
mandate's particulars are met, whether a sentence has quietly become untrue,
whether the record contradicts our own documentation - and on those a model
finds and *cites* while a rule decides. A candidate citing nothing retrievable
is dropped.

There is no readiness score. A product with three open findings is not seventy
per cent ready; it is not ready, and the findings are what somebody acts on. A
number would invite a threshold and a threshold invites launching at ninety.

**Every finding names the system that supplied the problem.** "The data is
incomplete" is not actionable; "the imaging system never sent an ingredient
panel" is.

**A capability directory** at `/.well-known/agent-cards.json`, built from the
same Agent Cards it lists, keeping capabilities this system *implements* apart
from ones it merely knows how to *reach*, and stating what each may not do.

**Nothing names a model.** Two alias lists survived in the gateway client as the
offline fallback and every one had gone stale against `litellm/config.yaml`, so
an outage produced a picker the gateway would have refused. A test greps for
their return.

**A correction run takes about 21 seconds** against a live gateway, down from
three to four minutes. The per-field rewrites and the per-document readings run
concurrently; the extraction *writes* stay strictly sequential, because a
watermark advances as each document is persisted and the next is read against
it.

## Driving the demo

The seed pack is a retailer onboarding an air purifier and a packaged snack
across six channels: its own website, two marketplaces with incompatible
schemas, the printed catalogue, shelf-edge labels, and search facets. The tape
runs 56 simulated days and carries six arcs.

1. **The status strip** — the replay transport lives at the bottom of every
   screen, so "Jump to inject" and single-stepping are available while you are
   looking at the map rather than two tabs away.
2. **Ingest Fabric** — sources, products, variants and channels, with the live
   feed. Click any node to trace what depends on it. Most of what arrives is
   routine and the system correctly ignores it.
3. **Day 13 — a warm-up.** A supplier flags kettle dimensions as provisional,
   then withdraws the notice three days later. The withdrawal *retires* the
   signal rather than stacking a second one on top, which is the whole reason
   the state reducer knows the difference between a correction and a
   resolution.
4. **Day 18 — sources disagree.** A portal spreadsheet says the snack weighs
   40 g, the label artwork says 38 g, and a sales email insists on 40 g again.
   The evidence desk pulls both documents' version histories and the source
   precedence in `POL-002` settles it: label artwork outranks a portal feed,
   which outranks an email. The system drafts a supplier clarification rather
   than guessing.
5. **Day 28 — the inject.** Revision v2 of the AeroPure specification says the
   rated power is 65 W, superseding the 45 W published in v1, and notes that a
   measurement sheet belonging to *one model in the range* was folded into the
   earlier document — without saying which. Run the loop and watch **Blast
   Radius**: one corrected field reaches fifteen content assets across five
   listings on four channels, including the base model's own web page, because
   a comparison table there quotes both variants. The prepared copy reads
   "Ultra-quiet 45W operation"; the stale figure is caught mechanically and the
   `low-energy` claim breaks against the substantiation table.
6. **Day 30 — the allergen.** A shared-line change adds "may contain peanuts"
   to the snack in all formats and corrects the ingredient order. This is a
   safety attribute, so the marketplaces are **held closed** rather than
   published with a warning, the `peanut-free` search facet is withdrawn, and
   reviewer approval stops being optional. Reordering the ingredients is
   treated as a real change, because that order is a legal declaration and not
   a presentation choice.
7. **Day 31 — a marketplace argues back.** Marketplace B rejects the feed with
   `MKB-2201`: the allergen statement is correctly worded but wrongly
   formatted. The run re-plans and fixes the format.
8. **Day 32 — the finale.** Revision v3 arrives: the 65 W rating applies to the
   **Max only**; the base model was always 45 W. Press "Re-plan on new
   evidence". The run resumes on the *same thread* — the pending approval is
   withdrawn and recorded as withdrawn, the scope narrows to the Max, and the
   print batch prepared under v2 is refused by the stale-version gate. Approve
   it and publishing writes COMMITTED facts and takes an exclusive lock per
   channel and product, so the attribute's history reads as a chain of
   assertions — what was inferred from which document version, and what was
   finally published — with valid time and known time kept apart.

`Ctrl`/`Cmd`+`K` opens the command palette from anywhere — jump to a section,
drive the transport, start the loop, or search the corpus directly. Theme,
density and the brand accent are in the appearance menu; all three persist.

## Architecture

| Concern | Implementation |
|---|---|
| Pipeline | LangGraph; deterministic throughout, with a model at four bounded points |
| Durability | `SqliteSaver` checkpoints — kill the process mid-run and resume |
| Model access | LiteLLM gateway, one egress point, with a response cache |
| State | SQLite, bitemporal facts with five provenance classes |
| Validation | Deterministic rules engine over channel schemas, claims and allergen declarations |
| Lineage | Typed edge walk: document → attribute → variant → asset → listing → channel |
| Retrieval | BM25 + dense embeddings fused with weighted RRF, numpy matrix |
| Event plane | SQLite tape with per-consumer cursors, replay clock |
| Source estate | Ten external systems, each an MCP server over HTTP, delivering in seeded batches at irregular times (`sc/estate/`) |
| Readiness | Nine checks over a product record - six rules, three that read and must cite - and a verdict that is arithmetic (`sc/readiness/`) |
| Exception handling | Bounded evidence loop over a read-only allowlist (`sc/graph/evidence.py`) |
| Re-planning | Same thread, next revision; prior readings carried forward and re-validated |
| Concurrency | Publish locks: a partial unique index makes them exclusive |
| A2A | Peers with Agent Cards and JSON-RPC (`sc/a2a/`) |
| MCP | Toolsets split by owning system (`sc/mcp/`), one of them able to write; connections made at runtime by a real handshake |
| Discovery | One directory at `/.well-known/agent-cards.json`, built from the cards it lists |
| UI | React + Vite, Tailwind v4 tokens, Radix primitives; every diagram is hand-rolled SVG — no chart or graph library |

### Why these choices

- **Mostly deterministic, and deliberately so.** This problem does not need an
  autonomous multi-agent system, and building one would have been the wrong
  answer confidently delivered. Propagation, versioning, taxonomy mapping and
  channel rules are ordinary software with a correct answer. AI is invited to
  exactly four places, each one a job that software genuinely cannot do:
  reading a corrected value out of unstructured supplier prose, arguing which
  variant a document meant, noticing that a sentence has become untrue for
  reasons no rule encodes, and rewriting copy. At every one of them the model's
  output is checked against the catalog before it touches anything.

- **Bitemporal facts, because the premise is a late correction.** Two
  independent axes: when a value is true in the world, and when we learned it.
  A correction never updates in place — it inserts a row naming the one it
  replaces. That is what lets the system answer "what did the content team know
  when they wrote this bullet?" separately from "what is actually true?", which
  is the question a supplier correction *is*.

- **The blast radius comes from the topology, never from a model.** Every
  content asset declares the attributes it was derived from, so working out
  what a correction touches is a graph walk, not a judgement. It also finds the
  non-obvious case: a correction scoped to the Max still lands on the base
  model's page, because a comparison table there quotes both.

- **Fail closed on safety.** A safety-class attribute whose value was inferred
  by a model below a confidence threshold, with no human override, blocks
  publication on every channel carrying that product. Not a warning banner — a
  hard stop with the attribute, the confidence and the threshold named. The
  cheapest possible way to be wrong about an allergen is to be slow about it.

- **BM25 alongside embeddings** — reviewers search for identifiers, and
  embeddings put `VAR-01A` and `VAR-01B` almost on top of each other despite
  their having opposite answers to the only question that matters about them.
  The tokenizer keeps `MKA-4102` and `VAR-01B` whole while still indexing their
  parts.

- **Rules as data, not code.** Channel requirements live in a table the
  validator reads and the corpus documents, so a reviewer can be shown the same
  rule that stopped the publish. Adding a channel is data entry, not a code
  change.

- **SQLite over Postgres** — one file, no server, and the audit trail is
  inspectable with a `sqlite3` shell during a demo.

- **numpy over a vector database** — the corpus is a few hundred chunks;
  retrieval is one matmul. An ANN index would add a dependency and an
  approximation to an operation that already takes under a millisecond.

- **A partial unique index for concurrency** — publish locks are exclusive per
  (channel + product, batch date), enforced by the database. Two runs
  republishing the same product to the same channel is impossible rather than
  merely unlikely, and the loser is told which run holds the lock.

- **The graph branches on the data, and only on the data.** A correction with a
  prior incident behind it goes through the precedent that incident left; one
  whose sources genuinely contradict each other goes to a supplier
  clarification, because inventing a resolution is worse than asking; one where
  nothing can be published goes to a constraint review. Every predicate is a
  pure function of state, so the same correction always takes the same path.
  Variety, not randomness: a graph that rolled dice would trade the
  reproducibility the audit trail depends on for the appearance of
  sophistication.

- **A closed evidence desk rather than open tool use.** Scope resolution is the
  one step where a model picks an action, so it gets an allowlist of seven
  read-only lookups and a hard cap on how many rounds it may take. Nothing on
  the desk writes a fact or publishes anything, which is what makes handing it
  to a model uninteresting rather than alarming. Two questions are answered
  from the catalog before it is asked anything at all: how the variants
  actually differ, and what versions of the source document exist. Both are
  facts about the *current* catalog, and left to its own judgement the model
  reliably decides a retrieved postmortem already told it — which is how a
  scope decision ends up resting on a document that was true last year.

- **Re-planning on the same thread** — a revision keeps the case, the audit
  trail and the checkpoint history, so "targeted re-planning rather than a full
  restart" is visible in the data rather than claimed in prose. A pending
  approval is withdrawn through the same interrupt a reviewer uses, so the
  ledger records who withdrew it and why; a recommendation whose evidence has
  moved is not one anybody should still be able to approve.

- **No chart library, and no Pareto frontier.** Two or three readings of one
  document is not an efficient frontier, and drawing one would be a chart
  pretending to be an analysis. A ranked table with the deciding evidence
  beside it is the honest form. The design tokens are a four-layer cascade
  (OKLCH primitives, semantic aliases, a density multiplier, then a Tailwind
  `@theme inline` bridge), which is what lets light, dark, system, two
  densities and a re-skinnable brand hue all fall out of CSS custom properties
  with no `dark:` prefix anywhere in the app.

### Degrading without a gateway

Every model step has a deterministic fallback: extraction falls back to the
structured hints each event carries, triage to measured severity, scope
resolution to the **widest** reading flagged low-confidence, copy regeneration
to a template. A circuit breaker opens after two connection failures so the
fallbacks run at full speed rather than paying a connect timeout per call.

The scope fallback is deliberately the widest and not the narrowest: with no
model available the safe assumption is that a correction affects more than you
can prove, not less.

## Tests

```bash
python -m pytest tests/ -q
```

416 tests, ~105 seconds. Six skip without an embedding matrix; the rest need no
network.

The graph tests run with the gateway deliberately unreachable, so the fallback
paths are what CI actually exercises. There is no LLM mocking anywhere in the
suite — a mocked model tests the mock. The whole six-arc demo above is
reachable with no model at all: the pipeline still resolves a scope, measures
the blast radius, writes a cited change summary and suspends at the reviewer.

## LangGraph Studio

```bash
startup.bat studio
```

Installs `langgraph-cli` if needed, puts the system into its demo position
(`scripts/prepare_demo.py`), and starts the dev server on `127.0.0.1:2024`.

Studio is optional and deliberately not on the critical path: its UI is hosted
at `smith.langchain.com` and needs a sign-in, though the graph and its state
are entirely local. So the Review & Audit tab draws the graph itself, from
`GET /api/graph`, which reads the topology out of the compiled LangGraph —
executed nodes highlighted, the untaken branch greyed, the suspended node
marked. Reading it from the running graph rather than hard-coding a picture
means the diagram cannot drift from what actually executes.

Note that `langgraph-cli` upgrades `langgraph` and `langgraph-checkpoint`,
which is why the checkpoint-sqlite pin in `requirements.txt` matters — a 1.x
graph with a 2.x saver fails on the first checkpoint write.

## MCP

Toolsets partitioned by the system that would own them, because the brief's
test is ownership. One server with twenty flat tools is one system with a
protocol bolted on.

| Toolset | Stands in for | Writes? |
|---|---|---|
| `product-catalog` | PIM master data | no |
| `channel-registry` | Channel specifications | no |
| `content-store` | Content and asset management | no |
| `knowledge-base` | Document management | no |
| `event-plane` | Integration bus | tape advance |
| `publishing-execution` | Channel publishing | **publishes** |

An operator can hand out the read-only servers and withhold the one that can
change a live listing. The safeguards travel with the tools rather than the
caller: `commit_plan` refuses without a recorded approval whichever server it
is reached through.

Set `USE_MCP=1` and the evidence lookups become real stdio round-trips to the
toolset that owns them; the console shows each call with the transport it
actually used, and a toolset that fails to spawn falls back in-process rather
than losing the run.

Beside those six, the **estate**: ten external systems, each its own server at
`/mcp/{system}` over Streamable HTTP, dialled at startup by a real handshake.
They are not toolsets this repository owns - they are systems it talks to, and
the listing labels which is which.

Connecting is a URL. An address that does not answer is recorded as degraded
with the reason rather than raising, because a demo that cannot boot when a mock
supplier is slow is worse than one missing a supplier.

**Discovery is not admission.** A connected system's tools become visible
immediately and callable never, until an operator admits specific ones - and
only while that system is answering. The tempting shortcut is to auto-admit
anything a system declares read-only, but "read-only" is the connecting system's
claim about itself, and the evidence desk's allowlist exists precisely because a
tool's self-description is not a control.

A discovered tool never shadows a built-in one. If a connected system declares
`commit_plan`, the built-in keeps the name and the collision is reported.

## A2A

Peers with Agent Cards another organisation's agent could discover:

```
GET  /a2a/{agent}/.well-known/agent-card.json
POST /a2a/{agent}          message/send, tasks/get, tasks/cancel
```

`lineage-analyst` walks the blast radius, `resolution-planner` proposes
candidate scopes, `validator` scores one deterministically, `copywriter`
rewrites affected copy. Four kinds of work with four different failure modes,
and four things a peer could replace independently — the copywriter especially,
which another team would want to swap for their own brand-voice model.

The approval gate is deliberately not a peer, and neither is publishing. A
human decision is not a capability to delegate, and a peer that could publish
is a peer that could publish.

Those cards were correct and not discoverable: a peer that knows an identifier
can fetch one, and a peer that knows only the host cannot find out what is here.
So there is one more document:

```
GET  /.well-known/agent-cards.json
```

Built from the same cards it lists rather than from a separate inventory, which
would drift within a release and drift silently. It keeps peers apart from
connected systems - one list would say this estate can do things it can only ask
somebody else to do - and every peer entry states what it may not do, because a
directory that merely omits the approval gate invites the reader to conclude it
was forgotten.

`USE_A2A=1` makes the graph delegate over JSON-RPC instead of calling the
handlers in-process. The validator's trace hash is identical either way; if it
were not, this would be two implementations rather than one capability with two
front doors.

## Layout

```
corpus/      authored content standards, channel specs, policies, prior incidents
data/        generated seed pack, incl. golden/extractions.jsonl - the answer
             key the eval grades against (reproducible; git-ignored)
sc/          contracts, db, state, sim, rag, llm, graph, tools, replay
sc/estate/   the ten external systems: manifest, emitter, defects, arrivals,
             their MCP servers, and the publication side
sc/readiness/ the nine checks, the verdict, the staging page
scripts/     generate_data.py, build_index.py, prepare_demo.py, evaluate.py
sc/graph/    nodes, branches, prompts, evidence desk, state, assembly
sc/a2a/      peer agents, their cards, the client that calls them
sc/mcp/      toolsets split by owning system, plus the stdio client
frontend/    React UI - tokens, ui primitives, app shell, views;
             dist/ is committed so the lab never needs npm
tests/       the suite
```
