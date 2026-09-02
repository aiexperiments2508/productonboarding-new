## MODIFIED Requirements

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
