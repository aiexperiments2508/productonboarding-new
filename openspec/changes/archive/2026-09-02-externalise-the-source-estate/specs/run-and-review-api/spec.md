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
