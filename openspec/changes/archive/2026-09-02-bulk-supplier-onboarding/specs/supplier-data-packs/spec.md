## Purpose

What a supplier is handed so that what comes back is what the checks read. The
pack is the only place the retailer's requirements are stated to somebody
outside it, and the whole of this capability is the rule that it must never
become a second statement of them: every column is derived from the attribute
registry and the retailer profile, and a template that could disagree with the
checks would be worse than no template at all.

## ADDED Requirements

### Requirement: Every column is derived from the registry and the profile

The pack SHALL derive each branch's columns from the attribute registry joined
to the retailer profile's branch declarations. No column, category, unit or
enumerated value SHALL be written down in the pack's own code.

Changing the retailer profile SHALL change the pack with no code change.

#### Scenario: The columns are exactly the attributes that apply

- **WHEN** a branch's template is built
- **THEN** its attribute columns are exactly those attributes that apply to at
  least one of that branch's taxonomy leaves, decided by the same predicate the
  readiness check uses before it reports a gap
- **AND** `tests/test_datapack.py::test_attribute_columns_are_exactly_what_the_registry_says_applies`
  asserts it against the derivation rather than against a list

#### Scenario: Changing the profile changes the pack

- **WHEN** a branch's required imagery is changed in the retailer profile
- **THEN** that branch's image columns change to match
- **AND** `tests/test_datapack.py::test_changing_the_profile_changes_the_pack`
  asserts it

### Requirement: Applicability is per taxonomy leaf, and a partial column says so

Applicability SHALL be decided per taxonomy leaf, never per branch. A column
that applies to only some of a branch's categories SHALL name the categories it
applies to, so that an empty cell on a row it does not cover is understood as
correct rather than missing.

#### Scenario: A saucepan is never asked for a wattage

- **WHEN** the Home & Kitchen template is built
- **THEN** the rated-power column is present, is marked as applying to only
  some categories, and names exactly those categories the registry says it
  applies to
- **AND** `tests/test_datapack.py::test_a_saucepan_is_never_asked_for_a_wattage`
  asserts it

#### Scenario: Asking by branch rather than by leaf is not silently narrower

- **WHEN** the applicability predicate is asked with a branch key rather than a
  taxonomy leaf
- **THEN** it matches only the attributes that apply to every category, and the
  pack's own derivation does not do this
- **AND** `tests/test_datapack.py::test_asking_by_branch_key_rather_than_by_leaf_finds_almost_nothing`
  pins both halves

### Requirement: The pack states the contract a spreadsheet would otherwise break

Each column SHALL carry, in addition to its machine name, a human label with
its unit and one sentence saying whether it is required and by which channel,
whether it is safety class, and whether its order carries meaning.

The workbook SHALL keep identifier columns text-formatted so that leading zeros
survive.

#### Scenario: A leading zero is not lost

- **WHEN** a GTIN beginning with a zero is written to the workbook
- **THEN** the cell is text-formatted and the value reads back with its leading
  zero intact
- **AND** `tests/test_datapack.py::test_the_workbook_keeps_the_gtin_column_text`
  asserts it

### Requirement: The worked example is real, one supplier's, and honestly damaged

Every branch SHALL ship a filled example drawn from that retailer's own
catalogue and from a single supplier, because a bundle is one supplier's
submission and an example drawn across a branch would be mostly refused on
arrival.

The example SHALL include one deliberately broken row per defect a supplier
file can carry, drawn from the closed set of conformance defects, each saying
what is wrong with it. Defects a file cannot demonstrate SHALL be named as
such rather than omitted.

A defect SHALL NOT be demonstrated by emptying a safety-class field.

#### Scenario: Five defects shown, two explained

- **WHEN** the pack is built
- **THEN** every representable defect appears in at least one branch's example,
  each broken row exhibits exactly one, and the two defects that need the rest
  of the estate to exist are recorded as not representable
- **AND** `tests/test_datapack.py::test_every_representable_defect_is_shown_or_explained`
  and `::test_the_example_never_blanks_a_safety_field_to_make_a_point` assert it

### Requirement: The pack degrades rather than failing

Producing the workbook MAY require a dependency the runtime does not need.
Where that dependency is absent, the pack SHALL be produced without the
workbook, SHALL say which format was not produced and why, and the platform
SHALL continue to serve the remaining formats.

#### Scenario: A missing spreadsheet library costs one format, not the pack

- **WHEN** the formats a platform can produce are asked for
- **THEN** every standard-library format reports as available, and the workbook
  reports as unavailable with the reason and the command that fixes it
- **AND** `tests/test_datapack.py::test_the_formats_report_what_this_installation_can_actually_build`
  asserts it
