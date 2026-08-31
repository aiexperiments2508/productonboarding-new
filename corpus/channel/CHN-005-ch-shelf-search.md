---
id: CHN-005
type: CHANNEL
title: CH-SHELF and CH-SEARCH - Shelf-Edge Labels and Search Facets
owner: Store Systems
version: 2.9
effective: 2026-02-05
entities: [CH-SHELF, CH-SEARCH, PRD-01, VAR-01A, VAR-01B, PRD-02, VAR-02A]
tags: [channel, shelf, label, facets, search, derived, truncation]
---

# CH-SHELF and CH-SEARCH - Shelf-Edge Labels and Search Facets

## Channel profiles

| property | CH-SHELF | CH-SEARCH |
|---|---|---|
| kind | SHELF | SEARCH |
| freeze window | 0 days | 0 days |
| asset | `shelf_text` | `facets` |
| authored | composed from attributes | never - derived only |

Both channels are short-form and both are dominated by their neighbours: a
shelf label sits beside five others, a facet sits beside every other value in
its filter. Neither can carry a qualifier, a footnote or a caveat, which is why
neither may carry a claim.

## Shelf-edge label rules

| rule | field | kind | value | severity |
|---|---|---|---|---|
| RUL-S01 | shelf_text | MAX_LEN | 40 | HARD |
| RUL-S02 | shelf_text | FORMAT | `\d+\s?W`, appliances only | SOFT |

Forty characters is the physical label. RUL-S01 is hard and is measured on the
rendered string including spaces.

RUL-S02 requires an appliance label to carry its wattage as digits followed by
`W`, with or without a space: `65W` and `65 W` both satisfy it. It is SOFT
because a small number of appliance lines legitimately have no meaningful rated
power, and a warning that a shop can override is the right treatment. It is not
soft because the wattage is optional when it exists.

The rule has a second effect that matters more than the first: **it guarantees
the wattage appears as a literal in shelf copy**, so any wattage correction
reaches CH-SHELF as a `stale_literal` and never as a silent no-op. VAR-01B's
label moving from `Northaven AP300 Max 45W` to `Northaven AP300 Max 65W` is a content
change on a channel that would otherwise look untouched by a spec correction.

Labels are truncated at composition, not at print. A label composed to 44
characters and cut to 40 by the label printer loses the wattage from the end of
the string, satisfies RUL-S01 and fails RUL-S02, which is how a truncation
defect surfaces as a format warning rather than a length one.

## No claims on shelf labels

`shelf_text` never carries a claim word. `ultra-quiet`, `peanut-free` and
`high-fibre` are substantiated statements requiring the surrounding copy that
40 characters cannot hold. A label states identity and one specification, and
nothing else.

## Facet derivation

CH-SEARCH holds no authored content. Facets are computed from the in-force
attribute values and the internal category (STD-003), and are recomputed
whenever any of their inputs changes.

| facet | derived from | recomputed when |
|---|---|---|
| `category` | internal category leaf | category remapped |
| `power_band` | `specs.power_w`, buckets at 50 W and 100 W | wattage corrected |
| `coverage_band` | `specs.coverage_m2`, buckets at 30 m² and 60 m² | coverage corrected |
| `allergen_free:<allergen>` | `food.allergens.contains` and `may_contain` | either allergen list changes |
| `fibre` | `food.fibre_g` >= 6 | fibre corrected |

**A facet is removed as readily as it is added.** The failure mode on a search
channel is not a missing filter, it is a stale one: a product that stays
filterable under `allergen_free:peanut` after a shared-line change is presented
to exactly the customer who must not see it. Facet removal is therefore
processed before facet addition, and a facet whose derivation can no longer be
evaluated is dropped rather than carried forward.

Facets are never hand-set, never inherited from a sibling variant, and never
copied from a marketplace. A facet that cannot be re-derived from an attribute
has no evidence behind it and is deleted.

## Related

STD-002 (units and rounding), STD-003 (facet derivation and category tree),
CHN-001 (where the claim actually lives), POL-001 (allergen facets),
POL-002 (what counts as material).
