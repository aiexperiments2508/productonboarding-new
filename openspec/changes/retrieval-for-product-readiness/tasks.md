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
- [ ] 4.2 Re-tune the fusion weights against a golden set extended to the new
      types. NOT DONE: the existing set was tuned on four types and still
      passes, so nothing is broken - but "still passes" is not the same as
      "still right", and the honest position is that the weights have not been
      measured against regulation or record passages.
