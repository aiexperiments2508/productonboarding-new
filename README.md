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
python scripts/build_datapack.py
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
| `http://127.0.0.1:8140` | **Back Office** | reference — stock, trading, campaigns, certificates |

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

## What V6 added

Up to here a supplier could send one corrected value, one document or one
image. That is the right shape for the correction story and the wrong shape for
the question a retailer asks first: **a supplier has forty new lines — how many
of them are fit to sell?**

**A supplier data pack, generated from the rules the system actually applies.**
`scripts/build_datapack.py` writes, for every branch the retailer trades, a
blank template and a worked example as CSV and as a pipe-delimited flat file,
plus one XLSX workbook, one Word specification and one JSON Schema covering all
of them. Every column comes from `data/catalog.json`'s attribute registry
joined to the branch declarations in the retailer profile. Nothing is written
down twice: point `RETAILER_PROFILE` at another profile and the templates
change with it.

Applicability is per *leaf*, not per branch, because five attributes are named
leaf by leaf — a kettle is mains and a saucepan is not, and both are `home.`. A
column that does not cover the whole branch says which categories it does
cover, so an empty cell on a row it does not cover is correct rather than
missing. `sc.state.baseline.applies_to_category` is the one predicate that
decides this, and the readiness check that would report the gap asks it too.

The workbook closes the four traps a spreadsheet sets on a supplier's behalf: the
GTIN column is text so a leading zero survives, units live in the header and
never in the cell, percentages are plain numbers, and the three ordered lists
say that their order is a legal declaration. The worked examples are real lines
from this catalogue with deliberately broken rows — one per defect a supplier
file can actually carry, drawn from the closed set in `sc/estate/defects.py`.
Two of the seven cannot be shown in a file at all, and the README sheet says
which two rather than shipping five and calling them seven.

**One archive, forty products.** `submit_product_feed` takes a .zip: one data
file at the root and an optional `images/` folder whose names the rows refer
to. It is exposed only on a system whose manifest entry accepts both attribute
rows and imagery, derived rather than declared — so the supplier portal has it
and the PIM and the data pool do not, with no code naming any of them.

Nothing about the bulk door relaxes the single door's rules. Every row becomes
an event on the live lane and is judged by the same ingestion, the same
precedence policy and the same safety override. Rows are asserted against a new
version of the supplier's *own* document, never a freshly minted id — a
document the seed pack does not know carries precedence zero and would lose
every contest it entered, so a bundle minting one would raise forty conflicts
and correct nothing while reporting success. A SKU the supplier does not own is
refused by line. A SKU the catalogue does not have becomes a proposal, held
exactly as `create_product_draft` holds one, with its own submission so a
reviewer accepts it through the same gate as a line typed into the form.

Three refusal scales, deliberately different: a malformed archive refuses the
bundle; an unrecognised column is reported and the bundle continues; a bad cell
loses the cell and not the row. That last one matters — twelve good values
discarded to punish one typo is how a portal stops being used, and the value
that would not parse is then reported as missing by the same check that would
have reported it blank, which is the truth about it.

**A sequential pass, and a report.** A quick action on the Ingest Fabric's
incoming stream walks the batch one product at a time, in the order the
supplier listed them, lighting the catalog map as it goes. It is not a graph
run and deliberately so: the correction graph answers *a published value
changed, what does it reach*, and is built round a case and an approval
interrupt — forty products through it would be forty suspended threads in a
queue that exists to hold one. Onboarding asks *is this record fit to launch*,
which `sc/readiness` already answers in milliseconds, and the pass is
`submissions._verdict`'s own loop turned into a generator.

The outcome is a new section, **Supplier Intake**, reachable from a button on
the fabric: how many went through clean, how many went back to the source, how
many are blocked, and — counted apart from all three — how many rows were
proposed new lines that nobody has decided on yet. A bundle of eleven rows of
which five are lines we do not have is a report about six products, and saying
"six assessed" without saying what happened to the other five is exactly the
undercount the rest of this system is arranged to avoid.

**"AI can fix it" is two claims, and they are counted separately.** A gap is a
*candidate* when a source passage is on file for it, which is deterministic and
provable rather than estimated: `enrich` refuses any fill whose chunk is not in
the supplied set, so no passage means no fill, and no model has to be asked to
know that. Whether a passage that exists actually *states* the value is a
reading question, and until the sources have been read the screen says "could
be" and not "will be". The two counts will differ, and that difference is the
interesting number.

A safety-class gap is never a candidate — not a candidate needing approval, not
a candidate. `enrich`'s own docstring says why: a plausible allergen list is not
an allergen list, and it gets printed on a label and read by somebody who needs
it to be right. They are counted and named so the exclusion is visible rather
than silent.

Applying writes facts and stops. Every fill lands INFERRED with the passage it
was read from, through the same `ingest.record_attribute` the graph uses, so
the fail-closed safety gate can still see it. No approval row, no reservation,
no committed action — a product becomes ready by having no findings left, which
is arithmetic, and publishing is a separate decision behind a gate this does
not touch. `tests/test_onboarding.py` pins that by counting the three tables
before and after.

## Driving the demo

The seed pack is a UK superstore onboarding an air purifier and a packaged
snack across six channels: its own website, two marketplaces with incompatible
schemas, the printed catalogue, shelf-edge labels, and search facets. The tape
runs 62 simulated days - the first of July to the thirty-first of August 2026 -
and carries six arcs.

Those two products sit in a catalog of a hundred and fifty, which is the point
of the rest of it. Every question the fabric and the product surface exist to
answer is a question about a population: which supplier is holding a launch up,
how much of last week's intake came in fit to publish, which category the data
pool keeps mangling. A catalog of six answers all of them by pointing at the
same two rows. So the background is generated around the six - a hundred and
forty-four products the demo never mentions, roughly two in five short of
something the checks will find - and the tape carries the five thousand routine
events that a population that size produces. What is hand-authored is the
story; what is generated is the world it happens in, and
`scripts/background.py` says which is which.

**The assortment is eight branches, and none of it is hardcoded.** Grocery,
Home & Kitchen, Clothing & Footwear, Electricals, Household & Personal Care,
Baby & Child, Health & Pharmacy, General Merchandise - real product lines a
shopper would recognise, under a fascia and supplier brands that are entirely
invented. Which branches exist, what each is called, which imagery a category
cannot launch without and which branches are regulated all live in
`data/profiles/ashcombe.json`, and `RETAILER_PROFILE` picks the file the same
way `DATA_SEED` picks the draw. Pointing the demo at a different retailer is a
new profile rather than a refactor; the parts the running system needs are
copied into `catalog.json` so `sc/` reads the assortment from the baseline
instead of holding category prefixes of its own.

**Seven more arcs happen to the rest of it.** The six above are the story and
they happen to six hand-authored products. Beside them the tape carries a pack
shrinking, a conformity certificate expiring, a country of origin moving, a
market authority serving a **withdrawal notice**, an export-control
classification, a fibre label revised, and the mandatory particulars for
cosmetics being amended. Between them they exercise fifteen classes of
correction rather than three, and the interesting ones are the three that are
not corrections at all: a takedown, a recall and an export restriction say
nothing in the record is wrong. `compliance.sale_permitted` is a safety-class
attribute for exactly that reason - marking it so buys forced escalation,
mandatory review, withholding rather than rewriting, and the per-channel
redaction path with no new rule code - and `sale_prohibited` is its own
publish-time constraint, because a product an authority has stopped is not a
product whose copy needs improving.

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
5. **Day 33 — the inject.** Revision v2 of the Northaven AP300 specification says the
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
| Readiness | Ten checks over a product record - seven rules, three that read and must cite - and a verdict that is arithmetic (`sc/readiness/`) |
| Supplier packs | Templates derived from the attribute registry and the retailer profile, in five formats; one .zip back (`sc/datapack/`) |
| Onboarding | A batch is a submission; a sequential readiness pass over it; a fill bounded by what a model can cite (`sc/onboarding/`) |
| Exception handling | Bounded evidence loop over a read-only allowlist (`sc/graph/evidence.py`) |
| Re-planning | Same thread, next revision; prior readings carried forward and re-validated |
| Concurrency | Publish locks: a partial unique index makes them exclusive |
| A2A | Peers with Agent Cards and JSON-RPC (`sc/a2a/`) |
| MCP | Toolsets split by owning system (`sc/mcp/`), one of them able to write; connections made at runtime by a real handshake |
| Discovery | One directory at `/.well-known/agent-cards.json`, built from the cards it lists |
| UI | React + Vite, Tailwind v4 tokens, Radix primitives; every diagram is hand-rolled SVG, with one exception — see below |

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

## Knowledge graph

A second reading of the same catalog. The product record answers *what is wrong
with this product and who has to fix it*; the graph answers *what is this
product connected to* — which is a different question, with different joins, and
the reason it is a graph rather than one more view over the same tables.

Seven domains, and the interesting queries are the ones that cross two of them
at a shared node. Those shared nodes are the model's real content:

```
                          ┌──────────────┐
        CATEGORY ─────────│              │───────── COMPLIANCE
   Category, Attribute,   │   Product    │   Certificate, Regulation,
   AttributeValue         │      │       │   Market, HazmatClass
                          │  HAS_VARIANT │
                          │      ▼       │
        MEDIA ────────────│   Variant    │───────── WAREHOUSE
   MediaNode,             │              │   Warehouse, StorageLocation,
   AssetRendition         │              │   StockLevel
                          └───┬──────┬───┘
                              │      │
                   SALES ─────┘      └───── MARKETING
        Channel, Listing,              Campaign, Promotion,
        PriceRecord, SalesFact          Keyword, Persona
```

`Variant` is the spine — it is the thing that carries a SKU, and every domain
hangs off it or off its product. The joins that matter:

| Join point | Bridges | What it makes answerable |
|---|---|---|
| `Market` | Compliance ↔ Sales ↔ Warehouse | stock held in a depot that cannot lawfully ship to a market that depot serves |
| `Category` | Category ↔ Media ↔ Sales | best sellers with no primary image; which subtrees have the weakest imagery |
| `Supplier` | Warehouse ↔ Category | a category that depends on one supplier |
| `Campaign` | Marketing ↔ two Products | cross-sell candidates that already share a campaign |
| `Certificate` | Compliance ↔ many Variants | everything sharing a certificate that lapses in ninety days |

None of those is answerable from any single tab, which is the argument for
building it at all. The last one is the clearest: `compliance.certificate_ref`
is carried on seventy-four variants and two of them cite `UKCA-2411`, but
nothing in the record view can see that they are the same certificate.

**Two of the seven domains are the retailer's own data and four are not.** The
catalog has products, variants, suppliers, categories, attributes, media,
channels and listings. It has no warehouse, no price, no sales figure and no
campaign — so those arrive from four simulated back-office systems declared in
`sc/estate/manifest.py`, the same way every other external system in this estate
does, and every node they produce is stamped `synthetic: true`. The graph draws
those with a dashed stroke and the legend says so. An invented revenue figure
rendered beside a genuine regulatory finding, with nothing to tell them apart,
is a claim this system has not earned.

### The one graph library

Every other diagram in this application is hand-rolled SVG, and the README said
so without qualification until the Knowledge Graph tab arrived. The exception is
**NVL** — `@neo4j-nvl/base`, Neo4j's own renderer, the one under Neo4j Browser
and Bloom. It was taken deliberately, with its costs measured rather than
assumed:

- Its licence is proprietary, not OSS.
- `@neo4j-nvl/base` depends on `@segment/analytics-next`, and peers on
  `neo4j-driver`. Neither reaches the browser — Rollup drops both, verified by
  grepping the built bundle — but both sit in `node_modules`, and
  `npm audit` reports four high-severity advisories that chain from NVL.
- The bundle grew from 610 kB to 2,401 kB (183 kB to 706 kB gzipped). On a
  localhost application that is not a load-time problem; it is still a fourfold
  increase and worth knowing.
- `disableTelemetry: true` is set on the instance.

The official React wrapper is **not** installed. It declares
`peer react "18.0.0 || ^19.0.0"` — exact 18.0.0 — which will not resolve against
this project's 18.3.1 and would have made `--legacy-peer-deps` permanent and
`startup.bat clean` a special case. Binding NVL to React by hand is forty lines
in `GraphCanvas.tsx` and `npm install` keeps working with no flags.

**NVL renders; it does not arrange.** The layout is `free` and the coordinates
come from `radialLayout.ts`: rings are hop distance from the SKU, sectors are
domains, in a fixed order. That is the part that actually fixed the picture. A
force layout — NVL's or anyone's — was being asked to rediscover, badly, two
things the data already knew, and what it produced was a hairball. Swapping
renderers alone would have produced the same shape in nicer pixels.

A canvas has no DOM per node, so the keyboard and screen-reader path is a real
focusable list beneath it rather than the per-node `aria-label` and `tabIndex`
the SVG carried.

### The schema

`sc/kg/schema.cypher` holds the constraints and indexes, and sits beside the
code that applies it for the same reason `sc/schema.sql` sits beside `sc/db.py`.
Every statement is `IF NOT EXISTS`, so applying it to a loaded graph is a no-op.

Three rules govern it, and the first is the load-bearing one:

- **A uniqueness constraint on every business key**, because `MERGE` is the
  loader. An unconstrained key does not raise — it inserts a second copy of
  every node of that label on the second run, and the graph doubles quietly
  while every count still looks plausible. `tests/test_kg_schema.py` reads the
  keys back out of `sc/kg/model.py` and fails if any is unbacked.
- **No range index on a constrained property** — a constraint creates its own.
- **An index only where a query filters**, and each one names the insight that
  reads it.

`sc/kg/model.py` is the single statement of the model: which domain each label
belongs to, which property is its key, which labels are generated, and which two
ends each relationship is allowed to join. The projection, the Cypher builders
and the schema test all read it, so a label added without a key is a test
failure rather than a subgraph that silently duplicates.

Note that `MERGE` is idempotent but not convergent: a node that leaves the
source stays in the graph. `scripts/load_graph.py --prune` is how it leaves.

### Running it

**Nothing is required.** With no Neo4j anywhere the tab works: the same
projection is walked in process and `GET /api/kg/status` reports
`backend: memory`. Every response says which engine answered, so the switch is
a transport decision rather than a behavioural one — the posture `sc/mcp/client.py`
already takes for `USE_MCP`.

For Cypher against a real graph database — and **without Docker**, in keeping
with the rest of this repository. Neo4j Community is a zip with a batch file in
it; on a machine with a JDK 17 or 21 it needs nothing else, and a container
runtime is one more thing to install, to be blocked on at work, and to explain
here.

```bash
startup.bat graph
```

That fetches Neo4j 5.26 into `neo4j/` (git-ignored), sets its initial password,
and installs the driver. Put `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` in
`.env`, and from then on `startup.bat` starts Neo4j alongside everything else —
it looks for `neo4j/` and steps aside quietly when it is not there.

Then, **with the platform running**:

```bash
python scripts/load_graph.py
```

That last condition is the point. The loader does not read the database — it
dials the four back-office systems on their own MCP endpoints and MERGEs what
they answer with, the same claim `estate_server.connect_all` makes at startup.
With the platform down it writes nothing and exits 1 with the real connection
error rather than half a graph. `--offline` reads SQLite instead, explicitly,
and stamps every node `via: sqlite` so a graph stays answerable about how it
was built.

No JDK and no way to get one? Neo4j Aura's free tier needs nothing local —
point `NEO4J_URI` at the `neo4j+s://` address it gives you. Or do nothing: the
tab works without any of this.

One consequence worth knowing: once `NEO4J_URI` is in `.env`,
`tests/test_kg_neo4j.py` stops skipping and the suite grows by about three
minutes. Those tests write, and write only the same idempotent `MERGE` the
loader performs — they leave the graph exactly as `load_graph.py` would, and
they delete nothing.

The queries use only core Cypher. A stock Neo4j ships no plugins, and a query
that needed APOC would turn one line of setup into a support question this
README could not answer.

### Where the data comes from

Products, variants, suppliers, categories, attributes, media, channels and
listings are the retailer's own. Warehouses, prices, sales, campaigns and the
certificate register are not — they arrive from four simulated back-office
systems declared in `sc/estate/manifest.py`, delivered onto a third event lane
(`REF`) at boot, and read over MCP by the Back Office console on port 8140.

That lane is invisible to everything else. The replay transport does not count
it, play it or lose it on a rewind; the live feed does not announce it; and
none of it becomes a product fact, because `ingest.HANDLERS` is a four-entry
table and a type absent from it is skipped by construction. A stock snapshot
cannot move a readiness verdict, and `tests/test_kg_data.py` asserts it.

Generate the pack with:

```bash
python scripts/generate_backoffice.py
```

Same seed, same bytes — `--check` builds it twice and compares.

## Tests

```bash
python -m pytest tests/ -q
```

677 tests, about eight and a half minutes. Three skip without an embedding
matrix; the rest need no network.

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
sc/readiness/ the ten checks, the verdict, the staging page
sc/datapack/ the supplier templates, in five formats, derived from the
             registry - and the reader that takes them back
sc/onboarding/ a bundle's batch, the sequential pass over it, and the bounded
             fill
scripts/     generate_data.py, build_index.py, prepare_demo.py, evaluate.py,
             stage_launch.py (two products on sale, for the late-change arc),
             build_datapack.py (the templates a supplier fills in)
sc/graph/    nodes, branches, prompts, evidence desk, state, assembly
neo4j/       Neo4j Community, unpacked by `startup.bat graph`. Optional,
             git-ignored, and deletable - the graph tab works without it
sc/kg/       the knowledge graph: the model, schema.cypher, the projection,
             the Cypher builders and the two backends. Not sc/graph/ - that
             one is the agent graph, and this one is the product graph
sc/a2a/      peer agents, their cards, the client that calls them
sc/mcp/      toolsets split by owning system, plus the stdio client
sc/lifecycle/ the board, one product's timeline, and accepting a proposed line
apps/        the three connected applications - vendor portal, storefront, ops
             console. Each its own process; none of them imports sc
frontend/    React UI - tokens, ui primitives, app shell, views;
             dist/ is committed so the lab never needs npm
tests/       the suite
```
