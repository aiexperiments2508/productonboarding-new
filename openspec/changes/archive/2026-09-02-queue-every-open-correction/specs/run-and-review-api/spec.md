## MODIFIED Requirements

### Requirement: The open correction cases are listable, and a run is started against one

The cases open at the replay clock SHALL be listable, worst first, with the
instant they were read at. A run SHALL accept the case to be decided; omitting it
SHALL NOT mean "look at everything" - the run still takes one coherent case.

**The list SHALL be re-derived on every read.** Nothing about a case is stored,
so a case the record has resolved disappears without anything having to retract
it, and a case a run *opened* - by reading a document nobody had examined - is
visible on the next read rather than waiting to be noticed.

That property is what makes the list safe to work through in a loop: a caller
may start a run against each open case in turn, re-reading the list between
runs, and each run stops at its own approval gate. Reaching an approval gate is
a success for such a sweep and not a reason to stop, because the queue of
decisions is the point.

#### Scenario: The case list is the pipeline's own grouping

- **WHEN** the open cases are requested
- **THEN** they are the cases the pipeline derives from the facts in force at the
  replay clock, in the same order, with that instant reported
- **AND** the grouping and the ordering are asserted by
  `tests/test_graph.py::test_cases_are_ordered_worst_first_and_deterministically`
  and `test_a_correction_that_names_no_product_is_not_dropped`

#### Scenario: A run is scoped to the case it was started against

- **WHEN** a run is started naming a case
- **THEN** the run decides that case and reports the others still open
- **AND** `tests/test_graph.py::test_a_scoped_run_decides_one_product_and_reports_the_rest`
  asserts the behaviour the route passes through

#### Scenario: A case the record resolved leaves the list without being retracted

- **WHEN** the record comes to hold the value a refused row carried, and the
  list is read again
- **THEN** that case is gone, and nothing retracted it
- **AND** `tests/test_graph.py::test_a_conflict_the_record_came_round_to_stops_being_open`
  asserts the derivation the route reports
