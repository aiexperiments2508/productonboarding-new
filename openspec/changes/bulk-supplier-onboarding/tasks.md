## 1. One definition of what applies

- [x] 1.1 Extract the `applies_to` prefix predicate to
      `sc.state.baseline.applies_to_category` and have `Baseline.applicable_attrs`,
      `checks.applicable_attributes` and `checks.mandatory_information` call it;
      verify via `tests/test_readiness.py` continuing to pass unchanged
- [x] 1.2 Correct the check counts the prose had left behind - seven
      deterministic and three that read, not six and three - at the definition
      site and in the one string the UI renders

## 2. The data pack

- [x] 2.1 Derive a branch's column set from the attribute registry joined to
      the retailer profile, per taxonomy leaf; verify via
      `tests/test_datapack.py::test_attribute_columns_are_exactly_what_the_registry_says_applies`
- [x] 2.2 Mark a column that covers only some of a branch's categories with the
      categories it covers; verify via
      `tests/test_datapack.py::test_a_saucepan_is_never_asked_for_a_wattage`
- [x] 2.3 Pin the trailing-dot trap so nobody loosens the prefix match; verify
      via `tests/test_datapack.py::test_asking_by_branch_key_rather_than_by_leaf_finds_almost_nothing`
- [x] 2.4 Take image columns from `profile.branches[*].required_media` and
      nowhere else; verify via
      `tests/test_datapack.py::test_changing_the_profile_changes_the_pack`
- [x] 2.5 Write CSV and a pipe-delimited flat file with the standard library,
      carrying three header rows; verify via
      `tests/test_datapack.py::test_csv_round_trips_through_its_own_reader`
- [x] 2.6 Write the workbook with `openpyxl`, keeping the GTIN column text and
      offering a dropdown where the catalog has a settled vocabulary; verify via
      `tests/test_datapack.py::test_the_workbook_keeps_the_gtin_column_text`
- [x] 2.7 Write the Word specification with `zipfile` and no compiled
      dependency, naming every attribute and its label; verify via
      `tests/test_datapack.py::test_the_specification_is_a_readable_docx_naming_every_attribute`
- [x] 2.8 Write a JSON Schema whose `category` enum is the branch's leaves;
      verify via `tests/test_datapack.py::test_json_schema_enumerates_the_categories_and_types`
- [x] 2.9 Fill every branch's example from one supplier's own lines, with one
      deliberately broken row per representable defect and a record of the two
      that a file cannot demonstrate; verify via
      `tests/test_datapack.py::test_every_representable_defect_is_shown_or_explained`
- [x] 2.10 Never demonstrate a defect by blanking a safety-class field; verify
      via `tests/test_datapack.py::test_the_example_never_blanks_a_safety_field_to_make_a_point`
- [x] 2.11 Add `scripts/build_datapack.py`, `requirements-datapack.txt`, the
      gitignore entry and the startup step; degrade to four formats without
      `openpyxl` rather than failing

## 3. The bundle intake

- [x] 3.1 Expose `submit_product_feed` only where the manifest says a system
      accepts both attribute rows and imagery; verify via
      `tests/test_bundle_intake.py::test_only_a_system_that_takes_rows_and_images_gets_the_bulk_door`
- [x] 3.2 Read one data file and an `images/` folder from a .zip, refusing a
      traversal path, a declared bomb, two data files and a non-zip by name;
      verify via the four refusal tests in `tests/test_bundle_intake.py`
- [x] 3.3 Assert rows against a new version of the supplier's own document;
      verify via
      `tests/test_bundle_intake.py::test_the_document_is_a_new_version_of_the_suppliers_own`
- [x] 3.4 Carry a top-level `entities` on every row and image event; verify via
      `tests/test_bundle_intake.py::test_every_row_event_carries_a_top_level_entities`
- [x] 3.5 Append the whole submission in one transaction with one arrival
      batch; verify via
      `tests/test_bundle_intake.py::test_one_upload_is_one_arrival_batch`
- [x] 3.6 Reject a cell without rejecting its row, and count the two
      separately; verify via
      `tests/test_bundle_intake.py::test_a_bad_cell_loses_the_cell_and_not_the_row`
- [x] 3.7 Report an unrecognised column without failing the bundle; verify via
      `tests/test_bundle_intake.py::test_an_unknown_column_is_reported_and_does_not_fail_the_bundle`
- [x] 3.8 Refuse another supplier's SKU by row, and hold an unknown SKU as a
      proposal with its own submission so the existing reviewer path accepts
      it; verify via the two SKU tests in `tests/test_bundle_intake.py`
- [x] 3.9 Serve a template through MCP so the vendor portal never fetches this
      platform directly; verify via `tests/test_app_boundary.py`

## 4. The pass and the report

- [x] 4.1 Walk a batch one product at a time in file order, streaming over POST
      like the run stream; verify via
      `tests/test_onboarding.py::test_the_pass_walks_every_product_once_in_file_order`
- [x] 4.2 Resolve the path the map lights on the server; verify via
      `tests/test_onboarding.py::test_every_product_carries_the_path_the_map_lights`
- [x] 4.3 Count with `rollup.tally` and propagate `checks_complete`; verify via
      `tests/test_onboarding.py::test_the_tally_is_the_sum_of_the_verdicts_it_counted`
      and `::test_a_narrow_assessment_is_reported_as_narrow`
- [x] 4.4 Keep the pacing incapable of reaching a result; verify via
      `tests/test_onboarding.py::test_the_pace_cannot_reach_a_result`
- [x] 4.5 Count proposed new lines apart from assessed products and say so on
      the report
- [x] 4.6 Light the product being assessed distinctly from an event pulse, and
      leave the decided ones showing their verdict

## 5. The bounded fill

- [x] 5.1 Never make a safety-class gap a candidate; verify via
      `tests/test_onboarding.py::test_a_safety_class_gap_is_never_a_candidate`
- [x] 5.2 Make candidacy track retrieval exactly, so a gap with no passage is
      never counted fixable; verify via
      `tests/test_onboarding.py::test_candidacy_tracks_retrieval_exactly`
- [x] 5.3 Require an actor; verify via
      `tests/test_onboarding.py::test_applying_needs_an_actor`
- [x] 5.4 Write every fill INFERRED through `ingest.record_attribute`; verify
      via `tests/test_onboarding.py::test_anything_written_is_inferred_and_never_recorded`
- [x] 5.5 Write no approval, no reservation and no committed action; verify via
      `tests/test_onboarding.py::test_applying_writes_no_approval_and_no_reservation`
- [x] 5.6 With no gateway, fill nothing and explain every gap; verify via
      `tests/test_onboarding.py::test_with_no_gateway_nothing_is_filled_and_every_gap_is_explained`
- [x] 5.7 Audit every apply, including one that filled nothing

## 6. Surfaces

- [x] 6.1 Add the bundle strip and the quick action to the Ingest Fabric
- [x] 6.2 Add the Supplier Intake section, reachable from the fabric
- [x] 6.3 Add the template download and the archive upload to the vendor
      portal, both crossing MCP
- [x] 6.4 Update the README, `.env.example` and `startup.bat`
