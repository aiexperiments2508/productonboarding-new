---
id: CHN-003
type: CHANNEL
title: CH-MKT-B - Marketplace B Feed Specification
owner: Marketplace Operations
version: 5.5
effective: 2026-03-01
entities: [CH-MKT-B, MKB-2201, MKB-2208, PRD-02, VAR-02A, VAR-02B, PRD-05]
tags: [channel, marketplace, feed, schema, rejection, mkb-2201, mkb-2208, allergen, ingredients]
---

# CH-MKT-B - Marketplace B Feed Specification

## Channel profile

| property | value |
|---|---|
| id | CH-MKT-B |
| kind | MARKETPLACE |
| freeze window | 0 days |
| schema | own taxonomy and own field names |
| rejection prefix | `MKB-` |

Marketplace B validates asynchronously. A row is accepted at submission and
rejected up to several hours later, so a defect that CH-MKT-A would have
bounced on contact is already live here when the rejection arrives.

## Field rules

| rule | field | kind | value | severity |
|---|---|---|---|---|
| RUL-B01 | title | MAX_LEN | 120 | HARD |
| RUL-B02 | powerConsumption | REQUIRED | - | HARD |
| RUL-B03 | allergenCodes | ENUM | `AL-PEANUT`, `AL-NUT`, `AL-MILK`, `AL-GLUTEN`, `AL-SOY`, `AL-EGG` | HARD |
| RUL-B04 | ingredientList | ORDERED_MATCH | `food.ingredients` | HARD |
| RUL-B05 | globalTradeItemNumber | REQUIRED | - | HARD |

## Field names

| internal path | feed field |
|---|---|
| `specs.power_w` | `powerConsumption` |
| `food.allergens.contains` + `food.allergens.may_contain` | `allergenCodes` |
| `identifiers.gtin` | `globalTradeItemNumber` |
| `food.ingredients` | `ingredientList` |

Marketplace B is camel-case throughout and its taxonomy is its own (STD-003).
Neither is negotiable and neither maps back cleanly, so the feed row is always
built forwards from the internal attributes.

## Allergen statement format

Marketplace B carries the coded list in `allergenCodes` and renders a customer
facing statement from it. It also validates the statement we send alongside,
and it validates it against our house format, character for character:

```
Contains: <allergen>[, <allergen>]. May contain: <allergen>[, <allergen>].
```

Concretely, for VAR-02A after the shared-line change:

```
Contains: almonds. May contain: peanuts.
```

- Sentence one is mandatory. Sentence two is present only when
  `food.allergens.may_contain` is non-empty, and is omitted entirely otherwise.
- Allergens are lower case, comma-separated, in the order they appear in the
  attribute list. No trailing "and".
- Both sentences end in a full stop. No line breaks, no parentheses, no
  qualifiers such as "traces of" or "produced in a facility that".
- The whole string matches `^Contains: .+\.(?: May contain: .+\.)?$`, the same
  expression CH-MKT-A enforces as RUL-A05.

Every allergen named in the statement has a matching code in `allergenCodes`
drawn from the RUL-B03 enum, and every code has a matching name. Almonds are
`AL-NUT`; peanuts are `AL-PEANUT` and are **not** covered by `AL-NUT`. A
peanut declaration sent as `AL-NUT` passes the enum check and misdeclares the
product.

## Rejection codes

| code | meaning | usual cause |
|---|---|---|
| `MKB-2201` | allergen_statement format invalid | statement assembled by hand, an empty `May contain:` sentence, or a missing full stop |
| `MKB-2208` | ingredient order does not match declared list | `ingredientList` re-sorted, or a supplier reorder applied to one field and not the other |

**MKB-2201** rejects the row and, unlike Marketplace A, suppresses the whole
listing rather than reverting to the previous version. A food listing rejected
with MKB-2201 is off sale until it is resubmitted and re-accepted.

**MKB-2208** is the reason `food.ingredients` is an ordered attribute
(STD-002). Marketplace B compares `ingredientList` element by element against
the declared ingredient order. A supplier reorder such as
`["oats","honey","sugar","almonds","sunflower oil"]` becoming
`["oats","honey","almonds","sugar","sunflower oil"]` changes no member and no
allergen, and still rejects every affected row until the attribute itself is
updated. Never normalise, alphabetise or de-duplicate an ingredient list on the
way into this feed.

## Republishing after a rejection

A rejection is evidence about one row, not about the correction that produced
it. Do not roll back the underlying attribute to clear a rejection: fix the
field the code names, keep the corrected value, and resubmit. Rolling back
restores a value the supplier has told us is wrong and re-opens whatever the
correction was closing.

## Related

STD-002 (ordered ingredients), STD-003 (mapping and taxonomy),
CHN-002 (CH-MKT-A allergen statement), POL-001 (allergen policy),
INC-2025-058, INC-2025-063 (a MKB-2201 and MKB-2208 rejection storm).
