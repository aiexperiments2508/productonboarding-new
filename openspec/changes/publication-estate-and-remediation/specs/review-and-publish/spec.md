## ADDED Requirements

### Requirement: A dispatch can be planned without being made

What a resolution would be sent to, and which of those systems would refuse it,
SHALL be answerable without publishing anything.

A reviewer approving a correction should see that the printed catalogue is
inside its freeze window before deciding, rather than discovering it from a
report afterwards. Planning SHALL write nothing: a surface that published as a
side effect of being looked at would be the worst possible way to learn this.

#### Scenario: Planning writes nothing

- **WHEN** a dispatch is planned
- **THEN** no action is committed
- **AND** `tests/test_publication.py::test_planning_a_dispatch_sends_nothing`
  asserts the count is unchanged

#### Scenario: A channel that cannot recall is deferred, not attempted

- **WHEN** a dispatch is planned for a correction reaching a channel inside a
  freeze window whose artefact cannot be recalled
- **THEN** that system is deferred and the deferral names the window
- **AND** `tests/test_publication.py::test_a_frozen_channel_is_deferred_rather_than_attempted`
  asserts both

### Requirement: Publishing and rollback report per system

A dispatch SHALL report an outcome for each publication system it reaches -
sent, deferred, or refused - each carrying its reason where it is not sent.

"Failed" is not an answer a caller can act on: it does not distinguish nothing
having gone out from almost everything having gone out, and the difference
decides what somebody does next.

The counts a dispatch reports SHALL be derived from the rows it returns, so the
summary cannot disagree with the detail beneath it.

#### Scenario: The counts agree with the rows

- **WHEN** a dispatch reports
- **THEN** the sent, deferred and refused counts equal the rows carrying each
  outcome
- **AND** `tests/test_publication.py::test_the_dispatch_report_counts_agree_with_its_rows`
  asserts each

#### Scenario: A channel never sent to is not reported as reverted

- **WHEN** a resolution is rolled back and one of the systems it reached was
  deferred rather than sent to
- **THEN** that system reports that it was never sent rather than reporting a
  reversal
- **AND** `tests/test_publication.py::test_a_channel_never_sent_to_is_not_reported_as_reverted`
  asserts the distinction, because reporting a reversal there would be a false
  statement about a printed page

### Requirement: A refusal is a property of the resolution, not of a channel

Where publication is refused, every system SHALL be reported refused, carrying
the single reason the approval boundary gave.

The gates - a recorded approval, evidence that has not moved, no open safety
violation - are properties of the resolution. Publishing to four channels a
resolution nobody approved would be four problems rather than none, and a
per-channel refusal would invite exactly that reading.

The reason SHALL be the one the boundary returned rather than one re-derived
here. Two accounts of why a publish was refused is one account too many.

#### Scenario: With no approval on record, every system refuses

- **WHEN** a dispatch is attempted for a resolution with no approval recorded
- **THEN** nothing is sent, every system is reported refused, and the response
  names the reason
- **AND** `tests/test_publication.py::test_a_dispatch_without_an_approval_refuses_every_system`
  asserts each

#### Scenario: One refusal is reported once

- **WHEN** a dispatch is refused across several systems
- **THEN** every system carries the same reason, and it is the response's own
- **AND** `tests/test_publication.py::test_a_refused_dispatch_reports_one_reason_not_six`
  asserts both
