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

On Windows, `startup.bat` does all of that and also starts the three connected
applications:

| | | |
|---|---|---|
| `http://127.0.0.1:8000` | **the platform** | API, UI, and every MCP server |
| `http://127.0.0.1:8110` | **Vendor Portal** | upstream — suppliers push corrections in |
| `http://127.0.0.1:8120` | **Storefront** | downstream — what a shopper sees |
| `http://127.0.0.1:8130` | **Ops Console** | downstream — print, shelf, search, errata |

`startup.bat solo` runs the platform alone; `startup.bat stage` puts two
products on sale first, so a late change has something to be late for.

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

**Eleven external systems, each reached over MCP.** A supplier portal, the
supplier's own PIM, the artwork library, the ERP, an industry data pool, a
regulatory feed, a marketplace connector, a translation service, an imaging
system, a market feed and a transport and logistics system. Each is its own server at `/mcp/{system}`, dialled at
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

**The six rule checks run on every click; the three that read prose run when
asked.** Opening a product used to be three model round trips - so it was a
wait rather than a look, and the wait bought findings nobody had asked for yet.
The default is now the rules alone, in milliseconds and with no gateway
traffic, and a control beside the verdict runs the rest.

That trade is only honest while the screen says what it did not do, so it does,
everywhere it could mislead. `checks_complete` is false until the reading
checks have run, and until then the word "ready" is not used: a record with no
rule findings reads **no rule findings**, in neutral, and the staging page -
the last surface before publication - refuses to open at all. One helper in
`frontend/src/components/verdict.ts` owns that decision, because five surfaces
render a verdict and a sixth will be added by somebody who has not read this.

**Every finding names the system that supplied the problem.** "The data is
incomplete" is not actionable; "the imaging system never sent an ingredient
panel" is. Ask for a root cause and the finding is joined to what the estate
declares about that system - what it is for, who owns it, how it is known to
misbehave - and a model writes the two together under the same fence as every
other model call here: it may use the finding, the declared behaviour and a
retrieved passage, and an account citing nothing retrievable is dropped for the
deterministic one. It runs after the verdict and cannot reach it.

**The imagery is real, and so are the gaps.** Every asset the catalog holds has
a file behind it and the staging page shows it; a role the category requires
and nobody delivered is drawn as a gap naming the system that owes it. A
missing image is a 404, never the application shell - because a browser draws
that as "broken", and "the imaging system has not sent this" needs a different
person to fix it than "this page is falling over".

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

## What V3 added

The system up to here is a **replay**. Five thousand events, recorded once,
released on a clock you can pause and step. Convincing, and entirely in the
past tense: nothing outside the process could put a new fact into it, and
nothing outside the process could see what came out.

V3 adds the present tense.

**Three connected applications**, each its own process on its own port, each
reaching the platform over MCP and by no other route. They have no database,
no access to the API, and — checked by `tests/test_app_boundary.py` — no import
of `sc`. That test exists because the boundary is one convenient line of Python
away from being false at any moment, and nothing would visibly break when it
was.

* **Vendor Portal.** A supplier signs in as one of three systems the retailer
  runs an intake for — the portal, the supplier's PIM, the industry data pool —
  and sends a corrected specification, a document, an image, or a proposal for
  a line the catalog does not have. Each endpoint's tool list is *derived* from
  what its system declares it accepts, so the data pool has no upload surface
  and the PIM has no imaging one.
* **Storefront.** The web page and the two marketplace listings, rendered from
  what each channel says it is currently showing.
* **Ops Console.** Print, shelf and search: the channels where a correction
  turns into somebody's afternoon.

**A live lane on the event tape.** A submission is a real event that the
platform's own ingestion judges under the same precedence policy, materiality
threshold and safety override as the recording — but it is not part of the
recording, so the transport cannot rewind it and the clock cannot walk into it.
The two lanes are told apart by a column and never by a sequence range; see the
docstring in `sc/replay/tape.py` for the two silent failures that decided that.

**A supplier cannot write a value into the catalog.** A submission is recorded
as a *document version*. What it asserts becomes a fact only when the graph
reads the document and writes it back as INFERRED, under the fail-closed safety
gate. The provenance taxonomy does the enforcing; there is no permission check
to route around.

**Redaction, and a second gate.** A late correction lands against copy that is
already live, and between knowing the value is wrong and having a validated
replacement the wrong value is still on sale. So hiding it and republishing are
separated: hiding is authorised by the approval that already agreed the value
was wrong and happens at once; republishing needs its own release decision,
enforced as a fourth refusal in `commit_plan` and recorded in its own table —
never in `approvals`, where it would have satisfied the first gate by itself.

What "hide" means is derived from what the channel can actually do, and one
correction gets five different right answers:

| Channel | Outcome |
|---|---|
| Own website | listing withheld — a food page reading "Contains: —" is not a lawful page |
| Marketplace A / B | listing withdrawn — its own rules make a placeholder a hard violation |
| Search facets | facet dropped — a shopper filtering "no peanuts" and finding peanuts is the harm |
| Shelf-edge labels | reprint queued — it stays wrong in the aisle until somebody walks over |
| Print catalogue | **erratum owed** — 214,000 catalogues cannot be recalled, and saying they were redacted would be the one lie that matters |

Copy is redacted with the value it quotes. A bullet reading "may contain milk"
above a spec row saying the allergen statement is being checked would make the
page worse than before it was corrected — and which copy quotes which value is
not a guess, it is the same `derived_from` lineage the blast radius has always
been computed from.

**Product Lifecycle**, a new section, is where the halves join: every product in
the lane its own state puts it in — proposed, with the supplier, cleared, pushed
downstream, on sale, or overtaken by a late change. Lanes are derived and never
stored, for the reason the publication estate is derived from the channels: a
stored status would be a second account of a product's state, and the first
thing it would disagree about is the product somebody just corrected. The three
applications open from a strip at the top of it.

## Driving the demo

The seed pack is a retailer onboarding an air purifier and a packaged snack
across six channels: its own website, two marketplaces with incompatible
schemas, the printed catalogue, shelf-edge labels, and search facets. The tape
runs 62 simulated days - the first of July to the thirty-first of August 2026 -
and carries six arcs.

Those two products sit in a catalog of a hundred and fifty, which is the point
of the rest of it. Every question the fabric and the product surface exist to
answer is a question about a population: which supplier is holding a launch up,
how much of last week's intake came in fit to publish, which category the data
pool keeps mangling. A catalog of six answers all of them by pointing at the
same two rows. So the background is generated around the six - a few hundred
products the demo never mentions, roughly a third of them short of something
the checks will find - and the tape carries the five thousand routine events
that a population that size produces. What is hand-authored is the story; what
is generated is the world it happens in, and `scripts/background.py` says which
is which.

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
5. **Day 33 — the inject.** Revision v2 of the AeroPure specification says the
   rated power is 65 W, superseding the 45 W published in v1, and notes that a
   measurement sheet belonging to *one model in the range* was folded into the
   earlier document — without saying which. Run the loop and watch **Blast
   Radius**: one corrected field reaches fifteen content assets across five
   listings on four channels, including the base model's own web page, because
   a comparison table there quotes both variants. The prepared copy reads
   "Ultra-quiet 45W operation"; the stale figure is caught mechanically and the
   `low-energy` claim breaks against the substantiation table.
6. **Day 35 — the allergen.** A shared-line change adds "may contain peanuts"
   to the snack in all formats and corrects the ingredient order. This is a
   safety attribute, so the marketplaces are **held closed** rather than
   published with a warning, the `peanut-free` search facet is withdrawn, and
   reviewer approval stops being optional. Reordering the ingredients is
   treated as a real change, because that order is a legal declaration and not
   a presentation choice.
7. **Day 36 — a marketplace argues back.** Marketplace B rejects the feed with
   `MKB-2201`: the allergen statement is correctly worded but wrongly
   formatted. The run re-plans and fixes the format.
8. **Day 37 — the finale.** Revision v3 arrives: the 65 W rating applies to the
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
| Source estate | Eleven external systems, each an MCP server over HTTP, delivering in seeded batches at irregular times (`sc/estate/`) |
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

598 tests, about eight minutes. Three skip without an embedding matrix; the
rest need no network.

Four of them are load-bearing beyond their own subject, and are worth knowing
about before changing the things they guard:

* `test_the_replay_cursor_cannot_walk_into_the_live_lane` and
  `test_a_live_event_does_not_poison_the_tape_ingest_cursor` — both failures
  are silent. The system goes on reporting success while it stops recording
  facts.
* `test_a_redaction_does_not_clear_the_frozen_version_violation` — the
  validator skips every check for a withheld listing, so a redaction routed
  through a change-set action would erase a frozen-version violation while the
  wrong catalogues were still in the world. That is INC-2026-002 in the corpus,
  happening a second time in the code written to prevent it.
* `test_a_release_approval_alone_does_not_publish_an_unapproved_resolution` —
  `commit_plan` reads the newest approval and tests only that it is APPROVE, so
  a release recorded in that table would satisfy the first gate by itself.

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

Beside those six, the **estate**: eleven external systems, each its own server at
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

**Two more surfaces, added in V3.** The estate above answers questions; these
two accept traffic, and they are listed apart from it because an operator
handing out an address should be able to tell from the path which is which.

*The vendor intake*, at `/mcp/intake/{system}`, for the three systems whose
manifest entry declares an `accepts` list. Each endpoint's tools are derived
from that list rather than written down, so narrowing a system in the manifest
removes its upload surface with no code change. Nothing here reaches the fact
store — a tool call appends an event, and the platform's own ingestion judges
it. That is checked by walking the module's imports, not asserted in a comment.

*The publication estate*, at `/mcp/publish/{channel}`, grew from three tools to
eleven: six reads that let a downstream application be built entirely on the
protocol, and five writes that all go through the planning boundary. `MUTATING`
is declared rather than inferred from the verbs, because "which of these can
act" is the question an operator actually asks.

The three applications in `apps/` are clients of those two surfaces and of
nothing else. Each holds its MCP session server-side — partly because the
platform's CORS configuration does not expose `Mcp-Session-Id` so a
browser-side client could not continue a session it had just opened, and
partly because a supplier identity set in a browser is a supplier identity
anybody can set.

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
sc/estate/   the eleven external systems: manifest, emitter, defects, arrivals,
             their MCP servers, and the publication side
sc/readiness/ the nine checks, the verdict, the staging page
scripts/     generate_data.py, build_index.py, prepare_demo.py, evaluate.py,
             stage_launch.py (two products on sale, for the late-change arc)
sc/graph/    nodes, branches, prompts, evidence desk, state, assembly
sc/a2a/      peer agents, their cards, the client that calls them
sc/mcp/      toolsets split by owning system, plus the stdio client
sc/lifecycle/ the board, one product's timeline, and accepting a proposed line
apps/        the three connected applications - vendor portal, storefront, ops
             console. Each its own process; none of them imports sc
frontend/    React UI - tokens, ui primitives, app shell, views;
             dist/ is committed so the lab never needs npm
tests/       the suite
```
