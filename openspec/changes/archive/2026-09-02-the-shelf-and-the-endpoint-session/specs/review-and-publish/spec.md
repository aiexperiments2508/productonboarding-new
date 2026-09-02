## ADDED Requirements

### Requirement: A channel may ask what it is carrying, and only what it is carrying

The publication surface SHALL offer a read answering what lines a channel is
carrying, scoped to the asking system. It SHALL NOT name a line belonging to
another channel.

The existing listing lookup deliberately refuses to confirm a line the asking
channel does not carry, which is what stops one channel discovering another's
assortment by exhaustive guessing. Telling a channel what is on its own shelf is
a different act, and the scoping is what keeps it different.

The answer SHALL be in the catalogue's own order rather than sorted by
identifier. Sorting by identifier orders a shop by brand prefix, which is
alphabetical rather than meaningful.

A downstream application SHALL obtain what a channel carries by asking. It SHALL
NOT hold its own copy of the catalogue - a list written down outside the
platform is wrong the next time a product is renamed, and it fails silently,
because "not carrying these lines" is a truthful answer about lines that no
longer exist.

#### Scenario: A channel can be asked what it is carrying

- **WHEN** a channel asks for its shelf
- **THEN** it is answered with the lines it carries
- **AND** `tests/test_publication.py::test_a_channel_can_be_asked_what_it_is_carrying`
  asserts it

#### Scenario: A shelf never names another channel's line

- **WHEN** a channel asks for its shelf
- **THEN** no line belonging to another channel appears in the answer
- **AND** `tests/test_publication.py::test_a_shelf_never_names_another_channels_line`
  asserts it

#### Scenario: The shelf leads with what the catalogue leads with

- **WHEN** a shelf is returned
- **THEN** its order is the catalogue's, not the identifier ordering
- **AND** `tests/test_publication.py::test_a_shelf_leads_with_the_lines_the_catalog_leads_with`
  asserts it
