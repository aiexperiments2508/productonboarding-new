## ADDED Requirements

### Requirement: What a system has delivered is read per system, not filtered from an estate-wide window

The recent deliveries of a system SHALL be read scoped to that system. They
SHALL NOT be obtained by reading the newest arrivals across the whole estate and
filtering afterwards.

A post-filtered window loses any system quiet enough to fall outside it, and
reports that system as having delivered nothing. That is indistinguishable from
a system that has genuinely gone silent - which is precisely the condition the
estate map exists to surface, so the failure hides the one signal the surface is
for.

#### Scenario: A quiet system behind a busy one is still found

- **WHEN** one system delivers heavily and another delivers rarely, and the
  quiet system's deliveries are read
- **THEN** its deliveries are returned rather than lost behind the busy one
- **AND** `tests/test_estate.py::test_recent_deliveries_finds_a_quiet_system_behind_a_busy_one`
  asserts it
