## MODIFIED Requirements

### Requirement: The catalogue offered to the model is the allowlist

The tool list presented to the investigator SHALL be rendered from the allowlist
itself, naming each tool and what it takes, and SHALL hold exactly as many
entries as the allowlist - so the prompt cannot drift from the governance
actually in force.

Where an operator has admitted a tool from a connected external system, that
tool SHALL appear on the catalogue named with the system it belongs to, so a
model choosing between a catalog lookup and a supplier's own answer can see
which is which. A flat list would make an external system's answer
indistinguishable from this system's.

**Connecting a system SHALL NOT put any of its tools on the catalogue.**
Discovery records what a system says it can do; admission is a separate act
taken by a person. A system that could widen the desk by connecting would make
the allowlist a formality, and the allowlist is the reason handing this desk to
a model is uninteresting rather than alarming.

An admitted tool SHALL leave the catalogue while its system is not answering. A
catalogue offering something unreachable spends a model's bounded rounds
discovering that.

#### Scenario: The rendered catalogue matches the table entry for entry

- **WHEN** the catalogue is rendered
- **THEN** every tool appears with the argument it takes, and the catalogue has
  exactly one line per allowlisted tool
- **AND** `tests/test_replan.py::test_the_catalogue_offered_to_the_model_matches_the_allowlist`
  asserts both

#### Scenario: Connecting a system widens nothing

- **WHEN** a system declaring tools is connected and the catalogue is rendered
- **THEN** the catalogue is unchanged
- **AND** `tests/test_directory.py::test_connecting_a_system_does_not_widen_the_desk`
  asserts the equality

#### Scenario: An admitted tool joins, named with its system

- **WHEN** an operator admits a tool on a connected system and the catalogue is
  rendered
- **THEN** the tool appears once, named with the system it belongs to
- **AND** `tests/test_directory.py::test_an_admitted_tool_joins_the_desk_named_with_its_system`
  asserts both

#### Scenario: An unreachable system's admitted tool leaves the catalogue

- **WHEN** a system whose tool was admitted stops answering
- **THEN** the tool is no longer offered, and the built-in entries are unchanged
- **AND** `tests/test_directory.py::test_a_degraded_systems_tool_leaves_the_desk`
  asserts both
