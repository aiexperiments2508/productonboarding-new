## ADDED Requirements

### Requirement: Readiness and publication read one rule table

The checks that decide whether a record is fit to publish SHALL read the same
channel rule rows the publish-time validator reads, rather than a second table
describing the same requirements.

Two implementations of one rule become two answers to "why was this held", and
a reviewer is shown whichever one happened to run. Worse, they drift silently:
a product passes readiness, reaches publication, and is refused on a rule the
readiness surface had no idea about - which teaches a reviewer that readiness
means nothing.

A readiness finding that rests on a channel rule SHALL name that rule's
identifier, so the finding and the refusal can be compared.

#### Scenario: A readiness finding names a rule the validator publishes against

- **WHEN** a record missing a channel-required attribute is assessed
- **THEN** every finding resting on a channel rule names an identifier the
  validator's own rule table contains
- **AND** `tests/test_readiness.py::test_readiness_and_publication_read_one_rule_table`
  asserts the containment

#### Scenario: A rule that cannot bind does not produce a finding

- **WHEN** a product is assessed against a channel rule requiring an attribute
  the product's category never defines
- **THEN** no finding is produced, because a product held for missing something
  it could not have is a finding nobody can act on
- **AND** `tests/test_readiness.py::test_a_check_does_not_fire_on_an_attribute_the_category_never_has`
  asserts the absence

### Requirement: A claim shown before publication is one the record substantiates

A claim rendered on a pre-publication preview SHALL be evaluated against the
same substantiation table the validator uses, and SHALL NOT be shown unless it
holds against the values in force.

A claim that appears on a preview and is then refused at publish is a claim the
reviewer approved and the channel rejected - the worst of both, because the
reviewer's approval was given on evidence the system already knew was wrong.

#### Scenario: Only substantiated claims reach the preview

- **WHEN** a preview is produced for a record whose prepared copy carries claims
- **THEN** every claim shown holds against the substantiation table given the
  values in force
- **AND** `tests/test_preview.py::test_an_unsubstantiated_claim_does_not_reach_the_page`
  asserts each

#### Scenario: A claim the record stops supporting is dropped

- **WHEN** a value moves so that a previously-held claim no longer holds
- **THEN** the claim is no longer shown
- **AND** `tests/test_preview.py::test_an_unsubstantiated_claim_does_not_reach_the_page`
  asserts the removal
