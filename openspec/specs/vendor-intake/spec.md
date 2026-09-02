# vendor-intake Specification

## Purpose

What a supplier may submit to the platform, what it may see of its own record,
and the provenance rule that stops a submission from becoming a value.

The load-bearing claim: **a supplier cannot write a fact.** A submission is a
document version. What it asserts becomes a fact only when the pipeline reads
the document and writes it back as an inference, under the fail-closed safety
gate. That is enforced by the provenance taxonomy rather than by an
authorisation check, because a check is a thing that can be passed, mocked or
forgotten at a new call site.

## Requirements

### Requirement: A submission is recorded as a document version, never as a value

A supplier submission SHALL be recorded as a version of a document. It SHALL
NOT write an attribute fact.

A correction SHALL revise the document the value came off, rather than minting
a new document - a newly minted identifier carries no precedence and would lose
every contest it entered. Re-submitting the same content SHALL NOT mint a
second version.

The submission SHALL land on the live lane and SHALL be visible before the
replay cursor reaches it. A repeated submission SHALL act once.

#### Scenario: A submission writes a document and not a value

- **WHEN** a supplier submits a corrected specification
- **THEN** a document version is recorded and no attribute fact is written
- **AND** `tests/test_intake.py::test_a_submission_is_recorded_as_a_document_version_and_not_as_a_value`
  asserts both

#### Scenario: A correction revises the document the value came off

- **WHEN** a supplier corrects a value it previously asserted
- **THEN** the revision is a new version of that same document, and a second
  identical submission does not mint another
- **AND** `tests/test_intake.py::test_a_correction_revises_the_document_the_value_came_off`
  and `::test_a_second_submission_does_not_re_mint_the_same_version` assert both

#### Scenario: It lands live and is visible at once

- **WHEN** a submission is made while the tape is behind it
- **THEN** it is on the live lane and readable immediately
- **AND** `tests/test_intake.py::test_the_submission_lands_on_the_live_lane_and_is_visible_at_once`
  asserts it

#### Scenario: A repeated submission acts once

- **WHEN** the same submission is delivered twice
- **THEN** it acts once
- **AND** `tests/test_intake.py::test_a_repeated_submission_acts_once` asserts it

### Requirement: A supplier sees its own products and no others

Every read and every write on the intake SHALL be scoped to the submitting
supplier. A supplier SHALL NOT read another supplier's specification or
submission, and SHALL NOT change another supplier's product. An unknown
supplier SHALL be refused rather than served an empty result.

Serving nothing to an unknown caller looks like a supplier with no products,
which is a state a real supplier can be in - so the two have to be
distinguishable.

What the intake reports about a specification SHALL agree with what the
catalog route reports, and a supplier SHALL be able to see which values it has
asserted.

#### Scenario: Scope holds on every direction

- **WHEN** a supplier reads and writes across the intake
- **THEN** it sees and changes only its own products
- **AND** `tests/test_intake.py::test_a_supplier_sees_only_its_own_products`,
  `::test_a_supplier_cannot_read_another_suppliers_specification`,
  `::test_a_supplier_cannot_change_another_suppliers_product` and
  `::test_a_supplier_cannot_read_another_suppliers_submission` assert each

#### Scenario: An unknown supplier is refused, not served nothing

- **WHEN** an unrecognised supplier calls the intake
- **THEN** it is refused
- **AND** `tests/test_intake.py::test_an_unknown_supplier_is_refused_rather_than_served_nothing`
  asserts it

#### Scenario: The intake and the catalog agree

- **WHEN** a supplier reads its own specification
- **THEN** it matches what the catalog route reports, and names the values that
  supplier asserted
- **AND** `tests/test_intake.py::test_the_specification_read_agrees_with_the_catalog_route`
  and `::test_a_supplier_is_told_which_values_it_asserted` assert both

### Requirement: The intake refuses what it cannot record faithfully

A submission SHALL be refused, with a reason, where it changes a safety
declaration without saying why, carries a value of the wrong type, names an
attribute nobody has defined, would take effect before it was sent, carries a
date that cannot be read, names an image role nobody declared, or exceeds the
upload limit.

A refusal naming the type it wanted, or the limit it exceeded, is one a
supplier can act on without a support call. Guessing at an unreadable date is
the specific failure worth naming: a date the system invented is
indistinguishable from one the supplier meant.

#### Scenario: A safety declaration cannot change silently

- **WHEN** a submission changes a safety-class declaration with no reason given
- **THEN** it is refused
- **AND** `tests/test_intake.py::test_a_safety_declaration_cannot_be_changed_without_saying_why`
  asserts it

#### Scenario: A malformed value is refused with what was wanted

- **WHEN** a value of the wrong type, or an undefined attribute, is submitted
- **THEN** it is refused, the first naming the type it expected
- **AND** `tests/test_intake.py::test_a_value_of_the_wrong_type_is_refused_with_the_type_it_wanted`
  and `::test_an_attribute_nobody_has_defined_is_refused` assert both

#### Scenario: A date is never guessed at

- **WHEN** a correction is dated before it was sent, or carries an unreadable
  date
- **THEN** each is refused rather than corrected or guessed
- **AND** `tests/test_intake.py::test_a_correction_cannot_take_effect_before_it_was_sent`
  and `::test_an_unreadable_date_is_refused_rather_than_guessed_at` assert both

#### Scenario: An image is refused by role and by size

- **WHEN** an undeclared image role, or an oversized upload, is submitted
- **THEN** each is refused with a named reason
- **AND** `tests/test_intake.py::test_an_image_role_nobody_declared_is_refused`
  and `::test_an_upload_over_the_limit_is_refused_with_a_named_reason` assert
  both

### Requirement: An uploaded asset reaches the record, and an unread document says so

An uploaded image SHALL reach the record and clear the check it answers, and
SHALL be attributed to the system that carried it. Uploaded bytes SHALL be
written outside the seed pack, so a regenerated pack does not delete what a
supplier sent.

A document with no text rendition SHALL report that it has not been read.
Reporting nothing wrong with a document nobody has read is a clean result that
means nothing.

A submission SHALL report every stage it reached, and a verdict on it SHALL
carry the caveat where the reading checks did not run.

#### Scenario: An upload clears the finding it answers

- **WHEN** a supplier uploads a required image
- **THEN** it reaches the record, clears the check, and names the carrying
  system
- **AND** `tests/test_intake.py::test_an_uploaded_image_reaches_the_record_and_the_checks`
  and `::test_an_uploaded_image_is_attributed_to_the_system_that_carried_it`
  assert both

#### Scenario: Uploaded bytes survive a regenerated pack

- **WHEN** a supplier uploads a file
- **THEN** it is written outside the seed pack
- **AND** `tests/test_intake.py::test_uploaded_bytes_land_outside_the_seed_pack`
  asserts it

#### Scenario: An unread document says it is unread

- **WHEN** a document with no text rendition is submitted
- **THEN** it reports that it has not been read rather than that nothing is
  wrong with it
- **AND** `tests/test_intake.py::test_a_document_with_no_text_says_it_has_not_been_read`,
  `::test_a_document_with_a_text_rendition_can_be_read` and
  `::test_a_document_version_reports_awaiting_extraction_not_nothing_wrong`
  assert each

#### Scenario: A submission reports its stages and its caveat

- **WHEN** a submission is followed through the pipeline
- **THEN** it reports every stage it reached, and its verdict carries the
  caveat where the reading checks did not run
- **AND** `tests/test_intake.py::test_a_submission_reports_every_stage_it_reached`
  and `::test_a_verdict_carries_its_caveat_when_the_reading_checks_did_not_run`
  assert both

### Requirement: A draft is not a product

A proposed new line SHALL say plainly that it is not in the catalog, and SHALL
be refused without a category.

#### Scenario: A draft declares itself

- **WHEN** a supplier proposes a new line
- **THEN** the response says it is not in the catalog, and a proposal with no
  category is refused
- **AND** `tests/test_intake.py::test_a_draft_says_plainly_that_it_is_not_in_the_catalog`
  and `::test_a_draft_without_a_category_is_refused` assert both
