## MODIFIED Requirements

### Requirement: A structured feed row becomes an observed fact

An attribute row arriving on a structured feed SHALL be recorded as an observed
fact carrying the value, the source document pinned at the version that asserted
it, the identifier of the event that delivered it, and a recording instant taken
from the event rather than from wall-clock time. A material change SHALL also
raise a correction signal.

The fact SHALL additionally name the external system the row came from. Which
supplier asserted a value and which system carried it are different questions,
and a record that answers only the first cannot say that two systems owned by
the same supplier disagreed.

Where the arrival carrying the row was stamped with conformance defects, those
defects SHALL be recorded against the fact rather than discarded, so that a
value known to have arrived malformed is not indistinguishable from one that
arrived clean.

#### Scenario: A feed row is recorded with its document and event

- **WHEN** an attribute row arrives on a supplier feed
- **THEN** the value is held as an observed fact, its source names the document
  at the version that asserted it, its note names the delivering event, its
  recording instant is the event's, and one specification-correction signal is
  raised
- **AND** `tests/test_ingest.py::test_a_feed_row_becomes_a_recorded_fact_naming_document_and_event`
  asserts each

#### Scenario: A recorded fact names the system that carried it

- **WHEN** the same attribute is delivered by two different external systems
- **THEN** each recorded fact names the system that carried it, and the two are
  distinguishable on that field alone
- **AND** `tests/test_ingest.py::test_a_recorded_fact_names_the_system_that_carried_it`
  asserts both

#### Scenario: A defect stamped on arrival survives into the record

- **WHEN** a row arrives on a delivery stamped with a conformance defect
- **THEN** the recorded fact carries that defect, and a row that arrived clean
  carries none
- **AND** `tests/test_ingest.py::test_a_defect_stamped_on_arrival_survives_into_the_record`
  asserts both
