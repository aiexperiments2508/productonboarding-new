## 1. The join

- [x] 1.1 Add `sc/tower/flow.py` with seven states from received to on sale and
      a pure `state_of` in the shape `stages.stage_of` already has; verify via
      `tests/test_tower.py::test_state_of_is_pure`
- [x] 1.2 Make every state reachable, so none is a name with no path to it;
      verify via `tests/test_tower.py::test_every_state_is_reachable`
- [x] 1.3 Order the precedence - not ingested, then stopped, then downstream,
      then waiting - and pin each step; verify via
      `tests/test_tower.py::test_not_ingested_outranks_every_other_signal` and
      `::test_a_stopped_row_that_is_also_on_sale_reads_as_stopped`
- [x] 1.4 Keep a gap the gate let through out of the blocked count; verify via
      `tests/test_tower.py::test_a_gap_the_gate_let_through_is_not_reported_as_blocked`
- [x] 1.5 Count a row waiting on a person as not cleared; verify via
      `tests/test_tower.py::test_a_row_waiting_on_a_person_has_not_cleared`
- [x] 1.6 Carry "the AI corrected this" as a flag and a count beside the state
      rather than as an eighth state
- [x] 1.7 Place every row a feed named, and answer `None` for a feed that does
      not exist; verify via
      `tests/test_tower.py::test_a_feed_places_every_row_it_named` and
      `::test_an_unknown_feed_is_not_invented`
- [x] 1.8 Read the same watermark comparison the submission surface makes, so
      two readings of "is this in the record" cannot disagree
- [x] 1.9 Recompute the lane per variant from `stages.stage_of` and the board's
      own three signals, and declare the grain in the payload
- [x] 1.10 Build the catalog, overlay and lane signals once per request rather
      than once per feed

## 2. The register

- [x] 2.1 Add `sc/tower/register.py` listing one row per submission, newest
      first, with no second identifier minted for a feed
- [x] 2.2 Report the carrier and the media-event count per feed rather than
      inventing a second feed type the estate would contradict
- [x] 2.3 Window on the simulated clock; verify via
      `tests/test_tower.py::test_the_window_filters_the_simulated_clock_not_the_real_one`
      and `::test_a_window_outside_the_horizon_is_empty_rather_than_everything`
- [x] 2.4 Offer arrival facts without the readiness pass, for a list that does
      not need every product assessed to be useful
- [x] 2.5 Agree with the per-feed view on the same feed; verify via
      `tests/test_tower.py::test_the_feed_and_the_register_agree_on_the_same_feed`
- [x] 2.6 Say when a window was truncated, so every figure below it reads as a
      sample; verify via `tests/test_tower.py::test_a_truncated_window_says_so`
- [x] 2.7 Add an index on arrival time, so a window is not a full scan of a
      table that grows by one row per delivered event

## 3. The KPIs

- [x] 3.1 Add `sc/tower/kpis.py` computing every figure as arithmetic over what
      another module decided
- [x] 3.2 Count the states the flow placed, rather than recounting them; verify
      via `tests/test_tower.py::test_the_kpis_count_the_states_the_flow_placed`
- [x] 3.3 Return `None` rather than zero for a rate whose denominator is empty;
      verify via `tests/test_tower.py::test_a_rate_over_nothing_is_none_rather_than_zero`
- [x] 3.4 Measure every duration on the real clock at both ends and carry the
      clock in the payload; verify via
      `tests/test_tower.py::test_durations_are_measured_on_the_real_clock`
- [x] 3.5 Refuse a duration whose ends are on different clocks rather than
      reporting it; verify via
      `tests/test_tower.py::test_a_duration_across_two_clocks_is_refused`
- [x] 3.6 Carry the incomplete-checks flag through aggregation the way the
      readiness rollup already does; verify via
      `tests/test_tower.py::test_checks_complete_survives_aggregation`
- [x] 3.7 Report residual errors - rows on sale still carrying an open finding
      - separately from blocked rows

## 4. The ledger

- [x] 4.1 Add `llm_ledger` to the schema, append-only, one row per invocation,
      with both clocks, the surface, the run, the feed and whether the call was
      priced
- [x] 4.2 Append at the completion choke points and at embedding, so embedding
      spend stops being invisible
- [x] 4.3 Guard the append so it can never raise into a model call
- [x] 4.4 Record a cache hit with its tokens intact and no cost; verify via
      `tests/test_tower.py::test_a_cache_hit_is_recorded_as_avoided_and_never_as_spend`
- [x] 4.5 Leave two ledger rows and one cache row for two identical calls;
      verify via
      `tests/test_tower.py::test_two_identical_calls_leave_two_ledger_rows_and_one_cache_row`
- [x] 4.6 Read what a hit would have cost off the cache's own record, never
      re-estimated
- [x] 4.7 Attribute spend to a feed and a surface; verify via
      `tests/test_tower.py::test_spend_is_attributable_to_a_feed_and_a_surface`
- [x] 4.8 Mark an unpriced call and count it apart, so a window nothing priced
      is not reported as free; verify via
      `tests/test_tower.py::test_an_unpriced_call_is_not_reported_as_free`
- [x] 4.9 Refuse a grouping outside the closed set rather than interpolating
      it; verify via
      `tests/test_tower.py::test_an_unknown_grouping_is_refused_rather_than_silently_substituted`

## 5. The caps

- [x] 5.1 Add a money cap and a token cap that trip independently, and name
      which one tripped in the refusal; verify via
      `tests/test_tower.py::test_a_token_cap_fires_where_a_money_cap_cannot`
- [x] 5.2 Raise the same error an unreachable gateway raises, so every existing
      deterministic fallback runs; verify via
      `tests/test_tower.py::test_a_breached_cap_refuses_the_way_an_unreachable_gateway_does`
- [x] 5.3 Start the meter at a ledger position when the cap is set, not at the
      beginning of time; verify via
      `tests/test_tower.py::test_the_meter_starts_when_the_cap_is_set` and
      `::test_raising_a_cap_restarts_its_meter`
- [x] 5.4 Demand a name to set a cap and write it to the ledger; verify via
      `tests/test_tower.py::test_the_cap_demands_a_name_and_writes_it_to_the_ledger`
- [x] 5.5 Cost nothing to check when no cap is set; verify via
      `tests/test_tower.py::test_no_cap_costs_nothing_to_check`

## 6. The personas

- [x] 6.1 Declare six personas as data, each with the tab it opens on and the
      figures it leads with, so the API and the console read one list
- [x] 6.2 Pin every tile to a KPI that exists and every persona to a tab that
      exists; verify via
      `tests/test_tower.py::test_every_persona_tile_is_a_kpi_that_exists` and
      `::test_every_persona_opens_on_a_tab_that_exists`
- [x] 6.3 State in the contract itself that a persona enforces nothing; verify
      via `tests/test_tower.py::test_the_persona_surface_states_that_it_enforces_nothing`

## 7. The surfaces

- [x] 7.1 Serve flow, feeds, one feed, KPIs, personas, spend and the cap over
      the HTTP API, with the cap alone demanding an actor
- [x] 7.2 Add a read-only `control-tower` MCP toolset and register it; verify
      via `tests/test_tower.py::test_the_control_tower_toolset_declares_no_mutating_tool`
- [x] 7.3 Record no fact and move no cursor while reading the tower; verify via
      `tests/test_tower.py::test_reading_the_tower_records_no_fact_and_moves_no_cursor`
- [x] 7.4 Build the four console tabs, and rename the component that rendered
      the Ingest Fabric so the section id is free for the tower

## 8. The prose that had drifted

- [x] 8.1 Correct the estate count in the README, the two docstrings and the
      test name - fifteen systems, not ten or eleven. The assertion was a lower
      bound and passed, so only the prose was wrong; verify via
      `tests/test_estate.py::test_the_manifest_declares_every_system_with_an_owner`
