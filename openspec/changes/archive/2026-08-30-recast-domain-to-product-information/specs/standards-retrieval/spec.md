## Purpose

Holds the written rules the system is answerable to - content standards, channel
specifications, policies and postmortems - and finds the passage that settles a
question, returning a citation an editor can open at the exact section the claim
came from.

## ADDED Requirements

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

#### Scenario: Every reference type is represented

- **WHEN** the index status is requested after a build
- **THEN** the passage count exceeds thirty and each of the four reference types
  has at least one passage
- **AND** `tests/test_rag.py::test_index_covers_the_whole_corpus` asserts both

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

#### Scenario: A question in a shopper's words finds the governing document

- **WHEN** each of the five paraphrase golden queries is run against an index
  built with an embedding matrix
- **THEN** each returns at least one of the documents that query is expected to
  find
- **AND** `tests/test_rag.py::test_hybrid_golden_set` asserts it per query, and
  skips when no matrix has been built

#### Scenario: Fusion finds a precedent the lexical half misses

- **WHEN** the paraphrase about a note giving a wrong number without naming the
  model is run lexically and then with both retrievers fused
- **THEN** the fused result includes the precedent postmortem and the lexical
  result does not
- **AND** `tests/test_rag.py::test_hybrid_beats_lexical_alone_on_paraphrase`
  asserts both, and skips when no matrix has been built
