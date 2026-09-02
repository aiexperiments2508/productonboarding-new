# run-and-review-api Specification

## Purpose
The HTTP contract over the correction factory: reading the catalog and what a
correction touches, listing the cases open, starting and watching a run,
delivering a reviewer's decision, revising a plan, driving the replay clock, and
reading back the audit trail and the bitemporal record.

## Requirements

### Requirement: The API is a thin layer over the functions the pipeline calls

Every read the API serves SHALL be produced by the same function the pipeline
itself calls, rather than by a second implementation. Two implementations of one
read become two accounts of the same state the first time either is edited.

#### Scenario: The catalog reads are the pipeline's own reads

- **WHEN** the catalog map, the blast radius of an entity, the variant table, the
  derivation of an entity, a channel's rules or a listing's state is requested
- **THEN** the answer is the one the corresponding catalog function produces,
  whose behaviour is asserted by `tests/test_propagation.py`
- **AND** this is verified by inspection of the route bodies; no route-level test
  exists - see tasks 5.2

#### Scenario: An unknown identifier is a client error, not a stack trace

- **WHEN** the variant table is requested for a product that does not exist, or a
  corpus document is requested that does not exist
- **THEN** the response is a 404 naming what was not found
- **AND** the underlying not-found answers are asserted by
  `tests/test_propagation.py::test_an_unknown_product_is_an_error_not_an_exception`

#### Scenario: A change-set route with no change set is refused

- **WHEN** the validate route is called with no change set, or the comparison
  route with no change sets
- **THEN** the response is a 400 naming the missing field
- **AND** this is verified by inspection of the route bodies

### Requirement: The graph diagram is read out of the pipeline that runs

The topology the console draws SHALL be read from the compiled pipeline rather
than from a hard-coded picture, so the diagram cannot drift from what actually
executes, and SHALL mark which edges are conditional. It SHALL NOT require an
external service to render, because the system must be demonstrable on a
restricted network.

#### Scenario: The topology is the compiled pipeline's own

- **WHEN** the topology is requested
- **THEN** it names every node and edge of the compiled pipeline, each edge
  flagged for whether it is conditional
- **AND** the compiled topology it reads is asserted by
  `tests/test_branches.py::test_the_graph_actually_branches` and
  `test_the_publish_conflict_cycle_exists`

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

### Requirement: A run and a revision are streamed as the pipeline's own progress

A run and a revision SHALL each be available as a stream that emits one message
per completed stage, opening with the identity of the run and closing with its
final state, so what a reader watches is the pipeline's own progress rather than
a progress bar imitating it. A failure inside the stream SHALL be delivered as a
message on that stream rather than by dropping the connection.

#### Scenario: The stream opens, reports each stage, and closes with the result

- **WHEN** a run is started on the streaming route
- **THEN** the first message names the run, one message follows per completed
  stage, and the last carries the run's final state including whether it is
  awaiting approval
- **AND** this is verified by inspection of the route body; the underlying
  per-stage stream is the pipeline's own

#### Scenario: A failure mid-stream is a message, not a dropped connection

- **WHEN** the pipeline raises while a run is streaming
- **THEN** an error message is emitted on the stream and the stream is closed
  normally
- **AND** this is verified by inspection of the route body

### Requirement: A run's state is readable with what it spent

The checkpointed state of a run SHALL be readable by thread, together with a
total of the model spend that run recorded. The total SHALL be summed on read
from the per-stage records rather than stored, because spend is written per stage
so that concurrent writers do not erase one another and a stored total would be a
second figure to keep in step with the first. The checkpoint history SHALL be
readable separately.

#### Scenario: The run state carries a spend total summed from its stages

- **WHEN** the state of a run is requested
- **THEN** it carries the checkpointed values and a total holding the calls,
  prompt, completion and total tokens, cache hits, cost and the number of stages
  that spent anything
- **AND** the per-stage records the total is summed from are asserted by
  `tests/test_graph.py::test_spend_is_keyed_by_node_so_one_writer_does_not_erase_another`
  and `test_a_node_records_what_its_model_calls_cost`

#### Scenario: The checkpoint history is readable

- **WHEN** the history of a run is requested
- **THEN** it returns the run's checkpoints, newest first, each naming the
  checkpoint it can be resumed from
- **AND** `tests/test_graph.py::test_checkpoint_history_is_available_for_time_travel`
  asserts the history the route serves

### Requirement: A decision is delivered through one route and one closed set of decisions

A reviewer's decision SHALL be accepted only as approve, reject or modify;
anything else SHALL be a 400 naming the three. The decision SHALL carry the actor
and may carry a comment, and SHALL be delivered into the suspended run rather
than acted on beside it, so the recorded provenance and the audit trail are the
pipeline's own.

#### Scenario: An unrecognised decision is refused

- **WHEN** a decision other than approve, reject or modify is delivered
- **THEN** the response is a 400 naming the three permitted decisions
- **AND** this is verified by inspection of the route body

#### Scenario: A delivered decision is recorded by the pipeline, not by the route

- **WHEN** an approval is delivered
- **THEN** the decision is recorded with decided provenance and the actor, and
  the publication that follows with committed provenance
- **AND** `tests/test_graph.py::test_a_decision_is_recorded_with_decided_provenance`
  and `test_a_publish_is_recorded_with_committed_provenance` assert both

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

### Requirement: A revision is its own route and refuses where there is nothing to revise

Revising a plan SHALL be a distinct request against a run's thread, carrying the
reason. Where the thread has no run, or no recommendation to revise, the request
SHALL be refused as a conflict rather than silently starting something new.

#### Scenario: Revising a thread with nothing to revise is a conflict

- **WHEN** a revision is requested for a thread with no run, or with no
  recommendation yet
- **THEN** the response is a 409 carrying the reason
- **AND** this is verified by inspection of the route body and the refusal it
  translates

#### Scenario: A revision returns the difference the pipeline computed

- **WHEN** a revision succeeds
- **THEN** the response carries the revision number and the statement of what
  moved
- **AND** `tests/test_replan.py::test_the_diff_reports_the_moved_figures` and
  `tests/test_graph.py::test_a_correction_of_a_correction_narrows_the_scope_and_reports_the_move`
  assert what the route returns

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

### Requirement: The record is readable on both time axes

A fact read SHALL accept both time axes independently, so "what did the content
team know when they wrote this" is answerable separately from "what is true", and
both SHALL default to the replay clock rather than to wall-clock time. A single
value's correction chain SHALL be readable by identifier. The audit ledger SHALL
be readable newest first with its detail and provenance decoded.

#### Scenario: Both axes default to the replay clock

- **WHEN** facts are requested with neither axis given
- **THEN** both the valid and the recorded instant are the replay clock
- **AND** this is verified by inspection of the route body; the bitemporal
  behaviour it exposes is asserted by
  `tests/test_bitemporal.py::test_correction_is_invisible_before_it_arrives` and
  `test_get_many_returns_one_winning_row_per_entity_attr`

#### Scenario: A value's correction chain is readable

- **WHEN** the lineage of a fact is requested
- **THEN** the chain of assertions that superseded one another is returned
- **AND** the chain is asserted by
  `tests/test_bitemporal.py::test_lineage_walks_back_to_the_original`

### Requirement: The governance surfaces are served from the governance in force

The evidence allowlist, the toolset partition and the peer roster SHALL each be
rendered from the structure that actually governs them rather than from a
separate description, so what is claimed on screen cannot drift from what is
enforced. Both transports SHALL be switchable at runtime without a restart,
because the switch is read per call.

#### Scenario: The allowlist served is the allowlist enforced

- **WHEN** the evidence tools are requested
- **THEN** the response carries the pass and per-pass limits and one entry per
  allowlisted tool, with what it takes and what it answers
- **AND** the allowlist it is rendered from is asserted by
  `tests/test_replan.py::test_every_allowlisted_tool_is_read_only` and
  `test_the_catalogue_offered_to_the_model_matches_the_allowlist`

#### Scenario: The toolset partition served is the registry that defines it

- **WHEN** the toolsets are requested
- **THEN** the response is the registry's own description, with each toolset's
  owner, tools, mutating tools and read-only flag, plus the transport state
- **AND** the partition it renders is asserted by
  `tests/test_protocols.py::test_the_dangerous_surface_is_one_named_server`

#### Scenario: A transport is switched without a restart

- **WHEN** either transport is switched on or off through its route
- **THEN** the next tool call or delegation takes the new setting and the route
  reports the new state
- **AND** the per-call reading this depends on is asserted by
  `tests/test_protocols.py::test_transport_is_off_unless_asked_for` and
  `test_delegation_is_off_unless_asked_for`

### Requirement: The peers are mounted at import and never prevent the app starting

The peer endpoints and their discovery cards SHALL be mounted when the
application is imported, so another organisation's agent can discover and call
them whether or not this deployment has delegation switched on - discovery and
delegation are different switches. A failure to mount SHALL be logged and SHALL
NOT prevent the application from starting.

#### Scenario: Mounting failure degrades to no peers, not to no application

- **WHEN** the peer mount raises at import
- **THEN** the roster is empty, a warning is logged, and the application still
  starts and serves every other route
- **AND** this is verified by inspection of the mount guard

### Requirement: The console is served without shadowing an API route

The built console SHALL be mounted after every API route, so its catch-all can
never shadow one. Where no console has been built the application SHALL still
start and SHALL say how to build one rather than failing.

#### Scenario: An API path is served by the API, not by the console catch-all

- **WHEN** any API path is requested with a console build present
- **THEN** the API route answers it, and only unmatched paths fall through to the
  console
- **AND** this is verified by inspection of the mount order

#### Scenario: With no console built the application still starts

- **WHEN** the root is requested with no console build present
- **THEN** the response says the console is not built and points at the API
- **AND** this is verified by inspection of the fallback route

### Requirement: The variant table carries the document behind every value

The variant table SHALL return, for a product, its variants with their listings,
the attribute table across those variants, and the attributes they disagree on
named separately. Each cell SHALL be the one the catalog tool itself produces -
the value together with the source document, that document's version, the
provenance kind and the confidence - and SHALL NOT be flattened to a bare value.

The document is the argument, not decoration. The base-versus-variant case rests
on the base model having been independently certified by a named document a
fortnight before an ambiguous correction named the product and not the variant,
and a reviewer cannot check that against a number on its own. Flattening the cell
silently disabled the evidence line that carries the whole argument, and made
this route and the catalog tool disagree about the same table.

#### Scenario: Each cell carries the document it stands on

- **WHEN** the variant table is requested for a product whose base model has been
  independently certified and whose other variant has been corrected by a
  different document
- **THEN** each cell carries its value, version, source document, provenance kind
  and confidence, and the differing attributes are named separately
- **AND** `tests/test_propagation.py::test_the_variants_endpoint_serves_the_document_the_value_stands_on`
  asserts the route's own cells, the differing list and the listings it adds,
  and `test_variant_diff_shows_the_document_each_value_stands_on` and
  `test_variant_diff_marks_exactly_the_attributes_that_differ` assert the cells
  the route passes through unchanged

#### Scenario: An unknown product is a 404

- **WHEN** the variant table is requested for a product that does not exist
- **THEN** the response is a 404 carrying the reason
- **AND** the underlying error is asserted by
  `tests/test_propagation.py::test_an_unknown_product_is_an_error_not_an_exception`

### Requirement: Connections are listed, added and removed through the API

The connected systems SHALL be readable as a list carrying, for each, its
identifier, its owner, the transport it is reached over, its state, when it was
last heard from, and the tools it declared. A system SHALL be connectable by
address alone, and disconnectable by identifier.

Connecting SHALL perform a real handshake and record what the system answered,
rather than trusting the address. A system that cannot be reached SHALL be
recorded as degraded with the reason, and SHALL NOT prevent the call from
returning.

#### Scenario: One address is one connection record, whatever it answered

- **WHEN** a system is connected by address, and then connected again at the
  same address
- **THEN** the connection is recorded with its transport and state, and the
  listing holds one record for that address carrying the later answer
- **AND** `tests/test_connections.py::test_connecting_the_same_address_twice_updates_one_record`
  and `::test_disconnecting_then_reconnecting_leaves_one_connection` assert both

#### Scenario: The tools a system declared are listed against it

- **WHEN** a connected system has declared what it can do
- **THEN** its toolset appears in the listing beside the built-in ones, labelled
  as connected and carrying the tools it declared
- **AND** `tests/test_connections.py::test_a_discovered_toolset_is_listed_beside_the_built_in_ones`
  asserts each

The handshake against an address that answers is not covered by a test. The
connection suite runs with nothing listening anywhere, deliberately - the happy
path needs a server and the failure path needs to not need one - so what the
suite exercises is the degraded path below.

#### Scenario: An address that cannot be reached is recorded, not raised

- **WHEN** a system is connected at an address nothing answers
- **THEN** the call returns, the connection is recorded as degraded with the
  reason, and no exception reaches the caller
- **AND** `tests/test_connections.py::test_an_unreachable_address_is_recorded_not_raised`
  asserts each

#### Scenario: Disconnecting removes the connection and keeps the record

- **WHEN** a connected system is disconnected by identifier
- **THEN** it leaves the connected listing, the facts it delivered remain
  readable, and reconnecting it restores it without duplicating anything
- **AND** `tests/test_connections.py::test_disconnecting_then_reconnecting_leaves_one_connection`
  asserts each

### Requirement: Topology changes are readable as a stream

A change to the estate - a system connecting, disconnecting, degrading or
recovering - SHALL be emitted on a stream, so that a reader watching the map
sees it without asking again. Each message SHALL name the system and what
happened to it.

The stream SHALL be a view of the connection records rather than a second
account of them, so a reader that missed a message and re-reads the list
arrives at the same picture.

#### Scenario: Connecting and disconnecting each emit one message

- **WHEN** a system is connected and then disconnected while the stream is open
- **THEN** one message names it as connected and one names it as disconnected,
  in that order
- **AND** this is verified by inspection of the two route bodies, each of which
  publishes once; no test covers the message count directly

#### Scenario: The stream and the list agree

- **WHEN** the estate is changed several times and the list is read afterwards
- **THEN** the list matches the state the stream's messages describe
- **AND** `tests/test_connections.py::test_the_topology_stream_and_the_listing_agree`
  asserts the equality

### Requirement: Products are searchable, readable and assessable through the API

A search route SHALL accept a SKU, an internal identifier or words from a name
and return matching variants. A record route SHALL return one product's merged
record. An assessment route SHALL return its findings and verdict. A preview
route SHALL return the staging page for a ready record and refuse otherwise.

Every one of these SHALL be produced by the same functions the rest of the
system calls, rather than by a second implementation. Two implementations of one
read become two accounts of the same product the first time either is edited.

#### Scenario: The API's product reads are the same reads

- **WHEN** the product routes are inspected against the functions they call
- **THEN** each delegates rather than re-deriving its answer
- **AND** `tests/test_product360.py::test_the_api_product_reads_are_the_pipelines_own`
  asserts the delegation

#### Scenario: A search with no match answers empty rather than failing

- **WHEN** a search route is called with a term nothing matches
- **THEN** it returns an empty result set with status 200
- **AND** `tests/test_product360.py::test_a_search_with_no_match_is_empty_not_an_error`
  asserts both

#### Scenario: A preview of an unready product is refused with its reasons

- **WHEN** the preview route is called for a product that is not ready
- **THEN** it refuses and the response carries the verdict and the findings
- **AND** `tests/test_preview.py::test_the_preview_route_refuses_an_unready_product`
  asserts both
