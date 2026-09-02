## 1. Rules first, and the word that goes with it

- [x] 1.1 Run the rule checks alone by default and the reading checks on
      request, so opening a product costs no model call
- [x] 1.2 Report a rule-only assessment as narrow, always; verify via
      `tests/test_readiness.py::test_the_rule_checks_alone_always_report_themselves_as_narrow`
- [x] 1.3 Reserve "ready" for a complete assessment and give a narrow one its
      own weaker wording; verify via
      `tests/test_readiness.py::test_a_narrow_assessment_can_still_be_ready_which_is_why_it_must_say_so`
- [x] 1.4 Leave a finding's weight untouched by the assessment being narrow;
      verify via
      `tests/test_readiness.py::test_findings_are_not_weakened_by_the_assessment_being_narrow`
- [x] 1.5 Put the rule in `frontend/src/lib/verdict.ts` and have all five
      verdict-rendering surfaces ask it
- [x] 1.6 Refuse to build a staging preview from a narrow verdict

## 2. The cost of opening a product

- [x] 2.1 Cache `gateway.embed`, the one model call in the platform that was
      not cached
- [x] 2.2 Run the reading checks concurrently rather than in sequence
- [x] 2.3 Build the overlay once per request rather than once per product
      assessed
- [x] 2.4 Stop the list route serialising records it then discards
- [x] 2.5 Debounce the search box

## 3. Imagery that is either there or reported missing

- [x] 3.1 Draw a deterministic asset per image the catalog holds, from the
      seed; verify via
      `tests/test_media.py::test_every_asset_the_catalog_holds_has_a_file_behind_it`
- [x] 3.2 Leave the deliberate gaps with no file, so a gap is a gap in the data
      and not a missing draw; verify via
      `tests/test_media.py::test_the_deliberate_gaps_have_no_file_either`
- [x] 3.3 Mount the assets ahead of the application catch-all, so a held image
      is served as an image and a missing one is a 404; verify via
      `tests/test_media.py::test_a_held_image_is_served_as_an_image` and
      `::test_a_missing_image_is_a_404_and_not_the_application_shell`
- [x] 3.4 Read the media strip and the readiness finding off one source; verify
      via `tests/test_media.py::test_the_media_strip_reports_the_gap_the_finding_reports`
- [x] 3.5 Name the system that owes a missing role; verify via
      `tests/test_media.py::test_a_missing_slot_names_who_owes_it`
- [x] 3.6 Report no gap for a category that requires no imagery; verify via
      `tests/test_media.py::test_a_category_that_needs_no_imagery_is_not_reported_as_missing_it`

## 4. Accounting for a finding

- [x] 4.1 Join a finding to what the estate declares about the system that
      caused it, and name the team that owns it; verify via
      `tests/test_rca.py::test_a_cause_names_the_system_and_the_team_that_owns_it`
- [x] 4.2 Name only a defect that system actually declares; verify via
      `tests/test_rca.py::test_the_defect_named_is_one_that_system_actually_declares`
- [x] 4.3 Produce an account with no model and say that it did; verify via
      `tests/test_rca.py::test_a_cause_is_produced_with_no_model_and_says_so`
- [x] 4.4 Run after the verdict with no route back to it; verify via
      `tests/test_rca.py::test_explaining_a_product_cannot_change_its_verdict`
- [x] 4.5 Offer no explanation for a clean product; verify via
      `tests/test_rca.py::test_a_clean_product_is_offered_no_explanation`
- [x] 4.6 Explain the worst finding first and count the ones left out rather
      than dropping them; verify via
      `tests/test_rca.py::test_the_worst_finding_is_explained_first` and
      `::test_the_findings_it_leaves_out_are_counted_rather_than_dropped`

## 5. One reader for the tape's dialects

- [x] 5.1 Make `sc/estate/reach.py` the single resolver, understanding every
      spelling the tape uses; verify via
      `tests/test_estate.py::test_the_payload_reader_understands_every_spelling_the_tape_uses`
- [x] 5.2 Share it with the arrival window, so the map and the window cannot
      disagree about who has been heard from
- [x] 5.3 Draw an edge for every system that has delivered; verify via
      `tests/test_estate.py::test_every_system_that_has_delivered_draws_an_edge`
- [x] 5.4 Add a transport and logistics system to the manifest, which had no
      such thing

## 6. A map that can be read

- [x] 6.1 Add a scoped map route - ten products by default, with search and
      facets - and leave `/api/network` unscoped, because a blast radius
      showing ten of a hundred and fifty is wrong
- [x] 6.2 Grow the frame with the busiest tier and report "+N not drawn" rather
      than truncating silently
- [x] 6.3 Coalesce the catalog refetch, which had been running on every
      released event
- [x] 6.4 Give panels their own overflow so the shell stops being the scroller
      and the page header stops scrolling away

## 7. A catalog worth rolling up

- [x] 7.1 Generate 150 products, 301 variants and 5,211 events across 1 July to
      31 August 2026, split 58% clear / 34% returned to source / 8% blocked
- [x] 7.2 Draw the background from its own PRNG stream so the six hero arcs do
      not move
- [x] 7.3 Declare the background's damage in a registry the generator asserts
      against; verify via
      `tests/test_golden.py::test_key_covers_every_material_document_and_invents_none`
- [x] 7.4 Make the demonstration's central ambiguity an authored arc event
      rather than a coincidence of routine traffic

## 8. Product 360's filters

- [x] 8.1 Measure the arrival window on the simulated clock, because the
      arrival timestamp is real wall clock and would have returned nothing
- [x] 8.2 Add supplier and category facets that narrow without reordering;
      verify via `tests/test_product360.py::test_filters_narrow_without_reordering`
- [x] 8.3 Page the list without repeating or dropping a row; verify via
      `tests/test_product360.py::test_paging_walks_the_whole_list_without_repeating_itself`
- [x] 8.4 Roll up what went downstream clean against what went back to source,
      broken down by who has to fix it

## 9. Two defects and a lock file

- [x] 9.1 Make the record's instant survive a tape that has released nothing,
      which is the state a freshly reset database is in
- [x] 9.2 De-duplicate a gateway outage on something other than the text, since
      a refused connection and an open circuit are phrased differently
- [x] 9.3 Stop tracking the editor lock file that should never have been
      committed
