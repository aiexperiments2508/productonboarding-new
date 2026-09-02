## MODIFIED Requirements

### Requirement: Every tool belongs to exactly one toolset

No tool SHALL appear on two toolsets, because overlap makes "which system owns
this" unanswerable. Every tool a toolset declares as mutating SHALL be a tool
that toolset actually exposes, and every declared tool SHALL resolve to its own
toolset when its owner is looked up. A tool nothing declares SHALL resolve to
unknown rather than to a guess.

A toolset MAY be discovered from a connected external system rather than
declared in the application. A discovered toolset SHALL be owned by the system
that declared it and SHALL be listed beside the built-in ones rather than merged
into them.

A discovered tool SHALL NOT shadow a built-in tool of the same name. Where the
names collide the built-in SHALL win, the collision SHALL be reported, and the
discovered tool SHALL remain reachable only under its own system. A connected
system quietly redefining the tool that commits a plan is precisely the failure
the partition exists to prevent.

#### Scenario: No tool is on two toolsets

- **WHEN** every toolset's tools are collected
- **THEN** no tool appears twice, and the failure would name both toolsets
- **AND** `tests/test_protocols.py::test_every_tool_belongs_to_exactly_one_toolset`
  asserts it

#### Scenario: A declared mutating tool is one the toolset exposes

- **WHEN** each toolset's mutating declarations are checked against its tools
- **THEN** every mutating tool is among them
- **AND** `tests/test_protocols.py::test_mutating_tools_are_declared_and_belong_to_their_toolset`
  asserts it

#### Scenario: Owner lookup covers every declared tool

- **WHEN** every declared tool's owner is looked up, and then an undeclared name
- **THEN** each tool resolves to its own toolset and the undeclared name resolves
  to unknown
- **AND** `tests/test_protocols.py::test_owner_lookup_covers_every_declared_tool`
  asserts both

#### Scenario: A discovered toolset is listed beside the built-in ones

- **WHEN** a system is connected and the combined listing is read
- **THEN** the built-in toolsets are present and unchanged, the discovered one
  appears beside them naming its system as owner, and each is labelled with
  where it came from
- **AND** `tests/test_connections.py::test_a_discovered_toolset_is_listed_beside_the_built_in_ones`
  asserts each

#### Scenario: A discovered tool does not shadow a built-in one

- **WHEN** a connected system declares a tool whose name a built-in toolset
  already uses
- **THEN** the built-in remains the owner of that name, the collision is
  reported on the connection, and the discovered tool is reachable only through
  its own system
- **AND** `tests/test_connections.py::test_a_discovered_tool_does_not_shadow_a_built_in_one`
  asserts each

### Requirement: A transport is off unless it is asked for, and never load-bearing

Both the tool transport and peer delegation SHALL be off by default and SHALL be
read per call rather than captured once, so the switch can be changed without a
restart. A tool with no route SHALL still run in-process rather than failing.

The transport a toolset is reached over SHALL be a property of its connection
rather than a property of the application, so that a spawned module and a
remote endpoint can be in use at the same time. Adding a transport SHALL NOT
change what any tool returns.

A connected system that stops answering SHALL degrade rather than fail: the
connection SHALL be marked degraded, any lookup routed to it SHALL fall back to
the in-process implementation where one exists, and the run SHALL continue. No
external system SHALL be load-bearing for a correction run.

#### Scenario: The tool transport is off unless asked for

- **WHEN** the switch is absent, then set on, then set off
- **THEN** the transport reports disabled, enabled and disabled in turn
- **AND** `tests/test_protocols.py::test_transport_is_off_unless_asked_for` asserts
  each

#### Scenario: Peer delegation is off unless asked for

- **WHEN** the delegation switch is absent and then set
- **THEN** delegation reports disabled and then enabled
- **AND** `tests/test_protocols.py::test_delegation_is_off_unless_asked_for` asserts
  both

#### Scenario: An unrouted tool still runs

- **WHEN** the transport is enabled and a tool with no route is called
- **THEN** it runs in-process with the arguments it was given and returns its
  result
- **AND** `tests/test_protocols.py::test_an_unrouted_tool_still_runs` asserts both

#### Scenario: Two transports are in use at once without disagreeing

- **WHEN** one toolset is reached over a spawned module and another over an HTTP
  endpoint, and the same lookup is made through each
- **THEN** both answer, each call is recorded with the transport it actually
  used, and the answers match what the in-process implementations return
- **AND** `tests/test_connections.py::test_two_transports_are_in_use_at_once_without_disagreeing`
  asserts each

#### Scenario: A system that stops answering degrades the connection, not the run

- **WHEN** a connected system becomes unreachable and a lookup it owns is made
- **THEN** the connection is marked degraded, the lookup returns the in-process
  answer, the fallback is recorded, and the run completes
- **AND** `tests/test_connections.py::test_an_unreachable_system_degrades_rather_than_failing`
  asserts each
