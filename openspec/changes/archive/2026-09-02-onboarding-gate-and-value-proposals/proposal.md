## Why

Onboarding a bundle asks two questions at once and answers them in the wrong
order.

**May we sell this at all?** is a question about regulation and about the
retailer's own policy. **Is the record complete?** is the question onboarding
is actually about. Today `readiness.assess` runs both in a single pass and
counts the findings, which is right for "is this fit to launch" and wrong for
"should this be onboarded", because the count treats a withdrawal notice and a
missing net-content as the same kind of thing. A product that may not lawfully
be sold therefore travels the whole pipeline: a source is retrieved for it, a
value is proposed for it, and somebody has to read the proposals before
discovering that the product is going back to its supplier regardless.

There is a second gap behind the first. Where a record is merely incomplete,
the only thing that can close a gap is a passage a model reads. So a field
nobody sent stays empty at a venue with no network, and it stays empty even
when the answer is already on file - the 45 W and 65 W variants of the same
kettle agree about their plug type, two hundred snack bars agree about their
unit of measure, and a category manager may have settled this exact field last
week. None of that is consulted, and the queue never learns from itself.

And where a value *is* proposed, the number that would decide whether to write
it is the model's own self-reported confidence. That is a fluent guess about
its own fluency: it moves with phrasing, it is uncalibrated between prompts,
and handing it the autonomy gate would make the gate the model's rather than
the retailer's.

Finally, the Ingest Fabric has stopped being about the graph. The estate panel,
the arrivals pulse, the supplier bundle and the live feed have all accumulated
under the map, which gets half a viewport of a screen it should own. And the
replay controls offer exactly one verb - `reset` - for two different acts:
rewinding the recording, and retracting what a supplier pushed through a portal
during a rehearsal. Running the second by accident is how a demo opens on
somebody else's submissions.

## What Changes

- **A gate in front of onboarding.** Regulation and the retailer's own policy
  are checked first. A product that fails goes back to its supplier with a
  sentence naming who said so, and nothing is retrieved, proposed or spent on
  it.
- **A fourth reading check, `policy_conformance`**, asking whether the record
  breaches the retailer's own written policy - which `saleability` does not
  ask, because a market authority forbidding a sale and an organisation
  declining to make one are different statements.
- **The gate is a set of check names, not a severity.** `policy_conformance`
  produces `OPEN` findings deliberately: it stops onboarding without claiming a
  law was broken. Reading the severity instead would either drop the policy
  check from the gate or force it to claim an authority it does not have.
- **A value is proposed from three sources, not one**: a passage a model read,
  the rest of the product and its category, and what a reviewer has decided
  before. The last two need no gateway, which is what lets a proposal exist at
  a venue with no network.
- **The confidence is composed here and is not the model's own number.** A
  self-report is discounted and counted as one input beside things already on
  file. Disagreement costs more than agreement pays, because evidence that a
  proposal is wrong is worth more than evidence that it is unremarkable.
- **Above the threshold a value is written INFERRED; below it, it becomes a
  question.** A category manager approves, rejects or rectifies with the
  evidence open, and their answer lands DECIDED - because the ledger is meant
  to be able to say who asserted a value.
- **Two rules sit in front of the threshold and neither moves with it**: a
  safety-class attribute is always decided by a person, and so is any value
  fewer than two sources agree with. The second is checked on a count rather
  than left to the weights, because a threshold is a knob and a safety property
  that holds only while nobody turns it is not one.
- **The Ingest Fabric is given back to the graph.** The machinery moves to
  System Control, the bundle to Supplier Intake, and what is in force moves to
  a rail that is shut by default - shut, not hidden: the handle carries the
  open-case count and takes the severity of the worst one.
- **`clear` beside `reset`.** A rewind stays a rewind; the deliberate act
  removes the portal events, the arrivals that carried them, the submission
  records and the questions nobody answered. It leaves the facts those
  submissions recorded, which is a real inconsistency and is said out loud
  where the button is.
- **The suite runs in parallel**, distributed by file, because each module owns
  its database and two workers sharing one would delete each other's fixtures
  mid-run.

## Capabilities

### New Capabilities

- `onboarding-gate`: whether a product may be onboarded at all, decided from
  regulation and the retailer's own policy before anything else runs.
- `value-proposals`: proposing a value for a field nobody sent, scoring the
  proposal from evidence already on file, and routing it to a person or to the
  record.

### Modified Capabilities

- `launch-readiness`: a fourth reading check reads the retailer's own policy
  and reports `OPEN` findings against it.
- `run-and-review-api`: the replay command separates rewinding the recording
  from retracting a supplier's submission.

## Impact

- `sc/onboarding/gate.py` - new; the partition of an existing summary.
- `sc/onboarding/history.py` - new; siblings, category convention and past
  decisions, without a gateway.
- `sc/onboarding/suggest.py` - new; the proposal and its composed score.
- `sc/onboarding/decide.py` - new; the threshold, the routing, the queue and a
  reviewer's answer.
- `sc/onboarding/fix.py`, `sc/onboarding/assess.py`, `sc/onboarding/__init__.py`
  - the gate runs first, and `fix` gains the second writing door.
- `sc/readiness/reading.py`, `sc/readiness/checks.py`, `sc/readiness/rollup.py`
  - `policy_conformance` joins the reading set.
- `sc/schema.sql` - `onboarding_suggestions`, and the indexes the queue and the
  prior lookup read through.
- `sc/replay/tape.py` - `clear` beside `reset`.
- `sc/main.py` - the threshold, the queue and the decision routes.
- `frontend/src/components/IngestFabric.tsx`, `SystemControl.tsx` - the map
  gets its screen back; System Control becomes tabbed.
- `pytest.ini`, `tests/conftest.py` - parallel by file, and the accepted-lines
  extension made per-module.
- `tests/test_onboarding.py`, `tests/test_readiness.py`,
  `tests/test_live_lane.py` - the gate, the score, the routing, the decisions
  and the clear.
