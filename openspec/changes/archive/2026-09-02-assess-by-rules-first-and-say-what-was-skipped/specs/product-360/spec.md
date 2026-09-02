## ADDED Requirements

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
