## MODIFIED Requirements

### Requirement: The replay clock is driven through one command route

Starting, pausing, stepping, changing speed, jumping, rewinding and clearing the
event tape SHALL all be one command, and every event the command releases SHALL
be ingested and broadcast before the response is returned. A jump with no
destination SHALL go to the correction the demonstration turns on.

**Rewinding the recording and retracting a supplier's submission SHALL be
different commands.** A rewind SHALL unrelease the recorded flight and SHALL
leave the live lane untouched, because moving the clock is not a reason to
withdraw something a supplier sent. Clearing SHALL be the deliberate act: it
SHALL remove the events that arrived through a supplier portal, the arrivals
that carried them, the submission records over them, and the proposals nobody
had answered.

Both commands SHALL clear the per-consumer cursors, and the live consumer's
cursor SHALL NOT be optional on a clear. Live sequence numbers restart at their
base once the rows are gone, so a cursor left at the old high-water mark would
silently discard every subsequent submission as already-seen - ingestion would
stop and report success, which is the exact failure a per-lane cursor exists to
prevent.

A clear SHALL leave the facts those submissions recorded, SHALL leave decisions
a person has taken and values already written unattended, and the surface
offering the command SHALL state that it does. Clearing the tape and retracting
a fact are different acts; the second needs supersession, and a control that
quietly did both would be a control nobody could reason about.

#### Scenario: A jump releases, ingests and reports

- **WHEN** the tape is jumped to a sequence
- **THEN** the released events are ingested, the resulting corrections are
  broadcast individually, and the response reports the replay state, how many
  events were released, and the correction sequence
- **AND** this is verified by inspection of the route body; the ingestion it
  calls is asserted by `tests/test_ingest.py`

#### Scenario: A jump with no destination goes to the correction

- **WHEN** a jump is requested with no destination
- **THEN** the tape advances to the sequence at which the correction is injected
- **AND** this is verified by inspection of the route body

#### Scenario: Clearing removes the portal traffic and rewinds the tape

- **WHEN** the tape is cleared after a supplier has pushed a submission through
  a portal
- **THEN** the recording is rewound and the portal events, their arrivals and
  their submission records are gone
- **AND** `tests/test_live_lane.py::test_clearing_removes_the_portal_traffic_and_rewinds_the_tape`
  asserts it

#### Scenario: A clear leaves the facts the submission recorded

- **WHEN** the tape is cleared after a submission has recorded facts
- **THEN** those facts are still in force
- **AND** `tests/test_live_lane.py::test_clearing_leaves_the_facts_a_submission_recorded`
  asserts it

#### Scenario: A submission after a clear is still ingested

- **WHEN** a supplier submits again after a clear
- **THEN** the submission is ingested rather than discarded as already-seen
- **AND** `tests/test_live_lane.py::test_a_submission_after_a_clear_is_still_ingested`
  asserts it

#### Scenario: A clear does not let a later submission lose to a surviving fact

- **WHEN** a submission arrives after a clear against an attribute a surviving
  fact still holds
- **THEN** the later submission wins the as-of read rather than tying and losing
  by identifier
- **AND** `tests/test_live_lane.py::test_a_clear_does_not_let_a_later_submission_tie_with_a_surviving_fact`
  asserts it

#### Scenario: Open questions go and answered ones stay

- **WHEN** the tape is cleared with both an undecided and a decided proposal
  outstanding
- **THEN** the undecided proposal is removed and the decided one is kept, so a
  reviewer's own past decisions survive a rewind
- **AND** `tests/test_live_lane.py::test_clearing_takes_the_open_questions_and_leaves_the_answered_ones`
  asserts it
