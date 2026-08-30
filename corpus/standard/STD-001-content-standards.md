---
id: STD-001
type: STANDARD
title: Product Content Standards
owner: Content Operations
version: 4.1
effective: 2026-02-01
entities: [CH-WEB, CH-MKT-A, CH-MKT-B, CH-PRINT, CH-SHELF, PRD-01, PRD-02]
tags: [content, title, bullets, tone, claims, substantiation, claim-consistency]
---

# Product Content Standards

## Purpose

Governs how prepared content is written for every channel, and the conditions
under which a marketing claim may appear in it. Channel *schema* limits - field
names, required fields, rejection codes - live in the CHN- series. This
document governs the copy itself and the evidence behind it.

## Title formulas

| Channel | Formula | Limit |
|---|---|---|
| CH-WEB | `<brand> <product name> <variant qualifier>` | 120 characters, RUL-W01 |
| CH-MKT-A | `<brand> <product name> - <headline spec>` | 80 characters, RUL-A01 |
| CH-MKT-B | `<brand> <product name> <variant qualifier>` | 120 characters, RUL-B01 |
| CH-PRINT | `<product name> <variant qualifier>` | catalogue copy 240 characters, RUL-P02 |
| CH-SHELF | `<short name> <headline spec>` | 40 characters, RUL-S01 |

The variant qualifier is **mandatory** wherever a product carries more than one
variant. PRD-01 ships as VAR-01A "AeroPure 300" and VAR-01B "AeroPure 300 Max".
A VAR-01B title reading only "AeroPure 300" is a defect even though it sits
well inside the character limit, because it makes the listing indistinguishable
from its sibling and makes every later correction ambiguous to scope.

Where the 80-character CH-MKT-A limit forces a choice, the variant qualifier is
kept and the headline spec is dropped. Identity outranks specification.

## Bullet budget

CH-WEB carries three to five bullets. Five is the ceiling (RUL-W02, SOFT);
three is the floor and is a content standard rather than a channel rule, so it
is enforced here and not by the feed.

- The first bullet carries the headline specification for the category:
  wattage and coverage for air treatment, net weight and fibre for food.
- No bullet repeats a value already stated in the title.
- A bullet that states a benefit must state the specification that supports it
  in the same bullet, not in a later one.
- Every claim word used in a bullet is recorded in that asset's `claims_used`.
  A claim asserted in copy but absent from `claims_used` is unevidenced copy
  and is treated as a `citation_missing` violation.

CH-MKT-A and CH-MKT-B derive their bullets from the CH-WEB set rather than
being written independently, so a correction lands once and propagates.

## Tone

Short sentences. Units always written with their value and never implied.
No superlative that is not substantiated by an attribute. No comparative claim
against a named competitor. No claim about a regulated property - allergens,
energy class, safety - that is not a direct restatement of a supplier-sourced
attribute value.

## Claim substantiation

A claim may appear in copy only if its rule below holds against the **in-force**
attribute values for that variant. The rule is evaluated at the variant, not at
the product: two variants of one product can disagree about whether a claim
holds, and frequently do.

| claim | holds only if |
|---|---|
| `ultra-quiet` | `specs.noise_db` ≤ 40 |
| `low-energy` | `specs.power_w` ≤ 50 |
| `peanut-free` | "peanut"/"peanuts" absent from `food.allergens.contains` ∪ `may_contain` |
| `gluten-free` | "gluten"/"wheat" absent from contains ∪ may_contain |
| `high-fibre` | `food.fibre_g` ≥ 6 |

A claim listed in an asset's `claims_used`, or in a variant's `claims`, whose
rule fails is a `claim_consistency` **HARD** violation. The claim is never
silently softened, reworded or dropped. The violation names the claim, the rule
it failed and the entity it failed on.

This table is also implemented in the validator as `CLAIM_RULES`. The
duplication is deliberate. The standard is what the business agreed; the code is
what the system enforces. Where the two disagree, the disagreement is itself the
finding and is arbitrated on the evidence, not resolved by assuming the code is
right.

## Copy that embeds an attribute value

Prose that quotes a number is derived data. The CH-WEB bullet
`"Ultra-quiet 45W operation for bedrooms and studies"` embeds
`specs.power_w` and depends on it twice over: once as a literal, once as the
substantiation for `ultra-quiet` and `low-energy`.

Such an asset declares the attributes it was built from in `derived_from`,
qualified by variant - `VAR-01B:specs.power_w`, never bare `specs.power_w`.
An asset whose `derived_from` includes an attribute that has since been
corrected is a `stale_asset` violation. An asset whose visible text still
contains the superseded literal is additionally a `stale_literal` violation.
The two are reported separately because they are fixed differently: one needs a
regenerate, the other needs a human to read the sentence.

A comparison table that cites both variants' values - as VAR-01A's CH-WEB
comparison asset does - is derived from both. A correction scoped to VAR-01B
therefore lands on VAR-01A's page. Scope the impact from `derived_from`, never
from the listing's own variant.

## Related

STD-002 (attribute units and rounding), STD-003 (taxonomy), CHN-001 (CH-WEB),
POL-001 (regulated claims), POL-002 (correction handling),
INC-2025-041 (variant-scoped wattage correction),
INC-2025-058 (claim left standing after an allergen change).
