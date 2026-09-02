## MODIFIED Requirements

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

## ADDED Requirements

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
