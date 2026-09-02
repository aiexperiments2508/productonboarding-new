# correction-pipeline Specification

## Purpose
Drives one arriving correction from the record and the unread supplier documents
through to a recommendation a reviewer signs - narrowing to a single case,
resolving which variants are meant, rewriting the content built on the old
value, and stopping at an approval gate that nothing downstream can route
around. It is also where a model is invited in, and therefore where the bounds
on a model are written down.

## Requirements

### Requirement: A run reaches a recommendation and an approval gate with no model available

Every stage that consults a model SHALL catch gateway failure and produce a
deterministic answer instead, so a complete run - reading the correction,
classifying it, resolving scope, planning, validating, propagating, rewriting
and recommending - SHALL finish and suspend for a human decision with no model
reachable. A stage that ran without a model SHALL say so rather than presenting
its fallback as a model's conclusion.

#### Scenario: The run suspends at the approval gate

- **WHEN** a run is started against a released correction with the gateway
  pinned to a closed port
- **THEN** the run is awaiting approval, its next step is the approval request,
  and its status says so
- **AND** `tests/test_graph.py::test_run_stops_at_the_approval_gate` asserts all
  three

#### Scenario: The correction is read out of the documents without a model

- **WHEN** the same run completes
- **THEN** corrections have been read out of the supplier documents, including a
  specification correction and an allergen change, and the run records that it
  could not reach the gateway
- **AND** `tests/test_graph.py::test_the_correction_is_read_without_a_model`
  asserts the signals, the kinds and the recorded error

#### Scenario: Every leg of the pipeline runs

- **WHEN** the same run completes
- **THEN** the trace shows the monitoring, extraction, classification, scope
  resolution, candidate planning, validation, ranking, propagation, claim
  scanning, regeneration, enrichment, final validation and recommendation stages
  all having run
- **AND** `tests/test_graph.py::test_every_leg_of_the_pipeline_runs` asserts each

#### Scenario: A stage that fell back reports no spend

- **WHEN** a classification stage runs with no gateway reachable
- **THEN** it reports no model spend at all, and records an error saying it ran
  blind
- **AND** `tests/test_graph.py::test_a_node_that_fell_back_records_no_spend`
  asserts both

### Requirement: A model may not originate a figure, a verdict or a decision

Every figure in a recommendation SHALL come from a validation pass over the
change set being recommended, and a recommendation SHALL name only a candidate
that was actually validated. A severity SHALL be escalated by measurement over
whatever a classifier concluded. The obligation to seek review SHALL be
recomputed from the change set at the gate rather than read from state.

#### Scenario: The recommendation quotes only validated figures

- **WHEN** a run reaches its recommendation
- **THEN** the recommendation's measures are exactly those of the ranked
  candidate it names, and its publishability is that candidate's
- **AND** `tests/test_graph.py::test_the_recommendation_quotes_validated_figures`
  asserts both

#### Scenario: A safety-class attribute or a regulated product is escalated by rule

- **WHEN** a run covers a correction to a safety-class attribute
- **THEN** the severity is the highest, the correction is material, and the
  stated reason says it was escalated by policy and names the safety class
- **AND** `tests/test_graph.py::test_the_safety_override_forces_critical` asserts
  each

#### Scenario: The gate recomputes the review obligation rather than trusting it

- **WHEN** a recommendation arrives at the gate carrying a review obligation
  explicitly set to false, over a change set that withholds a channel
- **THEN** the gate reports that review is required and names the ground
- **AND**
  `tests/test_graph.py::test_the_gate_recomputes_the_obligation_rather_than_trusting_it`
  asserts both

### Requirement: Review is required on measured grounds, and only on them

Review SHALL be required whenever a safety-class attribute moved, a regulated
product is affected, a channel is withheld, or a safety declaration is open on
the change set - each ground stated in words a reviewer can read. A change set
carrying none of those grounds SHALL NOT require review. The grounds SHALL be
carried to the reviewer, not merely held in state.

#### Scenario: Each measured ground requires review on its own

- **WHEN** a change set moves a safety-class attribute, or affects a regulated
  product, or withholds a channel
- **THEN** review is required in each case and the stated ground names the
  safety class, the regulated product or the safety hold respectively
- **AND**
  `tests/test_graph.py::test_review_is_required_on_every_measured_ground`
  asserts each of the three separately

#### Scenario: An open safety declaration requires review

- **WHEN** a routine change set is accompanied by an open allergen-declaration
  violation
- **THEN** a ground is stated naming that open declaration
- **AND**
  `tests/test_graph.py::test_an_open_safety_declaration_also_requires_review`
  asserts it

#### Scenario: A routine correction does not require review

- **WHEN** a change set sets one non-safety attribute on one variant with no
  violations
- **THEN** no ground is stated and review is not required
- **AND** `tests/test_graph.py::test_a_routine_correction_does_not_require_review`
  asserts both

#### Scenario: The reviewer is shown the obligation, not just the state

- **WHEN** a run reaches the approval gate
- **THEN** the recommendation requires review and states its grounds, and the
  material presented to the reviewer carries the identical grounds
- **AND**
  `tests/test_graph.py::test_the_run_reaches_the_gate_carrying_its_review_obligation`
  asserts each

### Requirement: With nothing to narrow it, a correction is read at its widest

Where no model is available to argue a narrower reading, the correction SHALL be
applied to every variant the record puts in scope, at the widest scope level,
with a low confidence and a rationale saying no model was available. A candidate
reading SHALL NOT span two products, and a reading that does SHALL be refused
with a reason a reviewer can read rather than dropped silently.

#### Scenario: The fallback reading is the widest, not the narrowest

- **WHEN** a notice naming a product and no variant is resolved with no gateway
  reachable
- **THEN** the reading covers every variant of that product at the widest scope
  level, holds more than one variant, and its rationale says no model was
  available
- **AND**
  `tests/test_graph.py::test_the_scope_fallback_is_the_widest_reading_not_the_narrowest`
  asserts each

#### Scenario: No reading holds another product's variants

- **WHEN** a run's candidate readings are examined
- **THEN** every reading's entities belong to exactly one product
- **AND** `tests/test_graph.py::test_a_scope_never_holds_another_products_variants`
  asserts it for every candidate

#### Scenario: A reading spanning two products is refused with its reason

- **WHEN** a reading naming variants of two different products is offered
- **THEN** it is refused with a reason saying another product's variants cannot
  be put in scope
- **AND**
  `tests/test_graph.py::test_a_reading_spanning_two_products_is_refused_with_its_reason`
  asserts the reason

### Requirement: A run decides one correction case and reports the others

A correction case SHALL be one product, because that is the unit a publish lock
is taken on and therefore the unit a reviewer commits. A run SHALL act on the
signals of one case only, and SHALL report every other case still open - with
its signal identifiers, its safety flag and its title, and without the signal
bodies - so that a correction never becomes invisible because this run is not
about it. A correction that cannot be attributed to a product SHALL be reported
as its own unscoped case rather than dropped. Where no case was named, the run
SHALL take the worst one open and say in its trace which it took. Cases SHALL be
ordered safety first, then regulated, then oldest, then identifier, and that
order SHALL NOT depend on the order the signals arrived in.

#### Scenario: A scoped run changes only its own product and reports the rest

- **WHEN** a run is started against a named product's case
- **THEN** every signal it acts on resolves to that product, every recommended
  change names that product or one of its variants, and the other product's
  correction is reported as still open with its signal identifiers, its safety
  flag and no signal bodies
- **AND**
  `tests/test_graph.py::test_a_scoped_run_decides_one_product_and_reports_the_rest`
  asserts each

#### Scenario: A run with no case named takes the worst one open

- **WHEN** a run is started with no case named against a record holding an
  allergen case and a specification case
- **THEN** it takes the allergen case, reports the other as open, acts only on
  the chosen case's signals, and names the chosen case once in its trace
- **AND** `tests/test_graph.py::test_a_run_with_no_case_named_takes_the_worst_one_open`
  asserts each

#### Scenario: A correction naming no product is still on the list

- **WHEN** a signal names only a channel and a document
- **THEN** it resolves to no product and is grouped into the unscoped case,
  which carries its identifier and an empty product
- **AND** `tests/test_graph.py::test_a_correction_that_names_no_product_is_not_dropped`
  asserts each

#### Scenario: Cases are ordered worst first, whatever order they arrived in

- **WHEN** a specification correction, an allergen change and a channel rejection
  are grouped into cases, and then grouped again in a different order
- **THEN** the safety case comes first in both, carries the highest severity
  hint, and outranks a case whose correction is three days older
- **AND** `tests/test_graph.py::test_cases_are_ordered_worst_first_and_deterministically`
  asserts each

### Requirement: Extraction is global, action is case-scoped

Reading a supplier document SHALL NOT depend on which case a run is deciding: a
document is read once and its facts are recorded whatever case is running, so a
run that skipped one would leave the case nobody has decided yet unreadable.
Narrowing to a case SHALL therefore be applied after reading rather than before
it, and no signal outside the case SHALL reach the classification, the severity
sentence, the scope resolution or the approval grounds.

#### Scenario: A scoped run is not contaminated by the documents it reads

- **WHEN** a run is started against a named case over a record where every
  correction is still sitting in an unread document
- **THEN** the run is scoped to that case, every signal it acts on resolves to
  that product, no other product's identifier appears in its severity sentence,
  and the other case is reported as open with its signal identifiers
- **AND** the allergen fact from the other product's document is on the record
  even though nothing in this run acted on it
- **AND**
  `tests/test_graph.py::test_a_scoped_run_is_not_contaminated_by_the_documents_it_reads`
  asserts each

### Requirement: Nothing publishes before a reviewer decides

No content SHALL reach a channel before a decision is recorded. A human decision
SHALL be recorded with decided provenance and the actor who made it; a
publication SHALL be recorded with committed provenance. A rejection SHALL close
the run with nothing published.

#### Scenario: A run at the gate has published nothing

- **WHEN** a run reaches the approval gate
- **THEN** there are no committed actions, no publish entry in the audit ledger,
  and no published facts
- **AND** `tests/test_graph.py::test_nothing_publishes_before_a_decision` asserts
  each

#### Scenario: A decision is distinguishable from an inference

- **WHEN** a reviewer approves a suspended run
- **THEN** exactly one decision is recorded, with decided provenance and the
  reviewer as actor, and the publication that follows is recorded with committed
  provenance
- **AND** `tests/test_graph.py::test_a_decision_is_recorded_with_decided_provenance`
  and `test_a_publish_is_recorded_with_committed_provenance` assert each

#### Scenario: A rejection closes the run without publishing

- **WHEN** a reviewer rejects a suspended run with a comment
- **THEN** the decision is recorded as a rejection and there are no committed
  actions
- **AND** `tests/test_graph.py::test_rejection_closes_the_run_without_publishing`
  asserts both

### Requirement: A run survives the process being lost, and a redelivered decision publishes once

A run suspended for a decision SHALL be recoverable from its checkpoint alone,
with no in-memory state, and SHALL still carry its recommendation. A decision
delivered twice SHALL publish once. The checkpoint history SHALL be readable,
newest first, with every entry naming the checkpoint it can be resumed from.

#### Scenario: A run waiting overnight is still there in the morning

- **WHEN** every in-memory object is dropped and the run is read back from its
  checkpoint
- **THEN** it is still awaiting approval, still carries its recommendation, and
  approving it still publishes
- **AND** `tests/test_graph.py::test_a_run_survives_the_process_being_lost`
  asserts each

#### Scenario: Resuming twice publishes once

- **WHEN** the same approval is delivered a second time
- **THEN** the number of committed actions and published facts is unchanged
- **AND** `tests/test_graph.py::test_resuming_twice_publishes_once` asserts both

#### Scenario: The checkpoint history is available for time travel

- **WHEN** the history of a suspended run is read
- **THEN** it holds more than three entries, one of them the approval-gate
  state, and every entry names a checkpoint
- **AND** `tests/test_graph.py::test_checkpoint_history_is_available_for_time_travel`
  asserts each

### Requirement: A publish overtaken while its approval was pending re-plans rather than failing

Where a publish is refused because a later source version is now in force, or
because it lost its publish lock, the run SHALL plan again against what is now
true and return to the approval gate, clearing the previous attempt's verdicts
so that options scored before and after the race never share a comparison table.
The cycle SHALL be bounded: once the retry budget is spent the run SHALL close
with the unresolved status rather than looping. A run that published SHALL NOT
re-enter the cycle.

#### Scenario: A later source version refuses the publish and the run re-plans

- **WHEN** a later document version lands on every variant in scope between
  approval and write, and the reviewer approves
- **THEN** the publish is refused as a stale version, nothing is committed, one
  retry is spent, and the run is back at the approval gate
- **AND**
  `tests/test_graph.py::test_publish_is_refused_once_a_later_source_version_is_in_force`
  asserts each

#### Scenario: A refused publish clears the previous attempt's verdicts

- **WHEN** a publish is refused for a lost lock, or for a later source version
- **THEN** the run is routed back to planning and the accumulated validation
  results are replaced rather than added to
- **AND** `tests/test_branches.py::test_a_lost_publish_lock_re_plans_and_clears_the_old_verdicts`
  and `test_a_later_source_version_spends_one_retry` assert each

#### Scenario: The second retry is a queue, not a recovery

- **WHEN** a publish is refused again with the retry budget already spent
- **THEN** the run takes the unresolved status, does not clear its results, and
  is routed to close
- **AND** `tests/test_branches.py::test_a_second_retry_is_a_queue_not_a_recovery`
  asserts each

#### Scenario: A published run does not re-enter the cycle

- **WHEN** a completed publication is verified
- **THEN** the terminal status is left alone and the run is routed to close
- **AND** `tests/test_branches.py::test_a_published_run_does_not_re_enter_the_cycle`
  asserts both

### Requirement: Routing is a pure function of state

The same state SHALL always route to the same destination, because the audit
trail and the reproducibility of a run depend on it. The pipeline SHALL branch
at no fewer than six points, and SHALL carry a route for each of: an immaterial
correction, a disagreement between sources, a resemblance to a past incident,
nothing publishable, and a publish that must be attempted again.

#### Scenario: The same state routes the same way twenty times over

- **WHEN** each router is called repeatedly on one state carrying a source
  conflict, competing readings, a prior incident, ranked candidates, a
  recommendation and a re-planning status
- **THEN** every call returns the same destination
- **AND** `tests/test_branches.py::test_routing_is_deterministic` asserts it for
  each of the five routers

#### Scenario: The topology has not collapsed back to a line

- **WHEN** the compiled pipeline is inspected
- **THEN** at least six nodes have conditional outgoing edges, and the precedent,
  supplier-question, blocked-review, publish-verification and park routes are all
  present
- **AND** `tests/test_branches.py::test_the_graph_actually_branches` asserts both

#### Scenario: The approval gate can reach both outcomes and the retry cycle exists

- **WHEN** the compiled pipeline's edges are inspected
- **THEN** the approval step can reach both publication and closure, publication
  reaches verification, and verification can reach planning again
- **AND** `tests/test_branches.py::test_the_approval_gate_can_reach_both_outcomes`
  and `test_the_publish_conflict_cycle_exists` assert each

### Requirement: The exception routes are additive, not terminal

A question sent to a supplier and a precedent drawn from a past incident SHALL
both rejoin the main line, because a supplier who has been asked a question has
not answered it yet while the wrong figure is still live. Where both hold, the
question SHALL outrank the reading material. A correction with no candidate at
all, and one where nothing is publishable, SHALL still reach a reviewer as a
finding rather than stranding the run.

#### Scenario: A disagreement outranks a postmortem, and both rejoin

- **WHEN** a run carries both an open source conflict and a matched prior
  incident
- **THEN** it is routed to the supplier question; with only the prior incident it
  is routed to the precedent; with neither it is routed straight to planning
- **AND** both exception routes rejoin the planning step and the blocked review
  rejoins the recommendation
- **AND** `tests/test_branches.py::test_a_disagreement_outranks_a_postmortem` and
  `test_both_scope_exceptions_rejoin_the_main_line` assert each

#### Scenario: An immaterial correction is parked rather than propagated

- **WHEN** a correction has been classified immaterial
- **THEN** it is routed to be acknowledged and parked; a material one goes on to
  scope resolution
- **AND** `tests/test_branches.py::test_immaterial_corrections_are_parked_not_propagated`
  asserts both

#### Scenario: A correction with no candidate still reaches a reviewer

- **WHEN** planning produced no candidate at all
- **THEN** the run is routed onward to ranking rather than stranded, and a run
  with nothing publishable is routed to the blocked review
- **AND** `tests/test_branches.py::test_a_correction_with_no_candidate_still_reaches_a_reviewer`
  and `test_nothing_publishable_goes_to_the_blocked_review` assert each

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

### Requirement: A document that cannot be read does not end a run

Where a document arrives as a reference rather than as text, the extracted text
SHALL be read from where the record says it is kept. Where the text cannot be
had - the reference names a revision the stored text is not, the document has no
stored text, the catalog does not know it, or the file is missing - the run SHALL
degrade to whatever the arrival itself carried rather than failing. Feeding one
revision's text to another revision's notice SHALL NOT happen, because that
would have the run extract superseded values as though they were the correction.

#### Scenario: A document arriving as a reference is read from where it is kept

- **WHEN** a notice arrives naming a document and version with no inline body
- **THEN** the document's text is returned and the record names the path it was
  read from
- **AND** `tests/test_graph.py::test_a_document_with_no_inline_body_is_read_from_disk`
  asserts both

#### Scenario: Four ways of failing to read all degrade rather than raise

- **WHEN** the notice names a revision the stored text is not, or a document with
  no stored text, or a document the catalog never heard of, or the stored text is
  missing from disk
- **THEN** each returns empty rather than raising, and the run continues
- **AND** `tests/test_graph.py::test_reading_from_disk_never_breaks_a_run` asserts
  all four

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
