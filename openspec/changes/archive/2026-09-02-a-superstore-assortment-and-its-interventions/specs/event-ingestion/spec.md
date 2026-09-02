## ADDED Requirements

### Requirement: A notice outranks label artwork, and no supplier may issue one

The source precedence order SHALL carry a notice kind ranked above label
artwork, and that kind SHALL NOT be issuable by a supplier.

Artwork is the legal source for what a pack says. A notice is the legal source
for whether the pack may be sold at all. They answer different questions, and
where the two meet the second outranks the first - a correctly printed pack for
a product that has been withdrawn is still a product that has been withdrawn.

That no supplier may issue one is what keeps the ranking from being a lever a
supplier could pull to outrank artwork it does not like.

#### Scenario: A notice wins a contest against artwork

- **WHEN** a notice and label artwork assert conflicting positions on the same
  product
- **THEN** the notice is in force
- **AND** this follows from the declared precedence, which
  `tests/test_ingest.py` exercises for the ordering generally

### Requirement: The correction kinds the tape carries are the kinds the classifier offers

The kinds a correction may be classified as SHALL be one table, read by both the
generator that writes the tape and the classifier that reads it. Every kind the
classifier's prompt offers SHALL be one that exists.

Two copies of a vocabulary agree until they are asked about something neither
was written against, and then both are correct about their own copy while the
system as a whole is wrong.

#### Scenario: One table, and no kind offered that does not exist

- **WHEN** the generator's kinds and the classifier's are compared, and the
  prompt's offered kinds are checked
- **THEN** they are one table and every offered kind exists
- **AND** `tests/test_golden.py::test_the_two_kind_tables_are_the_same_table` and
  `::test_every_kind_the_prompt_offers_is_a_kind_that_exists` assert both
