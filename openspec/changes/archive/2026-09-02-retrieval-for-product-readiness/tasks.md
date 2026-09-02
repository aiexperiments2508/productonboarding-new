## 1. The types the index was missing

- [x] 1.1 Accept `REGULATION`, `INTERNAL` and `MARKET` beside the four written
      standards, in the chunker and in the chunk contract; verify via
      `tests/test_rag.py::test_the_new_reference_types_are_indexed_and_searchable`
- [x] 1.2 Classify a document declaring an unknown type rather than dropping
      it, so a mistyped front matter loses a classification and never a
      document; verify via
      `tests/test_rag.py::test_an_unknown_document_type_is_classified_not_dropped`
- [x] 1.3 Author the regulation covering the two regulated categories in the
      seed pack, distinguishing what a market authority requires from what the
      retailer's own policy says about it; verify `corpus/regulation/`
- [x] 1.4 Author the internal documentation - what "complete" means for a new
      line, and what may never appear in a record; verify `corpus/internal/`
- [x] 1.5 Author the market context - season, festivity, region and popular
      usage - so a differentiator can cite a passage rather than a belief;
      verify `corpus/market/`

## 2. The record, made retrievable

- [x] 2.1 Chunk the catalog's held values one passage per variant, naming the
      document behind each value; verify via
      `tests/test_rag.py::test_a_products_own_record_is_retrievable`
- [x] 2.2 Build record passages with the index rather than carrying them, so a
      passage cannot describe a value that has since been corrected; verify via
      `tests/test_rag.py::test_record_passages_cannot_drift_from_the_catalog`
- [x] 2.3 Guard the record build so a missing catalog narrows the index rather
      than preventing it; verify by inspection of `collect_chunks`

## 3. Narrowing to a product

- [x] 3.1 Add a product-scoped entry point that filters before ranking; verify
      via `tests/test_rag.py::test_a_scoped_query_does_not_cross_products`
- [x] 3.2 Keep passages that name no entity, so a category-level regulation is
      not filtered out of the check it exists to fail; verify via
      `tests/test_rag.py::test_narrowing_filters_before_ranking`
- [x] 3.3 Make that opt-in, so callers narrowing to reduce a result set do not
      get the unscoped half back; verify by inspection of `_filter`

## 4. Leaving the retriever alone

- [x] 4.1 Confirm the fusion weights, RRF damping and tokeniser are unchanged
      and the golden set still passes; verify the existing `tests/test_rag.py`
      assertions
- [x] 4.2 Extend the golden set to the new types and measure the weights
      against it; verify via the extended `LEXICAL_GOLDEN` and `SEMANTIC_GOLDEN`
      in `tests/test_rag.py`. **The weights were not re-tuned, because the set
      cannot tune them**: swept across thirty combinations of semantic and
      lexical weight from 0.6 to 1.0, every single one scores identically. The
      set does not discriminate, so any new pair would have been chosen by
      taste and reported as tuning.
- [x] 4.3 Measure whether the new document types displaced the old answers -
      twenty-eight passages added to a hundred and fourteen is a real risk to a
      top-3 and the design said so; verify via
      `tests/test_rag.py::test_the_new_document_types_did_not_displace_the_old_answers`.
      They did not: the original five paraphrase queries score 3 of 5 whether
      or not the new types are in the pool.
- [x] 4.4 Turn the paraphrase set from per-case assertions into a scored floor;
      verify via `tests/test_rag.py::test_hybrid_golden_set`. Per-case
      assertions skip without an embedding matrix, which is nearly always, and
      that is how two of them came to be failing without anybody noticing - the
      guard that would have caught it is the guard that skips.
- [x] 4.5 Replace the claim that the dense half rescues a paraphrase query with
      the one that holds; verify via
      `tests/test_rag.py::test_the_fused_retriever_is_never_worse_than_lexical_alone`.
      **Measured: fused scores 4 of 8 and BM25 alone scores 4 of 8.** The dense
      half is not contributing on these queries with this embedding model. That
      does not make the fusion pointless - the identifier set is where the two
      genuinely differ - but the paraphrase argument is currently unearned, and
      a test asserting otherwise would be asserting a hope.
