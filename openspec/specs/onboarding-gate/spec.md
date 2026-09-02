# onboarding-gate Specification

## Purpose

Whether a product may be onboarded at all, asked and answered before anything
is retrieved, proposed or spent on it.

Two questions arrive together and only one of them is about onboarding. *May we
sell this?* is about regulation and about the retailer's own policy. *Is the
record complete?* is what onboarding is for, and it is only worth asking once
the first is settled. This capability is the first question, and its whole job
is to stop the second one being asked about a product that is going back to its
supplier.

## Requirements

### Requirement: Compliance is settled before completeness

The onboarding pass SHALL evaluate the gate for a product before any source is
retrieved for it, any value proposed for it, or any model invoked on its
behalf. A product the gate stops SHALL have no gaps collected, no proposals
recorded and no facts written.

Proposing a value for a product that is being returned to its supplier is work
somebody then has to read, and it is spend on a record whose wattage has
stopped being interesting.

#### Scenario: A stopped product is not worked

- **WHEN** a bundle contains a product the gate stops
- **THEN** nothing is retrieved for it, no value is proposed for it and no fact
  is written for it
- **AND** `tests/test_onboarding.py::test_a_product_the_gate_stops_is_not_onboarded`
  asserts it

#### Scenario: The batch report counts it as stopped

- **WHEN** the onboarding pass finishes over a bundle containing a stopped
  product
- **THEN** that product is reported as stopped rather than as filled, queued or
  clear
- **AND** `tests/test_onboarding.py::test_a_stopped_product_is_counted_as_stopped`
  asserts it

### Requirement: The gate partitions an assessment it did not make

The gate SHALL be computed from a single readiness summary by splitting its
findings on the check that raised each one. It SHALL NOT query the record,
invoke a model, read a clock, or apply any rule of its own.

A gate that re-derived "unsaleable" would be a second answer to a question that
already has one, and a reviewer would be shown whichever of the two happened to
run.

#### Scenario: The findings onboarding is about survive the gate

- **WHEN** a product carries both a gate finding and an ordinary completeness
  finding
- **THEN** the gate reports the first and leaves the second to the onboarding
  pass, which still sees it
- **AND** `tests/test_onboarding.py::test_the_gate_does_not_swallow_the_findings_onboarding_is_about`
  asserts it

### Requirement: The gate is a set of named checks and never a severity

The gate SHALL be defined as a set of check names - the saleability checks plus
the policy check - and SHALL NOT be defined as a severity comparison.

`BLOCKING` is reserved for a regulation saying a thing may not be sold. The
policy check reports `OPEN` findings, because a breach of the retailer's own
policy stops onboarding without being a claim about legality. A severity test
would either drop the policy check from the gate or make it assert an authority
it does not have; naming the checks keeps both true at once.

#### Scenario: A policy breach stops onboarding without claiming a law was broken

- **WHEN** the only gate finding on a product is a policy breach
- **THEN** the product is stopped, and the finding is still reported as `OPEN`
- **AND** `tests/test_onboarding.py::test_the_gate_is_named_checks_and_never_a_severity`
  asserts the gate is not a severity comparison

### Requirement: A refusal names who refused it

A stopped product SHALL carry the authority that stopped it and a sentence a
supplier can act on. Where both a regulation and the retailer's own policy
stopped it, the reported authority SHALL be the regulation.

Which of the two refused decides whether the answer can be argued with, so it
is the sentence the supplier is given.

#### Scenario: Regulation outranks policy in the sentence

- **WHEN** a product breaches both a mandate and an internal policy
- **THEN** the outcome names the regulation as the authority
