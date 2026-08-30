# protocol-surfaces Specification

## Purpose
The toolsets and peers this system publishes to other systems - which surface
owns which tool, what may be reached across a wire and what may not, and the
property both transports exist to preserve: that delegating a piece of work never
changes the answer it produces.

## Requirements

### Requirement: Every tool belongs to exactly one toolset

No tool SHALL appear on two toolsets, because overlap makes "which system owns
this" unanswerable. Every tool a toolset declares as mutating SHALL be a tool
that toolset actually exposes, and every declared tool SHALL resolve to its own
toolset when its owner is looked up. A tool nothing declares SHALL resolve to
unknown rather than to a guess.

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

### Requirement: The mutating surface is one named server

Exactly one toolset SHALL be able to change what a channel sees, so an operator
can hand out the read-only surfaces and withhold that one. The one permitted
exception is the event plane's tape control, which moves the clock and never the
catalog. No read-only toolset SHALL expose publication or rollback.

#### Scenario: Only the publishing toolset writes

- **WHEN** the toolsets that declare mutating tools are listed
- **THEN** the publishing toolset is among them, the product catalog, channel
  registry, content store and knowledge base are not, and once the tape control
  is set aside the publishing toolset is the only writer left
- **AND** `tests/test_protocols.py::test_the_dangerous_surface_is_one_named_server`
  asserts each

#### Scenario: Publication is unreachable from a read-only toolset

- **WHEN** each read-only toolset's tools are examined
- **THEN** neither publication nor rollback is among them
- **AND** `tests/test_protocols.py::test_commit_is_not_reachable_from_a_read_only_toolset`
  asserts both

### Requirement: Only read-only tools cross the wire

The routing table SHALL contain no mutating tool. Publishing to a channel over a
pipe that might have died halfway is worse than publishing in-process, and the
approval gate is not something to put a transport underneath. Every routed tool
SHALL name a toolset that exists and SHALL be a tool that toolset exposes.

#### Scenario: No mutating tool is routed

- **WHEN** the routing table is compared with every declared mutating tool
- **THEN** the two do not intersect
- **AND** `tests/test_protocols.py::test_only_read_only_tools_are_routed_over_the_wire`
  asserts it

#### Scenario: Every route names a real toolset and a real tool

- **WHEN** each route is resolved
- **THEN** the named toolset exists and exposes the routed tool
- **AND** `tests/test_protocols.py::test_every_routed_tool_names_a_real_toolset`
  asserts both

### Requirement: A transport is off unless it is asked for, and never load-bearing

Both the tool transport and peer delegation SHALL be off by default and SHALL be
read per call rather than captured once, so the switch can be changed without a
restart. A tool with no route SHALL still run in-process rather than failing.

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

### Requirement: The peers are split at real seams, and the approval gate is not one

The peer roster SHALL be exactly the four kinds of work another team could own
and replace independently: walking the lineage, enumerating candidate readings,
validating one deterministically, and rewriting affected copy. Neither the
approval gate nor publication SHALL be a peer - a human decision is not a
capability to delegate, and a peer that could publish is a peer that could
publish. Every peer SHALL declare a skill a caller could discover: an identifier,
a name, a description of substance, and example prompts.

#### Scenario: The roster is exactly the four seams

- **WHEN** the peer roster is read
- **THEN** it is the lineage analyst, the resolution planner, the validator and
  the copywriter
- **AND** `tests/test_protocols.py::test_peers_are_split_at_real_seams` asserts it

#### Scenario: No peer approves or publishes

- **WHEN** the roster is searched for an approver or a publisher
- **THEN** none is found
- **AND** `tests/test_protocols.py::test_the_approval_gate_is_not_a_peer` asserts it

#### Scenario: Every peer publishes a discoverable skill

- **WHEN** each peer's declaration is read
- **THEN** it carries a skill identifier and name, a description of more than
  thirty characters, and at least one example prompt
- **AND** `tests/test_protocols.py::test_every_peer_declares_a_skill_a_caller_could_discover`
  asserts each

### Requirement: A peer's address follows the port the server is on

The address advertised for a peer SHALL follow the port the server is actually
running on, and SHALL be overridable outright. A card advertising the wrong port
is a card nothing can call.

#### Scenario: The advertised address tracks the port, and an override wins

- **WHEN** the port is set with no override, and then an override is set
- **THEN** the address names that port, and then the override with any trailing
  separator removed
- **AND** `tests/test_protocols.py::test_base_url_follows_the_port_the_server_is_on`
  asserts both

### Requirement: A degraded peer falls back rather than failing

Where a peer cannot be reached, the work SHALL be done by the in-process handler
and the failure SHALL be recorded rather than swallowed, so a peer that stops
answering costs a log line and not a correction run. A peer retired after a
failure SHALL be given another chance when the transport is reset, so fixing the
configuration does not require a restart.

#### Scenario: An unreachable peer is answered in-process and the failure recorded

- **WHEN** delegation is enabled against an address where nothing listens and the
  validator peer is called
- **THEN** the in-process handler answers with a full result, and the call record
  shows that peer's call failed
- **AND** `tests/test_protocols.py::test_a_degraded_peer_falls_back_rather_than_failing`
  asserts both

#### Scenario: Reviving clears the degraded set

- **WHEN** a peer has been retired after a failure and the transport is reset
- **THEN** the degraded set is empty again
- **AND** `tests/test_protocols.py::test_reviving_clears_the_degraded_set` asserts
  it

### Requirement: Delegating does not change the answer

A peer SHALL return, for the same input, exactly what the in-process tool
returns - the same reproducibility hash, the same measures and the same
publishability. An interoperability demonstration that changed the numbers would
be showing two implementations rather than one capability with two front doors.

#### Scenario: The validator peer is the validator

- **WHEN** the same change set is validated through the peer handler and through
  the in-process tool
- **THEN** the reproducibility hash, the measures and the publishability are
  identical
- **AND** `tests/test_protocols.py::test_the_validator_peer_is_the_validator`
  asserts each

### Requirement: The copywriter peer works without a gateway and refuses an ambiguous literal

The copy peer's own implementation SHALL be deterministic, so that the factory
still produces publishable copy from the catalog alone and another team's
brand-voice model can replace the handler without changing the contract. It SHALL
substitute a corrected value where the record can say which occurrence is which,
SHALL rebuild a channel feed row under that channel's own field name, and SHALL
flag a claim the corrected value no longer supports before the copy is written.
Where the record cannot say which occurrence a value belongs to, it SHALL leave
the text unchanged, report the reference it could not place, and carry the
values it could not place with it so the model picking the work up is handed the
table rather than asked to recall it.

#### Scenario: Copy is rewritten from the catalog with no gateway

- **WHEN** the copy peer is asked to rewrite against a corrected wattage
- **THEN** the marketplace title carries the new figure and not the old, the feed
  row is rebuilt under the channel's own field name, and the claim the new value
  no longer supports is flagged
- **AND** `tests/test_protocols.py::test_the_copywriter_works_without_a_gateway`
  asserts each

#### Scenario: An ambiguous literal is refused rather than guessed

- **WHEN** the copy peer meets a comparison table quoting both variants at the
  same figure
- **THEN** the text is left unchanged, the reference it could not place is
  reported, and the value it could not place travels with the row
- **AND** `tests/test_protocols.py::test_the_copywriter_refuses_an_ambiguous_literal`
  asserts each
