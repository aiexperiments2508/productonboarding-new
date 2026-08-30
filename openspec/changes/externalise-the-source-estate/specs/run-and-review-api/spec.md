## ADDED Requirements

### Requirement: Connections are listed, added and removed through the API

The connected systems SHALL be readable as a list carrying, for each, its
identifier, its owner, the transport it is reached over, its state, when it was
last heard from, and the tools it declared. A system SHALL be connectable by
address alone, and disconnectable by identifier.

Connecting SHALL perform a real handshake and record what the system answered,
rather than trusting the address. A system that cannot be reached SHALL be
recorded as degraded with the reason, and SHALL NOT prevent the call from
returning.

#### Scenario: A system is connected by address and reports what it can do

- **WHEN** a system is connected by address
- **THEN** the connection is recorded with its transport and state, the tools it
  declared are listed against it, and the listing includes it
- **AND** `tests/test_connections.py::test_a_system_is_connected_by_address_and_reports_its_tools`
  asserts each

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
- **AND** `tests/test_connections.py::test_topology_changes_are_emitted_once_each`
  asserts both

#### Scenario: The stream and the list agree

- **WHEN** the estate is changed several times and the list is read afterwards
- **THEN** the list matches the state the stream's messages describe
- **AND** `tests/test_connections.py::test_the_topology_stream_and_the_listing_agree`
  asserts the equality
