## ADDED Requirements

### Requirement: A prohibited sale is its own publish-time refusal, independent of confidence

Where a market authority has prohibited the sale of a product, publishing SHALL
be refused by a constraint of its own in the safety gate. That refusal SHALL NOT
depend on the confidence of any inference.

This is the reason the constraint exists rather than being left to the machinery
already present. **The safety gate only ever fires on a low-confidence
inference.** A withdrawal notice is recorded *confidently* - it is a document
from a market authority saying so - which means the existing gate has no
objection to it. The product would be escalated for review, the review would
agree the notice is real, and the publish would proceed.

The refusal SHALL apply to every listing the product reaches, not only the one
that raised it, and SHALL NOT be treated as something regenerating copy can
resolve. A product may not be sold; rewriting the sentence about it does not
change that.

A product still permitted SHALL NOT be gated.

#### Scenario: The sale gate is part of the publish refusal

- **WHEN** a publish is attempted for a product whose sale is prohibited
- **THEN** it is refused by the sale constraint
- **AND** `tests/test_validator.py::test_the_sale_gate_is_part_of_the_publish_refusal`
  asserts it

#### Scenario: A withdrawal blocks every listing the product reaches

- **WHEN** a withdrawn product's listings are validated
- **THEN** every one of them is blocked
- **AND** `tests/test_validator.py::test_a_withdrawal_blocks_every_listing_the_product_reaches`
  asserts it

#### Scenario: Copy cannot fix a withdrawal

- **WHEN** the remediation for a withdrawal is derived
- **THEN** regenerating copy is not among the options
- **AND** `tests/test_validator.py::test_a_withdrawal_is_not_something_copy_can_fix`
  asserts it

#### Scenario: A permitted product is not gated

- **WHEN** a product with no prohibition against it is validated
- **THEN** the sale constraint does not fire
- **AND** `tests/test_validator.py::test_a_product_still_permitted_is_not_gated`
  asserts it
