# product-360 Specification

## Purpose

Finding a product the way everybody outside this system names it, and showing
what the estate has actually said about it: the merged record, the media, the
document behind every value, and the places where two systems that both sent
data do not agree.

## Requirements

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

### Requirement: The product list is windowed on the simulated clock and faceted

The product list SHALL be narrowable by an arrival window, by supplier and by
category. The window SHALL be measured on the simulated clock.

Arrival timestamps run on the real clock, and a window measured on those
returns everything or nothing depending on when the demonstration was last
reset - which is the trap the window helper documents at length and the reason
this is stated rather than left to the implementation.

A filter SHALL narrow the list without reordering it, and paging SHALL walk the
whole list without repeating or dropping a row.

#### Scenario: Filters narrow without reordering

- **WHEN** a filter is applied to the product list
- **THEN** the remaining rows are in the order they were in before
- **AND** `tests/test_product360.py::test_filters_narrow_without_reordering`
  asserts it

#### Scenario: Paging walks the list exactly once

- **WHEN** the list is paged from end to end
- **THEN** every row appears exactly once
- **AND** `tests/test_product360.py::test_paging_walks_the_whole_list_without_repeating_itself`
  asserts it

### Requirement: The rollup counts by who has to fix it

The list SHALL carry a rollup counting what went downstream clean against what
went back to source, broken down by the party responsible for correcting it.

Counting outcomes without attributing them answers "how bad is it" and not "who
do I call", and the second is the question a category manager opens the screen
with.

#### Scenario: The rollup attributes what went back to source

- **WHEN** the product list is rolled up over a window
- **THEN** it counts what went downstream clean against what was returned, split
  by the party that has to correct it
- **AND** this is verified by inspection of the rollup; the verdict counts it
  sums are asserted by `tests/test_readiness.py::test_the_tally_is_the_sum_of_the_verdicts_it_counted`

### Requirement: A map is scoped and a blast radius is not

The estate map SHALL be served by a route that is scoped - a bounded number of
products by default, narrowable by search and by facet - and SHALL report how
many nodes it did not draw rather than truncating silently. The frame SHALL
grow with the busiest tier rather than being fixed.

The unscoped route SHALL keep its shape. The two surfaces want opposite
defaults and that is the reason they are two routes: a map showing ten of a
hundred and fifty is a reasonable map, and a blast radius showing ten of a
hundred and fifty is a wrong answer about what a correction reaches.

#### Scenario: A scoped map says what it left out

- **WHEN** more nodes match than the scoped map draws
- **THEN** the response reports the number not drawn
- **AND** this is verified by inspection of the route body; no test covers the
  count directly
