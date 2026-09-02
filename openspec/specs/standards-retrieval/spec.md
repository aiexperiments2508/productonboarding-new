# standards-retrieval Specification

## Purpose
Holds the written rules the system is answerable to - content standards, channel
specifications, policies and postmortems - and finds the passage that settles a
question, returning a citation an editor can open at the exact section the claim
came from.

## Requirements

### Requirement: Identifiers survive tokenisation

Product, variant, supplier and channel-code identifiers SHALL be indexed whole
as well as by their parts, so that lexical search can separate two identifiers
that differ only in a suffix. Common function words SHALL be dropped.

#### Scenario: An identifier is not split into its pieces

- **WHEN** text naming a variant, a supplier and a channel rejection code is
  tokenised
- **THEN** each identifier appears as a whole token
- **AND** `tests/test_rag.py::test_identifiers_survive_tokenisation` asserts all
  three

#### Scenario: The prefix of an identifier is searchable too

- **WHEN** a variant identifier is tokenised
- **THEN** both the whole identifier and its leading part are present
- **AND** `tests/test_rag.py::test_identifier_parts_are_also_indexed` asserts
  both

#### Scenario: Two near-identical identifiers rank apart

- **WHEN** two passages differ only in the variant suffix they name, and one of
  those variants is searched for
- **THEN** the passage naming that variant ranks first
- **AND** `tests/test_rag.py::test_bm25_separates_similar_identifiers` asserts
  the ranking

#### Scenario: Function words do not become search terms

- **WHEN** a phrase containing articles and conjunctions is tokenised
- **THEN** those words are absent from the tokens
- **AND** `tests/test_rag.py::test_stopwords_are_dropped` asserts one of them

#### Scenario: A term the corpus does not contain returns nothing

- **WHEN** a term absent from every indexed passage is searched for
- **THEN** no results are returned rather than a list of weak matches
- **AND** `tests/test_rag.py::test_bm25_returns_nothing_for_absent_terms`
  asserts the empty result

### Requirement: A chunk is findable on its own

Each indexed passage SHALL carry the document it came from, that document's
type, and enough of its own heading context to be read without the surrounding
text. Document frontmatter, including list-valued fields, SHALL be parsed and
retained on the passage. Every document in the corpus SHALL produce at least one
passage.

#### Scenario: A passage is prefixed with where it came from

- **WHEN** a content-standards document is chunked
- **THEN** every passage begins with the document title and carries the document
  id and type
- **AND** `tests/test_rag.py::test_chunks_carry_document_and_heading_context`
  asserts all three on every passage

#### Scenario: Frontmatter lists survive into the passage metadata

- **WHEN** a document whose frontmatter declares an entity list is parsed
- **THEN** the identifier and the entity list are returned as structured
  metadata and the body starts after the frontmatter
- **AND** `tests/test_rag.py::test_frontmatter_is_parsed_including_lists`
  asserts the fields and the body

#### Scenario: No document is silently unindexed

- **WHEN** every markdown file in the corpus is chunked
- **THEN** each produces at least one passage
- **AND** `tests/test_rag.py::test_every_corpus_document_produces_chunks`
  asserts it per file

#### Scenario: A postmortem keeps the entities it is about

- **WHEN** a postmortem naming a product in its frontmatter is chunked
- **THEN** the passage carries the postmortem document type and that product
  among its entities
- **AND** `tests/test_rag.py::test_incident_metadata_is_retained` asserts both

### Requirement: Four reference document types are indexed

The index SHALL cover content standards, channel specifications, policies and
postmortems, with at least one passage of each type present.

It SHALL also cover three further kinds, because deciding whether a product may
launch asks questions the written standards cannot answer:

- **regulation** - what a market authority requires of a category, as opposed
  to what our own policy says about it. A system that cites its own policy as
  evidence of compliance is marking its own homework.
- **internal documentation** - the buying guides, category playbooks and
  onboarding rules a new starter is told and a system has never checked.
- **market context** - the region, season, festivity and popular usage a
  product page is written against. Without it, a claim about why somebody would
  buy this here and now has nothing behind it but whatever a model happens to
  believe.

A document declaring a type the index does not know SHALL be indexed under a
declared type rather than dropped, so that a mistyped front matter loses a
classification and never a document.

#### Scenario: Every reference type is represented

- **WHEN** the index status is requested after a build
- **THEN** the passage count exceeds thirty and each of the four reference types
  has at least one passage
- **AND** `tests/test_rag.py::test_index_covers_the_whole_corpus` asserts both

#### Scenario: Regulation, internal documentation and market context are indexed

- **WHEN** the index is built and its passages are counted by type
- **THEN** each of regulation, internal documentation and market context has at
  least one passage, and each is reachable from a default search
- **AND** `tests/test_rag.py::test_the_new_reference_types_are_indexed_and_searchable`
  asserts each

#### Scenario: A document declaring an unknown type is still indexed

- **WHEN** a document whose front matter names a type the index does not know is
  chunked
- **THEN** its passages are present and carry a known type
- **AND** `tests/test_rag.py::test_an_unknown_document_type_is_classified_not_dropped`
  asserts both

### Requirement: Correspondence is evidence, not guidance

Email and other correspondence SHALL be excluded from search results unless the
caller asks for it explicitly, so that a message cannot answer a question about
what the standard says.

#### Scenario: The mailbox is opt-in

- **WHEN** a query is run with default options and then again asking for
  correspondence
- **THEN** the default results contain no correspondence, and the opt-in results
  are at least as many
- **AND** `tests/test_rag.py::test_correspondence_is_excluded_by_default`
  asserts both

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

### Requirement: Queries that name things are answered without embeddings

A query naming an identifier, a rejection code or a policy term SHALL be
answered from the lexical index alone, so retrieval keeps working with no model
gateway and no embedding matrix available.

#### Scenario: The lexical golden set finds its documents

- **WHEN** each of the five golden queries naming a channel code, a rejection
  code, the precedence policy, the print freeze window or the claim table is run
  with the semantic half disabled
- **THEN** each returns at least one of the documents that query is expected to
  find
- **AND** `tests/test_rag.py::test_lexical_golden_set` asserts it per query

### Requirement: The corpus states the rules the code enforces

The policies and standards the system enforces deterministically SHALL also
exist as retrievable prose owned by a person, so a reviewer is shown the rule
that blocked a publish in a form they can argue with. The claim-substantiation
table and the source-precedence order SHALL each be retrievable by name.

#### Scenario: The precedence policy and the claim table are retrievable

- **WHEN** the golden queries for source precedence and for claim substantiation
  are run
- **THEN** they return the source-precedence policy document and the content
  standards document respectively
- **AND** `tests/test_rag.py::test_lexical_golden_set` asserts both cases

### Requirement: Every result is a followable citation

Each result SHALL be renderable as a citation carrying the passage identifier,
the document identifier, a source path that exists on disk, and an excerpt. The
passages of a document SHALL be fetchable in their original order.

#### Scenario: A citation opens the section it came from

- **WHEN** results for a question about the print freeze window are converted to
  citations
- **THEN** each citation names a passage, a document and a source path that
  exists, and carries a non-empty excerpt
- **AND** `tests/test_rag.py::test_citations_are_followable` asserts all four

#### Scenario: A document reads back in order

- **WHEN** the passages of the content standards document are fetched
- **THEN** they are returned in ascending ordinal order
- **AND** `tests/test_rag.py::test_document_fetch_returns_ordered_chunks`
  asserts the ordering

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

### Requirement: The product record is retrievable beside the prose

What the catalog holds about a product - its in-force attribute values and the
document behind each one - SHALL be indexed as passages, so that a question
about a product and a question about a standard are answered the same way and
cite evidence the same way.

A record passage SHALL name the entity it describes, so it can be filtered to.
It SHALL carry the source document behind each value, because a value with no
provenance is not evidence and this index is read for evidence.

The record is generated rather than authored, so it SHALL be rebuilt whenever
the index is. A passage describing a value that has since been corrected is
worse than no passage at all.

#### Scenario: A product's own values are findable

- **WHEN** the index is built and a product's identifier is searched for
- **THEN** a passage describing that product's held values is returned, naming
  the product and the document behind each value
- **AND** `tests/test_rag.py::test_a_products_own_record_is_retrievable`
  asserts each

#### Scenario: The record passages follow the catalog

- **WHEN** the index is rebuilt
- **THEN** every record passage describes an entity the catalog holds, and every
  value in it matches what the catalog holds for that entity
- **AND** `tests/test_rag.py::test_record_passages_cannot_drift_from_the_catalog`
  asserts both

### Requirement: A query can be narrowed to one product

Retrieval SHALL accept a product or variant and return only passages about that
entity or about no entity in particular. A readiness check that retrieved
another product's regulation would report a finding against the wrong product,
which is worse than reporting none.

The narrowing SHALL be applied before ranking rather than after, so that a
scoped query returns a full result set rather than whatever survives from a
globally-ranked one.

#### Scenario: A scoped query does not cross products

- **WHEN** a query that would otherwise match two products' passages is scoped
  to one of them
- **THEN** every result is about that product or about no product in particular,
  and none is about the other
- **AND** `tests/test_rag.py::test_a_scoped_query_does_not_cross_products`
  asserts both

#### Scenario: Narrowing does not shrink the result set

- **WHEN** the same query is run scoped and unscoped, both asking for the same
  number of results
- **THEN** the scoped query returns as many results as it has matching passages
  rather than only those that would have survived a global ranking
- **AND** `tests/test_rag.py::test_narrowing_filters_before_ranking`
  asserts the count

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
