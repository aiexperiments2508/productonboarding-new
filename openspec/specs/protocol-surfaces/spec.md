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

### Requirement: The mutating surface is one named server

Exactly one toolset SHALL be able to change what a channel sees, so an operator
can hand out the read-only surfaces and withhold that one. The one permitted
exception is the event plane's tape control, which moves the clock and never the
catalog. No read-only toolset SHALL expose publication or rollback.

**A toolset that only reports derived figures SHALL declare no mutating tool.**
Where every number a surface serves is recomputed on read from a module that
owns the decision behind it, there is nothing a tool could sensibly write to,
and a writable dashboard would be a second account of the truth.

**A control that changes what the system does unattended SHALL NOT be an
agent-callable tool.** A spend cap belongs with the approval gate and the
publish command rather than beside the reads: it stays on a surface that demands
the name of whoever set it and writes that name to the audit ledger.

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

### Requirement: A connected application reaches the platform only over the protocol

The applications in `apps/` SHALL reach the platform over MCP and by no other
route. This SHALL hold for the pages they serve as well as for the processes
themselves: a page SHALL NOT fetch the platform directly.

A file the platform generates for a supplier SHALL therefore cross the protocol
as content and be relayed by the application from its own origin. A page
linking directly to the platform would move the supplier's identity into the
browser, where it becomes whatever a tab claims.

#### Scenario: The applications exist as their own processes

- **WHEN** the applications are enumerated
- **THEN** each is present as its own server
- **AND** `tests/test_app_boundary.py::test_the_applications_are_actually_there`
  asserts it

#### Scenario: None of them imports the platform or calls the REST API

- **WHEN** each application's imports and outbound calls are walked
- **THEN** none reaches the platform package or its HTTP API
- **AND** `tests/test_app_boundary.py::test_no_connected_application_imports_the_platform`
  and `::test_no_connected_application_calls_the_platforms_rest_api` assert both

#### Scenario: Their pages stay inside their own server

- **WHEN** the applications' web pages are examined for what they fetch
- **THEN** none reaches past its own server
- **AND** `tests/test_app_boundary.py::test_the_web_pages_do_not_reach_past_their_own_server`
  asserts it

#### Scenario: A template download crosses MCP

- **WHEN** the vendor portal offers a supplier a template
- **THEN** the portal fetches it through an intake tool and serves the bytes
  from its own origin, and no page fetches an absolute URL
- **AND** `tests/test_app_boundary.py` asserts the whole boundary, including
  the new routes

### Requirement: An intake endpoint exposes exactly what its system accepts

Each vendor intake endpoint SHALL expose the tools derived from the event types
its manifest entry declares it accepts, and no others. Narrowing a system in
the manifest SHALL remove the corresponding tools with no code change.

A tool that requires more than one accepted event type SHALL be exposed only
where the system accepts all of them. A product feed carries attribute rows and
photographs in one archive, so an endpoint that cannot take both has no
real-world equivalent of one and SHALL NOT offer it.

Reading what the retailer asks for SHALL be available on every intake endpoint,
whatever it accepts: knowing the requirements is not a privilege that depends
on how a supplier is permitted to send them.

#### Scenario: Only accepting systems have an intake, and its tools are derived

- **WHEN** the intake endpoints are enumerated
- **THEN** each belongs to a system the manifest marks as accepting, its tools
  follow from what that system accepts, and it declares which of them can act
- **AND** `tests/test_intake.py::test_only_the_systems_the_manifest_marks_as_accepting_have_an_intake`,
  `::test_every_intake_tool_is_derived_from_what_its_system_accepts`,
  `::test_an_intake_endpoint_ends_in_a_slash` and
  `::test_the_intake_declares_which_of_its_tools_can_act` assert each

#### Scenario: The bulk door appears only where both are accepted

- **WHEN** the tool list for each vendor-facing system is derived
- **THEN** the system accepting attribute rows, documents and imagery exposes
  the product-feed tool, and the systems accepting only a subset do not
- **AND** `tests/test_bundle_intake.py::test_only_a_system_that_takes_rows_and_images_gets_the_bulk_door`
  asserts it

#### Scenario: Every endpoint can read the template

- **WHEN** the tool list for each vendor-facing system is derived
- **THEN** every one of them exposes the template read
- **AND** `tests/test_bundle_intake.py::test_every_endpoint_can_read_the_template`
  asserts it

### Requirement: The intake surface cannot reach the fact store

The intake surface SHALL NOT be able to reach the fact store. Its only write
SHALL be an appended event.

That is the enforcement behind "a supplier cannot write a value": not a
permission check, which is a thing that can be passed or forgotten at a new call
site, but the absence of a code path.

No intake tool SHALL shadow a built-in toolset's tool name, and an intake
endpoint SHALL NOT be registered as an outbound connection - it is a door into
this platform, not a system this platform talks to.

#### Scenario: The intake cannot reach the fact store

- **WHEN** the intake surface's reachable writes are examined
- **THEN** the fact store is not among them and an appended event is the only
  write
- **AND** `tests/test_protocols.py::test_the_intake_surface_cannot_reach_the_fact_store`
  and `::test_the_only_write_the_intake_makes_is_an_appended_event` assert both

#### Scenario: An intake shadows nothing and is not an outbound connection

- **WHEN** the intake tools and the connection registry are examined
- **THEN** no intake tool shadows a built-in name and no intake is registered
  as an outbound connection
- **AND** `tests/test_protocols.py::test_no_intake_tool_shadows_a_built_in_toolset_name`
  and `::test_intake_endpoints_are_not_registered_as_outbound_connections`
  assert both

### Requirement: A shared endpoint owns its session for the session's whole life

The endpoint a connected application reaches the platform through SHALL own its
transport session in a task of its own, for the life of the session. It SHALL
NOT open the session inside a request and leave it belonging to that request.

The transport runs its reader in the task that opened it. A session opened
inside a request therefore stops being read the moment that request finishes,
and the next caller gets a session whose replies nobody is reading - it waits
for ever and holds the endpoint while waiting, so every later call queues behind
a call that will never finish. Nothing raises; the page shows a spinner.

Concurrent callers SHALL all be answered. A call SHALL be shielded from its
caller's cancellation, so a browser that navigated away or a request that timed
out takes nothing down with it. A call that does not answer within a bounded
time SHALL be abandoned and its session reopened, so an endpoint wedged by some
other cause recovers without the process being restarted.

#### Scenario: Two calls at once do not wedge the endpoint

- **WHEN** two calls to one endpoint overlap
- **THEN** both are answered and the endpoint remains usable
- **AND** `tests/test_app_boundary.py::test_two_calls_at_once_do_not_wedge_an_endpoint`
  asserts it

#### Scenario: A caller that gives up leaves the endpoint usable

- **WHEN** a caller is cancelled mid-call
- **THEN** the session survives and the next call is answered
- **AND** `tests/test_app_boundary.py::test_a_caller_that_gives_up_does_not_take_the_session_with_it`
  asserts it

These two tests pin what is assertable in-process. They do **not** reproduce the
original deadlock, which needs the real transport's task affinity and therefore
a live platform, and they say so - a test named for a bug it cannot reproduce
reads as coverage that is not there.

### Requirement: A capability this platform implements is not an estate system

A toolset the platform serves for its own capabilities SHALL be published as a
toolset, and SHALL NOT appear among the external systems the platform connects
to.

The estate is the set of systems this platform *talks to*, and it is declared by
a manifest that nothing outside may name. A capability the platform
*implements* is the other side of that boundary, and the agent-card surface
exists to keep the two apart.

#### Scenario: The control tower is a read-only toolset

- **WHEN** the control tower's toolset is examined
- **THEN** it declares no mutating tool, and the spend cap is not among its
  tools
- **AND** `tests/test_tower.py::test_the_control_tower_toolset_declares_no_mutating_tool`
  asserts it

#### Scenario: A toolset does not widen the estate

- **WHEN** the systems named outside the manifest are collected
- **THEN** the control tower is not among them
- **AND** `tests/test_estate.py::test_no_system_is_named_outside_the_manifest`
  asserts it
