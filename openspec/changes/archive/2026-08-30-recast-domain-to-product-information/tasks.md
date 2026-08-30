## 1. Domain contracts

- [x] 1.1 Keep the provenance half of the contract module unchanged - the five
      provenance kinds, the bitemporal fact, the event envelope, approvals, the
      audit entry, retrieval chunks and replay control - and verify by running
      `tests/test_bitemporal.py` unedited (9 passed)
- [x] 1.2 Replace network, lane, BOM and SKU with catalog entities - Product,
      Variant, Channel, ChannelRule, Listing, ContentAsset, SourceDoc,
      AttributeDef - and verify the module imports and the contract enums cover
      the seven channel rule kinds and six action kinds
- [x] 1.3 Replace the plan delta with a change set over six action kinds, and
      restate the KPI set in fields affected, stale assets, blocked channels and
      listing readiness; verify via the KPI fields asserted in
      `tests/test_validator.py::test_untouched_catalog_validates_clean`
- [x] 1.4 Add `SourceRef` so a proposed change names the document, version and
      excerpt it was read from; verify via the citation checks in
      `tests/test_validator.py::test_an_uncited_change_is_not_publishable`
- [x] 1.5 Add a deterministically assembled change summary line - source, old
      value, new value, impacted outputs - so no consumer parses prose; verify
      via `tests/test_propagation.py::test_corrections_in_force_show_on_the_map_with_their_source`
- [x] 1.6 Add `AttributeDef.safety_class` as the switch a fail-closed rule
      reads; verify via `tests/test_propagation.py::test_variant_diff_carries_the_label_and_the_safety_flag`
- [x] 1.7 Reframe capacity reservations as publish locks keyed channel + product
      for a batch date, keeping the partial unique index that makes them
      exclusive; verify via `tests/test_orchestration.py::test_two_hard_locks_on_the_same_channel_product_day_conflict`

## 2. The bitemporal record

- [x] 2.1 Confirm the two-axis read - validity interval and recording instant
      queried independently - still holds against the new domain, verified by
      `tests/test_bitemporal.py::test_correction_is_invisible_before_it_arrives`
- [x] 2.2 Confirm greatest-recording-instant-wins and one-winning-row-per-entity
      -and-attribute, verified by `test_latest_correction_wins_among_several`
      and `test_get_many_returns_one_winning_row_per_entity_attr`
- [x] 2.3 Confirm corrections insert superseding rows and inherit the validity
      window, verified by `test_correction_inherits_validity_window_unless_overridden`
- [x] 2.4 Confirm lineage, late-arrival enumeration and the separate provenance
      counts, verified by `test_lineage_walks_back_to_the_original`,
      `test_corrections_since_surfaces_late_arrivals` and
      `test_provenance_kinds_are_counted_separately`

## 3. Seed pack and correction tape

- [x] 3.1 Generate a catalog of one air purifier with two variants and one
      packaged snack across six channels, using the local PRNG so the pack is
      byte-identical per `DATA_SEED`; verify by regenerating twice and comparing
- [x] 3.2 Keep entity ids as hardcoded constants so the hand-authored corpus can
      name them literally; verify the corpus references resolve via
      `tests/test_rag.py::test_incident_metadata_is_retained`
- [x] 3.3 Assert in the generator that the untouched catalog validates with zero
      violations and exit non-zero otherwise; verify via
      `tests/test_validator.py::test_untouched_catalog_validates_clean`
- [x] 3.4 Seed both purifier variants at 45 W and 38 dB so the baseline is
      internally consistent and still wrong; verify via
      `tests/test_propagation.py::test_variant_diff_marks_exactly_the_attributes_that_differ`
- [x] 3.5 Author the six-arc, 56-day tape - the brief's two scenarios plus a
      withdrawn provisional notice, a source disagreement, a feed rejection and
      a correction that is itself corrected; verify the tape loads and releases
      via the `tests/test_ingest.py` fixture

## 4. Corpus

- [x] 4.1 Replace the SOP, contract and incident sets with fifteen authored
      documents in four types - STANDARD, CHANNEL, POLICY, POSTMORTEM; verify
      via `tests/test_rag.py::test_index_covers_the_whole_corpus`
- [x] 4.2 Write the claim-substantiation table into the content standards
      document so the rule the engine enforces is also readable prose; verify it
      is retrievable by name via `tests/test_rag.py::test_lexical_golden_set`
- [x] 4.3 Write the source-precedence order into the correction-handling policy,
      recency never overriding precedence; verify it is retrievable by name via
      `tests/test_rag.py::test_lexical_golden_set`
- [x] 4.4 Write four postmortems as genuine precedent for the arcs they precede;
      verify each produces chunks with its entities via
      `tests/test_rag.py::test_every_corpus_document_produces_chunks` and
      `test_incident_metadata_is_retained`

## 5. Retrieval

- [x] 5.1 Teach the retrieval layer the four reference document types and keep
      correspondence opt-in; verify via
      `tests/test_rag.py::test_correspondence_is_excluded_by_default`
- [x] 5.2 Confirm the identifier-preserving tokenizer needed no change by
      running it against the new identifiers; verified by
      `test_identifiers_survive_tokenisation`, `test_identifier_parts_are_also_indexed`
      and `test_bm25_separates_similar_identifiers`
- [x] 5.3 Retarget the lexical golden set at the new corpus, five queries naming
      channel codes, rejection codes, the precedence policy, the freeze window
      and the claim table; verify via `tests/test_rag.py::test_lexical_golden_set`
- [x] 5.4 Retarget the paraphrase golden set and keep it skipping with a reason
      when no embedding matrix exists; verify via
      `tests/test_rag.py::test_hybrid_golden_set` (skipped without a matrix)
- [x] 5.5 Confirm citations remain followable to a source path that exists;
      verify via `tests/test_rag.py::test_citations_are_followable`

## 6. Verification

- [x] 6.1 Run `tests/test_bitemporal.py` and `tests/test_rag.py` together and
      confirm they pass with no gateway reachable (30 passed, 6 skipped for the
      absent embedding matrix)
- [ ] 6.2 Build the embedding matrix with a gateway available and confirm the
      paraphrase golden set passes rather than skips
