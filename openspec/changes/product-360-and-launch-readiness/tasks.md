## 1. The identifiers and the imagery

- [x] 1.1 Give every variant a SKU, distinct across the catalogue, hand-authored
      rather than derived from the internal key; verify via
      `tests/test_product360.py::test_every_variant_has_a_distinct_sku`
- [x] 1.2 Hold media as typed assets with a role from a declared set, so a
      missing hero shot is distinguishable from one filed under a name nobody
      checked; verify via
      `tests/test_product360.py::test_media_carries_a_declared_role`
- [x] 1.3 Leave two products deliberately short of a required image, named in
      the generator rather than sprinkled by the PRNG, so the check has
      something real to find and a demo cannot rehearse clean; verify via
      `tests/test_readiness.py::test_missing_media_is_found_by_role`

## 2. Finding a product

- [x] 2.1 Match on SKU, internal identifier and name, ranking an exact
      identifier first; verify via
      `tests/test_product360.py::test_an_exact_identifier_outranks_a_name_match`
- [x] 2.2 Answer an unmatched query with an empty list rather than an error;
      verify via
      `tests/test_product360.py::test_a_search_with_no_match_is_empty_not_an_error`
- [x] 2.3 List everything for an empty query, so the view does not open blank;
      verify via `tests/test_product360.py::test_an_empty_query_lists_everything`

## 3. The record

- [x] 3.1 Assemble one product once and hand it to every check, so nine checks
      cannot disagree about what is in force; verify by inspection of
      `sc/readiness/record.py`
- [x] 3.2 Carry the document, the provenance class and the carrying system on
      every value, with an explicit absence where the carrier is unknown;
      verify via
      `tests/test_product360.py::test_every_value_names_its_document_and_carrier`
- [x] 3.3 Keep the values that lost a precedence contest, because a settled
      disagreement is settled rather than absent; verify via
      `tests/test_product360.py::test_a_settled_disagreement_is_still_visible`

## 4. The six checks decided by rules

- [x] 4.1 Applicable attributes, channel-mandatory information, declared types,
      required media by role, source contradiction and forbidden content, all
      without a model; verify via
      `tests/test_readiness.py::test_the_deterministic_checks_need_no_model`
- [x] 4.2 Read the same channel rule rows the publish-time validator reads, and
      name the rule on the finding; verify via
      `tests/test_readiness.py::test_readiness_and_publication_read_one_rule_table`
- [x] 4.3 Suppress a rule that cannot bind on this category, so a snack is never
      held for missing a wattage; verify via
      `tests/test_readiness.py::test_a_check_does_not_fire_on_an_attribute_the_category_never_has`
- [x] 4.4 Name the system on every finding that has one, so a return is
      actionable; verify via
      `tests/test_readiness.py::test_an_open_finding_returns_the_product_to_its_source`

## 5. The three that may read

- [x] 5.1 Saleability, internal contradiction and semantic staleness, each
      producing a candidate that must cite a retrieved passage; verify via
      `tests/test_readiness.py::test_an_uncited_candidate_finding_is_dropped`
- [x] 5.2 Drop an uncited candidate rather than admitting it on confidence -
      the harness already measured this gateway stating 0.95 and being right
      0.76 of the time; verify the same test
- [x] 5.3 Report that the reading checks did not run rather than presenting a
      narrower result as a clean one; verify via
      `tests/test_readiness.py::test_an_assessment_without_a_model_says_so`
- [x] 5.4 Carry that caveat through the API into the UI; verify by opening a
      product with the gateway unreachable and reading the banner

## 6. The verdict

- [x] 6.1 Derive the outcome by counting findings, with no score, percentage or
      grade anywhere in the response; verify via
      `tests/test_readiness.py::test_readiness_reports_findings_and_no_score`
- [x] 6.2 Let only a saleability finding block, and never by accumulation;
      verify via `tests/test_readiness.py::test_only_a_saleability_finding_blocks`
- [x] 6.3 Keep the covering note out of the decision; verify via
      `tests/test_readiness.py::test_the_note_cannot_change_the_verdict`
- [x] 6.4 Order findings so two assessments read the same way; verify via
      `tests/test_readiness.py::test_an_assessment_is_reproducible`

## 7. The staging page

- [x] 7.1 Render only for a ready record, refusing with the verdict and the
      findings otherwise; verify via
      `tests/test_preview.py::test_a_blocked_record_is_refused_not_rendered`
- [x] 7.2 Show only figures the record holds, unchanged; verify via
      `tests/test_preview.py::test_every_figure_on_the_page_is_in_the_record`
- [x] 7.3 Show only claims the substantiation table supports; verify via
      `tests/test_preview.py::test_an_unsubstantiated_claim_does_not_reach_the_page`
- [x] 7.4 Put the preview behind the reviewer authorisation the approval gate
      uses - which is a named actor and nothing more, because neither route
      authenticates and this system has no identity provider anywhere. A
      boundary stricter here would protect unpublished copy more carefully than
      the decision to publish it; verify via
      `tests/test_preview.py::test_a_preview_without_a_name_is_refused` and
      `tests/test_preview.py::test_the_preview_asks_for_no_more_than_an_approval_does`
- [x] 7.5 Record who previewed what, rendered or refused, so "who saw this
      before it launched" is answerable; verify via
      `tests/test_preview.py::test_a_preview_is_recorded_against_the_person_who_asked`
      and `tests/test_preview.py::test_a_refused_preview_is_recorded_too`

## 8. The differentiator

- [x] 8.1 Ground it on an attribute the record holds and a passage the corpus
      carries, both required; verify via
      `tests/test_preview.py::test_a_differentiator_names_attributes_and_cites_a_passage`
- [x] 8.2 Withhold it rather than showing it on one leg; verify via
      `tests/test_preview.py::test_an_ungrounded_differentiator_is_withheld`
- [x] 8.3 Check forbidden content on what came back rather than requesting it in
      the prompt; verify via `tests/test_preview.py::test_a_forbidden_claim_is_rejected`
- [x] 8.4 Resolve the model's named attributes against paths and labels both.
      The first implementation matched paths only, the model answered "Sound
      level" rather than `specs.noise_db`, and a correctly grounded
      differentiator was rejected on every request while the templated form was
      silently used - a gate that rejects the right answer fails in the
      direction that looks like success; verify by opening a staging page
      against a live gateway and confirming `written_by_model`
- [x] 8.5 Produce one by template with no gateway, from the same two grounds;
      verify via `tests/test_preview.py::test_the_differentiator_survives_having_no_model`

## 9. The surface

- [x] 9.1 Add the routes, each delegating rather than re-deriving; verify via
      `tests/test_product360.py::test_the_api_product_reads_are_the_pipelines_own`
- [x] 9.2 Add the section, with the findings, the record and the staging page;
      verify by opening it
- [x] 9.3 Show the carrying system beside every value and the grounds beside the
      differentiator, so a reviewer can trace a claim without leaving the page;
      verify by opening a ready product
