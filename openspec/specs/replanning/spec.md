# replanning Specification

## Purpose
Revises a live correction case against evidence that arrived after the plan was
prepared, on the same thread and the same case, so a reviewer sees a continuation
of one decision rather than a second unrelated incident - with the superseded
reading still on the table and a statement of what moved.

## Requirements

### Requirement: A revision keeps the thread and the case

A revision SHALL re-enter the same run rather than starting a new one, so the
checkpoint history stays continuous and the identity the audit trail is written
against is unchanged. It SHALL carry the case forward explicitly and SHALL NOT
re-pick one: the second pass sees a record the first pass wrote to, so a fresh
pick could walk the incident onto a different product between revisions.

#### Scenario: A revision stays on the case the run was started against

- **WHEN** a run scoped to one product reaches the gate, a clarifying document
  version lands, and the run is revised
- **THEN** it is revision one, it is still on the same case, and the surviving
  reading is that product's
- **AND** `tests/test_graph.py::test_a_replan_stays_on_the_same_case` asserts each

### Requirement: A pending approval is withdrawn as a real decision

A recommendation whose evidence has moved is not one anybody may still approve.
Where a revision is asked for while a decision is pending, the pending approval
SHALL be withdrawn through the same interrupt a reviewer uses, recorded as a
rejection by the system with decided provenance and a comment saying it was
superseded before decision - not cleared out of state, because a recommendation
that simply vanished is the one thing an audit trail exists to prevent.

#### Scenario: A correction of a correction withdraws the pending approval

- **WHEN** a run suspended at the approval gate is revised after a later document
  version lands
- **THEN** exactly one approval is recorded by the system, as a rejection, with a
  comment saying it was superseded before decision, the audit ledger holds that
  one decision with decided provenance, and nothing was committed
- **AND** `tests/test_graph.py::test_a_correction_of_a_correction_withdraws_the_pending_approval`
  asserts each

### Requirement: A revision replaces its predecessor's accumulated results

Fields that accumulate across a run SHALL be replaced on a revision rather than
appended to, so a revision does not show two revisions' readings, candidates and
citations at once. The replacement SHALL be an explicit marker at the head of an
update, and SHALL be applied once per revision at the single point where a
revision begins.

#### Scenario: The reset marker replaces rather than appends

- **WHEN** an update is applied with and without the reset marker
- **THEN** a plain update appends, an update opening with the marker replaces
  with what follows it, and a marker alone empties the field
- **AND** `tests/test_replan.py::test_reset_marker_replaces_rather_than_appends`
  asserts each

#### Scenario: Signals reset on a revision

- **WHEN** a revision's signals are merged behind the reset marker
- **THEN** only the revision's signals remain
- **AND** `tests/test_replan.py::test_signals_reset_on_a_revision` asserts it

### Requirement: The superseded readings are carried forward, deduplicated by what they do

A revision that cannot re-offer yesterday's plan is a restart, so the readings
the previous revision validated SHALL be carried into the new one, labelled as
the previous plan and naming the reading they came from, and re-scored against
what has arrived since. A carried reading SHALL be given a fresh change-set
identifier, because validation is keyed on it and reusing one would return the
previous revision's verdict against the new world. Readings SHALL be matched on
the actions they take rather than on their names, so a reading re-proposed under
a new name is not carried twice, two previous readings that do the same thing
collapse to one, and a reading that changes nothing is not carried at all.

#### Scenario: A previous reading is re-offered as the previous plan

- **WHEN** a revision carries forward a reading the fresh pass did not re-propose
- **THEN** one reading is carried, labelled as the previous plan, naming the
  reading it came from
- **AND** `tests/test_replan.py::test_previous_readings_are_carried_into_the_revision`
  asserts each

#### Scenario: A carried reading gets a fresh change-set identifier

- **WHEN** a reading is carried forward
- **THEN** its change set does not reuse the previous revision's identifier
- **AND** `tests/test_replan.py::test_a_carried_reading_gets_a_fresh_delta_id`
  asserts it

#### Scenario: Readings are deduplicated by their actions, not their names

- **WHEN** the fresh pass re-proposes the same actions under a different name, or
  two previous readings take identical actions, or a previous reading takes none
- **THEN** nothing is carried in the first case, one reading is carried in the
  second, and nothing is carried in the third
- **AND** `tests/test_replan.py::test_a_reading_re_proposed_under_a_new_name_is_not_carried_twice`,
  `test_two_previous_readings_that_do_the_same_thing_collapse` and
  `test_a_reading_that_changes_nothing_is_not_carried_forward` assert each

### Requirement: The revision reports what moved

A revision SHALL report, arithmetically rather than as narrative, which reading
led before and which leads now, the difference in each measured figure, where the
superseded reading now ranks and whether it is still publishable, and which
corrections the superseded plan had not seen. Where the recommendation is
unchanged the revision SHALL say so explicitly, because holding is a finding too
and has to be distinguishable from a move. A first plan SHALL report no
difference, having nothing to have moved from. The superseded reading SHALL be
recognised by the actions it takes, so a revision that re-proposes it under a new
identifier does not read as a move.

#### Scenario: A first plan reports no difference

- **WHEN** a difference is computed with no previous recommendation
- **THEN** nothing is reported
- **AND** `tests/test_replan.py::test_no_diff_without_a_previous_recommendation`
  asserts it

#### Scenario: The difference reports the moved figures and the new corrections

- **WHEN** a revision replaces one reading with another that scores differently
- **THEN** it is reported as a move, naming both readings, giving the arithmetic
  difference for each measured figure, listing only the correction the superseded
  plan had not seen, and stating the revision number
- **AND** `tests/test_replan.py::test_the_diff_reports_the_moved_figures` asserts
  each

#### Scenario: The difference says where the superseded reading now ranks

- **WHEN** the superseded reading is re-scored and falls to second, no longer
  publishable
- **THEN** its new rank and its publishability are both reported
- **AND** `tests/test_replan.py::test_the_diff_says_where_the_superseded_reading_now_ranks`
  asserts both

#### Scenario: A recommendation that holds says so

- **WHEN** the revision re-ranks the same reading first, including where it was
  re-proposed under a new identifier
- **THEN** the difference reports that the recommendation holds, with a headline
  saying so and no reason for a move
- **AND** `tests/test_replan.py::test_the_diff_says_so_when_the_recommendation_holds`
  and `test_the_diff_matches_the_superseded_reading_on_what_it_does` assert each

### Requirement: A revision narrows the scope once the record separates the readings

Where a later document version, together with an independent certification of the
other variant, separates two readings the earlier ambiguity had joined, the
revision SHALL stop applying the correction to the variant the record now
excludes, and SHALL report that narrowing as a move. The superseded plan SHALL
remain on the table, re-scored against the newer version.

#### Scenario: The clarification narrows the reading and the run says what changed

- **WHEN** a run whose chosen reading covered both variants is revised after a
  document version naming one of them lands
- **THEN** it is revision one, the chosen reading covers only the named variant,
  no reading still covers the other, the difference names the previous reading's
  wider scope and the figures that moved, and the superseded plan is still ranked
- **AND**
  `tests/test_graph.py::test_a_correction_of_a_correction_narrows_the_scope_and_reports_the_move`
  asserts each
