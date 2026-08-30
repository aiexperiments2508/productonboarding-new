---
id: CHN-002
type: CHANNEL
title: CH-MKT-A - Marketplace A Feed Specification
owner: Marketplace Operations
version: 6.2
effective: 2026-03-01
entities: [CH-MKT-A, MKA-4102, PRD-01, VAR-01B, PRD-02, VAR-02A, VAR-02B]
tags: [channel, marketplace, feed, schema, rejection, mka-4102, wattage, gtin]
---

# CH-MKT-A - Marketplace A Feed Specification

## Channel profile

| property | value |
|---|---|
| id | CH-MKT-A |
| kind | MARKETPLACE |
| freeze window | 0 days |
| schema | strict, validated on ingest |
| rejection prefix | `MKA-` |

Marketplace A validates the whole feed row synchronously and rejects the row,
not the field. There is no partial acceptance: one bad `wattage` withdraws the
listing's title, bullets and price along with it.

## Field rules

| rule | field | kind | value | severity |
|---|---|---|---|---|
| RUL-A01 | title | MAX_LEN | 80 | HARD |
| RUL-A02 | wattage | REQUIRED | - | HARD |
| RUL-A03 | wattage | DTYPE | `int` | HARD |
| RUL-A04 | allergen_statement | REQUIRED | - | HARD |
| RUL-A05 | allergen_statement | FORMAT | `^Contains: .+\.(?: May contain: .+\.)?$` | HARD |
| RUL-A06 | gtin | REQUIRED | - | HARD |
| RUL-A07 | category | CATEGORY_MAPPED | - | HARD |

## Field names

Marketplace A does not use our attribute paths. The mapping is in STD-003; the
four that are renamed are repeated here because feed defects are almost always
raised against the marketplace name rather than the internal one.

| internal path | feed field |
|---|---|
| `specs.power_w` | `wattage` |
| `food.allergens.contains` + `food.allergens.may_contain` | `allergen_statement` |
| `identifiers.gtin` | `gtin` |
| `food.ingredients` | `ingredients` |

## Rejection code MKA-4102

**`MKA-4102` - required attribute missing or wrong type.**

This is the only rejection code Marketplace A raises for a data defect, and its
detail line names the field but not the cause. In practice it means one of:

| condition | example |
|---|---|
| required field absent | appliance row with no `wattage` (RUL-A02) |
| required field null or empty string | `gtin` present but blank (RUL-A06) |
| numeric field sent as text | `wattage` sent as `"65 W"` instead of `65` (RUL-A03) |
| numeric field sent as a range | `wattage` sent as `"60-70"` |
| food row with no allergen statement | RUL-A04 |

A row rejected with MKA-4102 is not retried with the same payload. Re-sending
an unchanged row produces an identical rejection and counts against the feed's
error rate, which is what turns a single defect into a suppression. Fix the
attribute at source, re-derive the row, then resubmit.

Wattage is where MKA-4102 lands most often, because `specs.power_w` is the one
appliance attribute this marketplace requires and suppliers send it as free
text more often than as a number. STD-002 governs the normalisation; the
marketplace does not accept it in any other shape.

## Allergen statement format

`allergen_statement` is one string, assembled from both allergen attributes:

```
Contains: almonds. May contain: peanuts.
```

The `May contain:` sentence is omitted entirely when `may_contain` is empty; it
is never written as an empty list, `none` or `n/a`. The regex in RUL-A05 is
anchored at both ends and both sentences must terminate with a full stop.

## Title truncation

The 80-character limit is 40 characters tighter than CH-WEB. Titles are not
truncated mechanically from the CH-WEB title - a mid-word cut publishes as
written and stays there. The CH-MKT-A title is composed to the formula in
STD-001 with the variant qualifier retained and the headline spec dropped.

## Related

STD-002 (integer wattage, GTIN), STD-003 (attribute and category mapping),
CHN-003 (CH-MKT-B, which rejects differently),
POL-001 (allergen handling), INC-2025-041 (an MKA-4102 storm on PRD-04),
INC-2025-063.
