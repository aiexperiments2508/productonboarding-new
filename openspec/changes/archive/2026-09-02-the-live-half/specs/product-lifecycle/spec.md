## Purpose

Every product in the lane its own state puts it in - with its supplier, awaiting
review, on sale, held back - so the recorded flight and whatever is happening now
meet on one screen.

Derived and never stored, for the reason the publication estate is derived from
the channels: a stored lane is a second account of the truth, and the first
thing it disagrees about is whatever somebody just changed.

## ADDED Requirements

### Requirement: Every product is in exactly one lane, derived on read

A product SHALL be placed in exactly one lane, computed from its current state
rather than stored. Every lane the placement rule can return SHALL be a lane the
board renders.

A lane the rule can produce and the board cannot show is a product that
disappears, which is worse than a product in the wrong column.

A product SHALL be as blocked as its worst variant. The board answers "can I
sell this product", and one unsellable size makes that answer no.

The board SHALL agree with the product list about verdicts, and SHALL say when a
placement was made without a model rather than presenting a narrower reading as
a complete one.

#### Scenario: One product, one lane, all rendered

- **WHEN** the catalog is placed on the board
- **THEN** every product lands in exactly one lane, and every lane the rule can
  return is one the board renders
- **AND** `tests/test_lifecycle.py::test_every_product_lands_in_exactly_one_lane`
  and `::test_every_lane_the_rule_can_return_is_a_lane_the_board_renders` assert
  both

#### Scenario: A product is as blocked as its worst variant

- **WHEN** a product has one variant fit to sell and one blocked
- **THEN** the product is placed as blocked
- **AND** `tests/test_lifecycle.py::test_a_product_is_as_blocked_as_its_worst_variant`
  asserts it

#### Scenario: The board and the list agree, and a narrow placement says so

- **WHEN** the board and the product list are compared, and a placement is made
  with no model
- **THEN** their verdicts match, and the narrow placement declares itself
- **AND** `tests/test_lifecycle.py::test_the_board_agrees_with_the_product_list_about_verdicts`
  and `::test_the_board_says_when_it_was_placed_without_a_model` assert both

### Requirement: Something needing attention outranks being on sale

Where more than one signal is true, a late change and a product having been sent
back SHALL each outrank the product being on sale. A redaction alone SHALL be
enough to put a product in the late lane.

A product on sale with an unread submission against it is the row somebody has
to look at, and a board filing it under "on sale" hides exactly the thing the
board exists to surface.

#### Scenario: Attention outranks being on sale

- **WHEN** a product on sale also has a late change, has been sent back, or
  carries a redaction
- **THEN** it is placed in the lane that needs attention
- **AND** `tests/test_lifecycle.py::test_a_late_change_outranks_being_on_sale`,
  `::test_being_sent_back_outranks_being_on_sale` and
  `::test_a_redaction_alone_puts_a_product_in_the_late_lane` assert each

### Requirement: A submission moves a product and stops counting once it has been read

A supplier submission SHALL move its product into the late lane, and the lane
SHALL say what landed and that it has not been read. Once a run has read the
submission it SHALL stop counting towards that lane.

A late lane that never empties is a late lane nobody looks at.

#### Scenario: A submission arrives, is announced, and is then absorbed

- **WHEN** a supplier submits, and a run subsequently reads the submission
- **THEN** the product enters the late lane saying what landed and that it is
  unread, and afterwards stops counting
- **AND** `tests/test_lifecycle.py::test_a_supplier_submission_moves_a_product_into_the_late_lane`,
  `::test_the_late_lane_says_what_landed_and_that_it_has_not_been_read` and
  `::test_a_submission_stops_counting_once_a_run_has_read_it` assert each

### Requirement: A product's timeline runs forwards and refuses where there is no product

A product SHALL have a timeline placing its submissions beside what the estate
delivered, in forward chronological order, each entry naming the system that
carried it. A timeline for a product the catalog does not hold SHALL be a
refusal rather than an empty page.

An empty page for an unknown product reads as a product with no history, which
is a state a real product can be in.

#### Scenario: A timeline reads forwards and names its carriers

- **WHEN** a product's timeline is read
- **THEN** submissions sit beside estate deliveries, in forward order, each
  naming the carrying system
- **AND** `tests/test_lifecycle.py::test_a_timeline_shows_a_submission_beside_what_the_estate_delivered`,
  `::test_a_timeline_runs_forwards` and
  `::test_a_submission_names_the_system_that_carried_it` assert each

#### Scenario: An unknown product is refused, not shown empty

- **WHEN** a timeline is requested for a product nobody has
- **THEN** it is refused
- **AND** `tests/test_lifecycle.py::test_a_timeline_for_a_product_nobody_has_is_a_refusal_not_an_empty_page`
  asserts it

### Requirement: A proposed line is on the board before it is in the catalog

A line a supplier has proposed SHALL appear on the board before anybody has
decided on it, and SHALL NOT be in the catalog until it is accepted.

Accepting SHALL put it in the catalog, SHALL assess it like any other product -
which, arriving with no attributes and no imagery, means it is not ready - and
SHALL be recorded against the person who accepted it. A line SHALL NOT be
accepted twice, and a submission that is not a proposal SHALL NOT be acceptable
at all. An accepted line SHALL leave the draft lane for a real one.

Accepting a line means the retailer takes on responsibility for what it says
about something it has never sold, so the ledger records who did that.

#### Scenario: Proposed, then accepted

- **WHEN** a line is proposed and then accepted
- **THEN** it is on the board before the decision and out of the catalog until
  it, and afterwards is in the catalog, assessed, not ready, and out of the
  draft lane
- **AND** `tests/test_lifecycle.py::test_a_proposed_line_is_on_the_board_before_anybody_has_decided`,
  `::test_a_proposed_line_is_not_in_the_catalog_until_it_is_accepted`,
  `::test_accepting_a_line_puts_it_in_the_catalog`,
  `::test_an_accepted_line_is_assessed_like_any_other_and_is_not_ready` and
  `::test_an_accepted_line_leaves_the_draft_lane_for_a_real_one` assert each

#### Scenario: Acceptance is attributable and single-use

- **WHEN** a line is accepted, accepted again, and a non-proposal is submitted
  for acceptance
- **THEN** the first is recorded against its actor, and the second and third are
  refused
- **AND** `tests/test_lifecycle.py::test_accepting_a_line_is_recorded_against_the_person_who_did_it`,
  `::test_a_line_cannot_be_accepted_twice` and
  `::test_a_submission_that_is_not_a_proposal_cannot_be_accepted` assert each
