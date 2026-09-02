## ADDED Requirements

### Requirement: One reader resolves every spelling the tape uses for a product

The identifiers an event names SHALL be resolved by a single reader, and that
reader SHALL understand every spelling the tape uses - a channel acknowledgement
naming a variant, a document or an email naming entities, and a structured feed
naming an entity. The map and the arrival window SHALL both use it.

A resolver that reads one spelling reports the systems that use the others as
having delivered nothing at all, however much they have delivered. Two
resolvers would let the map and the window disagree about whether a system has
been heard from, which is worse: one of the two would be right and there would
be no way to tell which.

The manifest SHALL declare a transport and logistics system, which the estate
previously had no example of.

#### Scenario: The reader understands every spelling on the tape

- **WHEN** the payloads on the tape are read for the products they name
- **THEN** every spelling the tape actually uses is resolved
- **AND** `tests/test_estate.py::test_the_payload_reader_understands_every_spelling_the_tape_uses`
  asserts it against the tape rather than against a list written beside the
  reader

#### Scenario: Every system that has delivered draws an edge

- **WHEN** the estate map is built
- **THEN** every system that has delivered an event is connected to what it
  delivered about
- **AND** `tests/test_estate.py::test_every_system_that_has_delivered_draws_an_edge`
  asserts it
