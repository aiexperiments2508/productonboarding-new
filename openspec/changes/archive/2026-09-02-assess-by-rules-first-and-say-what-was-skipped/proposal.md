## Why

Eight things are wrong with the V2 build, found by using it rather than by
testing it. They are unrelated to each other and share one shape: each is a
surface that is either slower than it needs to be or quieter about its own
limits than it should be.

**Product 360 opens on a model-backed assessment.** Three uncached embedding
calls plus three sequential completions before anything renders. Every click on
a product pays for prose nobody has asked to read yet. And `gateway.embed` is
the one model call in the platform that is not cached, which is why a single
click costs three network round trips.

**A narrow assessment reads like a complete one.** If the reading checks are
skipped or the gateway is down, the verdict still says "ready" - the same word
a full assessment produces. Five surfaces render a verdict and each phrases it
for itself, so the fix cannot be made in one of them.

**The staging page has no imagery, and a missing photograph is
indistinguishable from a broken page.** The server has always sent a URI, the
client renders the role as a grey pill, no image file exists anywhere, and the
SPA catch-all would answer `/media/*.jpg` with `index.html`.

**A finding names a system and stops there.** Nothing joins it to what the
estate declares about that system - what it is for, who owns it, how it is
known to misbehave - so a reviewer reads "SUP-04 sent this" and has to know the
rest.

**Six of eleven systems draw as boxes with no connectors.** The cause is one
line: the reach resolver reads `payload["entity_id"]`, and the tape names
products five ways - a channel acknowledgement says `variant_id`, a document
and an email say `entities`. Those systems have delivered dozens of events
each; nobody is listening in their dialect. There is also no transport or
logistics system in the manifest at all.

**The map draws every node** with no cap, no filter and no collision avoidance,
over a fixed 392px, and the shell re-fetches the entire catalog on every
released event.

**Sections are one long column of scroll** that takes the page header with them.

**The catalog is six products and 274 events over the wrong two months**, which
is too small to show a rollup meaning anything and dated outside the window the
demonstration runs in.

Two defects sit underneath these. `record._instant` reads the tape's simulated
clock, which is `None` until the tape releases its first event - so every
product read fails on a freshly reset database, which is the state a presenter
opens on. And a single gateway outage is reported twice, because the client
phrases a refused connection and an open circuit differently and the
de-duplication is a membership test against the text.

## What Changes

- **The six rule checks run alone and answer in milliseconds**; the three that
  read prose run when a reviewer asks for them.
- **The word "ready" is reserved for a complete assessment.** A narrow one
  reads "no rule findings", staging refuses to build from it, and the rule
  lives in one helper that all five verdict-rendering surfaces call.
- **A narrow assessment does not weaken its findings.** Fewer checks ran; the
  ones that did are worth exactly what they were worth before.
- **`gateway.embed` is cached**, the reading checks run concurrently, the
  overlay is built once per request rather than once per product assessed, the
  list route stops serialising records it throws away, and the search box is
  debounced.
- **Imagery is real.** The generator draws a deterministic SVG per asset, a
  mount serves them ahead of the catch-all, a missing one is a 404 rather than
  the application shell, and a role the category requires that nobody delivered
  is drawn as a gap naming the system that owes it.
- **A finding can be explained.** A new route joins it to what the estate
  declares about the system that caused it, and a model writes the two together
  under the same fence as every other model call here: it may use the finding,
  the declared behaviour and a retrieved passage, and an account citing nothing
  retrievable is dropped for the deterministic one. It runs after the verdict
  and cannot reach it.
- **One reader for the tape's five dialects.** `sc/estate/reach.py` becomes the
  single resolver, shared with the arrival window so the two cannot drift. A
  transport and logistics system joins the manifest.
- **A scoped map route** - ten products by default, with search and facets, a
  frame that grows with the busiest tier, and "+N not drawn" rather than silent
  truncation. `/api/network` keeps its shape, because a map showing ten of a
  hundred and fifty is reasonable and a blast radius showing ten of a hundred
  and fifty is wrong.
- **Panels own their overflow** rather than the shell being the scroller.
- **150 products, 301 variants and 5,211 events across 1 July to 31 August
  2026**, split 58% clear / 34% returned to source / 8% blocked. The six hero
  products and their arcs are untouched: the background draws from its own PRNG
  stream so the story's draws do not move, and its damage is declared in a
  registry the generator asserts against.
- **Product 360 gains the filters the screen exists to answer with** - an
  arrival window measured on the simulated clock, supplier and category facets,
  and a rollup counting what went downstream clean against what went back to
  source, broken down by who has to fix it.
- One scenario that had been passing by luck is made deliberate: the ambiguity
  the whole demonstration turns on depended on routine traffic happening to
  restate the base model's wattage before the inject. It becomes an authored
  arc event.

## Capabilities

### New Capabilities

- `system-behaviour-accounts`: joining a finding to what the estate declares
  about the system that caused it, and writing the two together without
  touching the verdict.
- `product-imagery`: the assets a product holds, the files behind them, and the
  gap where a required role was never delivered.

### Modified Capabilities

- `launch-readiness`: an assessment may run rule checks alone, and one that did
  says so in the verdict itself.
- `source-estate`: the reach resolver reads every spelling the tape uses, and
  the manifest gains a transport system.
- `product-360`: an arrival window on the simulated clock, supplier and
  category facets, a rollup by who has to fix it, and a scoped map beside the
  unscoped blast radius.

## Impact

- `sc/readiness/__init__.py`, `verdict.py` - rule-only assessment and the
  narrow flag.
- `frontend/src/lib/verdict.ts` - the one helper five surfaces call.
- `sc/llm/gateway.py` - `embed` joins the cache.
- `sc/rca.py` - the account of a finding.
- `sc/estate/reach.py` - one reader for five dialects, shared with the arrival
  window.
- `sc/estate/manifest.py` - a transport and logistics system.
- `sc/media/` and the media mount - deterministic SVG assets served ahead of
  the catch-all.
- `sc/main.py` - the scoped map route, the Product 360 window, facets and
  rollup.
- `sc/readiness/record.py` - `_instant` survives a tape that has released
  nothing.
- `scripts/generate_data.py` - 150 products over the right two months, with the
  background on its own PRNG stream and a declared damage registry.
- `tests/test_media.py`, `test_rca.py`, `test_readiness.py`, `test_estate.py`,
  `test_product360.py`, `test_golden.py`.
