## Purpose

Deciding whether a product's information is fit to publish, and when it is not,
naming the finding, the attribute it concerns and the system that supplied it -
so that "the data is incomplete" becomes something somebody can act on.

This is where a model is invited to read and forbidden to decide, and the
boundary is written down here rather than left to the implementation.

## ADDED Requirements

### Requirement: Readiness is a set of named findings, never a score

An assessment SHALL produce findings, each naming what is wrong, the attribute
or asset it concerns, the rule or passage it rests on, and the external system
that supplied the offending value where one is known.

It SHALL NOT produce a readiness score, percentage or grade. A product with
three open findings is not seventy per cent ready; it is not ready, and the
three findings are the thing anybody acts on. A number invites a threshold, and
a threshold invites publishing at ninety.

Findings SHALL be ordered deterministically, so two assessments of the same
record read the same way.

#### Scenario: An assessment names findings and no score

- **WHEN** a product with known defects is assessed
- **THEN** the result carries findings, each with a subject and a basis, and no
  field expressing overall readiness as a number
- **AND** `tests/test_readiness.py::test_readiness_reports_findings_and_no_score`
  asserts both

#### Scenario: The same record assesses the same way twice

- **WHEN** one record is assessed twice
- **THEN** the findings are identical in content and order
- **AND** `tests/test_readiness.py::test_an_assessment_is_reproducible`
  asserts the equality

### Requirement: Six checks are decided by rules alone

Completeness of applicable attributes, conformance of value types to the
declared schema, presence of channel-mandatory information, presence of the
media a category requires, contradiction between sources, and the presence of
content a policy forbids outright SHALL each be decided without consulting a
model.

Each SHALL read the same tables the publish-time validator reads. A product
that passed readiness and then failed publication on the same fact would mean
two implementations of one rule, which is the failure the rules-as-data design
already exists to prevent.

#### Scenario: Every deterministic check reports without a gateway

- **WHEN** a product is assessed with no model reachable
- **THEN** each of the six deterministic checks reports, and the assessment
  completes
- **AND** `tests/test_readiness.py::test_the_deterministic_checks_need_no_model`
  asserts both

#### Scenario: A missing mandatory attribute is found and attributed

- **WHEN** a product is missing an attribute a channel it lists on requires
- **THEN** a finding names the attribute, the channel that requires it, and the
  system that last supplied data for that product
- **AND** `tests/test_readiness.py::test_a_missing_mandatory_attribute_is_attributed`
  asserts each

#### Scenario: A category's required media is checked by role

- **WHEN** a product in a category requiring an ingredient panel has no asset in
  that role
- **THEN** a finding names the missing role and the category rule behind it
- **AND** `tests/test_readiness.py::test_missing_media_is_found_by_role`
  asserts both

#### Scenario: Readiness and publication cannot disagree on one fact

- **WHEN** a record failing a channel rule is assessed and then validated
- **THEN** both name the same rule
- **AND** `tests/test_readiness.py::test_readiness_and_publication_read_one_rule_table`
  asserts the agreement

### Requirement: Three checks may read, and none of them may decide

Whether a mandate covers this product, whether a sentence has become
semantically wrong, and whether the record contradicts internal documentation
SHALL be permitted to consult a model, because each requires reading prose that
no rule encodes.

On each, the model's output SHALL be a *candidate finding with a citation*. A
candidate SHALL be dropped unless it cites a retrievable passage, and the
passage SHALL be recorded on the finding so a reviewer can open it. A model
SHALL NOT originate the verdict, and no finding SHALL be admitted on confidence
alone.

Each SHALL have a deterministic fallback, so an assessment with no model
reachable reports fewer findings rather than failing - and SHALL say that it ran
without a model rather than presenting a narrower result as a complete one.

#### Scenario: An uncited candidate is dropped

- **WHEN** a model proposes a finding that cites no retrievable passage
- **THEN** the finding does not appear in the assessment, and the drop is
  recorded
- **AND** `tests/test_readiness.py::test_an_uncited_candidate_finding_is_dropped`
  asserts both

#### Scenario: An assessment without a model says so

- **WHEN** a product is assessed with no model reachable
- **THEN** the assessment reports that the reading checks did not run, rather
  than reporting their absence as a clean result
- **AND** `tests/test_readiness.py::test_an_assessment_without_a_model_says_so`
  asserts the statement

### Requirement: The verdict is arithmetic

The outcome SHALL be derived by counting open findings by severity, and SHALL be
one of a closed set: ready to launch, returned to source, or blocked.

A finding that a regulation forbids the sale SHALL block, and no accumulation of
other findings SHALL produce that outcome. Blocking is a statement about
legality, and reaching it by weight of evidence would make it a judgement.

The verdict SHALL be reproducible from the findings alone. A model MAY write the
covering note a reviewer reads; the note SHALL NOT be able to change the
outcome.

#### Scenario: No open finding releases the product

- **WHEN** a record with no open findings is assessed
- **THEN** the verdict is ready to launch
- **AND** `tests/test_readiness.py::test_a_clean_record_is_ready_to_launch`
  asserts the verdict

#### Scenario: An open finding returns it to the system that caused it

- **WHEN** a record with an open non-blocking finding is assessed
- **THEN** the verdict is returned to source, and it names the finding, the
  attribute and the system that supplied it
- **AND** `tests/test_readiness.py::test_an_open_finding_returns_the_product_to_its_source`
  asserts each

#### Scenario: Only a saleability finding blocks

- **WHEN** a record carrying many non-blocking findings is assessed, and then a
  record carrying one saleability finding
- **THEN** the first is returned to source and only the second is blocked
- **AND** `tests/test_readiness.py::test_only_a_saleability_finding_blocks`
  asserts both

#### Scenario: The verdict follows the findings and not the note

- **WHEN** the same findings are scored twice with different covering notes
- **THEN** the verdict is the same
- **AND** `tests/test_readiness.py::test_the_note_cannot_change_the_verdict`
  asserts the equality
