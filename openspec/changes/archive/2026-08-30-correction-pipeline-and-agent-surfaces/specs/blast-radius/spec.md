## MODIFIED Requirements

### Requirement: The totals agree with the affected lists

The reported totals SHALL be the sizes of the affected lists they summarise, and
the safety-flag and regulated-product counts SHALL be derived from the affected
attributes' safety class and the affected products' regulated flag.

Those totals measure **reach**, and reach is not grounds. A radius taken over
several signals at once unions their traversals, so it legitimately arrives at
products the run is not deciding about: tracing a document a correction cites
reaches everything else that document describes. A consumer deciding the severity
of one correction case SHALL therefore restrict the regulated test to the products
that case actually names, and SHALL NOT escalate a case on a regulated product it
merely reached. The traversal itself is unchanged - what changes is what may be
concluded from it.

#### Scenario: Totals are recomputable from the lists

- **WHEN** each of the seven root kinds is traced
- **THEN** the field, asset, listing and channel totals equal the lengths of the
  corresponding lists, and the safety-flag and regulated totals equal the sums
  over the affected attributes and products
- **AND** `tests/test_propagation.py::test_totals_agree_with_the_affected_lists`
  asserts each per root

#### Scenario: A regulated product counts once and its safety flags count each

- **WHEN** the regulated food product is traced
- **THEN** the regulated total is one and the safety-flag total is four
- **AND** `tests/test_propagation.py::test_a_regulated_product_is_counted_as_one`
  asserts both

#### Scenario: A case is not escalated on a regulated product it merely reached

- **WHEN** a run scoped to an air purifier traces a source-conflict signal that
  names a supplier document, and that document's traversal reaches a regulated
  snack
- **THEN** no other product's identifier appears in the severity sentence the run
  produces, and the regulated snack is reported as a separate open case rather
  than as grounds against the purifier
- **AND**
  `tests/test_graph.py::test_a_scoped_run_is_not_contaminated_by_the_documents_it_reads`
  asserts both
