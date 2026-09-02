## ADDED Requirements

### Requirement: The walk answers in the identifiers people act on

A trace SHALL additionally resolve to the SKUs it reaches, each carrying the
listings and channels that SKU is live on.

A blast radius expressed only in internal identifiers is one only this system
can read. The buyer asked which products are affected, the supplier asked what
to reissue and the marketplace account manager asked what to pull all work in
SKUs, and a finding they cannot address is a finding that does not travel.

A SKU SHALL be reported once however many listings carry it, and the listings
and channels under it SHALL be ordered, so two reads of one trace agree.

#### Scenario: A trace names the SKUs it reaches

- **WHEN** a correction is traced
- **THEN** every affected variant appears once with its SKU, the listings it is
  live on and the channels those listings feed
- **AND** `tests/test_publication.py::test_the_blast_radius_answers_in_skus`
  asserts each

#### Scenario: A correction to one variant names the sibling it reaches

- **WHEN** a correction scoped to one variant is traced, and another variant's
  content quotes the corrected value
- **THEN** both SKUs are reported
- **AND** `tests/test_publication.py::test_a_correction_to_one_variant_names_the_siblings_it_reaches`
  asserts the second, which is the case the whole propagation design exists for

### Requirement: The systems that must be told are grouped with their work

A trace SHALL group the listings it reaches by the publication system that owns
each one, carrying the SKUs affected on that system.

"Eleven listings" is a number and "these four SKUs on these three systems" is a
work list, and the second is what somebody acts on.

The publication systems SHALL be derived from the channels the catalog declares
rather than configured separately. A publication list that could disagree with
the channel list is a second account of where content goes, and the first thing
it would disagree about is the channel somebody has just added.

#### Scenario: Publication systems follow the channels

- **WHEN** the publication systems are read
- **THEN** there is exactly one per channel the catalog declares, each with a
  distinct identifier and its own endpoint
- **AND** `tests/test_publication.py::test_publication_systems_are_derived_from_the_channels`
  asserts each

#### Scenario: Each system carries the SKUs it has to reissue

- **WHEN** a trace is grouped by publication system
- **THEN** each system appears once, carrying the listings it owns and the SKUs
  those listings carry, both ordered
- **AND** `tests/test_publication.py::test_the_systems_to_tell_are_grouped_with_their_skus`
  asserts each

#### Scenario: A system that cannot recall what it published says so

- **WHEN** the publication systems are read
- **THEN** a system is marked unrecallable exactly where its channel declares a
  freeze window, because the window exists because the artefact cannot be pulled
  back and the two are the same fact
- **AND** `tests/test_publication.py::test_a_channel_that_cannot_be_recalled_says_so`
  asserts the correspondence
