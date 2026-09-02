## MODIFIED Requirements

### Requirement: The pending list is confirmed against the checkpoints

The list of cases awaiting a decision SHALL be confirmed against each run's
actual checkpoint rather than served from a status column alone, and SHALL carry
the material the reviewer is being shown. A run whose stored status says it is
waiting but whose checkpoint says otherwise SHALL NOT appear.

**The pending list is the queue, and every surface that reports on it SHALL read
that one list.** A count and a listing SHALL NOT be derived from separate
sources.

An approval gate that only its own author can see is not a gate. Where the queue
is held per-server and a review surface is scoped to one session's own thread
identifier, the two are each correct about their own source and disagree in
public - a badge reporting work waiting beside a screen reporting none, with the
waiting work being a decision nobody else can take. Reading one list makes that
disagreement unrepresentable rather than merely corrected.

A pending entry SHALL carry the grounds for choosing it over another: its
severity, whether review is mandatory, when it was raised, how many fields the
decision moves, and the product it concerns. A reviewer with several waiting
decisions otherwise triages by opening each one, which is a checkpoint load per
row to answer a question the list already holds.

Selecting an entry SHALL adopt that run wholly, so that a subsequent revision or
a reload follows the selected case rather than whichever run this client last
started.

#### Scenario: Only runs actually suspended appear

- **WHEN** the pending list is requested
- **THEN** each entry's run is confirmed to be awaiting approval from its
  checkpoint, and carries the material presented at the gate
- **AND** the checkpoint reading it confirms against is asserted by
  `tests/test_graph.py::test_a_run_survives_the_process_being_lost`

#### Scenario: A second person can open and decide a case they did not raise

- **WHEN** a run suspended by one client is listed and selected by another
- **THEN** the case opens with its material and its decision is available
- **AND** the resume path this rests on is asserted by
  `tests/test_graph.py::test_a_run_survives_the_process_being_lost`; the client
  behaviour is verified by use, there being no frontend test in this repository
