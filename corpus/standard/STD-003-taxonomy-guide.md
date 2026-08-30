---
id: STD-003
type: STANDARD
title: Internal Taxonomy and Channel Mapping
owner: Product Data
version: 2.7
effective: 2026-02-14
entities: [PRD-01, PRD-02, PRD-03, PRD-04, PRD-05, PRD-06, CH-MKT-A, CH-MKT-B]
tags: [taxonomy, category, mapping, attribute-map, facets]
---

# Internal Taxonomy and Channel Mapping

## Purpose

The internal tree is the only category a product has. Every channel category is
a mapping *from* it, computed and re-computed, never authored by hand on the
listing.

## The internal tree

| category | products |
|---|---|
| `home.air-treatment.purifiers` | PRD-01 AeroPure 300 Air Purifier |
| `home.air-treatment.fans` | PRD-06 Voltaic Desk Fan V2 |
| `home.kitchen.kettles` | PRD-04 Cascade Rapid Kettle |
| `audio.headphones.earbuds` | PRD-03 Brightline BT-200 Earbuds |
| `food.snacks.bars` | PRD-02 Orchard Valley Trail Mix Bar |
| `food.snacks.granola` | PRD-05 Orchard Valley Granola Clusters |

Prefixes are load-bearing. An attribute definition's `applies_to` is a prefix
match: `home.` picks up purifiers, fans and kettles; `home.air-treatment` picks
up purifiers and fans but not kettles; `food.` picks up bars and granola and
carries the allergen paths with it, which is what makes PRD-02 and PRD-05
regulated and PRD-01 not.

Never deepen the tree to solve a channel's problem. If a marketplace wants a
distinction the internal tree does not make, the distinction belongs in that
channel's mapping, not in our categories.

## Attribute mapping by channel

CH-MKT-A and CH-MKT-B rename fields. Everything else maps identically, and an
identity mapping is still a mapping - it is declared, not assumed.

| internal path | CH-MKT-A field | CH-MKT-B field |
|---|---|---|
| `specs.power_w` | `wattage` | `powerConsumption` |
| `food.allergens.contains` + `food.allergens.may_contain` | `allergen_statement` | `allergenCodes` |
| `identifiers.gtin` | `gtin` | `globalTradeItemNumber` |
| `food.ingredients` | `ingredients` | `ingredientList` |
| all others | identity | identity |

Two internal attributes collapse into one channel field on both marketplaces:
`contains` and `may_contain` become a single `allergen_statement` on CH-MKT-A
and a single `allergenCodes` list on CH-MKT-B. Impact analysis must therefore
run in the direction internal-to-channel. A change to `may_contain` alone still
rewrites the whole field, and a diff taken on the channel field cannot tell you
which internal attribute moved.

## Category mapping

CH-MKT-A requires a mapped category on every listing (RUL-A07,
`CATEGORY_MAPPED`). An internal category with no marketplace counterpart is a
HARD `channel_schema` violation and is reported as an unmapped category naming
the internal path - it is never approximated to the nearest parent.

| internal category | CH-MKT-A | CH-MKT-B |
|---|---|---|
| `home.air-treatment.purifiers` | Home > Air Quality > Purifiers | HOME_AIR_PURIFIER |
| `home.air-treatment.fans` | Home > Air Quality > Fans | HOME_AIR_FAN |
| `home.kitchen.kettles` | Home > Kitchen > Kettles | HOME_KITCHEN_KETTLE |
| `audio.headphones.earbuds` | Electronics > Audio > Earbuds | AUDIO_EARBUD |
| `food.snacks.bars` | Grocery > Snacks > Bars | FOOD_SNACK_BAR |
| `food.snacks.granola` | Grocery > Snacks > Cereal | FOOD_SNACK_CEREAL |

CH-MKT-B's taxonomy is flatter than ours and granola maps to its cereal node.
The mapping is lossy in that direction and must not be inverted: reading a
category back from CH-MKT-B tells you nothing about which internal node it came
from.

## Facets

CH-SEARCH facets are **derived** from attributes and the internal category.
They are never authored. A facet that cannot be re-derived from an attribute is
deleted rather than kept, because a hand-set facet survives corrections that
should have removed it.

| facet | derived from |
|---|---|
| `category` | internal category, leaf node |
| `power_band` | `specs.power_w` bucketed at 50 W and 100 W |
| `coverage_band` | `specs.coverage_m2` bucketed at 30 m² and 60 m² |
| `allergen_free` | `food.allergens.contains` and `may_contain`, both empty for that allergen |
| `fibre` | `food.fibre_g` >= 6 |

`power_band` crosses a bucket boundary at 50 W. VAR-01B moving from 45 W to
65 W therefore changes its facet as well as its copy, and a correction that
regenerates the copy without re-deriving the facet leaves the variant filterable
under a band it no longer belongs to.

## Related

STD-001 (title formulas), STD-002 (canonical attribute values),
CHN-002 (CH-MKT-A), CHN-003 (CH-MKT-B), CHN-005 (CH-SHELF and CH-SEARCH).
