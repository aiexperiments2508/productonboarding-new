# content-validation Specification

## Purpose
Decides deterministically whether a corrected product record is publishable on
each channel it lists on, and names the rule behind every block, so a reviewer
is never shown a missing channel without a reason.

## Requirements

### Requirement: Validation is reproducible

A validation pass over the same catalog, the same in-force values and the same
change set SHALL produce identical results on every run - the same violations,
the same measures, and the same trace hash. The result SHALL NOT depend on the
order in which actions appear in the change set. Iteration SHALL be sorted, with
ties broken by identifier.

#### Scenario: Repeated runs agree

- **WHEN** the same change set is validated fifty times
- **THEN** exactly one distinct trace hash is produced
- **AND** `tests/test_validator.py::test_identical_change_set_produces_identical_trace`
  asserts the single hash

#### Scenario: Action order is not part of the resolution

- **WHEN** two change sets holding the same two actions in opposite order are
  validated
- **THEN** the trace hash, the measures and the violations are equal
- **AND** `tests/test_validator.py::test_action_order_does_not_change_the_result`
  asserts all three

#### Scenario: Measures are stable and the in-force layer digests stably

- **WHEN** a change set is validated ten times, and separately an in-force layer
  is digested twice and validated twenty times
- **THEN** the measures agree across runs and the digest and trace hash are
  each single-valued
- **AND** `tests/test_validator.py::test_kpis_are_stable_across_repeat_runs` and
  `tests/test_validator.py::test_overlay_digest_is_stable` assert them

### Requirement: The untouched catalog validates clean

With no change set applied, the catalog SHALL produce no violations, be
publishable, and report full listing readiness and completeness with no fields
affected and no channels blocked. A readiness pass over the untouched catalog
SHALL be identical to validating an empty change set.

#### Scenario: The baseline is not quietly dirty

- **WHEN** readiness is computed for the untouched catalog
- **THEN** there are no violations, the result is publishable, listing readiness
  and completeness are 100%, and fields affected and channels blocked are zero
- **AND** `tests/test_validator.py::test_untouched_catalog_validates_clean`
  asserts each

#### Scenario: Baseline readiness is an empty change set

- **WHEN** the baseline readiness trace hash is compared with the trace hash of
  an empty change set
- **THEN** they are equal
- **AND** `tests/test_validator.py::test_baseline_readiness_is_an_empty_change_set`
  asserts the equality

### Requirement: A corrected value marks the content built on it stale

Every content asset that declares a corrected attribute among its sources SHALL
be reported stale, on the listing and channel it belongs to, naming the asset.
Regenerating an asset's copy within the same change set SHALL clear its
staleness. The count of stale assets reported SHALL agree with the distinct
assets named by staleness violations.

#### Scenario: Every derived asset is marked, including across variants

- **WHEN** a wattage correction scoped to one variant is validated
- **THEN** the marketplace feed row and the print catalogue copy quoting that
  wattage are stale, each violation names the asset, and the stale-asset count
  agrees with the distinct assets named
- **AND** `tests/test_validator.py::test_corrected_attribute_marks_every_derived_asset_stale`
  asserts all of it

#### Scenario: A comparison table carries the correction to the base model's page

- **WHEN** the same variant-scoped correction is validated
- **THEN** the base model's own web page asset is stale, on the web channel,
  because its comparison table quotes the corrected variant
- **AND** `tests/test_validator.py::test_correction_reaches_the_base_variant_comparison_table`
  asserts the asset and the channel

#### Scenario: Regenerating the copy clears the asset

- **WHEN** a change set corrects the value and regenerates the shelf copy that
  quoted it
- **THEN** that asset raises no violation
- **AND** `tests/test_validator.py::test_regenerating_the_copy_clears_the_stale_asset`
  asserts its absence

#### Scenario: The walk stays inside the corrected product

- **WHEN** a change set touching one purifier variant is validated
- **THEN** no entity belonging to the unrelated snack product or its listings
  appears in any violation
- **AND** `tests/test_validator.py::test_scope_stays_inside_the_corrected_product`
  asserts the exclusion

### Requirement: A superseded literal left in the prose is caught without a model

Where copy contains the old value as a literal after the value has moved, the
system SHALL raise a stale-literal violation naming the superseded value. The
match SHALL NOT fire on a number that merely contains the old value as a
substring. Severity SHALL be blocking on channels that cannot be corrected after
the fact and advisory elsewhere.

#### Scenario: Severity follows the channel's reversibility

- **WHEN** a wattage correction leaves the old figure in copy on four channels
- **THEN** the marketplace and print channels raise it as blocking, the shelf
  and web channels as advisory, and every violation names the superseded value
- **AND** `tests/test_validator.py::test_stale_literal_is_hard_on_the_marketplace_and_print`
  asserts the severities and the detail

#### Scenario: A longer number is not a match

- **WHEN** copy contains a different, longer number that begins with the
  superseded value
- **THEN** no stale-literal violation is raised for that asset, though the asset
  is still reported stale because it was built against the old version
- **AND** `tests/test_validator.py::test_stale_literal_does_not_match_inside_a_longer_number`
  asserts both

### Requirement: Every channel rule kind is evaluated

The system SHALL evaluate each channel rule against the rendered value for the
field it binds on, and each violation SHALL name the rule that bound. The
supported rule kinds SHALL cover presence, declared type, character budget,
rendered format, permitted value set, list order matching the source, and
taxonomy mapping. Rules SHALL be data, so that removing a rule's data stops it
binding and adding a channel needs no change to the evaluator.

#### Scenario: A character budget names the budget and the overrun

- **WHEN** a regenerated marketplace title exceeds the channel's title budget
- **THEN** the violation names the listing field, the channel, the budget as
  required, the actual length as available, and the rule identifier
- **AND** `tests/test_validator.py::test_max_len_reports_the_budget_and_the_overrun`
  asserts each

#### Scenario: A missing required field names the rule and the attribute

- **WHEN** a correction clears a value that two channels require
- **THEN** each channel raises a violation naming its own rule identifier and
  the field, with one required and zero available
- **AND** `tests/test_validator.py::test_required_field_missing_names_the_rule_and_the_attribute`
  asserts both channels

#### Scenario: A value of the wrong declared type is rejected

- **WHEN** a numeric attribute is corrected to a string
- **THEN** the violation names the type rule and the declared type
- **AND** `tests/test_validator.py::test_dtype_rejects_a_value_of_the_wrong_type`
  asserts both

#### Scenario: A malformed rendered statement is rejected

- **WHEN** a regenerated marketplace feed row carries an allergen statement that
  does not match the channel's required form
- **THEN** the violation names the format rule and is blocking
- **AND** `tests/test_validator.py::test_format_rejects_a_malformed_allergen_statement`
  asserts both

#### Scenario: A code outside the channel's vocabulary is rejected

- **WHEN** a regenerated feed row carries an allergen code the channel does not
  define
- **THEN** the violation names the enumeration rule and the offending code
- **AND** `tests/test_validator.py::test_enum_rejects_a_code_outside_the_channel_vocabulary`
  asserts both

#### Scenario: A reordered list is a different declaration

- **WHEN** an ingredient list is reordered relative to its source
- **THEN** the violation names the ordered-match rule and the expected order,
  and regenerating the feed row to the new order satisfies it
- **AND** `tests/test_validator.py::test_ordered_match_rejects_a_reordered_ingredient_list`
  and `test_regenerating_the_feed_row_satisfies_ordered_match` assert both

#### Scenario: An unmapped taxonomy node is named

- **WHEN** a channel's mapping for the product's taxonomy node is removed and a
  correction is validated
- **THEN** the violation names the mapping rule and the unmapped node
- **AND** `tests/test_validator.py::test_category_mapped_names_the_unmapped_taxonomy_node`
  asserts both

### Requirement: Claims are checked against the substantiation table

A marketing claim SHALL be checked against the documented condition that
substantiates it, and a claim whose condition no longer holds SHALL raise a
blocking violation on every channel carrying it, naming the claim and the
attribute that unsubstantiated it. A claim whose condition still holds SHALL
raise nothing. The table SHALL cover exactly the claims the content standards
document defines.

#### Scenario: The table covers the documented claims and no others

- **WHEN** the claim rules are enumerated
- **THEN** they are exactly the five claims the content standards document
  defines
- **AND** `tests/test_validator.py::test_claim_table_covers_the_documented_claims`
  asserts the set

#### Scenario: A higher measured value unsubstantiates its claim

- **WHEN** the wattage correction raises the value above the claim's cap
- **THEN** blocking violations are raised on all four channels carrying the
  claim, each naming the claim and the attribute
- **AND** `tests/test_validator.py::test_a_higher_wattage_unsubstantiates_low_energy`
  asserts the severities, entities, details and channels

#### Scenario: A louder measurement and a new allergen also unsubstantiate

- **WHEN** a noise measurement rises, and separately a may-contain allergen is
  added
- **THEN** the corresponding claims are each named in a violation
- **AND** `tests/test_validator.py::test_a_louder_measurement_unsubstantiates_ultra_quiet`
  and `test_may_contain_peanuts_unsubstantiates_peanut_free` assert them

#### Scenario: A claim that holds raises nothing

- **WHEN** readiness is computed for the untouched catalog
- **THEN** no claim violation is raised
- **AND** `tests/test_validator.py::test_a_claim_that_holds_raises_nothing`
  asserts the absence

### Requirement: Allergen declarations are checked in each channel's own format

An allergen that is in force but not declared SHALL raise a violation on every
listing of the product, naming the allergen. Where a channel requires a
particular rendering, the violation SHALL carry the declaration that channel
expects. A derived ingredient order that does not match its source SHALL raise a
blocking violation naming the source attribute. An untouched catalog SHALL raise
none of these.

#### Scenario: Each food channel is told its own required form

- **WHEN** a may-contain allergen is added
- **THEN** the statement-based marketplace violation carries the sentence that
  channel expects, and the code-based marketplace violation carries that
  channel's allergen code and is blocking
- **AND** `tests/test_validator.py::test_each_food_channel_demands_its_own_allergen_format`
  asserts both

#### Scenario: An undeclared allergen is named on every listing

- **WHEN** a may-contain allergen is added
- **THEN** all five listings of the product raise a declaration violation naming
  the allergen
- **AND** `tests/test_validator.py::test_an_undeclared_allergen_is_named_on_every_listing`
  asserts the listing set

#### Scenario: Derived ingredient order must match the source

- **WHEN** the source ingredient order changes
- **THEN** blocking violations are raised naming the source attribute, on both
  the prose and the feed-row declarations
- **AND** `tests/test_validator.py::test_derived_ingredient_order_must_match_the_source`
  asserts the severity and the detail

#### Scenario: Allergen checks are quiet on an untouched catalog

- **WHEN** readiness is computed for the untouched catalog
- **THEN** no allergen violation is raised
- **AND** `tests/test_validator.py::test_allergens_are_quiet_on_an_untouched_catalog`
  asserts the absence

### Requirement: Safety fails closed

An inferred value on a safety-class attribute whose confidence is below the
threshold, with no human decision behind it, SHALL raise a blocking violation on
every channel carrying that product, naming the attribute, the confidence
observed and the threshold missed, and SHALL make the result not publishable. A
confident inference, a human decision at any confidence, and any value on an
attribute that is not safety-class SHALL NOT raise it.

The listings the gate blocks SHALL be resolved at whatever level the value was
recorded against: a listing resolves to itself, a variant to its listings, and a
product to the listings of every one of its variants. The same evidence recorded
one level higher SHALL therefore produce the same block, because both writers
record whichever entity the evidence named and a supplier notice covering every
format names the product. An entity the catalog does not know SHALL reach no
listings.

Readiness SHALL count every listing a blocking violation reaches as not ready,
resolved the same way, so that a reviewer is never shown full readiness beside a
result that is not publishable.

#### Scenario: A low-confidence allergen inference blocks every channel

- **WHEN** a may-contain allergen is in force as an inference at 0.62 confidence
  recorded against a variant
- **THEN** blocking violations are raised on all five channels, each naming the
  attribute with the threshold as required and 0.62 as available and naming the
  entity the value was recorded against, the result is not publishable, the
  safety-flag count is non-zero, and listing readiness reads zero
- **AND** `tests/test_validator.py::test_low_confidence_on_a_safety_attribute_blocks_every_listing[VAR-02A]`
  asserts each

#### Scenario: The same evidence one level up blocks the same channels

- **WHEN** the identical inference is in force recorded against the variant's
  product instead
- **THEN** the same five channels are blocked, the violations name the product
  and the attribute, the result is not publishable, and listing readiness reads
  zero - the resolution reaches every listing of every variant the product holds
- **AND** `tests/test_validator.py::test_low_confidence_on_a_safety_attribute_blocks_every_listing[PRD-02]`
  asserts each; before this change the same evidence produced no violations at
  all and left the catalog publishable

#### Scenario: Confidence above the threshold passes

- **WHEN** the same allergen is in force as an inference at 0.95 confidence
- **THEN** no safety-confidence violation is raised
- **AND** `tests/test_validator.py::test_a_confident_inference_passes_the_gate`
  asserts the absence

#### Scenario: A human decision clears the gate

- **WHEN** the same low-confidence value is in force as a human decision rather
  than an inference
- **THEN** no safety-confidence violation is raised
- **AND** `tests/test_validator.py::test_a_human_decision_clears_the_gate`
  asserts the absence

#### Scenario: A non-safety attribute is not gated

- **WHEN** a wattage value is in force as an inference at 0.40 confidence
- **THEN** no safety-confidence violation is raised
- **AND** `tests/test_validator.py::test_the_gate_ignores_attributes_that_are_not_safety_class`
  asserts the absence

### Requirement: A decision taken against a superseded version blocks republishing

Where a standing decision on an attribute was taken against an earlier source
version than the one now in force, the system SHALL raise a blocking violation
naming that attribute, reporting the version in force as required and the
version decided against as available, and telling the reader the resolution must
be revalidated. A decision taken against the version in force SHALL raise
nothing.

#### Scenario: An older decision blocks

- **WHEN** the value in force stands on v2 and the standing decision was taken
  against v1
- **THEN** a blocking violation names the attribute, reports 2 as required and 1
  as available, and says the resolution must be revalidated
- **AND** `tests/test_validator.py::test_a_decision_taken_against_an_older_version_blocks_republishing`
  asserts each

#### Scenario: A current decision does not block

- **WHEN** the standing decision was taken against the version now in force
- **THEN** no version violation is raised for that attribute
- **AND** `tests/test_validator.py::test_a_current_decision_does_not_block_republishing`
  asserts the absence

### Requirement: An uncited change is not publishable

Any action that sets an attribute or regenerates copy without naming the source
document it was read from SHALL raise a blocking violation naming the action or
the asset, and SHALL make the result not publishable. A cited action SHALL raise
nothing.

#### Scenario: An uncited attribute change is refused

- **WHEN** an attribute is set with no source reference
- **THEN** a blocking violation names the attribute and the action, and the
  result is not publishable
- **AND** `tests/test_validator.py::test_an_uncited_change_is_not_publishable`
  asserts each

#### Scenario: An uncited regeneration is refused

- **WHEN** copy is regenerated with no source reference
- **THEN** the citation violation names exactly that asset
- **AND** `tests/test_validator.py::test_an_uncited_regeneration_is_not_publishable`
  asserts the entity

#### Scenario: A cited change raises nothing

- **WHEN** a cited attribute correction is validated
- **THEN** no citation violation is raised
- **AND** `tests/test_validator.py::test_a_cited_change_raises_nothing` asserts
  the absence

### Requirement: Every violation names what bound and against what

Every violation SHALL carry the constraint, the entity it binds on and a
readable detail; entities SHALL resolve to a real asset, listing or variant; and
a channel-rule violation SHALL name the rule identifier. Violations SHALL be
collapsed to one row per constraint, entity and channel, and returned in a
stable sorted order.

#### Scenario: Every row is attributable

- **WHEN** a change set holding two corrections is validated
- **THEN** every violation names a constraint, a resolvable entity and a detail,
  and every channel-rule violation names a rule identifier
- **AND** `tests/test_validator.py::test_every_violation_names_the_binding_rule_and_the_entity`
  asserts each

#### Scenario: One row per binding rule, in a stable order

- **WHEN** a correction is validated
- **THEN** no constraint, entity and channel triple repeats, and the rows are in
  sorted order
- **AND** `tests/test_validator.py::test_violations_are_collapsed_to_one_row_per_binding_rule`
  asserts both

### Requirement: A blocked channel is shown with its reason, never dropped

Withholding a listing from a channel SHALL remove that channel's violations
while still counting as a republish step and leaving the blocked-channel count
unchanged, so that the decision appears in the diff and in the measures rather
than as a silently absent channel. Publishability SHALL be exactly the absence
of blocking violations.

#### Scenario: Withholding costs a step and still shows the block

- **WHEN** a correction is validated with and without withholding the print
  listing
- **THEN** the withheld run reports no violations on that channel, the same
  blocked-channel count, and more republish steps
- **AND** `tests/test_validator.py::test_withholding_a_channel_costs_a_step_and_still_shows_the_block`
  asserts each

#### Scenario: Publishability is the absence of blocking violations

- **WHEN** an empty change set, a wattage correction and an allergen correction
  are each validated
- **THEN** each result is publishable exactly when it holds no blocking
  violation
- **AND** `tests/test_validator.py::test_feasibility_is_exactly_the_absence_of_hard_violations`
  asserts the equivalence

### Requirement: Validation is fast enough to fan out

A validation pass SHALL complete within 250 milliseconds, so candidate
resolutions can be validated concurrently behind a live reviewer interface.

#### Scenario: A pass stays inside the budget

- **WHEN** a correction is validated and readiness is computed for the untouched
  catalog
- **THEN** each reports a runtime under 250 milliseconds
- **AND** `tests/test_validator.py::test_validation_is_fast_enough_to_fan_out`
  asserts both

### Requirement: A published artefact that cannot be recalled is held to the version it went out on

Where a channel declares a freeze window - which marks a channel whose published
artefact cannot be withdrawn once it has left - a listing whose last published
source version has been overtaken by a value now in force SHALL raise a blocking
violation naming the listing and the channel, reporting the version in force as
required and the version in print as available, and telling the reader that a
reprint decision is needed rather than regenerated copy. The detail SHALL carry
the lead time the channel documents.

The rule SHALL NOT depend on a press date: none is held anywhere in the catalog.
The trigger is a superseded published version on an irreversible channel.

Regenerating the copy SHALL NOT clear the violation, because rebuilding an asset
changes nothing a shopper is already holding. Republishing the listing and
withholding it SHALL each clear it, because each changes what is in the world. A
listing that has never been published SHALL raise nothing, because there is no
artefact that can be stale. A channel that declares no freeze window SHALL raise
nothing, because a reversible channel answers a moved value by republishing.

The version a listing last went out on SHALL be read from the record of its last
publish where one exists, and from the catalog otherwise.

#### Scenario: A printed listing left on a superseded version is blocking

- **WHEN** a wattage correction is validated against a catalog whose print
  listing went to press on the earlier version
- **THEN** a blocking violation is raised on that listing and the print channel,
  reporting 2 as required and 1 as available, and the detail names the channel's
  documented lead time and calls for a reprint decision
- **AND** `tests/test_validator.py::test_a_frozen_channel_reports_the_artefact_left_on_a_superseded_version`
  asserts each

#### Scenario: Regenerating the copy does not clear it

- **WHEN** the same correction is validated together with a regeneration of the
  printed listing's copy
- **THEN** the asset is no longer reported stale, and the freeze-window
  violation on that listing still stands
- **AND** `tests/test_validator.py::test_regenerating_the_copy_does_not_clear_the_freeze_window`
  asserts both

#### Scenario: A reversible channel is not held to it

- **WHEN** the same correction is validated
- **THEN** the only listing raising it is the print listing, and the web listing
  raises nothing
- **AND** `tests/test_validator.py::test_a_reversible_channel_is_not_held_to_the_freeze_window`
  asserts both

#### Scenario: Withholding the listing is the reprint decision

- **WHEN** the correction is validated together with an action withholding the
  printed listing from its channel
- **THEN** no freeze-window violation is raised
- **AND** `tests/test_validator.py::test_withholding_the_listing_is_the_reprint_decision`
  asserts the absence

#### Scenario: Republishing the listing clears it

- **WHEN** the listing's last published version is recorded as the version now
  in force and the correction is validated
- **THEN** no freeze-window violation is raised
- **AND** `tests/test_validator.py::test_republishing_the_listing_clears_the_freeze_window`
  asserts the absence

#### Scenario: A listing that has never gone to press has nothing to be stale

- **WHEN** the printed listing carries no published version at all
- **THEN** no freeze-window violation is raised - an empty value is no artefact,
  not a version of zero
- **AND** `tests/test_validator.py::test_a_listing_that_has_never_gone_to_press_has_nothing_to_be_stale`
  asserts the absence
