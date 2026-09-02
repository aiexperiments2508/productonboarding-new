## ADDED Requirements

### Requirement: Republishing over a safety redaction needs its own release decision

Where a listing holds a safety redaction, publishing to it SHALL be refused
until a release decision has been recorded - a fourth refusal beside those the
publish path already applies.

A release decision SHALL be recorded in its own table and SHALL NOT be written
to the approvals table. If it lived there it would satisfy the first gate by
itself, and "we agreed the old value was wrong" would silently become "we agreed
the new value is right" - which is the one substitution the whole approval
architecture exists to prevent.

A release approval alone SHALL NOT publish an unapproved resolution, and a
rejected release SHALL NOT open the gate. A redaction of an ordinary field SHALL
NOT hold a publish at all, and an open safety violation SHALL still be reported
ahead of the release gate, so a reviewer sees the substantive problem rather
than only the procedural one.

Every release SHALL be recorded against the person who took it.

#### Scenario: The release decision is kept apart from the approval

- **WHEN** a release decision is recorded
- **THEN** the approvals table is unchanged
- **AND** `tests/test_redaction.py::test_a_release_decision_is_not_written_to_the_approvals_table`
  asserts it

#### Scenario: The publish is refused, then goes through

- **WHEN** a publish is attempted against a listing holding a safety redaction,
  and again once the release is recorded
- **THEN** the first is refused and the second proceeds
- **AND** `tests/test_redaction.py::test_publishing_to_a_listing_holding_a_safety_redaction_is_refused`
  and `::test_the_same_publish_goes_through_once_the_release_is_recorded` assert
  both

#### Scenario: Neither gate substitutes for the other

- **WHEN** only a release is recorded, and separately when a release is rejected
- **THEN** the unapproved resolution does not publish, and the rejection does not
  open the gate
- **AND** `tests/test_redaction.py::test_a_release_approval_alone_does_not_publish_an_unapproved_resolution`
  and `::test_a_rejected_release_does_not_open_the_gate` assert both

#### Scenario: An ordinary redaction holds nothing, and the real violation is still reported

- **WHEN** an ordinary field is redacted, and separately when an allergen
  violation is open behind a release gate
- **THEN** the first holds no publish and the second is still reported
- **AND** `tests/test_redaction.py::test_a_redaction_of_an_ordinary_field_does_not_hold_a_publish`
  and `::test_an_open_allergen_violation_is_still_reported_before_the_release_gate`
  assert both

#### Scenario: A release names who took it

- **WHEN** a release decision is recorded
- **THEN** it carries the person who took it
- **AND** `tests/test_redaction.py::test_a_release_is_recorded_against_the_person_who_took_it`
  asserts it

### Requirement: A publisher declares which of its tools mutate

Each publication system's endpoint SHALL declare which of its tools can write,
and SHALL serve exactly the tools it declares. The declared verb list SHALL
cover every tool that can write.

The count of tools is not the property worth asserting - it goes stale the
moment the surface grows. What matters is that the server serves what it
declares and that the mutating set is declared rather than guessed at from the
verbs, so an operator who wants to show somebody a blast radius does not have to
hand over the ability to act on it.

#### Scenario: A publisher serves exactly what it declares

- **WHEN** each publisher's tools are listed against its declaration
- **THEN** they match, and the mutating set is among them
- **AND** `tests/test_publication.py::test_every_publisher_declares_which_of_its_tools_mutate`
  asserts it

#### Scenario: The verb list covers every writing tool

- **WHEN** the declared verbs are compared with the tools that can write
- **THEN** the verbs cover them
- **AND** `tests/test_publication.py::test_the_declared_verbs_cover_every_tool_that_can_write`
  asserts it
