## MODIFIED Requirements

### Requirement: The catalog map is derived, not stored

The map of products, variants, listings and channels SHALL be derived from the
catalog on read, with a relation on every edge and every edge endpoint present
as a node, so the map cannot drift from the catalog it claims to draw.

The map SHALL also carry the external systems currently connected, joined to
what they feed, so that "where did this come from" is answerable one hop
further out than the supplier. A system that is connected but has delivered
nothing SHALL still appear; an estate that only shows what has already spoken
cannot show a silent system.

No node's position SHALL be read from stored data. A tier whose membership
changes while the application is running cannot be laid out from coordinates
written at generation time, and a stored position is a second account of a
structure the catalog already settles.

The map SHALL follow connections as they change: connecting a system SHALL add
it and its edges, and disconnecting one SHALL mark it degraded rather than
removing it and the facts it delivered.

#### Scenario: Each tier is joined with a derived edge

- **WHEN** the map is requested
- **THEN** there is one product-to-supplier edge per product, one
  product-to-variant edge per variant and one listing edge per listing, every
  edge endpoint is a known node, and the planning horizon matches the catalog's
- **AND** `tests/test_propagation.py::test_the_map_joins_every_tier_with_a_derived_edge`
  asserts each

#### Scenario: A quiet catalog reports no correction

- **WHEN** the map is requested with no facts recorded
- **THEN** the correction summary is empty in every field
- **AND** `tests/test_propagation.py::test_a_quiet_catalog_reports_no_corrections`
  asserts the empty shape

#### Scenario: Connected systems are on the map, including the silent ones

- **WHEN** the map is requested with the estate connected and one system having
  delivered nothing
- **THEN** every connected system is a node, each is joined to what it feeds,
  and the silent one is present
- **AND** `tests/test_connections.py::test_connected_systems_are_on_the_map_including_silent_ones`
  asserts each

#### Scenario: No node carries a stored position

- **WHEN** the catalog and the map are inspected for node coordinates
- **THEN** the catalog stores none and the map derives every position from the
  tier and the live membership of that tier
- **AND** `tests/test_connections.py::test_no_node_position_is_stored`
  asserts both

#### Scenario: Disconnecting a system degrades it and keeps what it delivered

- **WHEN** a system that has delivered facts is disconnected and the map is
  requested again
- **THEN** the system is still a node and is marked degraded, its edges remain,
  and the facts it delivered are unchanged
- **AND** `tests/test_connections.py::test_disconnecting_degrades_without_retracting`
  asserts each
