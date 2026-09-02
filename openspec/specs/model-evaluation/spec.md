# model-evaluation Specification

## Purpose

Measures whether the model touchpoints are right, not merely whether they run:
grading what was read out of a supplier document, at what scope, with what
stated confidence, against an answer key generated from the same payloads the
documents were written from - and reporting each number with the limit of the
measurement attached to it.

## Requirements

### Requirement: The answer key is generated from the data, never hand-labelled

The answer key SHALL be emitted by the same generator that writes the seed pack,
out of the same structured event payloads the documents' prose was written from,
and SHALL be rewritten whenever the data is. It SHALL cover every material
document the extractor is asked to read, in the order the tape delivers them,
and SHALL name no document the tape does not carry - the arrivals that are
already structured are never put in front of a model and grading them would
flatter the result with documents nobody asks a model to read.

The immaterial documents SHALL be sampled rather than covered exhaustively. The
tape carries hundreds of routine category notes that assert nothing, and a key
whose negatives outnumber its positives thirty to one measures how often a model
correctly says "nothing here" rather than whether it finds the correction.

Every corrected value in the key SHALL be something the catalog can hold: an
attribute path the catalog defines, against a product or variant the catalog
holds.

#### Scenario: A key that has fallen behind the tape is caught

- **WHEN** the key's event ids are compared with the events on the tape whose
  type the extractor reads
- **THEN** every material document among them is keyed, no keyed document is
  absent from the tape, and the key is in tape order
- **AND** `tests/test_golden.py::test_key_covers_every_material_document_and_invents_none`
  asserts each of the three separately, so a missing document and an invented
  one fail with different messages

#### Scenario: Every keyed row is expressible in the catalog

- **WHEN** every row of every keyed document is checked against the catalog
- **THEN** each names a defined attribute path and an entity the catalog holds
- **AND** `tests/test_golden.py::test_every_keyed_row_is_something_the_catalog_can_hold`
  asserts both

#### Scenario: The key still contains the question the measurement turns on

- **WHEN** the key is inspected for the classes the report is built from
- **THEN** it holds at least one ambiguous correction, at least one immaterial
  document, at least one document correcting more than one value, and at least
  one whose scope the payload settles to a single entity
- **AND** `tests/test_golden.py::test_the_key_still_contains_the_question`
  asserts each, so a key that lost its ambiguous correction cannot report a
  clean column having measured nothing at all

### Requirement: The key and the deterministic fallback cannot drift apart

The key and the node's deterministic fallback read the same event payload and
are therefore the key's two authors. For every field both of them produce, they
SHALL agree on every keyed document, so that a change to either is caught rather
than silently changing what the eval calls correct.

Where the two speak different vocabularies, the translation SHALL be pinned
explicitly rather than assumed away.

#### Scenario: Every shared field agrees on every document

- **WHEN** each keyed document is compared with the fallback's reading of the
  same event, field by field
- **THEN** materiality, attribute path, old value, new value, unit, whether it
  is a correction, whether it resolves an issue, whether it is provisional, and
  the correction kind all agree
- **AND** `tests/test_golden.py::test_key_agrees_with_the_deterministic_fallback`
  (parameterised over the eight shared fields) and
  `test_key_agrees_with_the_fallback_on_correction_kind` assert them

#### Scenario: The scope vocabulary mismatch is recorded, not assumed away

- **WHEN** the fallback's scope answer is translated into the key's vocabulary
  for every material document
- **THEN** the translation agrees with the key
- **AND** `tests/test_golden.py::test_the_fallback_answers_applies_to_in_the_catalogs_vocabulary`
  asserts it, recording a known mismatch - the prompt offers three answers and
  the structured payload speaks the catalog's own words - so that it stops being
  harmless loudly rather than quietly

### Requirement: The eval grades the prompt and the inputs that ship

The messages the scorer puts in front of a model SHALL be the messages the node
puts in front of a model, and the inputs the claim scan is graded on SHALL be
the inputs the node assembles, each built by one named function both callers
use. A scorer that rebuilt either for itself would go on reporting yesterday's
accuracy the first time the shipping version was revised.

#### Scenario: One function builds the extraction prompt for both callers

- **WHEN** the extraction messages are built for a supplier document
- **THEN** they are a system message and a user message, the system message
  names the fields the reply must carry, and the user message names the document
  being read
- **AND** `tests/test_golden.py::test_the_prompt_the_eval_grades_is_the_prompt_that_ships`
  asserts each against the same function the extraction node calls

### Requirement: A reply outside the contract is a contract failure, not a misread field

A reply the gateway will not accept SHALL be counted as a refusal and excluded
from the accuracy denominators, and the report SHALL name what was wrong with
it. A refused reply routes to the deterministic fallback and never influenced
anything downstream, so counting it as a misread field would report a model that
cannot emit a JSON object as one that cannot read a specification.

A refusal caused by a provider rate limit SHALL be labelled as a quota result
rather than a model result, because a run reporting those has measured a quota.

#### Scenario: Refusals are counted and named separately

- **WHEN** the first recorded run is read back from `data/eval/report.json`
- **THEN** of fifteen documents ten are answered and five refused, the refusal
  reason recorded for all five is that the reply was a JSON array where an
  object was required, and the accuracy figures are computed over the ten

### Requirement: Materiality is reported as precision and recall, never as one number

The materiality decision SHALL be reported as precision and recall separately,
with the counts behind them, because the two errors do not cost the same: a
missed correction reaches shoppers, and a false positive costs a reviewer a
minute. A single combined score SHALL NOT be presented in their place.

#### Scenario: The first run's materiality is reported both ways

- **WHEN** the first recorded run is read back from `data/eval/report.json`
- **THEN** materiality reports precision 1.00 and recall 0.83 with the true
  positives, false positives and false negatives beside them - one missed
  correction and no false positives

### Requirement: The scope answer is graded as a confusion matrix with one named cell

The scope answer SHALL be reported as a three-class confusion matrix over the
classes the prompt offers, with a reply outside those classes counted as its own
class rather than mapped onto the nearest one. The cell where an ambiguous
document is answered with a resolved variant SHALL be reported on its own,
because a model resolving an ambiguity the document did not resolve has skipped
the step the base-versus-variant design exists to perform.

A model's answer SHALL also be reported as defensible where the document
supports more than one reading, separately from exact agreement.

#### Scenario: The named failure did not occur for the graded model

- **WHEN** the first recorded run is read back from `data/eval/report.json`
- **THEN** all six graded documents are defensible, five are exact, and the
  count of ambiguous documents answered as a resolved variant is zero

### Requirement: Stated confidence is reported against observed accuracy at the gate's own edge

Confidence SHALL be reported as stated confidence against observed accuracy,
bucketed with the safety threshold as its own boundary, and the proportion of
answers at or above that threshold that were true SHALL be reported on its own.
That is the number that justifies the fail-closed threshold or does not.

Where a touchpoint is advisory - confirmed against a deterministic table before
anything acts on it - the report SHALL still record its overconfidence, because
what makes it contained is a property of the pipeline and not of the model.

#### Scenario: The advisory scanner's overconfidence is recorded

- **WHEN** the first recorded run is read back from `data/eval/report.json`
- **THEN** the claim scanner's flags in the top confidence bucket state about
  0.95 and are observed right 0.76 of the time over fifty flags

### Requirement: The report carries what the measurement cannot say

The report artefact SHALL carry, beside the numbers, the limits that make them
not what they look like. It SHALL state that the answer key is built from the
same payload the deterministic fallback reads, so the key can grade the model
and cannot grade the fallback; that the combined model-plus-fallback figure is
therefore arithmetic rather than evidence; that claim-scan recall measures
overlap with the deterministic table rather than value added; and which runs
were reported rather than graded because the record left no correct answer.

#### Scenario: A number read later arrives with its caveat

- **WHEN** the first recorded run is read back from `data/eval/report.json`
- **THEN** the report carries the notes naming each of those limits, alongside
  the gateway it ran against, the answer key it graded, the document count and
  the thresholds in force

### Requirement: A repeat run is free and identical

Model responses SHALL be cached outside the store the harness resets between
scenarios, so that the first run costs tokens and every run after it is free and
returns the same answers. Each scenario SHALL begin from a freshly seeded store
with the checkpoints cleared, so a measurement cannot read facts a previous
scenario recorded and the numbers cannot depend on the order the scenarios ran
in.

#### Scenario: The cache survives the reset that would otherwise discard it

- **WHEN** the harness reseeds between scenarios
- **THEN** the cached responses are copied out before the store is dropped and
  loaded back into the fresh one, and the report records the run's elapsed time
  and how often it was rate limited

### Requirement: Grading the model needs a gateway; guarding the key does not

The harness SHALL refuse to run against an unreachable gateway, saying so rather
than producing a report full of fallback readings labelled as model results. The
tests that guard the answer key SHALL need no gateway, so they run wherever the
rest of the suite does.

#### Scenario: The key's guards run in the ordinary suite

- **WHEN** the test suite runs with the gateway pinned to a closed port
- **THEN** every test in `tests/test_golden.py` runs and passes, and the
  harness itself is not part of the suite
