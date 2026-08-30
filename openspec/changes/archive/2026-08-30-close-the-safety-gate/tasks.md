## 1. One resolver for entity to listings

- [x] 1.1 Add a resolver that answers which listings an entity id reaches at
      whatever level it names - a listing is itself, a variant is its listings,
      a product is every variant's listings, an unknown id is nothing; verify
      the product case reaches both variants' listings through
      `tests/test_validator.py::test_low_confidence_on_a_safety_attribute_blocks_every_listing[PRD-02]`
- [x] 1.2 Resolve the fail-closed safety gate's listings through it, so a
      low-confidence safety value recorded against a product blocks every
      channel; verify the parameterised regression asserts five channels, the
      violation's entity id and `feasible = False` on both `VAR-02A` and
      `PRD-02`, and confirm it fails on the product case before the fix
- [x] 1.3 Resolve readiness scoring through it, so a product-level block is not
      reported as 100% of listings ready beside a result that is not
      publishable; verify `listings_ready_pct == 0.0` in the same test
- [x] 1.4 Resolve the scope walk and the republish-step count through it; verify
      the untouched catalog and the existing validator suite are unchanged
      (`tests/test_validator.py` passes with no baseline KPI moving)
- [x] 1.5 Resolve the reviewer's change summary and its violation-to-listing
      lookup through the same function rather than a second copy; verify by
      importing the validator's resolver in the graph nodes and running
      `tests/test_graph.py`

## 2. The freeze window

- [x] 2.1 Carry the version a listing last went out on into the validator's
      in-force layer, defaulting to the catalog value, and into its digest;
      verify determinism still holds via
      `tests/test_validator.py::test_overlay_digest_is_stable`
- [x] 2.2 Raise a blocking violation where a listing on a channel that publishes
      something irreversible stands on a superseded version, naming the versions
      and the documented lead time; verify via
      `test_a_frozen_channel_reports_the_artefact_left_on_a_superseded_version`
- [x] 2.3 Make regenerating the copy deliberately not clear it, and republishing
      or withholding clear it; verify via
      `test_regenerating_the_copy_does_not_clear_the_freeze_window`,
      `test_republishing_the_listing_clears_the_freeze_window` and
      `test_withholding_the_listing_is_the_reprint_decision`
- [x] 2.4 Raise nothing on a reversible channel and nothing on a listing that
      has never been published; verify via
      `test_a_reversible_channel_is_not_held_to_the_freeze_window` and
      `test_a_listing_that_has_never_gone_to_press_has_nothing_to_be_stale`
- [x] 2.5 Record the version each listing goes to press on when a publish
      commits, taking the latest version where two actions republish one
      listing and writing none for a withheld listing, and read it back through
      the in-force layer; verify by inspection of the commit and overlay paths
- [ ] 2.6 Cover the round trip with a test: commit a publish, rebuild the
      in-force layer from the store, and assert the freeze-window rule sees the
      version that publish recorded. The rule is covered at validation time and
      the write path is not covered at all.

## 3. Rollback retracts what was published

- [x] 3.1 On rollback, assert a superseding fact for every unsuperseded fact the
      publish recorded, restoring what it displaced, valid from the rollback
      onwards; verify via
      `tests/test_orchestration.py::test_rollback_retracts_what_was_published`
- [x] 3.2 Keep the read as of the moment the content was live returning what
      went out; verify in the same test
- [x] 3.3 Push the rollback instant past the latest row it retracts so a
      same-tick replay rollback is not lost to the store's ordering; verify the
      retraction is visible in the same test, which commits and rolls back
      inside one replay tick
- [x] 3.4 Skip rows already superseded so a repeated rollback retracts nothing
      twice; verify via `test_a_repeated_rollback_retracts_nothing_twice`
- [x] 3.5 Report the retracted count from the call and in the audit entry
      alongside the actions reversed; verify via the returned `retracted` list
      in `test_rollback_retracts_what_was_published`

## 4. What the code promised and did not do

- [x] 4.1 Document `Channel.freeze_days` and `Listing.published_version` as what
      they now are rather than what they promised, including that no press date
      exists in the catalog; verify by inspection
- [x] 4.2 Promote the source-precedence policy to one function both halves of
      the provenance split import; verify via
      `tests/test_ingest.py::test_both_halves_of_the_provenance_split_enforce_the_same_policy`,
      which asserts the two names are the same object
- [x] 4.3 Correct the module docstring still routing a reader to a toolset
      deleted eight commits earlier; verify by inspection

## 5. Verification

- [x] 5.1 Confirm the whole suite passes with the gateway unreachable and no
      baseline KPI moved (304 passed, 6 skipped)
- [x] 5.2 Close `deterministic-decision-core` task 6.3 - the safety gate now
      resolves product-level facts
- [x] 5.3 Close `deterministic-decision-core` task 6.4 - a rollback no longer
      leaves the published value standing in an as-of read
- [ ] 5.4 Close the residual this change records: give the rule, claim and
      allergen checks product-to-variant inheritance with an explicit layer
      precedence, so a high-confidence product-level allergen is
      declaration-checked before scope resolution runs
