## MODIFIED Requirements

### Requirement: Results can be narrowed before ranking

A caller SHALL be able to restrict results to given document types and to
passages concerning given entities, where an entity matches whether it is
declared in the document's frontmatter or named in the passage text. A filter
that matches nothing SHALL return nothing rather than falling back to an
unfiltered search.

**A passage whose document has not commenced SHALL NOT be returned.** The
as-of date SHALL default to the replay clock, because every other as-of read in
this system does and a retrieval answering about a different instant than the
catalog it is compared against is a subtle way to be wrong. A caller SHALL be
able to name a different date, and to turn the filter off to see what is coming.

A rule taking effect in December is not the answer to what may be published
today, and returning it as though it were is the same class of error as citing a
withdrawn policy - quieter, because the document is real, it retrieves cleanly,
the excerpt reads correctly, the citation resolves, and every anti-fabrication
gate in this system passes it.

**A passage with no commencement date SHALL be treated as in force, and so
SHALL one whose date cannot be parsed.** Correspondence, a catalog record and a
postmortem are statements about something that happened rather than rules that
commence. A typo should cost a document its date, not its presence: an
unfindable regulation is the failure this filter exists to prevent.

Commencement dates SHALL be precomputed onto the index rather than parsed per
chunk per query.

#### Scenario: A document-type filter is respected

- **WHEN** a query is restricted to postmortems
- **THEN** results are returned and every one is a postmortem
- **AND** `tests/test_rag.py::test_doc_type_filter_restricts_results` asserts
  both

#### Scenario: An entity filter matches header or body

- **WHEN** a query is restricted to a variant identifier
- **THEN** every result either declares that entity in its metadata or names it
  in its text
- **AND** `tests/test_rag.py::test_entity_filter_matches_header_or_body` asserts
  the disjunction per result

#### Scenario: An unknown entity yields an empty result

- **WHEN** a query is restricted to an entity no document mentions
- **THEN** nothing is returned
- **AND** `tests/test_rag.py::test_filters_that_match_nothing_return_nothing`
  asserts the empty result

#### Scenario: A rule that has not commenced is not returned

- **WHEN** a query would match a document whose commencement date is in the
  future
- **THEN** it is excluded, and turning the filter off brings it back
- **AND** `tests/test_rag.py::test_a_document_that_has_not_commenced_is_not_retrieved`
  and `::test_turning_the_filter_off_brings_everything_back` assert both

#### Scenario: The default as-of is the replay clock

- **WHEN** a query is run with no date named
- **THEN** commencement is judged against the replay clock
- **AND** `tests/test_rag.py::test_the_default_as_of_is_the_replay_clock`
  asserts it

#### Scenario: An undated or unparseable date does not hide a document

- **WHEN** a document carries no commencement date, or one that will not parse
- **THEN** it is still returned
- **AND** `tests/test_rag.py::test_an_undated_passage_is_always_in_force` and
  `::test_an_unparseable_effective_date_does_not_hide_a_document` assert both

#### Scenario: The filter did not displace the answers that were already right

- **WHEN** the existing golden sets are run with the filter in place
- **THEN** they return what they returned before
- **AND** `tests/test_rag.py::test_the_in_force_filter_did_not_displace_the_old_answers`
  asserts it

### Requirement: Paraphrased questions are answered by fusing both retrievers

Where an embedding matrix has been built, lexical and semantic rankings SHALL be
fused into one result list, and the fused list SHALL find documents that share
little vocabulary with the question. Where no matrix is present the system SHALL
still answer from the lexical half rather than fail.

**An embedding matrix SHALL be paired with the chunk list by content, not by
length.** A fingerprint covering the chunk identifiers *and their text* SHALL be
written when a matrix is written and checked on every load, and a matrix that
disagrees SHALL NOT be used.

A chunk identifier is a document and an ordinal, so rewording a sentence inside
a document leaves every identifier in the corpus exactly as it was. A count
check accepts the old vectors against the new text: row N is still *a* vector
for chunk N, just the wrong one, and every citation that follows is specific,
confident and wrong.

**A matrix written before the fingerprint existed SHALL be accepted and reported
as unverified rather than refused.** Switching dense search off on every
installation that has not reindexed is a worse failure, and a quieter one.

Rebuilds SHALL be serialised, because two concurrent builds produce exactly the
misalignment the fingerprint detects, by a route the fingerprint cannot prevent.

#### Scenario: A question in a shopper's words finds the governing document

- **WHEN** each of the five paraphrase golden queries is run against an index
  built with an embedding matrix
- **THEN** each returns at least one of the documents that query is expected to
  find
- **AND** `tests/test_rag.py::test_hybrid_golden_set` asserts it per query, and
  skips when no matrix has been built

#### Scenario: An edit that keeps the chunk count still invalidates the matrix

- **WHEN** a document is reworded without changing how many chunks it produces
- **THEN** the matrix is refused rather than used against the new text
- **AND** `tests/test_corpus_library.py::test_an_edit_that_preserves_the_chunk_count_invalidates_the_matrix`
  asserts it

#### Scenario: A matrix from before the check is an upgrade, not a failure

- **WHEN** an index with no recorded fingerprint is loaded
- **THEN** the matrix is used and reported unverified
- **AND** `tests/test_corpus_library.py::test_a_matrix_from_before_the_fingerprint_is_accepted_as_an_upgrade`
  asserts it

## ADDED Requirements

### Requirement: A fused ordering may be reranked, and reranking can neither invent nor drop

The fused result list MAY be reordered by a model reading the query beside each
candidate passage. It SHALL be off unless configured, and a caller SHALL be able
to insist on it or decline it per query.

Fusion decides what is *plausible*; reranking decides what is *relevant*. A
reciprocal-rank fusion knows one retriever ranked a passage third and the other
seventh, and has no way to notice that the passage is the cross-reference
section of the right document rather than the rule itself.

Three properties SHALL hold whatever the model returns:

- **It SHALL NOT invent.** A passage identifier the model was not given SHALL be
  dropped, and the drop SHALL be counted.
- **It SHALL NOT drop.** A candidate the model does not mention SHALL keep its
  fused position, so the worst a confused reranker can do is leave the fused
  ordering roughly alone.
- **It SHALL NOT fail quietly.** An unreachable gateway, a refusal, an
  unparseable reply or a non-numeric score SHALL leave the fused order untouched
  and SHALL be reported to the caller.

Reranking that silently did not happen looks identical to reranking that
happened and agreed, and a reader deciding how much to trust an ordering has to
be able to tell those apart.

Reranking SHALL read more candidates than the caller asked for, because the
passage it promotes to first is often one the fused ordering held well below the
requested depth. Where there is nothing to reorder, no model call SHALL be made.

#### Scenario: It is off until configured, and costs nothing while off

- **WHEN** a search runs with reranking unconfigured
- **THEN** no gateway call is made
- **AND** `tests/test_rerank.py::test_reranking_is_off_until_configured` and
  `::test_search_does_not_call_the_gateway_when_it_is_off` assert both

#### Scenario: It reorders by score and the score travels with the passage

- **WHEN** a reranked search returns
- **THEN** the order follows the scores, and each passage carries the score it
  was given
- **AND** `tests/test_rerank.py::test_it_reorders_by_score`,
  `::test_the_score_it_gave_travels_with_the_passage` and
  `::test_search_applies_it_when_the_switch_is_on` assert them

#### Scenario: An invented identifier is dropped and counted

- **WHEN** the model returns an identifier it was not given, or the same one
  twice
- **THEN** the first is dropped and counted, and the second is scored once
- **AND** `tests/test_rerank.py::test_an_invented_id_is_dropped_and_counted` and
  `::test_a_duplicated_id_is_scored_once` assert both

#### Scenario: A passage it ignores keeps its fused place

- **WHEN** the model omits a candidate from its reply
- **THEN** that candidate is still returned, in its fused position
- **AND** `tests/test_rerank.py::test_passages_it_ignores_keep_their_fused_place`
  asserts it

#### Scenario: Every failure leaves the fused order alone and says so

- **WHEN** the gateway is unreachable, the reply is unusable, or a score is not
  a number
- **THEN** the fused order stands and the caller is told
- **AND** `tests/test_rerank.py::test_a_dead_gateway_leaves_the_fused_order_alone`,
  `::test_an_unusable_reply_leaves_the_fused_order_alone`,
  `::test_a_non_numeric_score_is_dropped_not_guessed` and
  `::test_search_survives_a_dead_gateway_with_reranking_on` assert them

#### Scenario: It reads deeper than asked, and not at all when pointless

- **WHEN** a caller asks for fewer results than the reranker reads, and
  separately when only one candidate exists
- **THEN** the reranker reads the deeper set in the first case and makes no
  model call in the second
- **AND** `tests/test_rerank.py::test_it_reads_deeper_than_the_caller_asked_for`
  and `::test_one_candidate_is_not_worth_a_model_call` assert both
