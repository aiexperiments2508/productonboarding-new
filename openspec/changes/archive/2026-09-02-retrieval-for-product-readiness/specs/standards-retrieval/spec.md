## MODIFIED Requirements

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

## ADDED Requirements

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
