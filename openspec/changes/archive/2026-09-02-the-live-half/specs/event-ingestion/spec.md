## ADDED Requirements

### Requirement: A second lane carries what arrives now, told apart by a column

Events arriving from outside the process SHALL be held on their own lane,
distinguished by a column and never by a sequence range.

A sequence range is walked into by arithmetic, and two failures made that
concrete - both of which **report success**:

* the transport's advance had no upper bound, so the cursor would walk out of
  the recording and into the high band, and the transport would report having
  replayed everything;
* ingestion kept a single watermark, which a live event would push past every
  remaining recorded event - so ingestion would stop writing facts and report
  success.

The replay cursor SHALL NOT be able to enter the live lane, a jump aimed at a
live event SHALL land at the end of the recording, and ingestion SHALL keep its
watermark per lane.

A live event SHALL be judged by the same ingestion, under the same precedence
policy, materiality threshold and safety override as a recorded one. It SHALL
NOT be part of the recording: rewinding, reloading and backfilling the tape
SHALL all leave it alone.

#### Scenario: The cursor cannot walk into the live lane

- **WHEN** the transport is advanced past the end of the recording, and when a
  jump names a live event
- **THEN** the cursor stops at the end of the recording in both cases
- **AND** `tests/test_live_lane.py::test_the_replay_cursor_cannot_walk_into_the_live_lane`
  and `::test_jumping_to_a_live_event_lands_on_the_end_of_the_recording` assert
  both

#### Scenario: A live event does not poison the recorded lane's watermark

- **WHEN** a live event is ingested while recorded events remain unread
- **THEN** the recorded lane's cursor is unmoved and those events are still
  ingested
- **AND** `tests/test_live_lane.py::test_a_live_event_does_not_poison_the_tape_ingest_cursor`
  asserts it

#### Scenario: The transport cannot retract a submission

- **WHEN** the tape is reset, reloaded, or backfilled
- **THEN** submissions are untouched in each case
- **AND** `tests/test_live_lane.py::test_resetting_the_tape_does_not_retract_a_submission`,
  `::test_reloading_the_tape_does_not_delete_a_submission` and
  `::test_the_backfill_leaves_submissions_alone` assert each

#### Scenario: A submission is visible before the cursor reaches it

- **WHEN** a submission arrives ahead of the replay cursor
- **THEN** it is readable immediately
- **AND** `tests/test_live_lane.py::test_a_submission_is_visible_before_the_cursor_reaches_it`
  asserts it

### Requirement: A live arrival carries the simulated clock without moving it

A submission SHALL be stamped with the simulated clock rather than the wall
clock, and SHALL NOT advance it. Two submissions made at one paused instant
SHALL NOT tie.

The progress denominator SHALL count only the recorded flight, and the
simulated clock SHALL stop at the end of the recording. A live arrival is not
progress through a recording, and counting it as such would make the transport
report more than a hundred per cent replayed.

A submission SHALL be attributed to the endpoint it arrived through, and SHALL
carry no conformance defect - a defect is something an external system's
delivery is stamped with, and there is no such stamp on something a person just
typed.

The live sink SHALL be told what landed and what it raised, and a failing sink
SHALL NOT fail the submission.

#### Scenario: The simulated clock is carried, not moved

- **WHEN** a submission is made
- **THEN** it carries the simulated instant, the clock does not advance, and a
  second submission at the same paused instant does not tie with it
- **AND** `tests/test_live_lane.py::test_a_submission_carries_the_simulated_clock_not_the_wall_clock`,
  `::test_a_submission_does_not_move_the_simulated_clock` and
  `::test_two_submissions_at_one_paused_instant_do_not_tie` assert each

#### Scenario: Progress counts the recording only

- **WHEN** submissions are made and the transport's progress is read
- **THEN** the denominator counts the recorded flight alone, and the clock stops
  at its end
- **AND** `tests/test_live_lane.py::test_the_progress_denominator_counts_only_the_recorded_flight`
  and `::test_the_clock_stops_at_the_end_of_the_recording` assert both

#### Scenario: A submission is attributed and unstamped

- **WHEN** a submission arrives through an intake endpoint
- **THEN** it names that endpoint and carries no conformance defect
- **AND** `tests/test_live_lane.py::test_a_submission_is_attributed_to_the_endpoint_it_arrived_through`
  and `::test_no_defect_is_stamped_on_a_submission` assert both

#### Scenario: The sink hears what happened and cannot break the submission

- **WHEN** a submission is ingested with a sink attached, and again with a
  failing one
- **THEN** the sink is told what landed and what it raised, and the failing sink
  does not fail the submission
- **AND** `tests/test_live_lane.py::test_the_live_sink_is_told_what_landed_and_what_it_raised`
  and `::test_a_failing_sink_does_not_fail_the_submission` assert both
