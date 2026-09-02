## 1. Three applications, and the boundary around them

- [x] 1.1 Add the Vendor Portal, Storefront and Ops Console as their own
      processes on their own ports; verify via
      `tests/test_app_boundary.py::test_the_applications_are_actually_there`
- [x] 1.2 Let none of them import the platform; verify via
      `tests/test_app_boundary.py::test_no_connected_application_imports_the_platform`
- [x] 1.3 Let none of them call the platform's REST API; verify via
      `tests/test_app_boundary.py::test_no_connected_application_calls_the_platforms_rest_api`
- [x] 1.4 Keep their web pages inside their own server; verify via
      `tests/test_app_boundary.py::test_the_web_pages_do_not_reach_past_their_own_server`

## 2. The live lane

- [x] 2.1 Add a lane column and tell the lanes apart by it, never by a sequence
      range
- [x] 2.2 Bound the transport's advance so the cursor cannot walk into the live
      lane; verify via
      `tests/test_live_lane.py::test_the_replay_cursor_cannot_walk_into_the_live_lane`
      and `::test_jumping_to_a_live_event_lands_on_the_end_of_the_recording`
- [x] 2.3 Keep a watermark per lane, so a live event cannot push the tape's
      cursor past events it has not ingested; verify via
      `tests/test_live_lane.py::test_a_live_event_does_not_poison_the_tape_ingest_cursor`
- [x] 2.4 Leave submissions alone on reset, reload and backfill; verify via
      `tests/test_live_lane.py::test_resetting_the_tape_does_not_retract_a_submission`,
      `::test_reloading_the_tape_does_not_delete_a_submission` and
      `::test_the_backfill_leaves_submissions_alone`
- [x] 2.5 Make a submission visible before the cursor reaches it; verify via
      `tests/test_live_lane.py::test_a_submission_is_visible_before_the_cursor_reaches_it`
- [x] 2.6 Count only the recorded flight in the progress denominator and stop
      the clock at its end; verify via
      `tests/test_live_lane.py::test_the_progress_denominator_counts_only_the_recorded_flight`
      and `::test_the_clock_stops_at_the_end_of_the_recording`
- [x] 2.7 Stamp a submission with the simulated clock without moving it, and
      break the tie between two submissions at one paused instant; verify via
      `tests/test_live_lane.py::test_a_submission_carries_the_simulated_clock_not_the_wall_clock`,
      `::test_a_submission_does_not_move_the_simulated_clock` and
      `::test_two_submissions_at_one_paused_instant_do_not_tie`
- [x] 2.8 Attribute a submission to the endpoint it arrived through and stamp
      no conformance defect on it; verify via
      `tests/test_live_lane.py::test_a_submission_is_attributed_to_the_endpoint_it_arrived_through`
      and `::test_no_defect_is_stamped_on_a_submission`
- [x] 2.9 Tell the live sink what landed and what it raised, and let a failing
      sink not fail the submission; verify via
      `tests/test_live_lane.py::test_the_live_sink_is_told_what_landed_and_what_it_raised`
      and `::test_a_failing_sink_does_not_fail_the_submission`

## 3. The intake surface

- [x] 3.1 Derive each intake endpoint's tools from what the manifest says the
      system accepts, and give an intake only to systems that accept something;
      verify via
      `tests/test_intake.py::test_only_the_systems_the_manifest_marks_as_accepting_have_an_intake`,
      `::test_every_intake_tool_is_derived_from_what_its_system_accepts`,
      `::test_an_intake_endpoint_ends_in_a_slash` and
      `::test_the_intake_declares_which_of_its_tools_can_act`
- [x] 3.2 Keep the intake surface out of the fact store, with an appended event
      as its only write; verify via
      `tests/test_protocols.py::test_the_intake_surface_cannot_reach_the_fact_store`
      and `::test_the_only_write_the_intake_makes_is_an_appended_event`
- [x] 3.3 Let no intake tool shadow a built-in toolset name, and register no
      intake as an outbound connection; verify via
      `tests/test_protocols.py::test_no_intake_tool_shadows_a_built_in_toolset_name`
      and `::test_intake_endpoints_are_not_registered_as_outbound_connections`

## 4. What a supplier may see and say

- [x] 4.1 Show a supplier only its own products, and refuse an unknown supplier
      rather than serving nothing; verify via
      `tests/test_intake.py::test_a_supplier_sees_only_its_own_products`,
      `::test_a_supplier_cannot_read_another_suppliers_specification`,
      `::test_a_supplier_cannot_change_another_suppliers_product`,
      `::test_a_supplier_cannot_read_another_suppliers_submission` and
      `::test_an_unknown_supplier_is_refused_rather_than_served_nothing`
- [x] 4.2 Agree with the catalog route about what a specification says, and tell
      a supplier which values it asserted; verify via
      `tests/test_intake.py::test_the_specification_read_agrees_with_the_catalog_route`
      and `::test_a_supplier_is_told_which_values_it_asserted`
- [x] 4.3 Record a submission as a document version and never as a value; verify
      via `tests/test_intake.py::test_a_submission_is_recorded_as_a_document_version_and_not_as_a_value`
- [x] 4.4 Revise the document the value came off rather than minting a new one,
      and do not re-mint a version on a repeat; verify via
      `tests/test_intake.py::test_a_correction_revises_the_document_the_value_came_off`
      and `::test_a_second_submission_does_not_re_mint_the_same_version`
- [x] 4.5 Land the submission on the live lane, visible at once; verify via
      `tests/test_intake.py::test_the_submission_lands_on_the_live_lane_and_is_visible_at_once`
- [x] 4.6 Act once on a repeated submission; verify via
      `tests/test_intake.py::test_a_repeated_submission_acts_once`

## 5. Refusing what should not be accepted

- [x] 5.1 Demand a reason for changing a safety declaration; verify via
      `tests/test_intake.py::test_a_safety_declaration_cannot_be_changed_without_saying_why`
- [x] 5.2 Refuse a value of the wrong type naming the type it wanted, and an
      attribute nobody has defined; verify via
      `tests/test_intake.py::test_a_value_of_the_wrong_type_is_refused_with_the_type_it_wanted`
      and `::test_an_attribute_nobody_has_defined_is_refused`
- [x] 5.3 Refuse a correction dated before it was sent, and an unreadable date
      rather than guessing; verify via
      `tests/test_intake.py::test_a_correction_cannot_take_effect_before_it_was_sent`
      and `::test_an_unreadable_date_is_refused_rather_than_guessed_at`
- [x] 5.4 Refuse an undeclared image role and an oversized upload by name;
      verify via `tests/test_intake.py::test_an_image_role_nobody_declared_is_refused`
      and `::test_an_upload_over_the_limit_is_refused_with_a_named_reason`
- [x] 5.5 Refuse a draft with no category and say plainly that a draft is not in
      the catalog; verify via
      `tests/test_intake.py::test_a_draft_without_a_category_is_refused` and
      `::test_a_draft_says_plainly_that_it_is_not_in_the_catalog`

## 6. Uploads that actually reach the record

- [x] 6.1 Let an uploaded image reach the record and clear the check it
      answers, attributed to the system that carried it; verify via
      `tests/test_intake.py::test_an_uploaded_image_reaches_the_record_and_the_checks`
      and `::test_an_uploaded_image_is_attributed_to_the_system_that_carried_it`
- [x] 6.2 Write uploaded bytes outside the seed pack; verify via
      `tests/test_intake.py::test_uploaded_bytes_land_outside_the_seed_pack`
- [x] 6.3 Say a document has not been read rather than that nothing is wrong
      with it; verify via
      `tests/test_intake.py::test_a_document_with_no_text_says_it_has_not_been_read`,
      `::test_a_document_with_a_text_rendition_can_be_read` and
      `::test_a_document_version_reports_awaiting_extraction_not_nothing_wrong`
- [x] 6.4 Report every stage a submission reached, and carry the caveat when
      the reading checks did not run; verify via
      `tests/test_intake.py::test_a_submission_reports_every_stage_it_reached`
      and `::test_a_verdict_carries_its_caveat_when_the_reading_checks_did_not_run`

## 7. Redaction

- [x] 7.1 Refuse a redaction with no approval behind it, on every system;
      verify via `tests/test_redaction.py::test_a_redaction_without_an_approval_refuses_every_system`
- [x] 7.2 Read the authorising approval and never write one; verify via
      `tests/test_redaction.py::test_the_approval_that_authorises_a_redaction_is_read_and_never_written`
- [x] 7.3 Act once on a replayed redaction, and change nothing when only
      planning one; verify via
      `tests/test_redaction.py::test_a_replayed_redaction_acts_once` and
      `::test_planning_a_redaction_changes_nothing`
- [x] 7.4 Make a redaction a new fact rather than an edit, invisible to the
      validator, writing no attribute fact, moving no published version and
      emitting no change-set action; verify via
      `tests/test_redaction.py::test_a_redaction_is_a_new_fact_and_never_an_edit`,
      `::test_a_redaction_writes_no_attribute_fact_and_moves_no_published_version`,
      `::test_a_redaction_is_invisible_to_the_validator` and
      `::test_no_change_set_action_is_emitted_by_a_redaction`
- [x] 7.5 Keep what a channel showed before a redaction readable as of then;
      verify via
      `tests/test_redaction.py::test_what_a_channel_showed_before_a_redaction_is_still_readable_as_of_then`

## 8. One correction, five right answers

- [x] 8.1 Derive the action from what the channel can do; verify via
      `tests/test_redaction.py::test_one_correction_gets_a_different_right_answer_on_each_kind_of_channel`
- [x] 8.2 Withdraw a marketplace listing rather than placeholdering it, because
      its own rules make a placeholder a hard violation; verify via
      `tests/test_redaction.py::test_a_marketplace_withdraws_a_safety_field_rather_than_placeholdering_it`
      and `::test_withdrawing_a_listing_takes_it_off_air_in_the_shape_the_gateway_writes`
- [x] 8.3 Drop a search facet rather than leave it indexing a wrong value;
      verify via `tests/test_redaction.py::test_a_search_facet_is_dropped_rather_than_left_indexing_a_wrong_value`
- [x] 8.4 Queue a shelf label for reprint rather than claiming it is done;
      verify via `tests/test_redaction.py::test_a_shelf_redaction_queues_a_reprint_rather_than_claiming_it_is_done`
- [x] 8.5 Never report an unrecallable channel as redacted; open an erratum
      instead; verify via
      `tests/test_redaction.py::test_a_channel_that_cannot_be_recalled_is_never_reported_as_redacted`
      and `::test_a_print_channel_gets_an_erratum_obligation_instead_of_a_redaction`
- [x] 8.6 Redact copy with the value it quotes, through the existing lineage

## 9. Undoing, obligations and the ledger

- [x] 9.1 Restore what was hidden without deleting it, and refuse a restore
      where the redaction was an erratum; verify via
      `tests/test_redaction.py::test_a_restore_puts_back_what_was_hidden_without_deleting_it`
      and `::test_a_restore_refuses_where_the_redaction_was_an_erratum`
- [x] 9.2 Leave a safety redaction standing through a rollback; verify via
      `tests/test_redaction.py::test_a_rollback_does_not_undo_a_safety_redaction`
- [x] 9.3 Keep an obligation open until somebody discharges it, and stop one
      system discharging another's; verify via
      `tests/test_redaction.py::test_an_obligation_stays_open_until_somebody_discharges_it`
      and `::test_a_system_cannot_discharge_another_systems_obligation`
- [x] 9.4 Land every redaction in the ledger with actor, reason and system, and
      record errata and reprints under their own verbs; verify via
      `tests/test_redaction.py::test_every_redaction_lands_in_the_ledger_with_actor_reason_and_system`
      and `::test_an_erratum_and_a_reprint_are_recorded_under_their_own_verbs`
- [x] 9.5 Declare every publisher's mutating tools rather than inferring them
      from the verbs, and cover every writing tool with the declared verb list;
      verify via
      `tests/test_publication.py::test_every_publisher_declares_which_of_its_tools_mutate`
      and `::test_the_declared_verbs_cover_every_tool_that_can_write`

## 10. The release gate

- [x] 10.1 Record a release decision in its own table and never in the
      approvals table; verify via
      `tests/test_redaction.py::test_a_release_decision_is_not_written_to_the_approvals_table`
- [x] 10.2 Refuse a publish to a listing holding a safety redaction as a fourth
      refusal; verify via
      `tests/test_redaction.py::test_publishing_to_a_listing_holding_a_safety_redaction_is_refused`
      and `::test_the_same_publish_goes_through_once_the_release_is_recorded`
- [x] 10.3 Let a release approval alone not publish an unapproved resolution,
      and a rejected release not open the gate; verify via
      `tests/test_redaction.py::test_a_release_approval_alone_does_not_publish_an_unapproved_resolution`
      and `::test_a_rejected_release_does_not_open_the_gate`
- [x] 10.4 Leave an ordinary-field redaction holding no publish, and keep
      reporting an open allergen violation before the release gate; verify via
      `tests/test_redaction.py::test_a_redaction_of_an_ordinary_field_does_not_hold_a_publish`
      and `::test_an_open_allergen_violation_is_still_reported_before_the_release_gate`
- [x] 10.5 Record a release against the person who took it; verify via
      `tests/test_redaction.py::test_a_release_is_recorded_against_the_person_who_took_it`

## 11. The lifecycle board

- [x] 11.1 Place every product in exactly one lane, derived and never stored,
      and render every lane the rule can return; verify via
      `tests/test_lifecycle.py::test_every_product_lands_in_exactly_one_lane` and
      `::test_every_lane_the_rule_can_return_is_a_lane_the_board_renders`
- [x] 11.2 Order the precedence - a late change and being sent back each outrank
      being on sale; verify via
      `tests/test_lifecycle.py::test_a_late_change_outranks_being_on_sale`,
      `::test_being_sent_back_outranks_being_on_sale` and
      `::test_a_redaction_alone_puts_a_product_in_the_late_lane`
- [x] 11.3 Make a product as blocked as its worst variant; verify via
      `tests/test_lifecycle.py::test_a_product_is_as_blocked_as_its_worst_variant`
- [x] 11.4 Agree with the product list about verdicts, and say when a placement
      was made without a model; verify via
      `tests/test_lifecycle.py::test_the_board_agrees_with_the_product_list_about_verdicts`
      and `::test_the_board_says_when_it_was_placed_without_a_model`
- [x] 11.5 Move a product into the late lane on a supplier submission, say what
      landed and that it has not been read, and stop counting it once a run has;
      verify via
      `tests/test_lifecycle.py::test_a_supplier_submission_moves_a_product_into_the_late_lane`,
      `::test_the_late_lane_says_what_landed_and_that_it_has_not_been_read` and
      `::test_a_submission_stops_counting_once_a_run_has_read_it`
- [x] 11.6 Show a timeline running forwards, naming the carrying system, and
      refuse one for a product nobody has; verify via
      `tests/test_lifecycle.py::test_a_timeline_shows_a_submission_beside_what_the_estate_delivered`,
      `::test_a_timeline_runs_forwards`,
      `::test_a_submission_names_the_system_that_carried_it` and
      `::test_a_timeline_for_a_product_nobody_has_is_a_refusal_not_an_empty_page`

## 12. Proposed lines

- [x] 12.1 Put a proposed line on the board before anybody has decided, and keep
      it out of the catalog until accepted; verify via
      `tests/test_lifecycle.py::test_a_proposed_line_is_on_the_board_before_anybody_has_decided`
      and `::test_a_proposed_line_is_not_in_the_catalog_until_it_is_accepted`
- [x] 12.2 Put an accepted line in the catalog, assess it like any other, and do
      not report it ready; verify via
      `tests/test_lifecycle.py::test_accepting_a_line_puts_it_in_the_catalog` and
      `::test_an_accepted_line_is_assessed_like_any_other_and_is_not_ready`
- [x] 12.3 Record the acceptance against the person who made it, refuse a second
      acceptance, and refuse to accept a submission that is not a proposal;
      verify via
      `tests/test_lifecycle.py::test_accepting_a_line_is_recorded_against_the_person_who_did_it`,
      `::test_a_line_cannot_be_accepted_twice` and
      `::test_a_submission_that_is_not_a_proposal_cannot_be_accepted`
- [x] 12.4 Move an accepted line out of the draft lane into a real one; verify
      via `tests/test_lifecycle.py::test_an_accepted_line_leaves_the_draft_lane_for_a_real_one`
