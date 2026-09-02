## 1. The schema

- [x] 1.1 Put every label in a domain and give every domain at least one label;
      verify via `tests/test_kg_schema.py::test_every_label_belongs_to_a_domain`
      and `::test_every_domain_has_at_least_one_label`
- [x] 1.2 Give every label a business key with a constraint behind it, and
      constrain the alternate key; verify via
      `tests/test_kg_schema.py::test_every_label_has_a_business_key`,
      `::test_every_key_the_model_names_has_a_constraint_behind_it` and
      `::test_the_alternate_key_is_constrained_and_products_have_none`
- [x] 1.3 Declare both ends of every relationship and take the domain of what an
      edge reaches; verify via
      `tests/test_kg_schema.py::test_every_relationship_declares_both_of_its_ends`
      and `::test_an_edge_takes_the_domain_of_what_it_reaches`
- [x] 1.4 Apply and re-apply the schema without error, statement by statement;
      verify via `tests/test_kg_schema.py::test_the_schema_is_idempotent_statement_by_statement`
- [x] 1.5 Add no range index that repeats a constraint; verify via
      `tests/test_kg_schema.py::test_no_range_index_repeats_a_constraint`
- [x] 1.6 Name the search index the same in both places and cover exactly the
      searchable labels, each findable by its own key; verify via
      `tests/test_kg_schema.py::test_the_search_index_is_named_the_same_in_both_places`,
      `::test_the_search_index_covers_exactly_the_searchable_labels` and
      `::test_every_searchable_label_can_be_found_by_its_own_key`
- [x] 1.7 State the depth bound and keep it small; verify via
      `tests/test_kg_schema.py::test_the_depth_bound_is_small_and_stated`
- [x] 1.8 Mark as synthetic exactly the labels with no source data; verify via
      `tests/test_kg_schema.py::test_the_synthetic_labels_are_the_ones_with_no_source_data`

## 2. Cypher that cannot be injected into

- [x] 2.1 Bind every placeholder and use every parameter; verify via
      `tests/test_kg_cypher.py::test_every_placeholder_is_bound_and_every_parameter_is_used`
- [x] 2.2 Write no caller value into a statement; verify via
      `tests/test_kg_cypher.py::test_no_caller_value_is_written_into_a_statement`
      and `::test_a_hostile_node_id_stays_a_parameter`
- [x] 2.3 Take depth from a closed set of literal patterns, since Cypher will
      not bind it, and refuse anything outside; verify via
      `tests/test_kg_cypher.py::test_a_depth_outside_the_closed_set_is_refused`
- [x] 2.4 Make domains an enum and refuse a filter carrying Cypher; verify via
      `tests/test_kg_cypher.py::test_a_domain_filter_carrying_cypher_is_refused`
- [x] 2.5 Check saved queries against an allowlist by name, so an unknown
      insight never reaches a builder; verify via
      `tests/test_kg_cypher.py::test_an_unknown_insight_never_reaches_a_builder`
- [x] 2.6 Refuse an out-of-range parameter rather than clamping it; verify via
      `tests/test_kg_cypher.py::test_an_out_of_range_parameter_is_refused_not_clamped`
- [x] 2.7 Give every insight both implementations, with the same row cap and the
      declared columns; verify via
      `tests/test_kg_cypher.py::test_every_insight_in_the_catalogue_has_both_implementations`,
      `::test_the_row_cap_is_the_same_in_both_implementations` and
      `::test_every_saved_query_returns_the_columns_its_spec_declares`
- [x] 2.8 Need no plugin for any builder, and build statements only for known
      labels and types; verify via
      `tests/test_kg_cypher.py::test_no_builder_needs_a_plugin` and
      `::test_the_loader_only_builds_statements_for_known_labels_and_types`

## 3. Reference data that cannot reach a verdict

- [x] 3.1 Deliver the four invented domains as events from systems the manifest
      declares, on a third lane
- [x] 3.2 Keep the lane invisible to the transport and skipped by the ingestion
      handlers by construction; verify via
      `tests/test_kg_data.py::test_the_reference_lane_is_invisible_to_the_transport`
      and `::test_no_reference_event_becomes_a_product_fact`
- [x] 3.3 Leave every readiness verdict unchanged by the reference pack; verify
      via `tests/test_kg_data.py::test_a_readiness_verdict_is_unchanged_by_the_reference_pack`
- [x] 3.4 Name no product the arrival window would count; verify via
      `tests/test_kg_data.py::test_reference_payloads_name_no_product_the_window_would_count`
- [x] 3.5 Land every reference event as an arrival, stamped with no defect;
      verify via `tests/test_kg_data.py::test_every_reference_event_lands_as_an_arrival`
      and `::test_nothing_in_the_pack_is_stamped_with_a_defect`
- [x] 3.6 Keep the pack byte-identical per seed, idempotent on reload, and treat
      a missing pack as no error; verify via
      `tests/test_kg_data.py::test_the_reference_pack_is_byte_identical_for_a_seed`,
      `::test_loading_the_pack_twice_changes_nothing` and
      `::test_a_missing_pack_is_not_an_error`
- [x] 3.7 Plant every condition the insights look for, and name each; verify via
      `tests/test_kg_data.py::test_the_certificate_register_has_a_lapsing_cohort`,
      `::test_stock_sits_where_it_cannot_lawfully_ship`,
      `::test_cross_sell_pairs_share_more_than_one_campaign` and
      `::test_every_planted_condition_is_named`
- [x] 3.8 Read the certificate scheme off the catalog's own reference, and make
      the media gaps real; verify via
      `tests/test_kg_data.py::test_the_scheme_is_read_off_the_catalogs_own_reference`
      and `::test_the_best_sellers_without_media_are_real_gaps`

## 4. The projection and the insights

- [x] 4.1 Cover all seven domains, and still hold the catalog with no reference
      pack; verify via
      `tests/test_kg_insights.py::test_the_projection_covers_all_seven_domains`
      and `::test_a_graph_with_no_reference_pack_still_has_the_catalog`
- [x] 4.2 Join only labels the model admits, and mark only the invented domains
      synthetic; verify via
      `tests/test_kg_insights.py::test_every_edge_joins_two_labels_the_model_admits`
      and `::test_only_the_invented_domains_are_marked_synthetic`
- [x] 4.3 Answer all six insight views within their caps; verify via
      `tests/test_kg_insights.py::test_every_insight_answers_and_answers_within_its_cap`,
      `::test_certifications_expiring_finds_the_shared_ones`,
      `::test_bestsellers_missing_image_names_a_real_gap`,
      `::test_stock_that_cannot_ship_is_found_at_the_depot_that_serves_the_eu`,
      `::test_cross_sell_candidates_cross_a_category_boundary`,
      `::test_weakest_media_coverage_is_derived_from_real_imagery` and
      `::test_supplier_concentration_finds_the_single_source_categories`
- [x] 4.4 Grow a neighbourhood with depth and stop at the cap, filter a domain
      with its edges, and skip what is already on screen when expanding; verify
      via `tests/test_kg_insights.py::test_a_neighbourhood_grows_with_depth_and_stops_at_the_cap`,
      `::test_a_domain_filter_removes_a_domain_and_its_edges` and
      `::test_expanding_a_node_skips_what_is_already_on_screen`
- [x] 4.5 Say a path between two products in words, and find a product by every
      name it has; verify via
      `tests/test_kg_insights.py::test_a_path_between_two_products_is_said_in_words`
      and `::test_searching_finds_a_product_by_every_name_it_has`

## 5. Two backends that agree

- [x] 5.1 Produce statements Neo4j will actually run; verify via
      `tests/test_kg_neo4j.py::test_every_builder_produces_a_statement_neo4j_will_run`
- [x] 5.2 Apply and re-apply the schema, and merge idempotently; verify via
      `tests/test_kg_neo4j.py::test_the_schema_applies_and_re_applies` and
      `::test_merge_is_idempotent`
- [x] 5.3 Survive the load with every label and relationship intact, and find a
      product by identifier through the full-text index; verify via
      `tests/test_kg_neo4j.py::test_every_label_and_relationship_survived_the_load`
      and `::test_the_full_text_index_finds_a_product_by_sku`
- [x] 5.4 Return the same graph and the same saved-query rows from both
      backends; verify via
      `tests/test_kg_neo4j.py::test_both_backends_return_the_same_graph` and
      `::test_both_backends_answer_the_saved_queries_the_same`
- [x] 5.5 Refuse a bad depth before it reaches Neo4j; verify via
      `tests/test_kg_neo4j.py::test_a_depth_the_builder_refuses_never_reaches_neo4j`
- [x] 5.6 Import the driver inside a function, so a checkout without it still
      imports, starts and serves
- [x] 5.7 Fetch and run Neo4j without Docker, stepping aside quietly when it is
      not there

## 6. The routes

- [x] 6.1 Accept a product by every name it has, and answer an unknown key with
      a refusal rather than an empty graph; verify via
      `tests/test_kg_api.py::test_a_product_can_be_asked_for_by_every_name_it_has`
      and `::test_an_unknown_key_is_a_404_and_not_an_empty_graph`
- [x] 6.2 Bound the answer by depth and by node cap, and refuse a depth outside
      the closed set or a domain filter carrying Cypher; verify via
      `tests/test_kg_api.py::test_depth_and_the_node_cap_both_bound_the_answer`,
      `::test_a_depth_outside_the_closed_set_is_a_400` and
      `::test_a_domain_filter_that_is_really_cypher_is_a_400`
- [x] 6.3 Say which backend answered; verify via
      `tests/test_kg_api.py::test_the_response_says_which_backend_answered` and
      `::test_status_reports_the_backend_and_what_it_holds`
- [x] 6.4 Say a path in words, search by identifier and by name, and skip what
      the caller already has when expanding; verify via
      `tests/test_kg_api.py::test_a_path_between_two_products_comes_back_said_in_words`,
      `::test_search_finds_a_product_by_sku_and_by_name` and
      `::test_expanding_a_node_skips_what_the_caller_already_has`
- [x] 6.5 Run every saved query and return its declared columns, and run only
      those; verify via
      `tests/test_kg_api.py::test_every_saved_query_runs_and_returns_its_declared_columns`
      and `::test_the_saved_queries_are_the_only_ones_that_run`
- [x] 6.6 Read as of the replay clock rather than the wall clock; verify via
      `tests/test_kg_api.py::test_the_as_of_is_the_replay_clock_and_not_the_wall_clock`
- [x] 6.7 Hold no Cypher in the routes themselves; verify via
      `tests/test_kg_api.py::test_the_graph_routes_delegate_and_hold_no_cypher`
- [x] 6.8 Add a fourth back-office console reading the reference domains over
      MCP

## 7. Two faults found on the way

- [x] 7.1 Read arrivals per system rather than estate-wide and filtered
      afterwards, so a quiet system behind a busy one stops reporting nothing;
      verify via
      `tests/test_estate.py::test_recent_deliveries_finds_a_quiet_system_behind_a_busy_one`
- [x] 7.2 Give the segmented control the arrow-key handling its docstring
      promised and it did not have
