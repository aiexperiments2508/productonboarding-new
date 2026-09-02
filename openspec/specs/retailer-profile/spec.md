# retailer-profile Specification

## Purpose

The assortment as data the platform reads, rather than as constants the
platform contains.

The test of whether that is true is narrow and easy to fail: a profile file that
could be swapped while three modules still spelled out category prefixes is a
profile that can only be swapped for another one shaped exactly like it.

## Requirements

### Requirement: The assortment is a profile the platform reads, not code it contains

The branches, taxonomy, supplier roster, catalogue and per-branch facts SHALL be
held in a retailer profile selected at runtime, in the same way the data seed is
selected.

The parts the platform consults at run time SHALL be written into the catalog,
and the modules that decide applicability, preview and lifecycle SHALL read
category prefixes from the baseline rather than containing them.

A prefix left in rule code does not fail loudly under a different taxonomy - it
silently applies to nothing, and every check that depended on it passes.

#### Scenario: Applicability follows the profile rather than a literal

- **WHEN** the checks decide which attributes apply to a category
- **THEN** the decision is made from the baseline's taxonomy rather than from a
  prefix written into the check
- **AND** this is verified by inspection of the applicability predicate, which
  the readiness suite exercises throughout

### Requirement: Hero membership is recorded, not inferred from an identifier

Whether a product belongs to the authored narrative SHALL be recorded, and SHALL
NOT be derived from the shape of its identifier.

A prefix test was true only while the generated background stopped short of the
numbering it tested against, and became false without any code changing. A
property that is true by coincidence is one that stops being true silently.

#### Scenario: The background does not become the narrative by growing

- **WHEN** the generated background extends past the numbering an identifier
  test relied on
- **THEN** hero membership is unchanged, because it is recorded
- **AND** this is verified by inspection of the generator's membership record

### Requirement: One table for anything two components must agree about

Where the generator and the running platform must agree about a vocabulary -
the correction kinds, the allergen code map - they SHALL read one table rather
than holding a copy each.

A second copy is fine until the two are asked about something neither was
written against. An assortment declaring a new allergen made the generator and
the validation engine disagree about what a declaration renders as, and neither
was wrong about its own copy.

#### Scenario: The kind tables are the same table

- **WHEN** the generator's correction kinds and the classifier's are compared
- **THEN** they are the same table, and every kind the prompt offers exists
- **AND** `tests/test_golden.py::test_the_two_kind_tables_are_the_same_table` and
  `::test_every_kind_the_prompt_offers_is_a_kind_that_exists` assert both

#### Scenario: Both surfaces name one attribute the same way

- **WHEN** the same finding is rendered on two surfaces
- **THEN** each names the same attribute
- **AND** `tests/test_readiness.py::test_both_surfaces_name_the_same_attribute`
  asserts it

### Requirement: The pack is reproducible and the untouched catalog is clean

Regenerating the seed pack for a given seed SHALL produce byte-identical output,
and the untouched catalog SHALL validate with no violations.

Widening the assortment is only safe if both hold: reproducibility is what makes
a demonstration repeatable, and a clean untouched catalog is what makes every
finding attributable to an arc rather than to the generator.

#### Scenario: The same seed gives the same pack, and the clean catalog validates

- **WHEN** the pack is generated twice from one seed and the untouched catalog
  is validated
- **THEN** the two packs are identical and the validation reports no violations
- **AND** the reproducibility property is asserted throughout `tests/test_golden.py`
  and the clean-catalog property by `tests/test_validator.py`
