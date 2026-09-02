## ADDED Requirements

### Requirement: Whether the product may be sold at all is a deterministic check

Whether a market authority has withdrawn a product SHALL be answered by a
deterministic check, without consulting a model. A withdrawn product SHALL be
blocked; a product still permitted SHALL raise nothing.

The reading checks answer this too, and that is not enough. They need a gateway,
and a withdrawn product reading as *merely incomplete* whenever the gateway is
down is the worst available failure: the assessment is narrower than usual,
which the system says, and the one finding that matters is the one that went
missing.

#### Scenario: A withdrawn product is blocked with no model reachable

- **WHEN** a product carrying a withdrawal notice is assessed with no gateway
- **THEN** it is blocked
- **AND** `tests/test_readiness.py::test_a_withdrawn_product_is_blocked_without_a_model`
  asserts it

#### Scenario: A product still permitted raises nothing

- **WHEN** a product with no withdrawal against it is assessed
- **THEN** the check raises nothing
- **AND** `tests/test_readiness.py::test_a_product_still_permitted_raises_nothing`
  asserts it
