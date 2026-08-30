## 1. Retire the sampler

- [x] 1.1 Delete the Monte Carlo module and its tests; verify the package
      imports and no test references them
- [x] 1.2 Replace the plan-feasibility test file with a validation test file;
      verify `tests/test_validator.py` collects and runs

## 2. The validation pass

- [x] 2.1 Build the effective attribute table from baseline, facts in force and
      the change set, with sorted iteration and ties broken by id; verify
      determinism via `tests/test_validator.py::test_identical_change_set_produces_identical_trace`
      and `test_action_order_does_not_change_the_result`
- [x] 2.2 Keep the trace hash and the in-force layer digest stable; verify via
      `test_kpis_are_stable_across_repeat_runs` and `test_overlay_digest_is_stable`
- [x] 2.3 Mark every content asset whose source version has moved, and clear it
      when the copy is regenerated; verify via
      `test_corrected_attribute_marks_every_derived_asset_stale`,
      `test_correction_reaches_the_base_variant_comparison_table` and
      `test_regenerating_the_copy_clears_the_stale_asset`
- [x] 2.4 Catch a superseded literal still in the prose, with word-boundary
      matching and severity by channel reversibility; verify via
      `test_stale_literal_is_hard_on_the_marketplace_and_print` and
      `test_stale_literal_does_not_match_inside_a_longer_number`
- [x] 2.5 Evaluate all seven channel rule kinds from rule data, each violation
      naming the rule; verify one test per kind, `test_max_len_reports_the_budget_and_the_overrun`
      through `test_category_mapped_names_the_unmapped_taxonomy_node`
- [x] 2.6 Check claims against the substantiation table and assert the table is
      exactly the documented claim set; verify via
      `test_claim_table_covers_the_documented_claims`,
      `test_a_higher_wattage_unsubstantiates_low_energy` and
      `test_a_claim_that_holds_raises_nothing`
- [x] 2.7 Check allergen declarations in each channel's required format and in
      source order; verify via `test_each_food_channel_demands_its_own_allergen_format`,
      `test_an_undeclared_allergen_is_named_on_every_listing` and
      `test_derived_ingredient_order_must_match_the_source`
- [x] 2.8 Fail closed on a low-confidence inference on a safety-class attribute,
      naming attribute, confidence and threshold, and not on a decision or a
      non-safety attribute; verify via the four tests from
      `test_low_confidence_on_a_safety_attribute_blocks_every_listing` to
      `test_the_gate_ignores_attributes_that_are_not_safety_class`
- [x] 2.9 Refuse a decision taken against a superseded source version; verify
      via `test_a_decision_taken_against_an_older_version_blocks_republishing`
      and `test_a_current_decision_does_not_block_republishing`
- [x] 2.10 Require a citation on every attribute change and regeneration; verify
      via the three citation tests
- [x] 2.11 Collapse violations to one row per constraint, entity and channel in
      sorted order, each naming what bound; verify via
      `test_every_violation_names_the_binding_rule_and_the_entity` and
      `test_violations_are_collapsed_to_one_row_per_binding_rule`
- [x] 2.12 Keep a withheld channel visible in the measures and make
      publishability exactly the absence of blocking violations; verify via
      `test_withholding_a_channel_costs_a_step_and_still_shows_the_block` and
      `test_feasibility_is_exactly_the_absence_of_hard_violations`
- [x] 2.13 Keep a pass under 250ms so candidates can validate concurrently;
      verify via `test_validation_is_fast_enough_to_fan_out`
- [x] 2.14 Confirm the untouched catalog still validates clean after the rewrite;
      verify via `test_untouched_catalog_validates_clean` and
      `test_baseline_readiness_is_an_empty_change_set`

## 3. Blast radius

- [x] 3.1 Derive the catalog map from the catalog on read with a relation on
      every edge; verify via `tests/test_propagation.py::test_the_map_joins_every_tier_with_a_derived_edge`
      and `test_a_quiet_catalog_reports_no_corrections`
- [x] 3.2 Show corrections in force with their source document, stale-asset
      count and old-to-new summary line, honouring the recording instant; verify
      via `test_corrections_in_force_show_on_the_map_with_their_source` and
      `test_recorded_time_hides_a_correction_that_had_not_arrived_yet`
- [x] 3.3 Walk source document to attribute to asset to listing to channel, with
      variants held by products and versions superseding; verify via
      `test_the_correction_reaches_every_channel_that_used_the_old_value`,
      `test_every_chain_link_is_drawn_with_a_relation_the_ui_can_label` and
      `test_a_document_revision_is_drawn_as_a_supersedes_hop`
- [x] 3.4 Reach the base model's page through the shared comparison table;
      verify via `test_a_variant_correction_reaches_the_base_page_through_the_comparison_table`
- [x] 3.5 Make the totals recomputable from the affected lists; verify via
      `test_totals_agree_with_the_affected_lists` and
      `test_a_regulated_product_is_counted_as_one`
- [x] 3.6 Bound the walk by depth, cap the drawn chain without truncating the
      scope, terminate on a cyclic catalog and return an empty scope for an
      unknown root; verify via the four bounding tests
- [x] 3.7 Make two traces of one root byte-identical; verify via
      `test_two_traces_of_the_same_root_are_identical`
- [x] 3.8 Replace alternate-supplier lookup and bill-of-materials expansion with
      a variant attribute diff carrying the document each value stands on;
      verify via the five variant-diff tests
- [x] 3.9 Add a derivation read in both directions marking cross-variant
      sources, plus a channel-rule lookup and a single-listing state read; verify
      via the derivation, channel-rule and listing-state tests
- [x] 3.10 Confirm the traversal is a superset of what the validator binds on;
      verify via `test_every_listing_the_validator_flags_is_inside_the_blast_radius`

## 4. Event ingestion

- [x] 4.1 Replace the per-type conditional with a handler registry keyed by
      event type; verify a handler can be substituted, exercised by
      `tests/test_ingest.py::test_a_failed_batch_leaves_the_cursor_and_the_store_untouched`
- [x] 4.2 Record structured feed rows as observed facts pinned to the document
      version that asserted them, on the replay clock; verify via
      `test_a_feed_row_becomes_a_recorded_fact_naming_document_and_event`
- [x] 4.3 Write no attribute facts for documents and correspondence, recording
      only their arrival; verify via `test_documents_and_emails_write_no_attribute_facts`
- [x] 4.4 Apply a five per cent materiality threshold to numeric attributes and
      treat any change to a safety-class attribute as material; verify via
      `test_an_immaterial_change_is_recorded_without_raising_a_signal` and
      `test_any_change_to_a_safety_attribute_is_material`
- [x] 4.5 Raise a data-gap signal naming a channel that needs an empty required
      field; verify via `test_a_required_attribute_arriving_empty_is_a_data_gap`
- [x] 4.6 Raise a source conflict naming both documents and the precedence
      policy instead of letting a lower-ranked source overwrite; verify via
      `test_a_lower_precedence_source_does_not_overwrite_a_higher_one` and
      `test_an_equal_ranked_source_is_recorded_rather_than_disputed`
- [x] 4.7 Record channel rejections with their code and the internal paths
      behind the named field, and acknowledgements quietly; verify via
      `test_a_channel_rejection_carries_its_code` and
      `test_an_acknowledgement_is_recorded_without_raising_a_signal`
- [x] 4.8 Give the graph a way back in that records inferences with confidence
      and supersedes rather than overwrites; verify via
      `test_an_extracted_value_is_inferred_and_supersedes_rather_than_overwrites`
- [x] 4.9 Advance the cursor inside the same transaction as the facts; verify
      via `test_the_cursor_advances_with_the_batch_and_redelivery_is_a_no_op`
      and `test_a_failed_batch_leaves_the_cursor_and_the_store_untouched`

## 5. Review and publish

- [x] 5.1 Refuse a publish without a recorded approval and after a rejection,
      recording the refusal; verify via
      `tests/test_orchestration.py::test_commit_without_approval_is_refused`,
      `test_commit_after_rejection_is_refused` and
      `test_approved_commit_writes_an_audit_trail`
- [x] 5.2 Record what each channel received as a published fact citing its
      source version; verify via `test_a_commit_records_what_went_live`
- [x] 5.3 Keep exclusive publish locks exclusive at the database, keep
      exploration holds non-blocking, and name the holder on conflict; verify
      via the six locking tests
- [x] 5.4 Keep idempotency keys replay-safe and never cache a failure; verify
      via `test_replayed_commit_returns_the_original_result`,
      `test_distinct_keys_are_not_deduplicated` and
      `test_failed_calls_are_not_cached_as_results`
- [x] 5.5 Re-check version currency immediately before writing and refuse
      without taking a lock; verify via
      `test_publish_is_refused_once_a_later_source_version_is_in_force`,
      `test_a_refused_publish_takes_no_lock_and_is_on_the_record` and
      `test_the_source_version_the_resolution_cites_still_publishes`
- [x] 5.6 Refuse while a safety-confidence or allergen-declaration violation is
      open on an affected listing; verify via
      `test_publish_is_refused_while_a_safety_violation_is_open` and
      `test_publish_is_refused_while_an_allergen_declaration_is_open`
- [x] 5.7 Make safety a pre-sort in ranking rather than a weight; verify via
      `test_a_safety_flag_outranks_any_weighting`
- [x] 5.8 Release the locks and mark the actions reversed on rollback so the
      batch is reusable; verify via
      `test_rollback_releases_locks_and_reverses_actions` and
      `test_the_batch_is_reusable_after_rollback`
- [x] 5.9 Surface publish conflicts at proposal time rather than after approval;
      verify via `test_proposal_surfaces_conflicts_before_approval`

## 6. Verification

- [x] 6.1 Run the four test files together with no model gateway reachable and
      confirm they pass (119 passed)
- [x] 6.2 Confirm no model gateway call exists in the validation, traversal,
      ingestion or publishing modules, by inspection of the four modules
- [ ] 6.3 Close the residual: resolve safety-gate listings through a resolver
      that understands product-level facts as well as variant-level ones, so a
      fact recorded against a product blocks every variant's listings
- [ ] 6.4 Retract published facts on rollback, so an as-of read taken after a
      rollback no longer returns a value that has been pulled
