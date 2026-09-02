## Purpose

The external systems that feed the retailer: what each one is and who owns it,
what it emits, how it delivers, how badly it behaves, and what connecting to or
disconnecting from one means while the application is running. It is also where
the split between an asynchronous arrival and an ordered ingestion is written
down, because that split is what lets ten independent producers race without
changing what the retailer ends up believing.

## ADDED Requirements

### Requirement: The estate is declared as data, and every system names its owner

The estate SHALL be a declared list of external systems, each carrying an
identifier, a title, the real-world owner it stands for, the kinds of event it
emits, the transport it is reached over, and a conformance profile. There SHALL
be at least ten of them.

No part of the application SHALL name a system inline. A system that has to be
mentioned by name in code is a system nobody can add.

#### Scenario: Every declared system carries an owner and a profile

- **WHEN** the estate manifest is read
- **THEN** it holds at least ten systems, every one carries a distinct
  identifier, a named owner, at least one emitted event type and a conformance
  profile, and no two systems share an identifier
- **AND** `tests/test_estate.py::test_the_manifest_declares_every_system_with_an_owner`
  asserts each

#### Scenario: The systems a run talks to come from the manifest, not from code

- **WHEN** the modules that ingest, connect and render are searched for a
  literal system identifier
- **THEN** none appears outside the manifest and its tests
- **AND** `tests/test_estate.py::test_no_system_is_named_outside_the_manifest`
  asserts the absence

### Requirement: A system delivers in batches, at intervals it chooses

A system SHALL deliver its events in batches rather than one at a time, and the
size of a batch and the interval before the next one SHALL vary. Batches from
different systems SHALL be able to overlap, so that what a reader watches is
several systems talking at once rather than a queue being drained.

A batch SHALL be written in one transaction. Ten producers against one SQLite
writer is a contention problem if each event is its own commit.

#### Scenario: Deliveries vary in size and spacing

- **WHEN** a system's delivery schedule is built from the seed
- **THEN** the batches are not all the same size, the intervals between them are
  not all equal, and every event the system owns appears in exactly one batch
- **AND** `tests/test_estate.py::test_a_system_delivers_in_batches_of_varying_size_and_spacing`
  asserts each

#### Scenario: Two systems' batches overlap in time

- **WHEN** the schedules of the whole estate are laid on one timeline
- **THEN** at least two systems have batches whose intervals overlap
- **AND** `tests/test_estate.py::test_the_estate_delivers_concurrently`
  asserts the overlap

### Requirement: Timing varies, outcomes do not

The schedule SHALL be derived from the configured seed. Two runs of the same
seed SHALL produce the same batches in the same order carrying the same events,
so that a demo rehearsed on one day behaves identically on another.

Randomness that a reader can see SHALL NOT become randomness the record can
see. Where arrival order and ingestion order differ, the recorded facts SHALL
follow ingestion order.

#### Scenario: The same seed produces the same schedule

- **WHEN** the estate's delivery schedule is built twice from the same seed
- **THEN** the two schedules are equal in batch membership, batch order and
  batch timing
- **AND** `tests/test_estate.py::test_the_same_seed_produces_the_same_schedule`
  asserts the equality

#### Scenario: Batches arriving out of order still record the same facts

- **WHEN** the same batches are delivered in one order and then, from a clean
  store, in the reverse order
- **THEN** the recorded facts, their sequence and their provenance are identical
- **AND** `tests/test_estate.py::test_arrival_order_does_not_change_the_record`
  asserts the equality

### Requirement: An arrival is recorded apart from what it means

A delivery SHALL be recorded on arrival with the system that sent it, the batch
it belonged to, the moment it landed and the defects it is known to carry.
Recording an arrival SHALL NOT interpret it: an arrival is a fact about the
integration surface, and what the payload means is decided later by the code
that ingests it.

Ingestion SHALL take arrivals in sequence order regardless of the order they
landed in.

#### Scenario: An arrival names its system, its batch and when it landed

- **WHEN** a system delivers a batch
- **THEN** each arrival carries the system identifier, a batch identifier shared
  across the batch, an arrival instant, and the sequence of the event it carries
- **AND** `tests/test_estate.py::test_an_arrival_names_its_system_batch_and_instant`
  asserts each

#### Scenario: Ingestion follows sequence, not arrival

- **WHEN** arrivals landing out of sequence order are released into ingestion
- **THEN** they are ingested in sequence order and none is dropped as already
  seen
- **AND** `tests/test_estate.py::test_ingestion_follows_sequence_not_arrival`
  asserts both

### Requirement: A system's conformance is declared, and its defects are named

Every system SHALL carry a conformance profile saying how its payloads fall
short, and every defective payload SHALL carry the named defects it was given.
A defect SHALL be one of a closed set - a missing mandatory attribute, a value
of the wrong type, a foreign vocabulary, a broken format, a stale document
version, a contradiction with a higher-precedence source, or missing required
media.

At least one system SHALL be well-behaved and at least one SHALL be unreliable,
because an estate where everything is equally suspect measures nothing.

Every defect the estate is able to stamp SHALL be one that something downstream
reports. A defect nothing detects is a claim about validation that validation
does not make.

#### Scenario: Defects come from a closed set and are stamped where introduced

- **WHEN** the estate's arrivals are inspected
- **THEN** every defect named on an arrival is a member of the declared defect
  set, and the arrival names the system that introduced it
- **AND** `tests/test_estate.py::test_every_defect_is_named_and_attributed`
  asserts both

#### Scenario: The estate spans well-behaved and unreliable systems

- **WHEN** the conformance profiles are compared
- **THEN** at least one system introduces no defects and at least one introduces
  several kinds
- **AND** `tests/test_estate.py::test_the_estate_spans_good_and_bad_citizens`
  asserts both

#### Scenario: Every stamped defect is detected by something

- **WHEN** each defect kind the estate can stamp is checked against what the
  validation surfaces report
- **THEN** every kind is reported by at least one check
- **AND** `tests/test_estate.py::test_every_stamped_defect_is_detected`
  asserts the coverage, so the answer key cannot claim a defect nothing finds

### Requirement: A system is reached over a protocol, not imported

Each system SHALL be reachable as an MCP server over a transport recorded on its
connection. A system SHALL be able to run as its own process, and reaching one
SHALL NOT require importing the module that implements it.

The estate SHALL be startable alongside the application without a container, a
broker or a second command, because a demo that needs three terminals has three
ways to fail.

#### Scenario: Every declared system exposes an MCP surface

- **WHEN** each system in the manifest is asked what tools it exposes
- **THEN** each answers with at least one tool and names the transport it was
  reached over
- **AND** `tests/test_estate.py::test_every_system_exposes_an_mcp_surface`
  asserts both
