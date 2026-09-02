# redaction Specification

## Purpose

Hiding a value that is known to be wrong, while the corrected one is still being
agreed.

Between knowing a live value is wrong and having a validated replacement, the
wrong value is on sale. This capability is the move in that gap, and it is
shaped by one asymmetry: **hiding is authorised by the approval that already
agreed the value was wrong; republishing is not.**

## Requirements

### Requirement: A redaction is authorised by an existing approval, which it reads and never writes

A redaction SHALL be refused on every system where no approval stands behind
it. The authorising approval SHALL be read and SHALL NOT be written by the
redaction.

Asking for a second decision before ceasing to show something a reviewer has
already called wrong would be ceremony with a shopper on the other end of it. A
redaction that *wrote* an approval would manufacture the authority it claims to
act under.

Planning a redaction SHALL change nothing, and a replayed redaction SHALL act
once.

#### Scenario: No approval, no redaction

- **WHEN** a redaction is attempted with no approval behind it
- **THEN** every system refuses it
- **AND** `tests/test_redaction.py::test_a_redaction_without_an_approval_refuses_every_system`
  asserts it

#### Scenario: The approval is read, never written

- **WHEN** a redaction is carried out
- **THEN** the approval it cites is unchanged
- **AND** `tests/test_redaction.py::test_the_approval_that_authorises_a_redaction_is_read_and_never_written`
  asserts it

#### Scenario: Planning changes nothing and a replay acts once

- **WHEN** a redaction is planned, and then the same one is delivered twice
- **THEN** the plan changes nothing and the delivery acts once
- **AND** `tests/test_redaction.py::test_planning_a_redaction_changes_nothing`
  and `::test_a_replayed_redaction_acts_once` assert both

### Requirement: A redaction is a new fact and never an edit

A redaction SHALL write no attribute fact, SHALL move no published version,
SHALL be invisible to the publish-time validator, and SHALL emit no change-set
action. What a channel showed before a redaction SHALL remain readable as of
that time.

Hiding something today is not a claim about what was true yesterday, and the
store is bitemporal precisely so those stay separable.

#### Scenario: Nothing about the record moves

- **WHEN** a redaction is carried out
- **THEN** no attribute fact is written, no published version moves, the
  validator does not see it, and no change-set action is emitted
- **AND** `tests/test_redaction.py::test_a_redaction_is_a_new_fact_and_never_an_edit`,
  `::test_a_redaction_writes_no_attribute_fact_and_moves_no_published_version`,
  `::test_a_redaction_is_invisible_to_the_validator` and
  `::test_no_change_set_action_is_emitted_by_a_redaction` assert each

#### Scenario: History is still readable as of then

- **WHEN** a channel's state before a redaction is read as of that instant
- **THEN** it shows what was shown then
- **AND** `tests/test_redaction.py::test_what_a_channel_showed_before_a_redaction_is_still_readable_as_of_then`
  asserts it

### Requirement: What hiding means is derived from what the channel can do

The action taken SHALL be derived from the channel's own capabilities, and one
correction SHALL be permitted to produce a different correct action on each
kind of channel.

A marketplace listing SHALL be withdrawn rather than placeholdered, because its
own rules make a placeholder a hard violation. A search facet SHALL be dropped
rather than left indexing a wrong value. A shelf label SHALL be queued for
reprint rather than reported as done.

**A channel that cannot be recalled SHALL never be reported as redacted.** A
print run that has already shipped is not hidden by anything the platform does,
and saying otherwise would be a false statement about the physical world. It
SHALL open an erratum obligation instead.

Copy SHALL be redacted together with the value it quotes, through the same
lineage the blast radius uses. A bullet reading "may contain milk" above a spec
row saying the allergen statement is being checked would leave the page worse
than before the correction started.

#### Scenario: One correction, a different right answer per channel

- **WHEN** one correction is redacted across every kind of channel
- **THEN** each channel gets the action its own capabilities allow
- **AND** `tests/test_redaction.py::test_one_correction_gets_a_different_right_answer_on_each_kind_of_channel`
  asserts it

#### Scenario: A marketplace is withdrawn rather than placeholdered

- **WHEN** a safety field is redacted on a marketplace listing
- **THEN** the listing is withdrawn, in the shape that gateway writes
- **AND** `tests/test_redaction.py::test_a_marketplace_withdraws_a_safety_field_rather_than_placeholdering_it`
  and `::test_withdrawing_a_listing_takes_it_off_air_in_the_shape_the_gateway_writes`
  assert both

#### Scenario: Search drops the facet and the shelf queues a reprint

- **WHEN** the same correction reaches a search channel and a shelf channel
- **THEN** the facet is dropped rather than left indexing, and the label is
  queued rather than claimed done
- **AND** `tests/test_redaction.py::test_a_search_facet_is_dropped_rather_than_left_indexing_a_wrong_value`
  and `::test_a_shelf_redaction_queues_a_reprint_rather_than_claiming_it_is_done`
  assert both

#### Scenario: An unrecallable channel gets an erratum, never a redaction

- **WHEN** a correction reaches a print channel
- **THEN** an erratum obligation is opened and the channel is not reported as
  redacted
- **AND** `tests/test_redaction.py::test_a_channel_that_cannot_be_recalled_is_never_reported_as_redacted`
  and `::test_a_print_channel_gets_an_erratum_obligation_instead_of_a_redaction`
  assert both

### Requirement: Undoing a redaction is its own decision, and safety does not ride along

A restore SHALL put back what was hidden without deleting the redaction record,
and SHALL be refused where the redaction was an erratum - there is nothing to
put back on a channel that was never recalled.

A rollback SHALL NOT undo a safety redaction. Rolling back a publish restores a
previous state; it is not a decision that a value known to be wrong is now fine.

#### Scenario: A restore puts back without deleting

- **WHEN** a redaction is restored
- **THEN** what was hidden is shown again and the record of the redaction
  remains
- **AND** `tests/test_redaction.py::test_a_restore_puts_back_what_was_hidden_without_deleting_it`
  asserts it

#### Scenario: An erratum cannot be restored and a rollback cannot lift a safety redaction

- **WHEN** a restore is attempted on an erratum, and a rollback is run over a
  safety redaction
- **THEN** the first is refused and the second leaves the redaction standing
- **AND** `tests/test_redaction.py::test_a_restore_refuses_where_the_redaction_was_an_erratum`
  and `::test_a_rollback_does_not_undo_a_safety_redaction` assert both

### Requirement: An obligation stays open until its own owner discharges it

An obligation opened by a redaction SHALL remain open until it is discharged,
and one system SHALL NOT discharge another system's obligation.

Every redaction SHALL be recorded in the audit ledger with the actor, the
reason and the system. An erratum and a reprint SHALL be recorded under their
own verbs rather than as redactions, because they are different acts with
different evidence behind them.

#### Scenario: An obligation outlives the redaction that opened it

- **WHEN** an obligation is opened and left
- **THEN** it stays open, and another system cannot discharge it
- **AND** `tests/test_redaction.py::test_an_obligation_stays_open_until_somebody_discharges_it`
  and `::test_a_system_cannot_discharge_another_systems_obligation` assert both

#### Scenario: The ledger names actor, reason, system and verb

- **WHEN** redactions, errata and reprints are carried out
- **THEN** each reaches the ledger with its actor, reason and system, under its
  own verb
- **AND** `tests/test_redaction.py::test_every_redaction_lands_in_the_ledger_with_actor_reason_and_system`
  and `::test_an_erratum_and_a_reprint_are_recorded_under_their_own_verbs`
  assert both
