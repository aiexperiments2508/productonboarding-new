## Purpose

A supplier sends a whole range at once, and the retailer answers how much of it
can be sold. This capability covers the archive, the batch it becomes, the
sequential pass that judges it, the report that counts it, and the one bounded
place where a model is allowed to close a gap.

The rule underneath all of it: the bulk door relaxes nothing the single door
enforces. It is a different quantity of the same act.

## ADDED Requirements

### Requirement: One archive is one submission, judged row by row

An intake endpoint that accepts both attribute rows and imagery SHALL accept an
archive containing one data file and an optional images folder. Every row SHALL
become an event on the live lane and SHALL be judged by the platform's own
ingestion under the same precedence policy, materiality threshold and safety
override as a recorded event. No row SHALL write a value directly.

Rows SHALL be asserted against a new version of the submitting supplier's own
existing document. A newly minted document identifier carries no precedence and
would lose every contest it entered.

#### Scenario: A bundle lands as events under one batch

- **WHEN** a supplier submits an archive of rows and photographs
- **THEN** the submission appends one opening event, one event per row, one per
  photograph and one closing event, all carrying the same batch identifier, and
  the rows become facts attributed to the system that carried them
- **AND** `tests/test_bundle_intake.py::test_a_bundle_lands_as_events_on_the_live_lane`
  and `::test_the_document_is_a_new_version_of_the_suppliers_own` assert it

#### Scenario: One upload is one arrival

- **WHEN** a bundle of many rows is submitted
- **THEN** the whole submission is recorded as a single delivery batch, because
  it arrived once
- **AND** `tests/test_bundle_intake.py::test_one_upload_is_one_arrival_batch`
  asserts it

### Requirement: Refusals happen at the scale of the fault

A malformed archive SHALL refuse the whole bundle with a reason. An
unrecognised column SHALL be reported and SHALL NOT fail the bundle. A value
that cannot be read SHALL lose that cell and not its row, and rejected rows and
rejected cells SHALL be counted separately.

A path that would leave the archive, a declared uncompressed size over the
limit, more than one data file at the root, and an attachment that is not an
archive SHALL each be refused by name, before anything is decompressed or
appended.

#### Scenario: A typo in a header costs a column, not a bundle

- **WHEN** a bundle carries a column the registry does not define
- **THEN** the bundle is accepted, the column is reported unread, and the
  correctly-spelled column is not among those reported
- **AND** `tests/test_bundle_intake.py::test_an_unknown_column_is_reported_and_does_not_fail_the_bundle`
  asserts it

#### Scenario: An unreadable value is reported as missing, not as absent data

- **WHEN** a row carries a value that will not parse as its declared type
- **THEN** the row is accepted without that value, the cell is reported by line
  and column, and the readiness check subsequently reports the attribute as
  missing
- **AND** `tests/test_bundle_intake.py::test_a_bad_cell_loses_the_cell_and_not_the_row`
  asserts it

### Requirement: A line the catalogue does not have is a proposal

A row naming a SKU the catalogue does not hold SHALL become a proposed new line
held for a reviewer, recorded as its own proposal so that it is accepted
through the same decision path as one submitted singly. It SHALL NOT become a
product.

A row naming a SKU belonging to another supplier SHALL be refused by line.

#### Scenario: Five new lines are five proposals

- **WHEN** a bundle carries rows whose SKUs the catalogue does not hold
- **THEN** each becomes a pending proposal carrying the batch it arrived in,
  and none of them appears among the batch's assessed entities
- **AND** `tests/test_bundle_intake.py::test_a_sku_we_do_not_have_is_held_as_a_draft`
  asserts it

### Requirement: A batch is a submission, and its report is recomputed

The batch SHALL be the submission the archive created; no separate batch
identity, status or verdict SHALL be stored. Every figure in a batch's report
SHALL be recomputed on read from the same assessment and the same tally the
product summary uses.

#### Scenario: Nothing about the outcome is cached

- **WHEN** a batch's report is read twice
- **THEN** both reads return the same figures, computed each time, and the
  submission record carries no status or verdict column
- **AND** `tests/test_onboarding.py::test_the_report_is_recomputed_rather_than_stored`
  asserts it

### Requirement: The pass is sequential, and its pacing cannot reach a result

A batch SHALL be assessed one product at a time, in the order the supplier's
file listed them, streaming one message per product. Any delay applied between
products SHALL be presentation only: a pass run with it disabled SHALL return
an identical report.

Each product message SHALL carry the catalog nodes to highlight, resolved on
the server.

#### Scenario: The same answer at any speed

- **WHEN** a batch is assessed with pacing disabled and again through the
  ordinary report path
- **THEN** the totals and the per-product verdicts are identical
- **AND** `tests/test_onboarding.py::test_the_pace_cannot_reach_a_result` asserts it

### Requirement: Proposed lines are counted apart from assessed products

A report SHALL count proposed new lines separately from assessed products and
SHALL state that they are not included in the verdict totals. A batch of rows
of which some are lines the catalogue does not have SHALL NOT report the
assessed subset as though it were the whole.

#### Scenario: Six of eleven is not reported as eleven

- **WHEN** a bundle of eleven rows of which five are new lines is reported
- **THEN** the totals count six, the proposals count five, and the report says
  the proposals are not included

### Requirement: A gap is fixable only when a passage exists, and never when it is safety class

A gap SHALL be reported as a candidate for automatic filling only when
retrieval, asked as the enrichment step asks it, returns at least one passage.
This is a sound negative: the enrichment step refuses any fill whose source is
not among the supplied passages, so a gap with no passage cannot be filled.

A safety-class attribute SHALL NEVER be a candidate. Such gaps SHALL be counted
and named so that the exclusion is visible.

The count of candidates SHALL be presented as gaps with a source on file, and
SHALL NOT be presented as gaps that will be filled, until the sources have been
read.

#### Scenario: Candidacy tracks retrieval exactly

- **WHEN** a set of gaps is classified
- **THEN** a gap is a candidate if and only if retrieval returns a passage for
  it, and carries that passage as its citation
- **AND** `tests/test_onboarding.py::test_candidacy_tracks_retrieval_exactly` asserts it

#### Scenario: A safety-class gap is not a candidate

- **WHEN** a gap on a safety-class attribute is classified
- **THEN** it is held, counted separately, and given a reason
- **AND** `tests/test_onboarding.py::test_a_safety_class_gap_is_never_a_candidate`
  asserts it

### Requirement: Applying fills writes inferred facts and publishes nothing

Applying SHALL require a named actor and SHALL be recorded against them, even
when nothing was filled. Every filled value SHALL be recorded as inferred, with
its confidence and the passage it was read from, through the same path the
enrichment step writes through.

Applying SHALL NOT create an approval, a channel reservation or a committed
action. A product becomes ready by having no findings left; publishing remains
a separate decision behind its own gate.

Where no model is reachable, nothing SHALL be filled and every gap SHALL become
a request to the supplier with the reason.

#### Scenario: Nothing is published

- **WHEN** fills are applied to a batch
- **THEN** the approvals, reservations and committed actions are unchanged in
  number, and the returned verdicts come from a fresh assessment
- **AND** `tests/test_onboarding.py::test_applying_writes_no_approval_and_no_reservation`
  and `::test_the_report_after_applying_is_re_assessed_rather_than_predicted`
  assert it

#### Scenario: No gateway means no guesses

- **WHEN** fills are applied with no model reachable
- **THEN** nothing is written, every gap is returned as a supplier request with
  its reason, and the response says the gateway was unreachable
- **AND** `tests/test_onboarding.py::test_with_no_gateway_nothing_is_filled_and_every_gap_is_explained`
  asserts it
