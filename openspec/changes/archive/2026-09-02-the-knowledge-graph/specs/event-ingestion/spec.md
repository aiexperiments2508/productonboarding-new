## ADDED Requirements

### Requirement: A reference lane carries data that can never become a product fact

Reference data - stock snapshots, campaigns, certificate registers, trading
terms - SHALL arrive as events from systems the estate manifest declares, on a
lane of its own.

That lane SHALL be invisible to the transport, which SHALL NOT count it towards
replay progress; SHALL NOT be announced on the live feed, because nothing has
happened that a person needs to see; and SHALL be skipped by the ingestion
handlers **by construction** rather than by a filter that could be forgotten at
a new call site.

**No reference event SHALL become a product fact, and no readiness verdict SHALL
change because a reference pack was loaded.** This is the load-bearing
requirement of the whole reference lane: four of the graph's domains have no
source data and are therefore invented, and a verdict moved by invented
warehouse data would be indefensible.

Reference payloads SHALL name no product the arrival window would count, and
SHALL carry no conformance defect.

The pack SHALL be byte-identical for a given seed, SHALL be idempotent on
reload, and its absence SHALL NOT be an error.

#### Scenario: A reference event never reaches the fact store

- **WHEN** a reference pack is loaded and the record is read
- **THEN** no product fact came from it and every readiness verdict is unchanged
- **AND** `tests/test_kg_data.py::test_no_reference_event_becomes_a_product_fact`
  and `::test_a_readiness_verdict_is_unchanged_by_the_reference_pack` assert both

#### Scenario: The transport does not see the lane

- **WHEN** the transport's progress is read with a reference pack loaded
- **THEN** the lane is not counted
- **AND** `tests/test_kg_data.py::test_the_reference_lane_is_invisible_to_the_transport`
  asserts it

#### Scenario: Reference payloads do not enter the arrival window

- **WHEN** the arrival window is computed
- **THEN** no reference payload names a product it would count
- **AND** `tests/test_kg_data.py::test_reference_payloads_name_no_product_the_window_would_count`
  asserts it

#### Scenario: Every reference event still lands as an arrival, undefected

- **WHEN** the pack is loaded
- **THEN** each event is recorded as an arrival and none carries a conformance
  defect
- **AND** `tests/test_kg_data.py::test_every_reference_event_lands_as_an_arrival`
  and `::test_nothing_in_the_pack_is_stamped_with_a_defect` assert both

#### Scenario: The pack is reproducible, idempotent and optional

- **WHEN** the pack is generated twice, loaded twice, and then removed
- **THEN** the two are byte-identical, the second load changes nothing, and its
  absence is not an error
- **AND** `tests/test_kg_data.py::test_the_reference_pack_is_byte_identical_for_a_seed`,
  `::test_loading_the_pack_twice_changes_nothing` and
  `::test_a_missing_pack_is_not_an_error` assert each

#### Scenario: Every condition the insights look for is planted and named

- **WHEN** the pack is generated
- **THEN** it carries a lapsing certificate cohort, stock that cannot lawfully
  ship, and cross-sell pairs sharing more than one campaign, each named
- **AND** `tests/test_kg_data.py::test_the_certificate_register_has_a_lapsing_cohort`,
  `::test_stock_sits_where_it_cannot_lawfully_ship`,
  `::test_cross_sell_pairs_share_more_than_one_campaign` and
  `::test_every_planted_condition_is_named` assert each
