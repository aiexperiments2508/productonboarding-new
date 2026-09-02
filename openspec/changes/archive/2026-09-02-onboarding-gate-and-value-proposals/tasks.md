## 1. The policy check

- [x] 1.1 Add `readiness.reading.policy_conformance`, retrieving `POLICY`
      passages for the record's category and reporting breaches of the
      retailer's own written policy; verify via
      `tests/test_readiness.py::test_the_policy_check_is_one_of_the_reading_four`
- [x] 1.2 Report its findings as `OPEN` and never `BLOCKING`, so that
      "we will not sell it like this" cannot be read as "it may not lawfully be
      sold"; verify via
      `tests/test_readiness.py::test_a_policy_breach_is_open_and_never_blocking`
- [x] 1.3 Drop a candidate finding whose citation is not one of the passages
      supplied, on the same gate `enrich` uses; verify via
      `tests/test_readiness.py::test_the_policy_check_drops_a_candidate_it_cannot_cite`
- [x] 1.4 Return no findings and `checks_complete=False` when the gateway is
      unreachable, so a narrower assessment is never reported as a clean one

## 2. The gate

- [x] 2.1 Add `sc/onboarding/gate.py`, partitioning one `readiness.assess`
      summary by the check that raised each finding; no query, no model, no
      clock
- [x] 2.2 Define the gate as a set of check names - the saleability set plus
      `policy_conformance` - rather than as a severity; verify via
      `tests/test_onboarding.py::test_the_gate_is_named_checks_and_never_a_severity`
- [x] 2.3 Name the authority that stopped a product, regulation ranking above
      policy, and compose the sentence the supplier is given
- [x] 2.4 Run the gate before anything else in the onboarding pass, and collect
      no gaps for a stopped product, so that nothing is retrieved or proposed
      for one by construction; verify via
      `tests/test_onboarding.py::test_a_product_the_gate_stops_is_not_onboarded`
- [x] 2.5 Keep the findings onboarding is about out of the gate's own count;
      verify via
      `tests/test_onboarding.py::test_the_gate_does_not_swallow_the_findings_onboarding_is_about`
- [x] 2.6 Count a stopped product as stopped in the batch report; verify via
      `tests/test_onboarding.py::test_a_stopped_product_is_counted_as_stopped`

## 3. What is already on file

- [x] 3.1 Add `sc/onboarding/history.py` returning siblings, category
      convention and past decisions as priors, each with its support count and
      the row it came from
- [x] 3.2 Need no gateway for any of it; verify via
      `tests/test_onboarding.py::test_a_sibling_value_is_found_without_a_gateway`
- [x] 3.3 Name the value a prior found, so the reviewer reads the evidence
      rather than a score; verify via
      `tests/test_onboarding.py::test_a_prior_names_the_value_it_found`
- [x] 3.4 Read a settled decision back as a prior for the next proposal on the
      same attribute; verify via
      `tests/test_onboarding.py::test_a_settled_decision_becomes_a_prior_for_the_next_one`

## 4. The proposal and its score

- [x] 4.1 Add `sc/onboarding/suggest.py`, composing one proposal from a
      validated passage fill and the priors, and writing nothing
- [x] 4.2 Discount a model's self-reported confidence to a fraction of its
      claim and count it as one input among things already on file
- [x] 4.3 Weight disagreement heavier than agreement, prior for prior; verify
      via `tests/test_onboarding.py::test_disagreement_costs_more_than_agreement_pays`
- [x] 4.4 Refuse to let a prior too thin to support a value refute one; verify
      via `tests/test_onboarding.py::test_a_prior_too_thin_to_support_a_value_is_too_thin_to_refute_one`
      and `::test_a_category_convention_does_weigh_in_both_directions`
- [x] 4.5 Score a safety-class attribute zero and say so in the reasons; verify
      via `tests/test_onboarding.py::test_a_safety_class_proposal_never_routes_autonomously`
- [x] 4.6 Cap priors alone below the default threshold, so an offline pass
      produces questions rather than silent facts; verify via
      `tests/test_onboarding.py::test_priors_alone_do_not_reach_the_default_threshold`
- [x] 4.7 Have every reason state what it contributed; verify via
      `tests/test_onboarding.py::test_every_reason_says_what_it_contributed`

## 5. Routing and the threshold

- [x] 5.1 Add `sc/onboarding/decide.py` holding the autonomy threshold in
      `runtime_config`, clamped so it can be neither zero nor above one
- [x] 5.2 Take the proposal object rather than a confidence, and refuse a
      safety-class attribute and an uncorroborated proposal before consulting
      the number; verify via
      `tests/test_onboarding.py::test_a_lone_source_is_refused_structurally_and_not_by_arithmetic`
- [x] 5.3 Route on the threshold for everything else; verify via
      `tests/test_onboarding.py::test_the_threshold_decides_everything_else`
- [x] 5.4 Audit every move of the threshold against a named actor; verify via
      `tests/test_onboarding.py::test_moving_the_threshold_is_audited`
- [x] 5.5 Refuse a threshold that would mean never asking; verify via
      `tests/test_onboarding.py::test_the_threshold_cannot_be_set_to_never_asking`

## 6. The queue and the decision

- [x] 6.1 Add `onboarding_suggestions` to the schema with its indexes, and
      upsert one live proposal per field per bundle; verify via
      `tests/test_onboarding.py::test_re_assessing_a_batch_does_not_reopen_a_settled_question`
- [x] 6.2 Write no fact for a queued proposal until somebody decides; verify
      via `tests/test_onboarding.py::test_a_queued_proposal_writes_no_fact_until_somebody_decides`
- [x] 6.3 Write an autonomous fill `INFERRED` through `ingest.record_attribute`
      with its confidence and citation; verify via
      `tests/test_onboarding.py::test_an_autonomous_fill_is_inferred_and_a_decided_one_is_not`
- [x] 6.4 Write an approval as `DECIDED`, named to the person; verify via
      `tests/test_onboarding.py::test_approving_writes_the_value_as_decided_and_not_as_inferred`
- [x] 6.5 Write the reviewer's own value on a rectification; verify via
      `tests/test_onboarding.py::test_rectifying_writes_the_reviewers_value_rather_than_the_proposal`
- [x] 6.6 Write nothing on a rejection and say where the value has to come
      from; verify via
      `tests/test_onboarding.py::test_rejecting_writes_nothing_and_names_where_the_value_comes_from`
- [x] 6.7 Demand a name on every decision and refuse a second decision on a
      settled proposal; verify via
      `tests/test_onboarding.py::test_a_decision_needs_a_name` and
      `::test_a_decided_proposal_cannot_be_decided_again`
- [x] 6.8 Reach the audit ledger from every decision; verify via
      `tests/test_onboarding.py::test_every_decision_reaches_the_ledger`
- [x] 6.9 Survive an autonomous fill that carries no citation on every surface
      that renders the audit line; verify via
      `tests/test_onboarding.py::test_an_autonomous_fill_built_from_priors_carries_no_citation`
- [x] 6.10 Expose the threshold, the queue and the decision over the HTTP API,
      each demanding an actor

## 7. Rewind, and the deliberate act

- [x] 7.1 Scope `tape.reset` to the recorded flight so a rewind cannot retract
      a supplier's submission
- [x] 7.2 Add `tape.clear`, removing the portal events, the arrivals that
      carried them and the submission records; verify via
      `tests/test_live_lane.py::test_clearing_removes_the_portal_traffic_and_rewinds_the_tape`
- [x] 7.3 Leave the facts those submissions recorded, and say so where the
      button is; verify via
      `tests/test_live_lane.py::test_clearing_leaves_the_facts_a_submission_recorded`
- [x] 7.4 Clear both ingest watermarks, so a submission after a clear is still
      ingested; verify via
      `tests/test_live_lane.py::test_a_submission_after_a_clear_is_still_ingested`
- [x] 7.5 Re-anchor the live instant, so a later submission cannot tie with a
      surviving fact and lose by id; verify via
      `tests/test_live_lane.py::test_a_clear_does_not_let_a_later_submission_tie_with_a_surviving_fact`
- [x] 7.6 Take the open questions and leave the answered ones; verify via
      `tests/test_live_lane.py::test_clearing_takes_the_open_questions_and_leaves_the_answered_ones`

## 8. The screens

- [x] 8.1 Move the estate panel and the arrivals machinery to System Control,
      and the supplier bundle to Supplier Intake
- [x] 8.2 Put what is in force into a rail shut by default, whose handle
      carries the open-case count and the severity of the worst one
- [x] 8.3 Make System Control tabbed rather than a column of panels, and put
      Clear on its replay tab beside the sentence naming what it leaves behind

## 9. The suite

- [x] 9.1 Run pytest in parallel distributed by file, because each module owns
      its database
- [x] 9.2 Make the accepted-lines extension per-module for the same reason,
      closing the pre-existing leak
