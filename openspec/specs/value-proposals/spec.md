# value-proposals Specification

## Purpose

A supplier leaves a field empty. This capability covers what the retailer
proposes to put in it, how much that proposal is worth, who gets to decide it,
and what provenance the answer lands with.

The rule underneath all of it: **the number that decides whether a value is
written unattended is composed by this system, not reported by a model.** A
model's confidence in its own reading is a fluent guess about its own fluency.
Everything else in the score is a count of things already on file, which is
checkable, stable between runs, and is what the reviewer is shown.

## Requirements

### Requirement: A proposal is composed from evidence already on file as well as from reading

A proposed value SHALL be composed from up to three kinds of source: a passage
a model read and cited, other variants of the same product, the convention of
the product's category, and decisions a person has already taken about the same
attribute. The catalog and decision sources SHALL require no model gateway.

An installation with no network still holds two hundred snack bars that agree
about their unit of measure and a reviewer who settled this field last week.
Both are answers, and refusing to consult them because a document could not be
read is refusing the cheaper evidence in favour of the dearer.

#### Scenario: A sibling answers with no gateway reachable

- **WHEN** a variant leaves an attribute empty that a sibling variant holds,
  and no model gateway is reachable
- **THEN** a proposal is produced carrying the sibling's value and naming it as
  the source
- **AND** `tests/test_onboarding.py::test_a_sibling_value_is_found_without_a_gateway`
  asserts it

#### Scenario: A prior names the value it found

- **WHEN** a proposal is built from priors
- **THEN** each prior states the value it holds and the support behind it,
  rather than contributing only to a score
- **AND** `tests/test_onboarding.py::test_a_prior_names_the_value_it_found`
  asserts it

#### Scenario: A settled decision becomes evidence for the next question

- **WHEN** a person has decided the same attribute before
- **THEN** that decision is offered as a prior on the next proposal for it
- **AND** `tests/test_onboarding.py::test_a_settled_decision_becomes_a_prior_for_the_next_one`
  asserts it

### Requirement: The confidence is composed, and a model's self-report is discounted

The confidence attached to a proposal SHALL be computed by this system. A
model's self-reported confidence SHALL be admitted only as a discounted input
alongside counts of corroborating and contradicting evidence, and SHALL NOT on
its own reach the autonomy threshold.

Every contribution to the score SHALL be reported as a named reason stating
what it contributed, so that the number a reviewer is shown can be read back to
the evidence that produced it.

#### Scenario: Priors alone do not reach the threshold

- **WHEN** a proposal is supported only by catalog and decision priors
- **THEN** its confidence falls below the default autonomy threshold
- **AND** `tests/test_onboarding.py::test_priors_alone_do_not_reach_the_default_threshold`
  asserts it

#### Scenario: Every reason says what it contributed

- **WHEN** a proposal is produced
- **THEN** each reason on it states its own contribution to the score
- **AND** `tests/test_onboarding.py::test_every_reason_says_what_it_contributed`
  asserts it

### Requirement: Disagreement is weighted heavier than agreement

A prior holding a *different* value SHALL subtract more from a proposal's
confidence than the same class of prior holding the same value adds to it.

Evidence that a proposal is wrong is worth more than evidence that it is
unremarkable.

A prior with too little support to raise a proposal's confidence SHALL likewise
have too little support to lower it. Thin evidence is thin in both directions,
and an asymmetry that let it refute but not support would make a handful of
rows into a veto.

#### Scenario: A disagreeing sibling costs more than an agreeing one pays

- **WHEN** the same class of prior is made to agree and then to disagree with
  an otherwise identical proposal
- **THEN** the disagreement moves the confidence further than the agreement did
- **AND** `tests/test_onboarding.py::test_disagreement_costs_more_than_agreement_pays`
  asserts it

#### Scenario: A prior too thin to support is too thin to refute

- **WHEN** a category prior has too little support to raise a proposal
- **THEN** it is not allowed to lower one either
- **AND** `tests/test_onboarding.py::test_a_prior_too_thin_to_support_a_value_is_too_thin_to_refute_one`
  and `::test_a_category_convention_does_weigh_in_both_directions` assert it

### Requirement: Two refusals sit in front of the threshold and do not move with it

A proposal on a safety-class attribute SHALL be routed to a person, and a
proposal fewer than two sources agree with SHALL be routed to a person,
whatever the confidence and whatever the threshold in force. Both SHALL be
decided before the confidence is compared to the threshold, and neither SHALL
be reachable by moving the threshold.

The threshold is a knob an operator can turn. A safety property that holds only
while nobody turns it is not a safety property, so the source count is checked
structurally rather than left to the weights falling short.

#### Scenario: A lone source is refused on a count, not on arithmetic

- **WHEN** a proposal has one supporting source and a confidence above the
  threshold
- **THEN** it is routed to a person
- **AND** `tests/test_onboarding.py::test_a_lone_source_is_refused_structurally_and_not_by_arithmetic`
  asserts it

#### Scenario: A safety-class attribute is never written unattended

- **WHEN** a proposal is made on a safety-class attribute
- **THEN** it is routed to a person however much agrees with it
- **AND** `tests/test_onboarding.py::test_a_safety_class_proposal_never_routes_autonomously`
  asserts it

#### Scenario: The threshold decides everything else

- **WHEN** a corroborated, non-safety proposal is scored either side of the
  threshold
- **THEN** the threshold alone decides whether it is written or queued
- **AND** `tests/test_onboarding.py::test_the_threshold_decides_everything_else`
  asserts it

### Requirement: The autonomy threshold is held in configuration and audited when it moves

The threshold SHALL be readable and settable at runtime, SHALL be clamped so
that it can be set neither to a value that asks nobody nor above certainty, and
every move SHALL be recorded in the audit ledger against a named actor with its
previous value.

"Why was this written without anybody approving it" is answered by the
threshold that was in force, and a threshold with no history cannot answer it.

#### Scenario: Moving the threshold is audited

- **WHEN** the threshold is set by a named actor
- **THEN** the ledger records the actor, the previous value and the new one
- **AND** `tests/test_onboarding.py::test_moving_the_threshold_is_audited`
  asserts it

#### Scenario: The threshold cannot be set to never asking

- **WHEN** a threshold below the floor is submitted
- **THEN** it is clamped rather than accepted
- **AND** `tests/test_onboarding.py::test_the_threshold_cannot_be_set_to_never_asking`
  asserts it

### Requirement: A queued proposal writes nothing until a person answers it

A proposal routed to a person SHALL be recorded with the exact value,
confidence, evidence, safety classification and threshold it was judged
against, and SHALL write no fact until a decision is taken on it.

The queue is stored rather than derived precisely because a reviewer approves
*the value they were shown*; a queue that recomputed its rows could let somebody
approve one number and write another.

One live proposal SHALL exist per attribute per bundle: re-assessing a bundle
SHALL refresh an open proposal and SHALL NOT reopen a settled one.

#### Scenario: Nothing is written while a question is open

- **WHEN** a proposal is queued for a person
- **THEN** no fact exists for that attribute until a decision is recorded
- **AND** `tests/test_onboarding.py::test_a_queued_proposal_writes_no_fact_until_somebody_decides`
  asserts it

#### Scenario: Re-assessing does not reopen a settled question

- **WHEN** a bundle whose proposal has already been decided is assessed again
- **THEN** the decided proposal is left alone
- **AND** `tests/test_onboarding.py::test_re_assessing_a_batch_does_not_reopen_a_settled_question`
  asserts it

### Requirement: An autonomous fill is INFERRED and a person's answer is DECIDED

A value written without a person SHALL be recorded with inferred provenance,
carrying its confidence and its citation, through the same ingestion door an
enrichment writes through. A value a person approved or typed SHALL be recorded
with decided provenance, named to them.

The two are different classes of knowledge. The publish-time safety gate treats
them differently because they *are* different: a category manager approving a
value takes responsibility for it, which is the thing an inference cannot do.

A proposal built only from priors SHALL be permitted to carry no citation, and
every surface rendering its audit line SHALL survive that.

#### Scenario: The two doors write different provenance

- **WHEN** one value is filled autonomously and another is approved by a person
- **THEN** the first is recorded as inferred and the second as decided
- **AND** `tests/test_onboarding.py::test_an_autonomous_fill_is_inferred_and_a_decided_one_is_not`
  asserts it

#### Scenario: An approval is attributed to the person who gave it

- **WHEN** a category manager approves a proposal
- **THEN** the value is written as decided and named to them
- **AND** `tests/test_onboarding.py::test_approving_writes_the_value_as_decided_and_not_as_inferred`
  asserts it

#### Scenario: A fill with no citation does not break the audit line

- **WHEN** an autonomous fill is built from priors and cites no passage
- **THEN** it is written and its audit line renders
- **AND** `tests/test_onboarding.py::test_an_autonomous_fill_built_from_priors_carries_no_citation`
  asserts it

### Requirement: A decision is attributable, single-use and never a publication

Every decision SHALL demand a named actor, SHALL be refused on a proposal that
has already been decided, and SHALL be written to the audit ledger. A
rectification SHALL write the reviewer's own value rather than the proposed
one. A rejection SHALL write nothing and SHALL say where the value has to come
from instead.

No decision SHALL publish anything. A reviewer answering "yes, that value is
right" has not said "put it on sale"; publication needs its own plan, approval
and channel reservation.

#### Scenario: A decision needs a name and cannot be taken twice

- **WHEN** a decision arrives without an actor, or on a settled proposal
- **THEN** it is refused
- **AND** `tests/test_onboarding.py::test_a_decision_needs_a_name` and
  `::test_a_decided_proposal_cannot_be_decided_again` assert it

#### Scenario: Rectifying writes the reviewer's value

- **WHEN** a reviewer rectifies a proposal
- **THEN** their value is written, not the proposed one
- **AND** `tests/test_onboarding.py::test_rectifying_writes_the_reviewers_value_rather_than_the_proposal`
  asserts it

#### Scenario: Rejecting writes nothing and says what is needed

- **WHEN** a reviewer rejects a proposal
- **THEN** no fact is written and the response names where the value must come
  from
- **AND** `tests/test_onboarding.py::test_rejecting_writes_nothing_and_names_where_the_value_comes_from`
  asserts it

#### Scenario: Every decision reaches the ledger

- **WHEN** any decision is taken
- **THEN** the audit ledger holds it
- **AND** `tests/test_onboarding.py::test_every_decision_reaches_the_ledger`
  asserts it
