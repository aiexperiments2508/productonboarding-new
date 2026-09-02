## ADDED Requirements

### Requirement: The open-correction queue covers trouble that leaves no fact behind

The corrections in force SHALL include a value that lost a precedence contest, a
required value a document asserted empty, and a document no longer in force that
values are still standing on - as well as the moved values and refused feeds
already derived.

Each of these is a kind of trouble the estate detects and the record does not
hold as a changed value in force, so a queue derived from values alone cannot
see any of them.

**A value that lost a precedence contest SHALL be recomputed rather than
stored.** Ingestion refuses to record a row ranking below the document in force,
and it is right to - recording the loser would let a lower-ranked source quietly
beat a higher-ranked one. Both halves of the contest survive anyway: the losing
value in the event payload, and the winning value as the fact in force. The
contest SHALL be recomputed against what is in force *now*, so a row the record
later adopted, or whose document later outranked the one that beat it, stops
being reported.

**A required value asserted empty SHALL be classified as missing information by
the same predicate ingestion applies**, not by attribute path. Two copies of
that predicate would be two definitions of a gap, and the queue would disagree
with the record that filled it.

All three SHALL be derived on read and SHALL NOT be stored. Nothing then has to
be retired: a conflict the record came round to, a gap later filled and a
document later reinstated stop being reported because the record stopped saying
them, which is the only resolution rule that cannot drift out of step with the
facts.

#### Scenario: A feed row that lost a precedence contest opens a case

- **WHEN** a row is refused for ranking below the document in force
- **THEN** an open correction reports the disagreement, naming the losing value
  and the value that stands
- **AND** `tests/test_graph.py::test_a_feed_row_that_lost_a_precedence_contest_opens_a_case`
  asserts it

#### Scenario: A conflict the record came round to retires itself

- **WHEN** the record subsequently holds the value the refused row carried
- **THEN** the correction stops being reported, with nothing having retracted it
- **AND** `tests/test_graph.py::test_a_conflict_the_record_came_round_to_stops_being_open`
  asserts it

#### Scenario: A required value submitted empty is a gap, not a change

- **WHEN** a document asserts a required attribute with no value in it
- **THEN** the open correction reports missing information rather than a
  correction to what the field used to say
- **AND** `tests/test_graph.py::test_a_required_value_submitted_empty_opens_a_case_as_a_gap`
  asserts it

## MODIFIED Requirements

### Requirement: A correction a later notice settles is not an open correction

Where a later notice withdraws or resolves what an earlier one raised, the
earlier correction SHALL be retired rather than shown alongside its own
withdrawal, and the withdrawal SHALL NOT itself stand as an open correction. A
later correction on the same subject SHALL supersede an earlier one without
implying the field is now right on the page. A resolution SHALL retire only
corrections about the same subject.

**A document falling out of force is a different thing from a notice being
withdrawn, and the two SHALL be distinguished by what still stands on it.**

Retracting a revision is usually the opposite of bad news - a provisional
document pulled after the question it raised was settled - and that reading is
carried on the event itself and retires what it clears. A retraction that leaves
values *unsupported* is the opposite, and SHALL open a correction rather than
retire one.

A correction SHALL be raised only where a value in force **pins** the retracted
document version: a value that revision asserted and nothing has since replaced.
A value that merely inherits the version, or one recorded from an earlier
revision, is still supported and SHALL NOT be reported. Keying on the document
rather than the version would report every value a document ever asserted as
unsupported the moment any later revision were retracted, which is the opposite
of what a retraction means.

One correction SHALL be raised per subject rather than per attribute, because a
revision retracted under six of a variant's attributes is one piece of news
about that variant.

A correction raised this way SHALL NOT act as a resolver, so it cannot retire
the corrections it stands beside.

#### Scenario: A withdrawn notice is not an open correction

- **WHEN** a run reads a tape carrying a provisional notice and the withdrawal
  that cleared it three days later
- **THEN** the withdrawal is in the released window and the withdrawn entity
  appears in no signal the run acts on
- **AND** `tests/test_graph.py::test_a_withdrawn_notice_is_not_an_open_correction`
  asserts both

#### Scenario: A withdrawal retires what it clears and nothing else

- **WHEN** a withdrawal is merged with the correction it clears and an unrelated
  correction on another product
- **THEN** only the unrelated correction remains open
- **AND** `tests/test_graph.py::test_a_withdrawal_retires_what_it_clears` and
  `test_a_withdrawal_does_not_cancel_an_unrelated_correction` assert each

#### Scenario: An unwithdrawn notice still stands

- **WHEN** a provisional notice is merged with no resolution
- **THEN** it is unchanged
- **AND** `tests/test_graph.py::test_an_unwithdrawn_notice_still_stands` asserts it

#### Scenario: A revision supersedes without resolving

- **WHEN** a second correction to the same field on the same variant is merged
  with the first
- **THEN** only the later one remains open
- **AND** `tests/test_graph.py::test_a_revision_supersedes_but_does_not_resolve`
  asserts it

#### Scenario: Retracting a revision nothing stands on opens nothing

- **WHEN** a document version is retracted and no value in force pins it
- **THEN** no correction is raised about it
- **AND** `tests/test_graph.py::test_withdrawing_a_revision_nothing_stands_on_opens_nothing`
  asserts it

#### Scenario: Retracting a revision values stand on opens one correction

- **WHEN** a document version is retracted while values in force pin it across
  several attributes of one subject
- **THEN** one correction is raised for that subject, naming the attributes left
  unsupported, and it retires nothing
