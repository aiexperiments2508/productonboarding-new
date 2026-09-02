# event-ingestion Specification

## Purpose
Turns arriving supplier feed rows, document revisions, correspondence and
channel responses into recorded facts and correction signals exactly once,
without guessing at anything unstructured and without letting a weaker source
displace a stronger one.

## Requirements

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

### Requirement: Unstructured arrivals are not interpreted here

The arrival of a document revision or a piece of correspondence SHALL be
recorded as a structured fact about the arrival itself. Their contents SHALL NOT
be turned into attribute facts at ingestion, because reading them requires a
model and a confidence, and collapsing that split would make the provenance
distinction decorative.

#### Scenario: A document and an email write no attribute facts

- **WHEN** a document revision naming an old and a new value, and an email about
  it, are ingested
- **THEN** no correction signal is raised, the attribute's fact count is
  unchanged, and the document's new version is held as a fact
- **AND** `tests/test_ingest.py::test_documents_and_emails_write_no_attribute_facts`
  asserts each

### Requirement: Materiality is asymmetric for safety

A numeric attribute change SHALL raise a correction signal only when it moves by
more than five per cent, but **any** change to a safety-class attribute SHALL be
material regardless of size. An immaterial change SHALL still be recorded. A
required attribute arriving empty SHALL raise a data-gap signal naming a channel
that needs the field.

#### Scenario: A small numeric change is recorded without a signal

- **WHEN** a net weight arrives 2.5% below the value in force
- **THEN** no signal is raised and the new value is held
- **AND** `tests/test_ingest.py::test_an_immaterial_change_is_recorded_without_raising_a_signal`
  asserts both

#### Scenario: The same small change on a safety attribute is material

- **WHEN** the same 2.5% change arrives on an attribute marked safety-class
- **THEN** a specification-correction signal is raised naming that attribute
- **AND** `tests/test_ingest.py::test_any_change_to_a_safety_attribute_is_material`
  asserts both

#### Scenario: An empty required attribute is a data gap

- **WHEN** a required identifier arrives empty
- **THEN** a data-gap signal is raised whose summary names a channel that
  requires the field
- **AND** `tests/test_ingest.py::test_a_required_attribute_arriving_empty_is_a_data_gap`
  asserts both

### Requirement: A lower-ranked source does not displace a higher-ranked value

Where a material change arrives from a document ranked below the document behind
the value already in force, the system SHALL raise a source-conflict signal
naming both documents and the policy that settles the ranking, and SHALL leave
the value in force unchanged. Documents of equal rank SHALL be recorded normally
as a correction. A document the catalog does not know SHALL rank below every
document it does, so an unattributed value never displaces an attributed one.

#### Scenario: A portal spreadsheet does not overwrite a pack label

- **WHEN** a lower-ranked document asserts a different identifier than the one
  in force from a higher-ranked document
- **THEN** a source-conflict signal is raised naming both documents and the
  precedence policy, and the value in force is unchanged
- **AND** `tests/test_ingest.py::test_a_lower_precedence_source_does_not_overwrite_a_higher_one`
  asserts each

#### Scenario: An equal-ranked source is a correction, not a dispute

- **WHEN** a later version of the same document asserts a different value
- **THEN** a specification-correction signal is raised and the new value is held
- **AND** `tests/test_ingest.py::test_an_equal_ranked_source_is_recorded_rather_than_disputed`
  asserts both

### Requirement: A channel response is recorded on the listing and the channel

A channel rejection SHALL raise a channel-rejection signal carrying the
channel's own rejection code and the internal attribute paths behind the
channel-side field it names, and SHALL record the refused status on both the
listing and the channel. An acknowledgement SHALL record the listing as live and
raise no signal.

#### Scenario: A rejection carries its code and maps to internal paths

- **WHEN** a marketplace rejects a listing naming a channel-side field and a
  code
- **THEN** a channel-rejection signal carries that code in its value and its
  summary and names the internal attribute paths behind the field, and the
  refused status is recorded on both the listing and the channel
- **AND** `tests/test_ingest.py::test_a_channel_rejection_carries_its_code`
  asserts each

#### Scenario: An acknowledgement is recorded quietly

- **WHEN** a channel acknowledges a listing
- **THEN** no signal is raised and the listing is recorded live
- **AND** `tests/test_ingest.py::test_an_acknowledgement_is_recorded_without_raising_a_signal`
  asserts both

### Requirement: An extracted value is inferred and supersedes rather than overwrites

A value read out of prose and written back through ingestion SHALL be recorded
as an inference carrying its confidence, the document and version it was read
from, and the delivering event. A subsequent extraction naming the fact it
supersedes SHALL win the as-of read even when recorded on the same replay tick,
and both SHALL remain walkable as lineage.

#### Scenario: A re-extraction supersedes on the same tick

- **WHEN** a value is extracted at 0.72 confidence and later corrected by a
  second extraction naming the first
- **THEN** the first is held as an inference with its confidence, document
  version and event, and after the second the lineage holds both values newest
  first and the newer value is the one in force
- **AND** `tests/test_ingest.py::test_an_extracted_value_is_inferred_and_supersedes_rather_than_overwrites`
  asserts each

### Requirement: The cursor advances with the facts it writes

The ingestion cursor SHALL advance inside the same transaction as the facts of
that batch. An event at or behind the cursor SHALL NOT be processed again. A
batch that fails partway SHALL leave both the cursor and the record untouched,
so the batch is redelivered rather than silently half-applied.

#### Scenario: A redelivered event is a no-op

- **WHEN** an event is ingested and then ingested again
- **THEN** the first raises a signal and advances the cursor to that event, and
  the second raises nothing and writes no further fact
- **AND** `tests/test_ingest.py::test_the_cursor_advances_with_the_batch_and_redelivery_is_a_no_op`
  asserts each

#### Scenario: A failed batch leaves nothing behind

- **WHEN** a batch of two events fails while handling the second
- **THEN** the error propagates, the cursor is where it started, and the first
  event's fact is not in the record
- **AND** `tests/test_ingest.py::test_a_failed_batch_leaves_the_cursor_and_the_store_untouched`
  asserts each

### Requirement: Event types are dispatched by registry

Handling SHALL be dispatched from a registry keyed by event type, so that adding
a feed or a channel is a table entry rather than a further branch in a
conditional, and so a handler can be substituted for testing.

#### Scenario: A handler can be replaced at its registry entry

- **WHEN** the handler for one event type is replaced
- **THEN** ingestion of that event type uses the replacement
- **AND** `tests/test_ingest.py::test_a_failed_batch_leaves_the_cursor_and_the_store_untouched`
  substitutes a handler through the registry to exercise it

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

### Requirement: A notice outranks label artwork, and no supplier may issue one

The source precedence order SHALL carry a notice kind ranked above label
artwork, and that kind SHALL NOT be issuable by a supplier.

Artwork is the legal source for what a pack says. A notice is the legal source
for whether the pack may be sold at all. They answer different questions, and
where the two meet the second outranks the first - a correctly printed pack for
a product that has been withdrawn is still a product that has been withdrawn.

That no supplier may issue one is what keeps the ranking from being a lever a
supplier could pull to outrank artwork it does not like.

#### Scenario: A notice wins a contest against artwork

- **WHEN** a notice and label artwork assert conflicting positions on the same
  product
- **THEN** the notice is in force
- **AND** this follows from the declared precedence, which
  `tests/test_ingest.py` exercises for the ordering generally

### Requirement: The correction kinds the tape carries are the kinds the classifier offers

The kinds a correction may be classified as SHALL be one table, read by both the
generator that writes the tape and the classifier that reads it. Every kind the
classifier's prompt offers SHALL be one that exists.

Two copies of a vocabulary agree until they are asked about something neither
was written against, and then both are correct about their own copy while the
system as a whole is wrong.

#### Scenario: One table, and no kind offered that does not exist

- **WHEN** the generator's kinds and the classifier's are compared, and the
  prompt's offered kinds are checked
- **THEN** they are one table and every offered kind exists
- **AND** `tests/test_golden.py::test_the_two_kind_tables_are_the_same_table` and
  `::test_every_kind_the_prompt_offers_is_a_kind_that_exists` assert both

### Requirement: A reference lane carries data that can never become a product fact

Reference data - stock snapshots, campaigns, certificate registers, trading
terms - SHALL arrive as events from systems the estate manifest declares, on a
lane of its own.

That lane SHALL be invisible to the transport, which SHALL NOT count it towards
replay progress; SHALL NOT be announced on the live feed, because nothing has
happened that a person needs to see; and SHALL be skipped by the ingestion
handlers **by construction** rather than by a filter that could be forgotten at
a new call site.

**No reference event SHALL become a product fact, and no readiness verdict SHALL
change because a reference pack was loaded.** This is the load-bearing
requirement of the whole reference lane: four of the graph's domains have no
source data and are therefore invented, and a verdict moved by invented
warehouse data would be indefensible.

Reference payloads SHALL name no product the arrival window would count, and
SHALL carry no conformance defect.

The pack SHALL be byte-identical for a given seed, SHALL be idempotent on
reload, and its absence SHALL NOT be an error.

#### Scenario: A reference event never reaches the fact store

- **WHEN** a reference pack is loaded and the record is read
- **THEN** no product fact came from it and every readiness verdict is unchanged
- **AND** `tests/test_kg_data.py::test_no_reference_event_becomes_a_product_fact`
  and `::test_a_readiness_verdict_is_unchanged_by_the_reference_pack` assert both

#### Scenario: The transport does not see the lane

- **WHEN** the transport's progress is read with a reference pack loaded
- **THEN** the lane is not counted
- **AND** `tests/test_kg_data.py::test_the_reference_lane_is_invisible_to_the_transport`
  asserts it

#### Scenario: Reference payloads do not enter the arrival window

- **WHEN** the arrival window is computed
- **THEN** no reference payload names a product it would count
- **AND** `tests/test_kg_data.py::test_reference_payloads_name_no_product_the_window_would_count`
  asserts it

#### Scenario: Every reference event still lands as an arrival, undefected

- **WHEN** the pack is loaded
- **THEN** each event is recorded as an arrival and none carries a conformance
  defect
- **AND** `tests/test_kg_data.py::test_every_reference_event_lands_as_an_arrival`
  and `::test_nothing_in_the_pack_is_stamped_with_a_defect` assert both

#### Scenario: The pack is reproducible, idempotent and optional

- **WHEN** the pack is generated twice, loaded twice, and then removed
- **THEN** the two are byte-identical, the second load changes nothing, and its
  absence is not an error
- **AND** `tests/test_kg_data.py::test_the_reference_pack_is_byte_identical_for_a_seed`,
  `::test_loading_the_pack_twice_changes_nothing` and
  `::test_a_missing_pack_is_not_an_error` assert each

#### Scenario: Every condition the insights look for is planted and named

- **WHEN** the pack is generated
- **THEN** it carries a lapsing certificate cohort, stock that cannot lawfully
  ship, and cross-sell pairs sharing more than one campaign, each named
- **AND** `tests/test_kg_data.py::test_the_certificate_register_has_a_lapsing_cohort`,
  `::test_stock_sits_where_it_cannot_lawfully_ship`,
  `::test_cross_sell_pairs_share_more_than_one_campaign` and
  `::test_every_planted_condition_is_named` assert each
