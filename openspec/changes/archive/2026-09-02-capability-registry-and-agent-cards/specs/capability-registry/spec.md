## Purpose

One document naming everything this estate can do - the capabilities it
implements and the capabilities it can reach - so that a stranger who knows only
the host can find out what is here, and so "what can this system do" is
answerable without a person handing over a list.

## ADDED Requirements

### Requirement: The estate publishes one discoverable directory

A single document SHALL list every published capability, served from a
well-known location so that a caller who knows only the address can find it.

It SHALL be built from the cards actually served rather than from a separate
list of names. A directory assembled from its own inventory drifts from the
capabilities it claims to index within a release, and it drifts silently: the
directory still looks complete.

A capability that could not be published SHALL be absent from the directory
rather than listed. A directory naming something nobody can reach is worse than
a short one.

#### Scenario: The directory names every published peer

- **WHEN** the directory is requested
- **THEN** every peer that was successfully published appears, each with its
  own card address, its endpoint and its skill
- **AND** `tests/test_directory.py::test_the_directory_names_every_published_peer`
  asserts each

#### Scenario: The directory and the individual cards agree

- **WHEN** the directory's entries are compared with the per-agent cards served
  at their own addresses
- **THEN** the identifiers, names and skills are the same
- **AND** `tests/test_directory.py::test_the_directory_and_the_cards_agree`
  asserts the equality

#### Scenario: A capability that failed to publish is not advertised

- **WHEN** the directory is built from a mount list missing an agent
- **THEN** that agent does not appear
- **AND** `tests/test_directory.py::test_an_unpublished_capability_is_not_advertised`
  asserts the absence

### Requirement: Implemented and reachable capabilities are kept apart

The directory SHALL distinguish a capability this system *implements* from one
it merely knows how to *reach*. Each entry SHALL name its protocol and, for a
reachable one, whether it is currently answering.

Flattening the two would say this estate can do things it can only ask somebody
else to do - which is the difference between an agent and an address book, and
the difference matters most to the reader least able to check it.

#### Scenario: A peer and a connected system are distinguishable

- **WHEN** the directory is requested with a system connected
- **THEN** the peer entries and the system entries carry different kinds, each
  names its protocol, and every system entry names its state
- **AND** `tests/test_directory.py::test_a_peer_and_a_system_are_distinguishable`
  asserts each

#### Scenario: The counts agree with the entries

- **WHEN** the directory is requested
- **THEN** the reported counts equal the entries actually listed
- **AND** `tests/test_directory.py::test_the_counts_agree_with_the_entries`
  asserts the equality

### Requirement: The directory states what a capability may not do

An entry for a capability this system implements SHALL state the things it is
not permitted to do, rather than leaving them to be inferred from absence.

The approval gate and publishing are deliberately not capabilities: a human
decision is not something to delegate, and a peer that could publish is a peer
that could publish. A directory that merely omits them leaves a reader to
conclude they were forgotten.

#### Scenario: Every peer entry names its limits

- **WHEN** the directory is requested
- **THEN** each peer entry carries the actions it may not take, and those
  include approving a resolution and publishing to a channel
- **AND** `tests/test_directory.py::test_every_peer_entry_names_its_limits`
  asserts both
