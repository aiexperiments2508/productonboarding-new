## ADDED Requirements

### Requirement: A decision the interface claims is available is reachable from it

Where a surface states that a reviewer takes a decision, a control that takes
that decision SHALL exist on that surface.

A proposed line had an acceptance function, a route, and a lane that rendered
it, and no control anywhere called any of them - so the last step of the journey
was a shell command while three surfaces said a reviewer accepts the line. That
is a worse gap than a missing feature: the claim is made and the place it would
be honoured is empty.

The decision SHALL be presented first on a proposal, because on a proposal it is
the only available action.

#### Scenario: The Proposed lane offers its own decision

- **WHEN** a card in the Proposed lane is opened
- **THEN** the acceptance decision is on it, above the evidence
- **AND** this is verified by inspection of the drawer; no frontend test covers
  it, and the acceptance it calls is asserted by
  `tests/test_lifecycle.py::test_accepting_a_line_puts_it_in_the_catalog`

### Requirement: Accepting a line asks for a name and for nothing it already has

Accepting a proposed line SHALL require a name, which SHALL be recorded in the
ledger. Accepting means the retailer takes on responsibility for what the line
says about something it has never sold.

There is no identity provider in this system and the surface SHALL NOT imply
there is: the name is taken at its word and written down, which is worth more
than a blank.

An identifier for the new line SHALL be offered and SHALL NOT be required -
minted where it is omitted, which is right for a demonstration and wrong for a
retailer that already knows what it will call the thing. The name and category
SHALL NOT be asked for at all: they came from the supplier, and a reviewer
should accept the line they were shown rather than retype it.

#### Scenario: The acceptance is attributed

- **WHEN** a line is accepted
- **THEN** the ledger records who accepted it
- **AND** `tests/test_lifecycle.py::test_accepting_a_line_is_recorded_against_the_person_who_did_it`
  asserts it

### Requirement: The confirmation says what was and was not done

On accepting a line, the confirmation SHALL state that the line is incomplete
and with its supplier, and SHALL state that accepting is not publishing.

An accepted line arrives with no attributes and no imagery. Reporting a product
created, and letting somebody discover later that it holds nothing, converts a
correct outcome into a surprise.

#### Scenario: An accepted line is not ready and is not published

- **WHEN** a line is accepted
- **THEN** it is in the catalog, assessed like any other product, not ready, and
  on no channel
- **AND** `tests/test_lifecycle.py::test_an_accepted_line_is_assessed_like_any_other_and_is_not_ready`
  asserts the readiness half, and the publication gates assert the rest
