## Context

See proposal.md - Why. The starting state is a suite that runs the whole
pipeline with the gateway on a closed port, deliberately, so that what CI
exercises is the deterministic fallback in every node. Nothing measures the
model.

Constraints that shape the approach:

- There is no LLM mocking anywhere in the repository, and adding some to measure
  quality would measure the mock. So this cannot be a test; it is a script that
  needs a live gateway.
- The demo store is a single SQLite file the pipeline resets. A grading run that
  shares it would trample a demo in progress, and a run that does not reset
  between scenarios would let one scenario read facts another recorded.
- Every node catches `GatewayError` and falls back. That is exactly right in
  production and exactly wrong here: a quota exhausted halfway through a sweep
  produces a run that measures the fallback and reports it as the model.
- Fifteen documents is what the tape holds. The design has to be honest about
  what a set that size can support.

## Goals / Non-Goals

**Goals:**

- Grade the model against a key nobody hand-wrote, so the key regenerates with
  the data instead of rotting behind it.
- Grade the prompt and the inputs that actually ship.
- Produce an artefact whose numbers arrive with their limits attached.

**Non-Goals:**

- Grading the deterministic fallback. The key is written from the same payload
  the fallback reads, so it cannot. This is stated in the report rather than
  worked around, because working around it means hand-labelling, and a
  hand-labelled key rots.
- A headline accuracy percentage. The output of a fifteen-document set is a
  confusion matrix and a list of named failure modes.
- Becoming part of CI. It needs a gateway; the suite is what runs without one.

## Decisions

**The key is emitted by the generator, from the payload the prose was written
from.** Every correction event already carries a structured payload beside its
prose - the entity, the path, the old and new value, the unit, whether it is
material, what scope the supplier stated. Those are exactly the fields the
extractor is asked to produce. Writing the key from them means the key is
authored by the same run that authors the data and cannot fall behind it.

*Alternative considered.* Hand-labelling fifteen documents. It would have taken
an afternoon and produced a key that is wrong the first time the generator seed
changes, silently, in the direction of flattering whichever model was current
when it was written.

*The cost, and it is the important one.* The deterministic fallback reads the
same payload. So the key's second author is the thing the key would have to
grade, and the combined "model or fallback" figure is right on every document by
construction. That is arithmetic, not evidence. It is the most load-bearing
sentence in the report and it is carried in the artefact rather than left in a
commit message.

**Two tests hold the key to its two authors.** The key can drift from the tape,
so a test asserts it covers exactly the documents the extractor reads, in order.
It can drift from the fallback, so a test asserts they agree field by field.
Neither needs a gateway, so both run everywhere the suite does. A third asserts
the scorer builds the extraction prompt with the function the node calls.

**One `applies_to` mismatch is pinned rather than fixed.** The extraction prompt
offers BASE, VARIANT and UNCLEAR; the structured payload answers in the
catalog's own words, PRODUCT and ALL. Nothing downstream reads the field - it is
carried into the run trace and no further - so the mismatch costs nothing today.
It is asserted in a test with the translation written out, so the day it starts
costing something it does so loudly.

**Refusals are a separate column, not wrong answers.** A reply the gateway will
not accept routes to the fallback and never influenced anything. Folding it into
accuracy would report a model that cannot emit a JSON object as one that cannot
read a specification. Keeping the column is what turned "we should use
schema-validated structured output" into "a third of calls violate the
contract."

**Pacing lives in the script, not in the gateway.** A minimum interval and a
backoff chain sit around the harness's own posting function. Putting them in
`sc.llm.gateway` would change the behaviour the eval exists to observe. Once a
full backoff chain has failed the rest of the run fails fast and says so,
because a spend cap does not clear and waiting again just turns a capped account
into a slow way of producing the same error. Rate-limited rows are labelled as
quota results, not model results.

**The cache lives in a sidecar outside the store.** Each scenario drops the
application database, which is where the response cache lives, so without a
sidecar every reseed would throw the cache away and every run would be a fresh
bill. Copying it out before the drop and back after is what makes a repeat run
free **and identical** rather than merely cheaper - which is what makes the
recorded report reproducible.

**Two verdicts per document, because confidence and accuracy answer different
questions.** *Correct* is strict: did it produce the reading the payload leads
with. *Truthful* asks whether what it said is true of the document at all - a
document that revises two values has two right answers and the reply template
carries one. The calibration curve is built from *truthful*, because that is
what a stated confidence is a claim about.

**Values are compared after coercion, with the raw comparison reported beside
it.** A model answering `"65"` for an integer field has read the document
correctly; counting it wrong would measure JSON typing rather than
comprehension. Reporting both makes the difference visible - in the first run it
is the gap between 7 raw and 10 coerced.

**Scope truth is the union of the corrections delivered for that product by that
day**, because a correction case is a product and a run at day 30 is holding the
day-18 correction too. Where the newest correction leaves the variant genuinely
open, there is no correct answer and the run is reported rather than graded.
Grading it would be scoring the model against an answer the record does not
contain.

## Risks / Trade-offs

**Fifteen documents cannot support a headline accuracy figure.** → No headline
figure is reported. The rendered output is a confusion matrix, a refusal
taxonomy and a list of named failure modes, and the proposal says the same.

**The fail-closed safety gate is unmeasured.** No document carrying a
safety-class attribute falls inside the eval window - `safety_documents: 0` - so
the one number the harness was built to justify is the one it did not produce.
→ Recorded in the report and left as an open task rather than filled with a
figure from an adjacent measurement.

**Three of the seven model call sites are graded** - extraction, scope
resolution and the claim scan. Copy regeneration, triage, enrichment and the
reviewer's narrative are not. → Stated rather than implied; the three graded are
the ones whose output is checkable against a record, and the others are prose
whose grading needs a judge this repository does not have.

**Claim-scan recall measures overlap with the deterministic table**, because the
prompt tells the model the table has already been checked. → Recorded in the
report as a note. It is a real measurement of a different thing, not a broken
measurement of recall.

**The first run graded one model.** A cross-model sweep exists for the
extraction touchpoint only, in `data/eval/by_model.json`; scope, claims and
calibration have never run against more than one model, and the headline report
carries one. → Left as an open task rather than reported as a comparison.

**A grading run resets a database.** → It pins its own `DB_PATH` before anything
reads one, so it cannot reset a demo in progress.

## Migration Plan

1. Emit the key from the generator; regenerate the seed pack.
2. Land the two key-guard tests, which run without a gateway.
3. Lift the extraction messages and the claim-scan inputs into named functions
   both the node and the scorer call.
4. Land the harness; record the first run.
5. Rollback is deleting the script and the key emission; nothing in the pipeline
   depends on either.

## Open Questions

- Whether an eval window that contains a safety-class document should be added
  to the tape, or whether the gate should be measured by a separate fixture. The
  first changes the demo data every arc depends on; the second measures
  something the pipeline does not run. Neither answer changes the specs above.
