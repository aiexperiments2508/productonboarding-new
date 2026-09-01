# Prompt — generate the Veriflow three-lane demo automation

> Paste this whole file into Claude (Claude Code for Part A, the Claude Chrome
> extension for Part B). It is a specification, not a script: it says what the
> demo must prove and what the generated automation must assert. The generated
> automation *is* the recording — running it again is the replay.

---

## 1. Your role

Generate a **repeatable, self-asserting demo automation** for the Autonomous
Product Intelligence Factory (Veriflow) in this repository. It is driven from
Chrome by the Claude browser extension against the real running stack — no
mocks, no stubbed API, no seeded screenshots.

The demo has to survive being run in front of a room, twice in a row, on a
laptop with no network. Every claim it makes on screen must be one the codebase
actually produces.

---

## 2. The system you are automating

Started by `startup.bat` (Windows) or `python run.py` plus the app servers.

| Port | Application | Role in the demo |
|---|---|---|
| `127.0.0.1:8000` | **The platform** — API, React UI, every MCP server | where the demo is watched |
| `127.0.0.1:8110` | **Vendor Portal** | upstream — the three suppliers push their feeds in here |
| `127.0.0.1:8120` | **Storefront** | downstream — what a shopper sees |
| `127.0.0.1:8130` | **Ops Console** | downstream — print, shelf, search, errata |
| `127.0.0.1:8140` | **Back Office** | reference — stock, trading, campaigns, certificates |

The four apps reach the platform **only over MCP** (`/mcp/intake/{system}`).
They hold no database and import no `sc` module — `tests/test_app_boundary.py`
enforces it. The automation must respect that boundary: never reach 8000's API
from a page served by 8110.

**Platform sections** (left rail, defined in `frontend/src/app/nav.ts`):
Ingest Fabric · Supplier Intake · Product Lifecycle · Product 360 · Blast
Radius · Readings · Review & Audit · System Control.

**Supplier Intake tabs**, in the order a batch moves through them:
`Compliance gate` → `Onboarding` → `Suggestions` → `Decisions`.

---

## 3. Domain truths the automation must not violate

These are properties of the code. If the generated script asserts anything that
contradicts one of them, the script is wrong — not the system.

1. **The gate runs first and it stops things.** `sc/onboarding/gate.py`
   partitions one readiness summary by check name. `GATE_CHECKS` =
   `sale_permitted`, `saleability`, `forbidden_content` (authority
   `REGULATION`) plus `policy_conformance` (authority `POLICY`). A stopped
   product is *not onboarded*: no source is retrieved for it, no value is
   proposed, nothing downstream is spent on it.
2. **The gate is a set of check names, never a severity.** `policy_conformance`
   is deliberately `OPEN`, not `BLOCKING`. Do not assert "blocking ⇒ gated".
3. **Nothing is written on a model's own confidence.** `suggest` composes a
   score from a discounted self-report (`CITED_TRUST = 0.72`) plus counts of
   what is already on file. `decide.route` applies three refusals **in this
   order**: safety-class → fewer than `MIN_SOURCES` (2) supporters → below the
   threshold. The score is consulted *last*.
4. **`MIN_SOURCES = 2` is structural, not a knob.** Turning the threshold down
   must not make a single-source proposal autonomous. Assert this.
5. **A safety-class attribute always goes to a person**, whatever the score,
   whatever agrees with it. Safety-class paths in the seed pack:
   `food.allergens.contains`, `food.allergens.may_contain`,
   `compliance.sale_permitted`, `compliance.min_age`,
   `compliance.export_control`, `cosmetic.inci`, `health.active_ingredient`,
   `specs.plug_type`, `specs.battery_type`.
6. **Provenance is not cosmetic.** An autonomous fill lands `INFERRED` with its
   confidence and citation. A person's decision lands `DECIDED`. They are
   different kinds and the audit trail must be able to tell them apart.
7. **Onboarding never publishes.** `fix` writes facts and stops. A product
   becomes ready by having no findings left — that is arithmetic. Publication
   needs `commit_plan`, a recorded approval and a channel reservation, and the
   automation must press those separately and say so.
8. **`checks_complete` is the honest half of every verdict.** Without a gateway
   only the deterministic checks ran, the word "ready" is not used, and the
   staging page refuses to open. `frontend/src/components/verdict.ts` owns that
   decision. The automation must read that flag and narrate the narrow case as
   narrow rather than papering over it.
9. **A supplier cannot write a value into the catalog.** A submission is
   recorded as a *document version*; what it asserts becomes a fact only when
   the graph reads the document back as `INFERRED` under the fail-closed safety
   gate.
10. **Verdicts are a closed set of three**: `READY_TO_LAUNCH`,
    `RETURN_TO_SOURCE`, `BLOCKED` (`sc/readiness/verdict.py`).

---

## 4. The three lanes — what each must prove

Three suppliers. Three separate feeds. Three different outcomes, each visible
on screen and each provable from the API.

### Lane A — clean, end to end, and a human presses the button

* **Profile:** a non-regulated product whose record already holds every
  mandatory attribute its channels require and every media role its category
  requires.
* **Expected:** gate `PASSED` · zero findings · verdict `READY_TO_LAUNCH` ·
  appears under *Went through clean* · staging preview opens · lifecycle stage
  moves `CLEARED` → `PUSHED_DOWNSTREAM` after the reviewer commits.
* **The point of the lane:** no hazard, no gap, nothing intercepted. The only
  thing standing between the feed and the shopper is a person pressing publish
  — and the presenter presses it, in the application, on camera.
* **Prove it downstream:** the value is visible on the Storefront (8120) and
  the Ops Console (8130).

### Lane B — information missing, intercepted, corrected by AI, pushed through

* **Profile:** a product missing **one or more non-safety-class** attributes —
  e.g. `specs.power_w`, `energy.class`, `pack.net_quantity`, `origin.country`,
  `packaging.recyclable_pct`, `textile.care_code` — where corroboration exists:
  a sibling variant holding the value, a category convention, a past decision,
  and/or a retrievable passage in a document already on file.
* **Expected:** gate `PASSED` · `RETURN_TO_SOURCE` with N gaps · after *Propose
  values for every gap*, at least one proposal routes `AUTONOMOUS` (confidence
  ≥ threshold **and** ≥ 2 supporters) · written `INFERRED` with its citation ·
  re-assessment shows the gap closed · the product reaches `READY_TO_LAUNCH`.
* **The point of the lane:** the system caught it, held it, closed it from what
  it already knew, and showed its working — the confidence bar with the
  threshold drawn *on* it, and the signed reason list underneath.
* **Must also show:** a proposal in the same batch that did **not** clear — one
  source only, or below threshold — sitting in *Decisions*. The lane is not
  "AI fixes everything"; it is "AI fixes what it can defend, and asks about the
  rest."

### Lane C — hazardous / critical, stopped, and it stays stopped

* **Profile:** at least one of —
  * a **gate stop**: `compliance.sale_permitted = false` (withdrawal notice in
    force, `REG-003`), a forbidden phrase in live copy (`forbidden_content`,
    `INT-002`), a mandate the record breaches (`saleability`), or a breach of
    the retailer's own policy (`policy_conformance`, `POL-*`); **and/or**
  * a **safety-class gap**: a missing `food.allergens.contains`,
    `compliance.min_age`, `health.active_ingredient`, `specs.plug_type` etc. on
    a regulated line. The seed pack has 49 regulated products including
    baby formula, biscuits and pain relief — natural candidates.
* **Expected:** appears under *Stopped at the gate* on the **Compliance gate**
  tab, tagged `REGULATION` or `POLICY`, with `returned to {supplier}`, and the
  sentence naming the clause rather than the check. It is **absent** from the
  Onboarding tab. Its confidence column reads `—` and `decided by a person`,
  never a percentage. Turning the autonomy threshold down to `0.80` in System
  Control does **not** move it.
* **The point of the lane:** this is the brand-reputation lane. The demo must
  show that nothing was spent on it — no retrieval, no proposal — and that no
  operator knob can push it through.

---

## 5. What to generate — three parts

### Part A — `demo/stage_demo.py` (Python, run before the browser)

Puts the stack into an identical starting position every time and builds the
three feeds.

1. **Reset:** `python run.py --reset`, then `scripts/generate_data.py`,
   `scripts/build_datapack.py`, then `scripts/prepare_demo.py --warm`. `--warm`
   runs one correction loop and throws it away so the SQLite LLM cache is
   populated — the point is not speed, it is *the same output every time*
   regardless of the venue's wifi.
2. **Discover the three suppliers rather than hardcoding them.** Read
   `GET /api/products`, `GET /api/products/{id}/readiness` and the catalog to
   score every supplier against the three profiles in §4, then pick the best fit
   per lane. Suppliers must be distinct. Print the chosen triple and write it to
   `demo/selection.json` so Part B reads the same names. Fail loudly if a lane
   has no candidate — never silently substitute one.
3. **Build three archives** into `demo/feeds/`, one per supplier. A bundle is
   **one .zip: exactly one data file at the root** (CSV pulled from
   `GET /api/intake/datapack/{branch}?fmt=csv`, so the columns are the ones the
   registry actually derived) **plus an optional `images/` folder**. Limits from
   `sc/datapack/read.py`: ≤ 200 rows, ≤ 400 members, ≤ 24 MB archive, ≤ 2 MB per
   image.
4. **Route each feed through a different intake system** so the three feeds are
   visibly separate on the live lane: `supplier-portal` (accepts everything),
   `supplier-pim` (specs and documents, no imagery), `gdsn-pool` (attribute rows
   only). A bundle carrying photographs into `gdsn-pool` is correctly refused
   its imagery — do not use that pairing by accident.
5. **Emit `demo/expected.json`:** per lane, the supplier, the SKUs, the expected
   verdict, the expected gate outcome and authority, and the expected routing.
   Part B asserts against this file.

### Part B — `demo/runbook.md` (the browser script the Chrome extension executes)

A numbered beat sheet. Every beat states: **where** (URL + section + tab),
**what to do** (the exact control, by its visible label), **what must be true**
(assertion, read from the page — not from your memory of what should happen),
and **what to capture** (screenshot name).

Use the visible labels, which are stable in this codebase:

* Intake header button — **Walk the batch** (streams the pass one product at a
  time; the counter reads `n/total`).
* Intake KPIs — **Stopped at the gate**, **Went through clean**, **Recorded
  autonomously**, **Awaiting your decision**.
* Suggestions tab — *Who is asking* field (placeholder `your name`), then
  **Propose values for every gap**. The toast reports
  `{filled} recorded, {queued} for you to decide, {requested} back to the supplier`.
* Decisions tab — **Approve** · **Rectify** (→ **Record this instead**) ·
  **Reject**.
* System Control → **Onboarding policy** — the autonomy threshold, offered at
  the stops `0.80 / 0.85 / 0.90 / 0.95 / 1.00`, and it demands a name because
  moving it is audited.
* System Control → **Replay & feed** — transport (`Start`/`Pause`, step 1, step
  10, `Jump`, `Reset`) and the **Clear the tape** panel, which arms twice
  (`Clear` → `Yes — clear it`).

### Part C — `demo/artifacts/`

Written by the run, so the demo can be replayed without the stack up:

* `NN-<beat>.png` — one screenshot per beat, in order.
* `run.json` — every assertion with expected and actual, the submission ids,
  batch ids, fact ids written, and the wall clock.
* `demo.gif` — the beats stitched in order, for the version that runs in a
  slide.
* `transcript.md` — the narration line per beat, so a second presenter can drive
  it.

---

## 6. The beat sheet the runbook must cover

1. **Cold open — the estate.** 8000 → *Ingest Fabric*. The catalog as a graph,
   the tape arriving over it. Capture the resting state.
2. **Supplier A sends a clean feed.** 8110 → sign in as the system + supplier A
   → *Bulk feed* → take the template → send the archive. Assert the portal
   reports `accepted`; record the `submission_id`.
3. **Supplier B sends an incomplete feed.** Sign out, sign in as supplier B on a
   different intake system, send feed B.
4. **Supplier C sends the hazardous feed.** Sign out, sign in as supplier C,
   send feed C.
5. **The three arrivals are visible as three.** 8000 → *System Control* →
   *Replay & feed*, live lane. Assert three distinct submissions, three
   suppliers, three carriers.
6. **Walk batch C first.** *Supplier Intake* → select batch C → **Walk the
   batch**. Assert the *Stopped at the gate* KPI is ≥ 1; open **Compliance
   gate**; assert the authority tag and the `returned to {supplier}` line; assert
   the stopped SKU is **absent** from the *Onboarding* tab.
7. **Prove nothing was spent on C.**
   `GET /api/onboarding/suggestions?submission_id=<C>` returns no proposal for
   the stopped SKU. Capture it.
8. **Try to force C through.** *System Control* → *Onboarding policy* → move the
   threshold to `0.80` with a name. Re-read C. Assert the safety-class row still
   reads `decided by a person` and still routes `HUMAN`. **Put the threshold
   back to `0.95`** and assert both moves are in the audit ledger.
9. **Walk batch B.** Assert gaps > 0 and verdict `RETURN_TO_SOURCE`.
10. **The AI closes what it can defend.** *Suggestions* → name → **Propose values
    for every gap**. Assert: at least one `AUTONOMOUS` fill; the confidence bar
    sits at or past the threshold mark; the reason list is signed (agreeing *and*
    disagreeing evidence); the written fact is `INFERRED` with a citation. Assert
    at least one proposal did **not** clear and is waiting in *Decisions*.
11. **A person answers the rest.** *Decisions* → **Approve** one, **Rectify** one
    with a typed value. Assert both land `DECIDED`, not `INFERRED`, and that a
    decided proposal cannot be decided twice (expect `409`).
12. **B is now ready.** Re-read the batch report. Assert the gap count fell and
    the verdict moved to `READY_TO_LAUNCH` — and assert `checks_complete` is true
    before using the word "ready" anywhere in the narration.
13. **Walk batch A.** Assert zero findings and `READY_TO_LAUNCH` on the first
    pass, with nothing proposed and nothing queued.
14. **The presenter publishes A.** *Product 360* → find the SKU → open the
    staging preview → *Review & Audit* → record the approval → commit the plan.
    This is the beat the room came for: **a human presses it.** Assert a
    reservation and a committed action exist afterwards.
15. **Downstream.** 8120 Storefront and 8130 Ops Console show A (and B's
    corrected value). Assert C appears nowhere downstream.
16. **The board tells the whole story in one screen.** *Product Lifecycle* —
    assert C in `WITH_SUPPLIER`, B in `CLEARED`/`PUSHED_DOWNSTREAM`, A in
    `PUSHED_DOWNSTREAM`/`LIVE`. Capture. This is the closing frame.

---

## 7. Determinism and repeatability

The single hardest requirement. Encode all of it.

* **Rewinding is not resetting.** `tape.reset()` unreleases the *recorded* lane
  only and deliberately leaves the live lane alone — retracting a supplier's
  submission because somebody moved the clock would be a lie about history. To
  start the demo again you need **Clear the tape**
  (`POST /api/control/replay {"action": "CLEAR"}`), which rewinds the recording
  *and* removes what the portals pushed, including both ingest watermarks.
  Neither one clears `facts`.
* Because facts survive a clear, a second run over the same catalog will find
  Lane B's gap already filled. **Part A must therefore do a full
  `run.py --reset` between runs**, not just a tape clear. Make that the
  documented reset path, and make the runbook refuse to start if
  `demo/selection.json` is older than the database.
* Fixed actor names (`demo-cm` for decisions, `demo-publisher` for the commit),
  fixed idempotency keys per feed, fixed file names. The audit ledger should read
  identically across runs apart from timestamps.
* The feeds are **checked in** under `demo/feeds/` once generated, so a venue
  with no time to regenerate can run from the committed archives.
* Warm the cache (`prepare_demo.py --warm`). A rehearsal populates the SQLite LLM
  cache keyed on `(model, temperature, messages)`, and a served call is recorded
  as a **hit** rather than as a call — the usage panel stays honest.
* If no gateway is reachable the run still completes on the deterministic
  fallbacks. In that case `checks_complete` is false, and the runbook must
  **switch to the narrow narration** rather than skipping the assertion.

---

## 8. Failure handling

* Every assertion failure stops the run, writes the actual value into
  `run.json`, captures a screenshot, and prints which lane broke. A demo that
  quietly continues past a failed assertion is worse than one that stops.
* Never retry a submission by resending it — that is what idempotency keys are
  for, and a duplicate archive is a second submission.
* If a beat cannot be reached (a section empty, a batch missing), say which
  precondition was not met. Do not synthesise the screen.

---

## 9. Acceptance criteria for what you generate

- [ ] Runs twice in a row from a cold `--reset` with identical assertions passing.
- [ ] Picks its three suppliers by discovery, and prints why each was chosen.
- [ ] All three lanes end in their expected lifecycle stage.
- [ ] Asserts provenance — `INFERRED` for the autonomous fill, `DECIDED` for the
      human one — not merely that "a value appeared".
- [ ] Asserts the two structural refusals (safety-class, `MIN_SOURCES`) hold with
      the threshold lowered to `0.80`, and restores the threshold.
- [ ] Never claims a product was published by onboarding.
- [ ] Never uses the word "ready" while `checks_complete` is false.
- [ ] `demo/artifacts/` alone is enough to present the demo with the stack down.

---

## 10. Do not

* Do not hardcode SKUs, product ids or supplier ids in the runbook — read them
  from `demo/selection.json`.
* Do not reach the platform API from a vendor-portal page, or import `sc` into
  anything under `apps/`.
* Do not seed a fact directly to make a lane come out right. If a lane cannot be
  produced by a feed, the feed is wrong.
* Do not present the confidence figure as the model's own confidence.
* Do not add a fourth verdict, a readiness score, or a percentage complete.
