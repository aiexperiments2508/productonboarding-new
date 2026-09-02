## MODIFIED Requirements

### Requirement: A run reports what it spent and how long each step took

Model spend SHALL be recorded per stage rather than as one accumulator, so that
concurrent writers do not erase one another, and a stage that reached no model
SHALL report no spend at all. Every trace line SHALL carry the time taken to
reach it, so that "which step is slow" is answerable from the run's own artefact.

Where a stage makes several model calls concurrently, their spend SHALL merge
within that stage to the same totals the calls would have produced one after
another, and a gateway outage that every one of them meets SHALL be reported
once rather than once per call. An accumulator that is correct under one worker
and wrong under six is not a smaller bug for being harder to see.

#### Scenario: A stage records what its model calls cost

- **WHEN** a classification stage runs against a reachable gateway
- **THEN** it reports one call with its prompt, completion and total tokens, its
  cost and its cache hit, keyed under that stage's name
- **AND** `tests/test_graph.py::test_a_node_records_what_its_model_calls_cost`
  asserts the whole record

#### Scenario: Spend is keyed by stage so one writer does not erase another

- **WHEN** two stages each record spend and the records are merged
- **THEN** each stage's calls, tokens, cost and cache hits are summed within that
  stage, and both stages survive the merge
- **AND** `tests/test_graph.py::test_spend_is_keyed_by_node_so_one_writer_does_not_erase_another`
  asserts each

#### Scenario: Spend inside one stage survives its calls being made at once

- **WHEN** a stage's model calls are made concurrently and their spend is folded
  back into the stage's record
- **THEN** the calls, tokens, cost and cache hits total what the same calls made
  in sequence would have totalled, and no call is lost or counted twice
- **AND** `tests/test_graph.py::test_spend_within_a_stage_survives_concurrent_workers`
  asserts each

#### Scenario: One outage is reported once, however many calls met it

- **WHEN** a stage's concurrent model calls all fail against an unreachable
  gateway
- **THEN** the stage reports the outage as a single error line and every field
  it could not reach a model for falls back deterministically
- **AND** `tests/test_graph.py::test_a_gateway_outage_is_reported_once_however_many_workers_meet_it`
  asserts both

#### Scenario: Every trace line says how long it took

- **WHEN** a run completes
- **THEN** every trace line carries a non-negative elapsed time and the run as a
  whole took more than none
- **AND** `tests/test_graph.py::test_every_trace_line_says_how_long_it_took`
  asserts each

## ADDED Requirements

### Requirement: Independent model work within a stage may be done at once

Where a stage makes several model calls that do not read one another's results,
it MAY make them concurrently. Doing so SHALL NOT change what the stage
produces: the actions, the trace line, the recorded values and the validation
trace hash SHALL be identical to those the same stage produces making the same
calls one after another.

Results SHALL be assembled in the order of the work rather than the order the
replies arrived. Ordering by completion is not a tie-break that is usually
right, it is a different answer on a fast network.

The number of calls in flight SHALL be bounded, and the bound SHALL be reducible
to one. A concurrent implementation whose serial case is unreachable cannot be
compared against the thing it replaced.

#### Scenario: Rewriting fields at once produces what rewriting them in turn did

- **WHEN** the same correction is regenerated with one worker and with several
- **THEN** the proposed actions, their order, the rewritten text, the citations
  and the trace hash of the validated result are identical
- **AND** `tests/test_graph.py::test_parallel_regeneration_matches_the_sequential_result`
  asserts the equality

#### Scenario: The reply that arrives first does not become the first result

- **WHEN** a stage's concurrent calls return in an order other than the order
  they were issued in
- **THEN** the assembled result follows the order of the targets, not the order
  of the replies
- **AND** `tests/test_graph.py::test_results_follow_the_targets_not_the_replies`
  asserts the ordering

### Requirement: A stage that threads a value through its work keeps that work in order

Where a stage's steps read a value the previous step wrote, those steps SHALL
run in sequence. Reading a document against a recorded instant that a later
document's writes have already advanced is the difference between recording a
correction and recording it twice.

Such a stage MAY still make its model calls concurrently, because a reading of
a document depends on the catalog and the document alone. The concurrency SHALL
be confined to the part that reads, and the part that writes SHALL proceed in
the order the events arrived on the tape.

#### Scenario: Documents are persisted in tape order however their readings raced

- **WHEN** several supplier documents are read concurrently and then persisted
- **THEN** they are persisted in tape order, each against the recorded instant
  the previous one advanced to, and a covering email restating the
  specification it accompanies still records nothing new
- **AND** `tests/test_graph.py::test_extraction_persists_in_tape_order_however_its_readings_raced`
  asserts both
