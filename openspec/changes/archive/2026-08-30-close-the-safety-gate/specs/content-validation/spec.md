## MODIFIED Requirements

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

## ADDED Requirements

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
