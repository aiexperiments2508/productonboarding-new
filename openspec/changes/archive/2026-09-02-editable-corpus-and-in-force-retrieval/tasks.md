## 1. The door

- [x] 1.1 Add `sc/rag/library.py` addressing documents by identifier only, and
      validate the identifier against a narrow pattern; verify via
      `tests/test_corpus_library.py::test_a_document_id_cannot_escape_the_corpus`
- [x] 1.2 Compose the path for a new document from its type and title, and
      assert the result is inside the corpus root; verify via
      `tests/test_corpus_library.py::test_a_title_cannot_escape_the_corpus`
- [x] 1.3 Refuse to author a type that is synthesised on every build, since a
      file of one would be silently overwritten; verify via
      `tests/test_corpus_library.py::test_a_synthesised_type_cannot_be_authored`
- [x] 1.4 Demand an actor on every mutation and refuse without one; verify via
      `tests/test_corpus_library.py::test_a_change_has_to_be_attributable`
- [x] 1.5 Refuse to create over an existing document; verify via
      `tests/test_corpus_library.py::test_creating_over_an_existing_document_is_refused`
- [x] 1.6 Serialise write-then-rebuild behind a reentrant lock, because the
      mutation helpers call each other

## 2. Front matter that survives a round trip

- [x] 2.1 Round-trip every authored document's front matter through the writer;
      verify via
      `tests/test_corpus_library.py::test_frontmatter_round_trips_for_every_authored_document`
- [x] 2.2 Refuse a scalar that would read back as a list, and a list item
      carrying the separator; verify via
      `tests/test_corpus_library.py::test_a_scalar_that_would_read_back_as_a_list_is_refused`
      and `::test_a_list_item_containing_a_comma_is_refused`
- [x] 2.3 Preserve keys the writer does not model, so editing a postmortem
      cannot drop a field out of a compliance record; verify via
      `tests/test_corpus_library.py::test_unmodelled_frontmatter_keys_survive_an_edit`
- [x] 2.4 Keep a body that opens with a horizontal rule from being read back as
      a second front-matter block; verify via
      `tests/test_corpus_library.py::test_a_body_starting_with_a_rule_is_not_read_as_a_second_header`
- [x] 2.5 Write atomically, so an interrupted save cannot leave a half-written
      regulation in the corpus

## 3. Retire, restore, destroy

- [x] 3.1 Make a created document retrievable at once; verify via
      `tests/test_corpus_library.py::test_a_created_document_is_retrievable_at_once`
- [x] 3.2 Filter retired documents where the corpus is walked, not where a file
      is read, so "this text produces chunks" stays a fact about the text;
      verify via
      `tests/test_corpus_library.py::test_chunk_document_still_answers_for_a_retired_file`
- [x] 3.3 Take a retired document out of the index and leave it on disk; verify
      via `tests/test_corpus_library.py::test_a_retired_document_leaves_the_index_and_stays_on_disk`
- [x] 3.4 Put it back on restore; verify via
      `tests/test_corpus_library.py::test_restoring_puts_it_back`
- [x] 3.5 Refuse a hard delete until retirement has happened; verify via
      `tests/test_corpus_library.py::test_hard_delete_requires_retirement_first`
- [x] 3.6 Write the whole text into the ledger before unlinking; verify via
      `tests/test_corpus_library.py::test_a_deleted_document_is_recoverable_from_the_ledger`

## 4. What notices a document leaving

- [x] 4.1 Report the identifiers the Python tree names literally, and refuse
      with a distinct error a caller can acknowledge; verify via
      `tests/test_corpus_library.py::test_removing_a_document_the_code_names_is_refused`
- [x] 4.2 Report when a document is the last active member of a load-bearing
      type, naming the check that stops working; verify via
      `tests/test_corpus_library.py::test_retiring_the_last_of_a_load_bearing_type_is_flagged`
- [x] 4.3 Keep the reference scan from reporting its own example strings;
      verify via
      `tests/test_corpus_library.py::test_the_reference_scan_does_not_report_its_own_examples`
- [x] 4.4 Audit every mutation against a name; verify via
      `tests/test_corpus_library.py::test_every_mutation_is_audited_against_a_name`

## 5. Pairing the matrix with the text

- [x] 5.1 Stamp a fingerprint of chunk identifiers and their text when a matrix
      is written, and check it on load
- [x] 5.2 Refuse a matrix whose text has changed even when the chunk count has
      not; verify via
      `tests/test_corpus_library.py::test_an_edit_that_preserves_the_chunk_count_invalidates_the_matrix`
- [x] 5.3 Accept a matrix predating the fingerprint as an upgrade and report it
      unverified rather than refusing it; verify via
      `tests/test_corpus_library.py::test_a_matrix_from_before_the_fingerprint_is_accepted_as_an_upgrade`
- [x] 5.4 Serialise rebuilds behind a lock, because the API runs these handlers
      in a threadpool
- [x] 5.5 Rebuild the lexical half on save and leave embedding as an explicit
      act, reporting when the vectors have fallen behind

## 6. Uploads

- [x] 6.1 Read `.docx` with `zipfile` and `xml.etree`, mapping style names to
      heading levels; verify via
      `tests/test_corpus_library.py::test_a_docx_becomes_markdown_with_its_headings`
      and `::test_an_extracted_docx_can_be_saved_and_retrieved`
- [x] 6.2 Split front matter out of an uploaded markdown file for the editor;
      verify via
      `tests/test_corpus_library.py::test_markdown_frontmatter_is_split_out_for_the_editor`
- [x] 6.3 Feature-detect `pypdf`, insert page markers, and say so in a sentence
      when it is absent; verify via
      `tests/test_corpus_library.py::test_a_pdf_gets_page_headings`
- [x] 6.4 Refuse a mislabelled file and an unaccepted suffix by name; verify via
      `tests/test_corpus_library.py::test_a_mislabelled_pdf_says_so` and
      `::test_an_unaccepted_suffix_is_refused`
- [x] 6.5 Cap the upload size at the same figure the estate intake uses; verify
      via `tests/test_corpus_library.py::test_upload_size_is_capped`
- [x] 6.6 Keep a stored original out of the index, so an upload is not indexed
      twice; verify via
      `tests/test_corpus_library.py::test_a_stored_original_is_not_indexed_twice`
- [x] 6.7 Keep extraction advisory: it fills the editor and a person presses
      save

## 7. In force at a date

- [x] 7.1 Precompute each chunk's commencement date onto the index rather than
      parsing it per query
- [x] 7.2 Exclude a passage whose document has not commenced, as of the replay
      clock by default; verify via
      `tests/test_rag.py::test_a_document_that_has_not_commenced_is_not_retrieved`
      and `::test_the_default_as_of_is_the_replay_clock`
- [x] 7.3 Let a caller turn the filter off to see what is coming; verify via
      `tests/test_rag.py::test_turning_the_filter_off_brings_everything_back`
- [x] 7.4 Treat an undated passage, and one whose date will not parse, as in
      force; verify via
      `tests/test_rag.py::test_an_undated_passage_is_always_in_force` and
      `::test_an_unparseable_effective_date_does_not_hide_a_document`
- [x] 7.5 Leave the existing golden sets answering as they did; verify via
      `tests/test_rag.py::test_the_in_force_filter_did_not_displace_the_old_answers`

## 8. Reranking

- [x] 8.1 Add `sc/rag/rerank.py`, off until configured; verify via
      `tests/test_rerank.py::test_reranking_is_off_until_configured` and
      `::test_search_does_not_call_the_gateway_when_it_is_off`
- [x] 8.2 Reorder by the model's score and carry that score with the passage;
      verify via `tests/test_rerank.py::test_it_reorders_by_score` and
      `::test_the_score_it_gave_travels_with_the_passage`
- [x] 8.3 Read deeper than the caller asked for, so a promoted passage is not
      truncated away first; verify via
      `tests/test_rerank.py::test_it_reads_deeper_than_the_caller_asked_for`
- [x] 8.4 Drop an identifier it was not given and count the drop; verify via
      `tests/test_rerank.py::test_an_invented_id_is_dropped_and_counted` and
      `::test_a_duplicated_id_is_scored_once`
- [x] 8.5 Keep candidates it ignores in their fused place; verify via
      `tests/test_rerank.py::test_passages_it_ignores_keep_their_fused_place`
- [x] 8.6 Leave the fused order untouched and say so on a dead gateway, an
      unusable reply or a non-numeric score; verify via
      `tests/test_rerank.py::test_a_dead_gateway_leaves_the_fused_order_alone`,
      `::test_an_unusable_reply_leaves_the_fused_order_alone`,
      `::test_a_non_numeric_score_is_dropped_not_guessed` and
      `::test_search_survives_a_dead_gateway_with_reranking_on`
- [x] 8.7 Skip the model call where there is nothing to reorder; verify via
      `tests/test_rerank.py::test_one_candidate_is_not_worth_a_model_call`
- [x] 8.8 Carry the identifiers it expects back in the prompt; verify via
      `tests/test_rerank.py::test_the_prompt_carries_the_ids_it_expects_back`
- [x] 8.9 Apply it from search when the switch is on; verify via
      `tests/test_rerank.py::test_search_applies_it_when_the_switch_is_on`

## 9. Followable citations

- [x] 9.1 Open the peek on the passage retrieval scored and offer the whole
      document beneath it, scrolled to and highlighting the cited passage
- [x] 9.2 Fall back to the file on disk for a document the index no longer
      holds, which is when a reader most needs it
- [x] 9.3 Make the citation chips live, gated on carrying a passage identifier,
      because most name a supplier document with no file in the library
- [x] 9.4 Stop the Ask panel discarding the reference it already computes
- [x] 9.5 Serve the library and the rerank switch over the HTTP API, each
      mutation demanding an actor
