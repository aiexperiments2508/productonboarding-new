## Why

Every test in this repository asserts that the pipeline **runs**. They run with
the model gateway pinned to a closed port on purpose, so what CI exercises is
the deterministic fallback in every node - which is the right call, because a
suite that mocked a model would be testing the mock. The consequence is that
nothing in the repository said whether a model reading a supplier document gets
the answer **right**. The only golden sets were two retrieval ones.

That gap matters more here than it would elsewhere, because the system gates on
a stated confidence. An inferred value on a safety-class attribute below 0.90
withholds every listing of the product. A model that says 0.8 and is right 40%
of the time is not a quality problem, it is a governance defect - the number the
gate trusts does not mean what the gate assumes it means. Nothing measured that.

There was also nothing to argue with. The repository's own claims about model
behaviour - what the extractor gets right, whether the base-versus-variant
architecture is earning its keep, whether the claim scanner adds anything over
the deterministic table - were assertions, not measurements.

## What Changes

- **An evaluation harness**, `scripts/evaluate.py`, that grades a live model
  against an answer key and writes a machine-readable report. It is a script and
  not a test, because it needs a gateway the suite deliberately does not have.
- **An answer key emitted by the generator**, not hand-labelled. Every
  correction event already carries a structured payload beside the prose that
  was written from it - the fields the extractor is supposed to produce - so the
  key is written from the same source of truth as the data and regenerates with
  it rather than rotting behind it.
- **Three of the model touchpoints are graded**: what the extractor read out of
  prose, which variants scope resolution applied a correction to, and what the
  claim scanner flagged. Confidence calibration is built across them, bucketed
  with 0.90 as its own edge because that is where the safety gate binds.
- **The grading uses the shipping prompt and the shipping inputs.** The
  extraction messages and the claim-scan inputs are lifted into named functions
  the node and the scorer both call, so a revised prompt cannot leave the eval
  reporting yesterday's accuracy.
- **Refusals are counted apart from wrong answers.** A reply the gateway will
  not accept routes to the deterministic fallback and never influenced anything;
  counting it as a misread field would report a model that cannot emit a JSON
  object as one that cannot read a spec sheet.
- **The harness paces itself** and labels rate-limited rows as quota results
  rather than model results, because a provider limit hit halfway through a
  sweep produces a run that measures the fallback and reports it as the model.
- **Responses are cached in a sidecar** outside the store each scenario drops,
  so the first run costs tokens and every run after it is free and identical.
- **Two tests guard the key** without needing a gateway: that it has not fallen
  behind the tape, and that it has not drifted from the deterministic fallback
  that reads the same payload.

### What the first run measured

Against `gemini-2.5-flash` over 15 documents, recorded in `data/eval/report.json`:

- **Five of fifteen replies were a JSON array where an object was required.** A
  third of calls violated the contract and fell back. That turns the argument
  for schema-validated structured output from a stylistic preference into a
  number.
- **`applies_to` was defensible on all six graded documents, and UNCLEAR was
  never called VARIANT.** The failure the base-versus-variant design exists to
  prevent - a model resolving an ambiguity the document did not resolve - did
  not occur for this model.
- **Materiality: precision 1.00, recall 0.83.** One missed correction, no false
  positives. Reported separately rather than folded into an F1, because the
  costs are not symmetric: a miss reaches shoppers, a false positive costs a
  reviewer a minute.
- **`scan_claims` states about 0.95 and is observed right 0.76 of the time**
  over fifty flags. It is advisory and every flag is confirmed against the
  deterministic claim table before anything acts on it, which is why that
  overconfidence is contained rather than dangerous. It is also the number that
  would make it dangerous if the node ever stopped being advisory.

### What the run could not measure, recorded rather than glossed

- **The answer key is built from the same payload the deterministic fallback
  reads.** It can grade the model and it cannot grade the fallback - which is
  right on every document by construction, and that is a property of the key,
  not evidence about the fallback. This is the harness's own caveat and it is
  carried in the report artefact so a number read six months from now arrives
  with the reason it is not what it looks like.
- **The fail-closed safety gate is unmeasured.** No document carrying a
  safety-class attribute falls inside the eval window: `safety_documents: 0`.
  The one number the harness was built to produce is the one it did not produce.
- **`scan_claims` recall is measured against the same rule table the prompt
  tells the model is already checked**, so it measures overlap with the
  deterministic pass rather than value added.
- **Fifteen labelled documents is too thin for a headline accuracy figure.** The
  useful output of this run is the confusion matrix and the named failure modes,
  not a percentage.

## Capabilities

### New Capabilities

- `model-evaluation`: grading the model touchpoints against an answer key
  generated from the same payloads the data is - what was read, at what scope,
  with what confidence - and reporting the result with the limits of the
  measurement attached to it.

### Modified Capabilities

None. Nothing in the pipeline's behaviour changes. Two inputs the nodes already
assembled are lifted into named functions so the scorer can call the same ones,
which is a refactor, not a requirement change.

## Impact

- `scripts/evaluate.py` - new: throttle, cache sidecar, per-touchpoint scoring,
  calibration, the rendered tables and the JSON report.
- `scripts/generate_data.py` - emits `data/golden/extractions.jsonl` beside the
  seed pack, from the same event payloads.
- `sc/graph/nodes.py` - `extract_messages` and `scan_claims_inputs` made public
  so the node and the scorer share one prompt and one set of inputs.
- `tests/test_golden.py` - new: the key against the tape, and the key against
  the deterministic fallback. Runs without a gateway, like everything else.
- `.gitignore` - `data/golden/` and `data/eval/` are regenerated, not carried.
- `README.md` - **not yet updated.** It still reports 267 tests and has no
  evaluation section at all, which is the largest outstanding item on this
  change.
