## Purpose

Finding a product the way everybody outside this system names it, and showing
what the estate has actually said about it: the merged record, the media, the
document behind every value, and the places where two systems that both sent
data do not agree.

## ADDED Requirements

### Requirement: A product is findable by the identifier the world uses

Every variant SHALL carry a SKU, distinct across the catalogue, and SHALL be
findable by it. The internal identifier SHALL remain what it is and SHALL also
find the product: a system that renames its own keys to look friendlier has
made its audit trail harder to read for a cosmetic gain.

A search SHALL also match on name, and SHALL rank an exact identifier match
above a name match. Somebody typing a SKU knows exactly what they want.

#### Scenario: A SKU finds exactly one product

- **WHEN** a variant's SKU is searched for
- **THEN** that variant is the first result, and no other variant outranks it
- **AND** `tests/test_product360.py::test_a_sku_finds_exactly_one_product`
  asserts both

#### Scenario: The internal identifier still finds it

- **WHEN** a variant's internal identifier is searched for
- **THEN** the same variant is the first result
- **AND** `tests/test_product360.py::test_the_internal_identifier_still_finds_it`
  asserts the match

#### Scenario: A name finds a product without its identifier

- **WHEN** words from a product's name are searched for
- **THEN** its variants are returned
- **AND** `tests/test_product360.py::test_a_name_finds_a_product`
  asserts the match

#### Scenario: An identifier outranks a name that merely mentions it

- **WHEN** a query is an exact SKU that also appears inside another product's
  description
- **THEN** the variant that owns the SKU ranks first
- **AND** `tests/test_product360.py::test_an_exact_identifier_outranks_a_name_match`
  asserts the ranking

### Requirement: The record shows what was delivered and who delivered it

A product's record SHALL carry, for every attribute in force: the value, the
document behind it, the provenance class, and the external system that carried
it. A value whose carrier is unknown SHALL say so rather than being attributed
to nothing in particular.

The record SHALL also carry the values that did **not** win. A disagreement
settled by source precedence is settled, not absent, and a reviewer asking "did
anything else say otherwise" is asking the question the estate exists to answer.

#### Scenario: Every value names its document, its class and its carrier

- **WHEN** a product's record is read
- **THEN** each in-force value carries a value, a source document, a provenance
  class and either a named system or an explicit absence
- **AND** `tests/test_product360.py::test_every_value_names_its_document_and_carrier`
  asserts each

#### Scenario: A settled disagreement is still visible

- **WHEN** two systems have asserted different values for one attribute and
  precedence settled it
- **THEN** the record shows the value in force and the value it beat, with the
  system behind each
- **AND** `tests/test_product360.py::test_a_settled_disagreement_is_still_visible`
  asserts both

### Requirement: Media is part of the record, not an afterthought

Media SHALL be held as typed assets carrying a role, so that "the category
requires an ingredient panel and none arrived" is a fact about the record rather
than an impression of it.

A role SHALL be drawn from a declared set. A free-text role would make the
requirement unenforceable, because nothing could tell a missing hero shot from a
hero shot filed under a name nobody checked.

#### Scenario: Media carries a role from the declared set

- **WHEN** the media held for a product is read
- **THEN** every asset names a role in the declared set and the product it
  belongs to
- **AND** `tests/test_product360.py::test_media_carries_a_declared_role`
  asserts both

#### Scenario: A product with no media reports none rather than failing

- **WHEN** the record of a product that has received no media is read
- **THEN** the media list is empty and the record is otherwise complete
- **AND** `tests/test_product360.py::test_a_product_with_no_media_still_has_a_record`
  asserts both
