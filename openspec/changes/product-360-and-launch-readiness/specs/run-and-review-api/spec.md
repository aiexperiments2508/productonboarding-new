## ADDED Requirements

### Requirement: Products are searchable, readable and assessable through the API

A search route SHALL accept a SKU, an internal identifier or words from a name
and return matching variants. A record route SHALL return one product's merged
record. An assessment route SHALL return its findings and verdict. A preview
route SHALL return the staging page for a ready record and refuse otherwise.

Every one of these SHALL be produced by the same functions the rest of the
system calls, rather than by a second implementation. Two implementations of one
read become two accounts of the same product the first time either is edited.

#### Scenario: The API's product reads are the same reads

- **WHEN** the product routes are inspected against the functions they call
- **THEN** each delegates rather than re-deriving its answer
- **AND** `tests/test_product360.py::test_the_api_product_reads_are_the_pipelines_own`
  asserts the delegation

#### Scenario: A search with no match answers empty rather than failing

- **WHEN** a search route is called with a term nothing matches
- **THEN** it returns an empty result set with status 200
- **AND** `tests/test_product360.py::test_a_search_with_no_match_is_empty_not_an_error`
  asserts both

#### Scenario: A preview of an unready product is refused with its reasons

- **WHEN** the preview route is called for a product that is not ready
- **THEN** it refuses and the response carries the verdict and the findings
- **AND** `tests/test_preview.py::test_the_preview_route_refuses_an_unready_product`
  asserts both
