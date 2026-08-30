## Purpose

Turns arriving supplier feed rows, document revisions, correspondence and
channel responses into recorded facts and correction signals exactly once,
without guessing at anything unstructured and without letting a weaker source
displace a stronger one.

## ADDED Requirements

### Requirement: A structured feed row becomes an observed fact

An attribute row arriving on a structured feed SHALL be recorded as an observed
fact carrying the value, the source document pinned at the version that asserted
it, the identifier of the event that delivered it, and a recording instant taken
from the event rather than from wall-clock time. A material change SHALL also
raise a correction signal.

#### Scenario: A feed row is recorded with its document and event

- **WHEN** an attribute row arrives on a supplier feed
- **THEN** the value is held as an observed fact, its source names the document
  at the version that asserted it, its note names the delivering event, its
  recording instant is the event's, and one specification-correction signal is
  raised
- **AND** `tests/test_ingest.py::test_a_feed_row_becomes_a_recorded_fact_naming_document_and_event`
  asserts each

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
