# blast-radius Specification

## Purpose
Traces a corrected value to every field, content asset, listing and channel
built on it, deriving the answer from the catalog rather than from a judgement,
and drawing each hop with a relation a reviewer can read.

## Requirements

### Requirement: The catalog map is derived, not stored

The map of products, variants, listings and channels SHALL be derived from the
catalog on read, with a relation on every edge and every edge endpoint present
as a node, so the map cannot drift from the catalog it claims to draw.

The map SHALL also carry the external systems currently connected, joined to
what they feed, so that "where did this come from" is answerable one hop
further out than the supplier. A system that is connected but has delivered
nothing SHALL still appear; an estate that only shows what has already spoken
cannot show a silent system.

No node's position SHALL be read from stored data. A tier whose membership
changes while the application is running cannot be laid out from coordinates
written at generation time, and a stored position is a second account of a
structure the catalog already settles.

The map SHALL follow connections as they change: connecting a system SHALL add
it and its edges, and disconnecting one SHALL mark it degraded rather than
removing it and the facts it delivered.

#### Scenario: Each tier is joined with a derived edge

- **WHEN** the map is requested
- **THEN** there is one product-to-supplier edge per product, one
  product-to-variant edge per variant and one listing edge per listing, every
  edge endpoint is a known node, and the planning horizon matches the catalog's
- **AND** `tests/test_propagation.py::test_the_map_joins_every_tier_with_a_derived_edge`
  asserts each

#### Scenario: A quiet catalog reports no correction

- **WHEN** the map is requested with no facts recorded
- **THEN** the correction summary is empty in every field
- **AND** `tests/test_propagation.py::test_a_quiet_catalog_reports_no_corrections`
  asserts the empty shape

#### Scenario: Connected systems are on the map, including the silent ones

- **WHEN** the map is requested with the estate connected and one system having
  delivered nothing
- **THEN** every connected system is a node, each is joined to what it feeds,
  and the silent one is present
- **AND** `tests/test_connections.py::test_connected_systems_are_on_the_map_including_silent_ones`
  asserts each

#### Scenario: No node carries a stored position

- **WHEN** the catalog and the map are inspected for node coordinates
- **THEN** the catalog stores none and the map derives every position from the
  tier and the live membership of that tier
- **AND** `tests/test_connections.py::test_no_node_position_is_stored`
  asserts both

#### Scenario: Disconnecting a system degrades it and keeps what it delivered

- **WHEN** a system that has delivered facts is disconnected and the map is
  requested again
- **THEN** the system is still a node and is marked degraded, its edges remain,
  and the facts it delivered are unchanged
- **AND** `tests/test_connections.py::test_disconnecting_degrades_without_retracting`
  asserts each

### Requirement: Corrections in force are shown with the document behind them

Where a value in force stands on a later document version than the content was
built on, the map SHALL report the document, the attribute with its value,
version, source document, provenance kind and confidence, the count of assets
left standing on a moved version, and a summary line reading old value to new
value. A listing whose channel refused it SHALL be shown with that status rather
than dropped from the map.

#### Scenario: A correction, its source and a refused listing all appear

- **WHEN** a base-model certification, a variant correction and a channel
  rejection are all in force
- **THEN** the map names the revised document, gives the corrected attribute's
  value, version, document, provenance and confidence, reports the rejected
  listing's status on its edge, counts the stale assets, and carries an
  old-to-new summary line
- **AND** `tests/test_propagation.py::test_corrections_in_force_show_on_the_map_with_their_source`
  asserts each

#### Scenario: A question asked from before the correction sees the baseline

- **WHEN** the map is requested with a recording instant before the correction
  landed
- **THEN** no correction is reported and the requested recording instant is
  echoed back
- **AND** `tests/test_propagation.py::test_recorded_time_hides_a_correction_that_had_not_arrived_yet`
  asserts both

### Requirement: The walk reaches everything built on the corrected value

From a root - a document, a product, a variant, an attribute, an asset, a
listing or a channel - the system SHALL return the affected attributes,
variants, products, assets, listings and channels, and SHALL reach nothing that
did not use the value. The affected channels SHALL be exactly the channels of
the affected listings.

#### Scenario: Every channel that used the value is reached, and no other

- **WHEN** a variant wattage attribute is traced
- **THEN** every asset declaring it is affected, the five listings and four
  channels that carry it are affected, the affected channels are exactly the
  channels of those listings, and the unrelated product's variants and its
  search channel are absent
- **AND** `tests/test_propagation.py::test_the_correction_reaches_every_channel_that_used_the_old_value`
  asserts each

#### Scenario: A variant correction reaches the base model's page

- **WHEN** the same variant wattage attribute is traced
- **THEN** the base model's page asset, its listing and the base variant are all
  affected, and the chain draws the derivation hop to that asset and the listing
  hop from it
- **AND** `tests/test_propagation.py::test_a_variant_correction_reaches_the_base_page_through_the_comparison_table`
  asserts the sets and both hops

#### Scenario: Every listing the validator flags is inside the radius

- **WHEN** the same correction is validated and traced
- **THEN** every listing named by a violation is among the traced listings
- **AND** `tests/test_propagation.py::test_every_listing_the_validator_flags_is_inside_the_blast_radius`
  asserts the containment

### Requirement: Every hop carries a relation the reader can label

Each link in the chain SHALL name a source, a target and a relation drawn from
the closed set of relations the system defines. A document revision SHALL be
drawn as a supersession hop between versions and a definition hop to the
attribute it defines, and a document SHALL NOT be drawn as defining an attribute
another document has since certified.

#### Scenario: Every hop from every root kind is labelled

- **WHEN** each of the seven root kinds is traced
- **THEN** the chain is non-empty, every relation is one the system defines, and
  every hop names both ends
- **AND** `tests/test_propagation.py::test_every_chain_link_is_drawn_with_a_relation_the_ui_can_label`
  asserts each per root

#### Scenario: A revision is a supersession hop

- **WHEN** a revised document is traced
- **THEN** the chain draws the new version superseding the old and defining the
  corrected attribute, and the attribute another document certified is not
  among the affected attributes
- **AND** `tests/test_propagation.py::test_a_document_revision_is_drawn_as_a_supersedes_hop`
  asserts each

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

### Requirement: The walk is bounded and terminates

The walk SHALL accept a depth bound that limits how far it travels, SHALL
terminate on a cyclic catalog without redrawing a hop, and SHALL cap the length
of the drawn chain without truncating the affected sets. An unknown root SHALL
return an empty scope rather than raising.

#### Scenario: Depth bounds what is reached

- **WHEN** an attribute is traced at depth one, two and three
- **THEN** depth one reaches only the attribute and its variant, depth two
  reaches assets and listings but no channels, depth three reaches channels, and
  the chain grows with each depth
- **AND** `tests/test_propagation.py::test_depth_bounds_the_walk` asserts each

#### Scenario: A cycle terminates and draws no hop twice

- **WHEN** the catalog is made cyclic by having two variants' assets quote each
  other and an attribute is traced
- **THEN** the walk finishes, no hop is drawn twice, the chain stays within the
  cap, and the added asset is still reported affected
- **AND** `tests/test_propagation.py::test_a_cyclic_catalog_terminates_and_never_redraws_a_hop`
  asserts each

#### Scenario: The cap shortens the explanation, never the answer

- **WHEN** a channel that reaches the whole catalog is traced
- **THEN** the chain is exactly the cap long while the listing, channel and
  asset totals still cover the entire catalog
- **AND** `tests/test_propagation.py::test_the_chain_is_capped_without_truncating_the_scope`
  asserts each

#### Scenario: An unknown root is an empty answer, not an exception

- **WHEN** a variant identifier and an attribute path that do not exist are
  traced
- **THEN** the root is echoed, the chain is empty, every affected list is empty
  and every total is zero
- **AND** `tests/test_propagation.py::test_an_unknown_root_returns_an_empty_scope_rather_than_raising`
  asserts each

### Requirement: A trace is reproducible

Two traces of the same root against the same catalog SHALL be identical,
because the traversal is part of the audit trail.

#### Scenario: Twenty traces serialise identically

- **WHEN** an attribute root and a product root are each traced twenty times
- **THEN** each produces a single distinct serialisation
- **AND** `tests/test_propagation.py::test_two_traces_of_the_same_root_are_identical`
  asserts both

### Requirement: A variant diff is the evidence for a scope decision

The system SHALL return, for a product, the attribute table across its variants
with the attributes that differ marked, each cell carrying the value, the source
document, that document's version, the provenance kind and the confidence.
Attribute rows SHALL carry the human label, the unit and the safety class. A
value only one variant carries SHALL count as a difference. An unknown product
SHALL return an error rather than raise.

#### Scenario: Exactly the differing attributes are marked

- **WHEN** the purifier product's variants are diffed at baseline
- **THEN** both variants are listed in order, only the identifier and coverage
  attributes are marked as differing, and both variants read the same wattage
- **AND** `tests/test_propagation.py::test_variant_diff_marks_exactly_the_attributes_that_differ`
  asserts each

#### Scenario: Each value shows the document it stands on

- **WHEN** the base model has been independently certified and the other variant
  corrected by a different document
- **THEN** the wattage row is marked differing and each cell carries its value,
  version, document, provenance kind and confidence
- **AND** `tests/test_propagation.py::test_variant_diff_shows_the_document_each_value_stands_on`
  asserts both cells in full

#### Scenario: A value only one variant carries is a difference

- **WHEN** an attribute is removed from one variant and the product is diffed
- **THEN** that row is marked differing and holds only the remaining variant
- **AND** `tests/test_propagation.py::test_a_value_only_one_variant_carries_is_a_difference_too`
  asserts both

#### Scenario: Rows carry label, unit and safety class

- **WHEN** the food product and the purifier product are diffed
- **THEN** the allergen row is marked safety-class and carries its label, and
  the wattage row carries its unit
- **AND** `tests/test_propagation.py::test_variant_diff_carries_the_label_and_the_safety_flag`
  asserts each

#### Scenario: An unknown product is an error, not an exception

- **WHEN** a product identifier that does not exist is diffed
- **THEN** an error is returned
- **AND** `tests/test_propagation.py::test_an_unknown_product_is_an_error_not_an_exception`
  asserts it

### Requirement: Derivation is readable in both directions

The system SHALL report, for a content asset, the listing and variant it belongs
to and every attribute it was built from with the document and version each
value stands on, marking sources that belong to a different variant. For a
listing it SHALL report every asset on it and the union of their sources. An
unknown identifier SHALL return an error rather than raise.

#### Scenario: A cross-variant source is named as such

- **WHEN** the base model's page asset's derivation is read
- **THEN** it names the listing and variant, marks exactly the other variant's
  four attributes as cross-variant, and every source carries a document and
  version
- **AND** `tests/test_propagation.py::test_get_derivation_names_the_cross_variant_edge`
  asserts each

#### Scenario: A listing's derivation covers every asset on it

- **WHEN** a listing's derivation is read
- **THEN** it lists exactly that listing's assets and includes the corrected
  attribute among its sources
- **AND** `tests/test_propagation.py::test_get_derivation_of_a_listing_covers_every_asset_on_it`
  asserts both

#### Scenario: An unknown identifier is an error, not an exception

- **WHEN** an asset identifier that does not exist is read
- **THEN** an error is returned
- **AND** `tests/test_propagation.py::test_get_derivation_of_an_unknown_id_is_an_error_not_an_exception`
  asserts it

### Requirement: A channel's rules are readable, narrowed to a field

The system SHALL return a channel's rules, optionally narrowed to those binding
on a named channel-side field together with the internal attribute paths behind
that field, and SHALL expose the channel's own publishing constraints. An
unknown channel SHALL return an error rather than raise.

#### Scenario: Only the rules binding on the named field are returned

- **WHEN** a marketplace channel's rules are requested for one field
- **THEN** only the two rules binding on that field are returned, with the
  internal attribute path behind it
- **AND** `tests/test_propagation.py::test_channel_rules_returns_only_what_binds_on_the_named_field`
  asserts both

#### Scenario: Without a field the whole channel is returned

- **WHEN** the same channel's rules are requested with no field
- **THEN** all seven rules are returned in order, with the channel's required
  attributes and fields
- **AND** `tests/test_propagation.py::test_channel_rules_without_a_field_returns_the_whole_channel`
  asserts each

#### Scenario: A channel's publishing constraint is visible on it

- **WHEN** the print channel's rules are requested, and then an unknown
  channel's
- **THEN** the print channel reports its freeze period, and the unknown channel
  returns an error
- **AND** `tests/test_propagation.py::test_the_print_freeze_window_is_visible_on_its_channel`
  asserts both

### Requirement: One listing's current state is readable

The system SHALL report, for a listing, its channel, its status, the values
behind it with the document each stands on, and which of its assets are stale
and through which attribute references. An unknown listing SHALL return an error
rather than raise.

#### Scenario: A listing is clean until something moves under it

- **WHEN** a listing's state is read against an unchanged catalog
- **THEN** no asset is stale, the status is the prepared state, the value reads
  the baseline figure, and the channel is named
- **AND** `tests/test_propagation.py::test_a_listing_is_clean_until_something_moves_under_it`
  asserts each

#### Scenario: A corrected value marks the copy that quoted it

- **WHEN** a correction is in force and the listing's state is read
- **THEN** its assets are stale, the value carries its new version, document,
  provenance and confidence, every stale asset names the attribute reference,
  and the base model's page is stale through the comparison table alone
- **AND** `tests/test_propagation.py::test_a_corrected_value_marks_the_copy_that_quoted_it_stale`
  asserts each

#### Scenario: A refused feed is reported on the listing

- **WHEN** a channel rejection is in force and the listing's state is read
- **THEN** the listing reports the rejected status
- **AND** `tests/test_propagation.py::test_a_rejected_feed_is_reported_on_the_listing_with_its_status`
  asserts it

#### Scenario: An unknown listing is an error, not an exception

- **WHEN** a listing identifier that does not exist is read
- **THEN** an error is returned
- **AND** `tests/test_propagation.py::test_an_unknown_listing_is_an_error_not_an_exception`
  asserts it

### Requirement: The walk answers in the identifiers people act on

A trace SHALL additionally resolve to the SKUs it reaches, each carrying the
listings and channels that SKU is live on.

A blast radius expressed only in internal identifiers is one only this system
can read. The buyer asked which products are affected, the supplier asked what
to reissue and the marketplace account manager asked what to pull all work in
SKUs, and a finding they cannot address is a finding that does not travel.

A SKU SHALL be reported once however many listings carry it, and the listings
and channels under it SHALL be ordered, so two reads of one trace agree.

#### Scenario: A trace names the SKUs it reaches

- **WHEN** a correction is traced
- **THEN** every affected variant appears once with its SKU, the listings it is
  live on and the channels those listings feed
- **AND** `tests/test_publication.py::test_the_blast_radius_answers_in_skus`
  asserts each

#### Scenario: A correction to one variant names the sibling it reaches

- **WHEN** a correction scoped to one variant is traced, and another variant's
  content quotes the corrected value
- **THEN** both SKUs are reported
- **AND** `tests/test_publication.py::test_a_correction_to_one_variant_names_the_siblings_it_reaches`
  asserts the second, which is the case the whole propagation design exists for

### Requirement: The systems that must be told are grouped with their work

A trace SHALL group the listings it reaches by the publication system that owns
each one, carrying the SKUs affected on that system.

"Eleven listings" is a number and "these four SKUs on these three systems" is a
work list, and the second is what somebody acts on.

The publication systems SHALL be derived from the channels the catalog declares
rather than configured separately. A publication list that could disagree with
the channel list is a second account of where content goes, and the first thing
it would disagree about is the channel somebody has just added.

#### Scenario: Publication systems follow the channels

- **WHEN** the publication systems are read
- **THEN** there is exactly one per channel the catalog declares, each with a
  distinct identifier and its own endpoint
- **AND** `tests/test_publication.py::test_publication_systems_are_derived_from_the_channels`
  asserts each

#### Scenario: Each system carries the SKUs it has to reissue

- **WHEN** a trace is grouped by publication system
- **THEN** each system appears once, carrying the listings it owns and the SKUs
  those listings carry, both ordered
- **AND** `tests/test_publication.py::test_the_systems_to_tell_are_grouped_with_their_skus`
  asserts each

#### Scenario: A system that cannot recall what it published says so

- **WHEN** the publication systems are read
- **THEN** a system is marked unrecallable exactly where its channel declares a
  freeze window, because the window exists because the artefact cannot be pulled
  back and the two are the same fact
- **AND** `tests/test_publication.py::test_a_channel_that_cannot_be_recalled_says_so`
  asserts the correspondence
