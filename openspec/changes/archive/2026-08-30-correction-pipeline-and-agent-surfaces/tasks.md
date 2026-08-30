## 1. State, the evidence desk and the prompts

- [x] 1.1 Keep the reset marker and the resettable reducer, so a revision can
      clear an accumulating field at all; verify via
      `tests/test_replan.py::test_reset_marker_replaces_rather_than_appends` and
      `test_signals_reset_on_a_revision`
- [x] 1.2 Re-derive signal merging on kind plus shared entity plus shared
      attribute path, comparing real timestamps rather than ISO strings; verify
      via `tests/test_graph.py::test_a_revision_supersedes_but_does_not_resolve`
      and `test_a_withdrawal_does_not_cancel_an_unrelated_correction`
- [x] 1.3 Retire a correction a later notice resolves, and keep the resolver off
      the open list; verify via `test_a_withdrawal_retires_what_it_clears`,
      `test_an_unwithdrawn_notice_still_stands` and
      `test_a_withdrawn_notice_is_not_an_open_correction`
- [x] 1.4 Exempt a source conflict from supersession, so a later correction on
      the same attribute does not hide the disagreement the precedence policy
      exists to surface; verified by inspection of the exemption set - no test
      covers it directly
- [x] 1.5 Swap the seven evidence tool bodies for catalog and corpus lookups,
      keeping the allowlist frame; verify via
      `tests/test_replan.py::test_every_allowlisted_tool_is_read_only` and
      `test_an_allowlisted_tool_the_registry_knows_is_on_a_read_only_toolset`
- [x] 1.6 Render the catalogue from the tool table so the prompt cannot drift
      from the governance in force; verify via
      `test_the_catalogue_offered_to_the_model_matches_the_allowlist`
- [x] 1.7 Refuse an unlisted tool and a missing argument, recording both rather
      than dropping them; verify via
      `test_a_tool_outside_the_allowlist_is_refused_not_executed`,
      `test_a_refusal_is_recorded_rather_than_dropped` and
      `test_a_tool_called_without_its_argument_is_refused_with_guidance`
- [x] 1.8 Return a failing lookup as evidence rather than raising; verify via
      `test_a_failing_lookup_is_evidence_rather_than_a_dead_run`
- [x] 1.9 Cap the passes and the requests per pass; verify via
      `test_the_loop_is_bounded`
- [x] 1.10 Resolve the variant comparison and the document version history from
      the catalog before the investigator is prompted, labelled as required;
      verify via `test_the_standing_questions_are_about_the_catalog_not_the_corpus`
      and `test_mandatory_requests_run_before_any_agent_request`
- [x] 1.11 Pull the affected channels' rules for a safety-class correction, in
      sorted order and capped, and none for a correction that touches nothing
      safety-class; verify via
      `test_a_safety_class_correction_also_pulls_the_channel_rules` and
      `test_a_correction_that_touches_nothing_safety_class_pulls_no_channel_rules`
- [x] 1.12 Budget the required lookups separately from the investigator's own;
      verify via `test_an_agent_flood_cannot_crowd_out_a_mandatory_lookup`
- [x] 1.13 Write seven prompts that hand the model every figure rather than
      asking it to recall one, and pass branch context only when that branch
      ran; verified by inspection of `sc/graph/prompts.py`

## 2. The correction pipeline

- [x] 2.1 Build the twenty-two-node graph with the content leg the previous
      graph had no equivalent of; verify via
      `tests/test_graph.py::test_every_leg_of_the_pipeline_runs`
- [x] 2.2 Give every model step a deterministic fallback that catches gateway
      failure and says it ran blind; verify via
      `test_the_correction_is_read_without_a_model` and
      `test_a_node_that_fell_back_records_no_spend`
- [x] 2.3 Reach the approval gate with no gateway reachable; verify via
      `test_run_stops_at_the_approval_gate`
- [x] 2.4 Escalate a safety-class attribute or a regulated product to the
      highest severity by measurement, whatever a classifier said; verify via
      `test_the_safety_override_forces_critical`
- [x] 2.5 Recompute the review obligation at the gate from the change set;
      verify via `test_the_gate_recomputes_the_obligation_rather_than_trusting_it`
      and the three-way `test_review_is_required_on_every_measured_ground`
- [x] 2.6 Keep a negative control on the review obligation; verify via
      `test_a_routine_correction_does_not_require_review`
- [x] 2.7 Carry the grounds to the reviewer rather than only into state; verify
      via `test_the_run_reaches_the_gate_carrying_its_review_obligation` and
      `test_an_open_safety_declaration_also_requires_review`
- [x] 2.8 Take the widest reading when no model can argue a narrower one, and
      refuse a reading spanning two products with its reason; verify via
      `test_the_scope_fallback_is_the_widest_reading_not_the_narrowest`,
      `test_a_scope_never_holds_another_products_variants` and
      `test_a_reading_spanning_two_products_is_refused_with_its_reason`
- [x] 2.9 Quote only validated figures in the recommendation, and name only a
      candidate that was validated; verify via
      `test_the_recommendation_quotes_validated_figures`
- [x] 2.10 Publish nothing before a decision, and record the decision and the
      publication with distinguishable provenance; verify via
      `test_nothing_publishes_before_a_decision`,
      `test_a_decision_is_recorded_with_decided_provenance`,
      `test_a_publish_is_recorded_with_committed_provenance` and
      `test_rejection_closes_the_run_without_publishing`
- [x] 2.11 Survive the process being lost and publish once on a redelivered
      decision; verify via `test_a_run_survives_the_process_being_lost`,
      `test_resuming_twice_publishes_once` and
      `test_checkpoint_history_is_available_for_time_travel`
- [x] 2.12 Re-plan rather than fail when a publish is overtaken, bounded by one
      retry; verify via
      `test_publish_is_refused_once_a_later_source_version_is_in_force` and the
      four `tests/test_branches.py` cycle tests
- [x] 2.13 Keep every router a pure function of state; verify via
      `tests/test_branches.py::test_routing_is_deterministic` over all five
      routers
- [x] 2.14 Keep both scope exceptions additive and route an empty candidate list
      onward; verify via `test_a_disagreement_outranks_a_postmortem`,
      `test_both_scope_exceptions_rejoin_the_main_line`,
      `test_a_correction_with_no_candidate_still_reaches_a_reviewer` and
      `test_nothing_publishable_goes_to_the_blocked_review`
- [x] 2.15 Keep the topology from collapsing back to a line; verify via
      `test_the_graph_actually_branches`,
      `test_the_publish_conflict_cycle_exists` and
      `test_the_approval_gate_can_reach_both_outcomes`
- [x] 2.16 Record model spend per node and elapsed time per trace line; verify
      via `test_a_node_records_what_its_model_calls_cost`,
      `test_spend_is_keyed_by_node_so_one_writer_does_not_erase_another` and
      `test_every_trace_line_says_how_long_it_took`
- [x] 2.17 Read a referenced document from where the record says its text is
      kept, and degrade rather than raise on all four ways that can fail;
      verify via `test_a_document_with_no_inline_body_is_read_from_disk` and
      `test_reading_from_disk_never_breaks_a_run`

## 3. Case scoping

- [x] 3.1 Group open signals into per-product cases, worst first and
      independently of arrival order; verify via
      `test_cases_are_ordered_worst_first_and_deterministically`
- [x] 3.2 Keep a correction that names no product on the list as its own case;
      verify via `test_a_correction_that_names_no_product_is_not_dropped`
- [x] 3.3 Put the case filter after extraction, in a node of its own, and stop
      the monitoring step filtering at all; verify via
      `test_a_scoped_run_is_not_contaminated_by_the_documents_it_reads`, which
      seeds no prior run so every correction is still unread
- [x] 3.4 Record every document's facts whatever case is running; verify via the
      recorded-fact assertion in the same test
- [x] 3.5 Report the other open cases without their signal bodies; verify via
      `test_a_scoped_run_decides_one_product_and_reports_the_rest`
- [x] 3.6 Take the worst case open when the caller named none, and say which in
      the trace; verify via `test_a_run_with_no_case_named_takes_the_worst_one_open`
- [x] 3.7 Measure the escalation over the products the case names rather than
      over everything the radius reached; verify via the severity-sentence
      assertion in `test_a_scoped_run_is_not_contaminated_by_the_documents_it_reads`
- [x] 3.8 Leave the first run over a fresh record unscoped on purpose, since
      that pass is what creates the case list; verified by inspection - the
      scoped tests are second runs for exactly this reason

## 4. Re-planning

- [x] 4.1 Re-enter the same thread and carry the case forward explicitly; verify
      via `tests/test_graph.py::test_a_replan_stays_on_the_same_case`
- [x] 4.2 Withdraw a pending approval through the same interrupt a reviewer
      uses, recorded as a decision with an actor and a reason; verify via
      `test_a_correction_of_a_correction_withdraws_the_pending_approval`
- [x] 4.3 Clear the accumulating fields once per revision, at the head of the
      revision; verified by inspection of the latch, exercised by every replan
      test
- [x] 4.4 Carry the superseded readings forward with a fresh change-set id,
      deduplicated by action signature; verify via the five
      `tests/test_replan.py` carry-forward tests
- [x] 4.5 Report what moved, where the superseded reading now ranks, and when
      the recommendation holds; verify via the five `_plan_diff` tests
- [x] 4.6 Narrow the scope when a later version separates the readings, and say
      what that changed; verify via
      `test_a_correction_of_a_correction_narrows_the_scope_and_reports_the_move`

## 5. Peers and toolsets

- [x] 5.1 Replace the four peers with four seams another team could own; verify
      via `tests/test_protocols.py::test_peers_are_split_at_real_seams` and
      `test_every_peer_declares_a_skill_a_caller_could_discover`
- [x] 5.2 Keep the approval gate and publishing off the roster; verify via
      `test_the_approval_gate_is_not_a_peer`
- [x] 5.3 Partition six toolsets by the system that would own them, with every
      tool in exactly one; verify via
      `test_every_tool_belongs_to_exactly_one_toolset`,
      `test_mutating_tools_are_declared_and_belong_to_their_toolset` and
      `test_owner_lookup_covers_every_declared_tool`
- [x] 5.4 Concentrate every write in the publishing toolset, with the tape
      control as the one stated exception; verify via
      `test_the_dangerous_surface_is_one_named_server` and
      `test_commit_is_not_reachable_from_a_read_only_toolset`
- [x] 5.5 Route only read-only tools over the wire, each naming a real toolset;
      verify via `test_only_read_only_tools_are_routed_over_the_wire` and
      `test_every_routed_tool_names_a_real_toolset`
- [x] 5.6 Keep both transports off by default, read per call, and keep an
      unrouted tool working; verify via `test_transport_is_off_unless_asked_for`,
      `test_delegation_is_off_unless_asked_for` and
      `test_an_unrouted_tool_still_runs`
- [x] 5.7 Advertise a peer at the port the server is on, overridable; verify via
      `test_base_url_follows_the_port_the_server_is_on`
- [x] 5.8 Fall back in-process on a degraded peer, record the failure, and clear
      the degraded set on revive; verify via
      `test_a_degraded_peer_falls_back_rather_than_failing` and
      `test_reviving_clears_the_degraded_set`
- [x] 5.9 Return an identical reproducibility hash and measures through the peer
      and in-process; verify via `test_the_validator_peer_is_the_validator`
- [x] 5.10 Make the copy peer deterministic, and refuse an ambiguous literal
      rather than guessing; verify via `test_the_copywriter_works_without_a_gateway`
      and `test_the_copywriter_refuses_an_ambiguous_literal`

## 6. Verification

- [x] 6.1 Run the four graph test files with the gateway pinned to a closed
      port and confirm they pass with no LLM mocking anywhere
- [x] 6.2 Confirm every model call site is inside a handler with a complete
      deterministic answer behind it, by inspection of the seven call sites
- [ ] 6.3 Exercise both protocol transports against a live server rather than
      only their contracts - nothing in `tests/test_protocols.py` spawns a
      server or opens a socket, so the wire itself is only ever exercised by
      hand against the running app
- [ ] 6.4 Cover the multi-pass investigation loop in the scope resolver. With
      the gateway closed the loop exits on the first pass, so the extra rounds
      and the evidence fed back into the second prompt have no automated
      coverage - only the request execution beneath them does
