## RENAMED Requirements

- FROM: `### Requirement: Three checks may read, and none of them may decide`
- TO: `### Requirement: Four checks may read, and none of them may decide`

A fourth reading check joins the three, so the requirement's own name would
otherwise be wrong. Renamed rather than added beside, because it is the same
requirement about the same set - a second one would leave the main spec
claiming three checks and four checks at once.

## MODIFIED Requirements

### Requirement: Four checks may read, and none of them may decide

Whether a mandate covers this product, whether a sentence has become
semantically wrong, whether the record contradicts internal documentation, and
whether the record breaches the retailer's own written policy SHALL each be
permitted to consult a model, because each requires reading prose that no rule
encodes.

The policy check SHALL be a distinct question from the saleability check.
Whether a market authority forbids a sale and whether this organisation has
said it will not make one are different statements, and answering the second
out of the first would make every statement of internal preference into a claim
about legality.

A finding from the policy check SHALL be reported as open and SHALL NOT be
reported as blocking. Blocking is reserved for a regulation saying a thing may
not be sold. Stopping onboarding on a policy breach is the onboarding gate's
job, and the gate reads a set of check names precisely so that it can stop a
product without the finding having to claim an authority it does not have.

On each of the four, the model's output SHALL be a *candidate finding with a
citation*. A candidate SHALL be dropped unless it cites a retrievable passage,
and the passage SHALL be recorded on the finding so a reviewer can open it. A
model SHALL NOT originate the verdict, and no finding SHALL be admitted on
confidence alone.

Each SHALL have a deterministic fallback, so an assessment with no model
reachable reports fewer findings rather than failing - and SHALL say that it ran
without a model rather than presenting a narrower result as a complete one.

#### Scenario: An uncited candidate is dropped

- **WHEN** a model proposes a finding that cites no retrievable passage
- **THEN** the finding does not appear in the assessment, and the drop is
  recorded
- **AND** `tests/test_readiness.py::test_an_uncited_candidate_finding_is_dropped`
  and, for the policy check,
  `::test_the_policy_check_drops_a_candidate_it_cannot_cite` assert both

#### Scenario: An assessment without a model says so

- **WHEN** a product is assessed with no model reachable
- **THEN** the assessment reports that the reading checks did not run, rather
  than reporting their absence as a clean result
- **AND** `tests/test_readiness.py::test_an_assessment_without_a_model_says_so`
  asserts the statement

#### Scenario: A policy breach is open and never blocking

- **WHEN** the policy check reports a breach of the retailer's own policy
- **THEN** the finding is open, and no accumulation of policy findings produces
  a blocking verdict
- **AND** `tests/test_readiness.py::test_a_policy_breach_is_open_and_never_blocking`
  asserts it

#### Scenario: The policy check is one of the reading set

- **WHEN** the reading checks are enumerated
- **THEN** the policy check is among them and is run on the same pass
- **AND** `tests/test_readiness.py::test_the_policy_check_is_one_of_the_reading_four`
  asserts it
