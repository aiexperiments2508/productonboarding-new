# bitemporal-record Specification

## Purpose
Holds what is true about a product attribute, what the system believed about it
at any past instant, and on whose authority - so a correction that arrives late
never rewrites the record it replaces, and a decision taken on Monday can be
defended on Monday's evidence.

## Requirements

### Requirement: Two independent time axes

Every recorded fact SHALL carry a validity interval saying when the assertion is
true in the world, and a recording instant saying when this system learned it.
A read SHALL be answerable for any pair of those instants independently.

#### Scenario: A correction is invisible to a question asked before it arrived

- **WHEN** a value is recorded, then corrected days later, and the record is
  read for the same world instant with the recording instant set before the
  correction landed
- **THEN** the read returns the original value, and the same read with the
  recording instant set after the correction returns the corrected value
- **AND** `tests/test_bitemporal.py::test_correction_is_invisible_before_it_arrives`
  asserts both readings

#### Scenario: A fact not yet in force is not yet an answer

- **WHEN** a fact is recorded today with a validity interval that opens next
  week, and the record is read for today
- **THEN** no fact is returned, and a read for a world instant inside the
  interval returns it
- **AND** `tests/test_bitemporal.py::test_valid_window_excludes_facts_not_yet_in_force`
  asserts both readings

#### Scenario: A closed validity interval stops applying

- **WHEN** a fact is recorded with a closing bound and the record is read for a
  world instant after that bound
- **THEN** no fact is returned, while a read inside the interval returns the
  value
- **AND** `tests/test_bitemporal.py::test_closed_window_stops_applying` asserts
  both readings

### Requirement: The greatest recording instant wins

Among the facts whose validity interval covers the asked-for world instant and
whose recording instant is at or before the asked-for recording instant, the
system SHALL return the one with the greatest recording instant. Ties SHALL be
broken deterministically so that repeated reads of an unchanged store agree.

#### Scenario: The latest of several corrections is the answer

- **WHEN** a value has been corrected twice, at two different recording instants
- **THEN** a read taken between the two corrections returns the first
  correction, and a read taken after both returns the second
- **AND** `tests/test_bitemporal.py::test_latest_correction_wins_among_several`
  asserts both readings

#### Scenario: A bulk read returns one winning row per entity and attribute

- **WHEN** the record holds a superseded value, its correction, and an unrelated
  entity's value, and all facts of that entity type are read as of one pair of
  instants
- **THEN** exactly one fact is returned per entity and attribute, carrying the
  winning value, and no superseded row appears beside its winner
- **AND** `tests/test_bitemporal.py::test_get_many_returns_one_winning_row_per_entity_attr`
  asserts the count and the values

### Requirement: A correction inserts rather than updates

A correction SHALL be written as a new fact naming the fact it supersedes. The
system SHALL NOT update or delete the superseded row. A correction SHALL inherit
the superseded fact's validity interval unless the caller overrides it.

#### Scenario: A correction inherits the window it corrects

- **WHEN** a fact with both an opening and a closing validity bound is corrected
  without a new interval being given
- **THEN** the corrected fact carries the same opening and closing bounds
- **AND** `tests/test_bitemporal.py::test_correction_inherits_validity_window_unless_overridden`
  asserts both bounds

### Requirement: Correction lineage is walkable

The system SHALL be able to walk a fact back through every value it superseded,
to the original assertion, returning each step's value and provenance in order
from newest to oldest.

#### Scenario: The chain returns every value and its provenance

- **WHEN** a value has been corrected twice and the lineage of the newest fact
  is requested
- **THEN** the three values are returned newest first, each with the provenance
  kind it was recorded under
- **AND** `tests/test_bitemporal.py::test_lineage_walks_back_to_the_original`
  asserts the value order and the provenance order

### Requirement: Late arrivals are enumerable

The system SHALL be able to list the facts that superseded something and were
recorded after a given instant, so a run already in flight can be told its
evidence has moved.

#### Scenario: A correction recorded after the watermark is surfaced

- **WHEN** a correction is recorded and the corrections since an earlier instant
  are requested
- **THEN** that correction is returned, and the same request made from an
  instant after it returns nothing
- **AND** `tests/test_bitemporal.py::test_corrections_since_surfaces_late_arrivals`
  asserts both results

### Requirement: Provenance kinds are kept distinct

Every fact SHALL carry exactly one provenance kind from a closed set of five -
an observation from a source system or document, a model or heuristic
conclusion, a human decision, a validator output, and a value published to a
channel - together with the source it came from and, where the value was
concluded rather than observed, a confidence. The system SHALL be able to report
how many facts it holds of each kind, counted separately and never merged.

#### Scenario: Two facts of different kinds are counted apart

- **WHEN** one observed fact and one concluded fact are recorded and the
  provenance mix is requested
- **THEN** the report shows one of each kind rather than a total of two
- **AND** `tests/test_bitemporal.py::test_provenance_kinds_are_counted_separately`
  asserts the mix
