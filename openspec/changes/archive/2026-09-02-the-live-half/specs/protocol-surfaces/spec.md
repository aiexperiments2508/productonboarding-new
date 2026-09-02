## ADDED Requirements

### Requirement: A connected application reaches the platform only over the protocol

Each connected application SHALL run as its own process and SHALL reach the
platform over MCP and by no other route. It SHALL NOT import the platform
package and SHALL NOT call the platform's HTTP API. This SHALL hold for the
pages they serve as well as for the processes themselves: a page SHALL NOT
fetch the platform directly.

Every one of those is one convenient line away from being false at any moment,
and the application would keep working when it happened - faster, and outside
the boundary the whole architecture is stated in terms of. So each is asserted
rather than agreed.

#### Scenario: The applications exist as their own processes

- **WHEN** the applications are enumerated
- **THEN** each is present as its own server
- **AND** `tests/test_app_boundary.py::test_the_applications_are_actually_there`
  asserts it

#### Scenario: None of them imports the platform

- **WHEN** each application's imports are walked
- **THEN** none reaches the platform package
- **AND** `tests/test_app_boundary.py::test_no_connected_application_imports_the_platform`
  asserts it

#### Scenario: None of them calls the REST API

- **WHEN** each application's outbound calls are walked
- **THEN** none reaches the platform's HTTP API
- **AND** `tests/test_app_boundary.py::test_no_connected_application_calls_the_platforms_rest_api`
  asserts it

#### Scenario: Their pages stay inside their own server

- **WHEN** the applications' web pages are examined for what they fetch
- **THEN** none reaches past its own server
- **AND** `tests/test_app_boundary.py::test_the_web_pages_do_not_reach_past_their_own_server`
  asserts it

### Requirement: An intake endpoint exposes exactly what its system accepts

An intake endpoint SHALL exist only for a system the manifest declares as
accepting something, and its tools SHALL be derived from what that system
accepts rather than written down beside it. Narrowing a system in the manifest
SHALL remove the corresponding tools with no code change.

Each endpoint SHALL declare which of its tools can act.

#### Scenario: Only accepting systems have an intake, and its tools are derived

- **WHEN** the intake endpoints are enumerated
- **THEN** each belongs to a system the manifest marks as accepting, its tools
  follow from what that system accepts, and it declares which of them can act
- **AND** `tests/test_intake.py::test_only_the_systems_the_manifest_marks_as_accepting_have_an_intake`,
  `::test_every_intake_tool_is_derived_from_what_its_system_accepts`,
  `::test_an_intake_endpoint_ends_in_a_slash` and
  `::test_the_intake_declares_which_of_its_tools_can_act` assert each

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
