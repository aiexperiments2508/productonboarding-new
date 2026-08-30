---
id: CHN-001
type: CHANNEL
title: CH-WEB - Own Website Product Detail Page
owner: Digital Merchandising
version: 3.0
effective: 2026-01-08
entities: [CH-WEB, PRD-01, VAR-01A, VAR-01B, PRD-02, VAR-02A, VAR-02B]
tags: [channel, web, pdp, title, bullets, claims, comparison-table]
---

# CH-WEB - Own Website Product Detail Page

## Channel profile

| property | value |
|---|---|
| id | CH-WEB |
| kind | WEB |
| freeze window | 0 days |
| publishes | continuously, on approval |
| rejection codes | none - we own the channel |

CH-WEB has no freeze window and no external validator. Both facts make it the
most forgiving channel to publish to and the most dangerous one to be wrong on,
because nothing between the change and the customer will catch a mistake.

## Field rules

| rule | field | kind | value | severity |
|---|---|---|---|---|
| RUL-W01 | title | MAX_LEN | 120 | HARD |
| RUL-W02 | bullets | MAX_LEN | 5 | SOFT |

RUL-W02 is SOFT: a sixth bullet is published with a warning rather than
withheld. Nothing else on this channel is soft. A claim that fails
substantiation, a stale literal or a missing citation is HARD here exactly as it
is on a marketplace, because the absence of an external gate is not a reason to
lower the internal one.

## Assets on a CH-WEB listing

| asset | content | derived from |
|---|---|---|
| `title` | product and variant name | variant identity |
| `bullets` | 3-5 selling points | headline attributes for the category |
| `description` | long-form copy | attributes plus editorial |
| `comparison_table` | side-by-side variant specs | **both** variants' attributes |

Attribute values are unsubstituted at rest: the copy holds the literal, not a
placeholder. That is a deliberate choice - the page is the record of what a
customer was told - and it is why every asset declares `derived_from` and why a
correction has to walk that list rather than re-render a template.

## The comparison table crosses variants

VAR-01A's CH-WEB listing carries a `comparison_table` asset whose
`derived_from` names **both** `VAR-01A:specs.power_w` and
`VAR-01B:specs.power_w`. It exists to let a customer choose between the
AeroPure 300 and the AeroPure 300 Max, so it necessarily quotes both.

The consequence is the one people get wrong: **a correction scoped to VAR-01B
changes content on VAR-01A's page.** Impact must be computed from
`derived_from` across the whole catalogue, not from the listings belonging to
the corrected variant. Any process that starts from "which listings does
VAR-01B have" will miss this asset, and it will miss it silently.

## Claims on the PDP

Bullets are where claims live. A CH-WEB bullet reading
`"Ultra-quiet 45W operation for bedrooms and studies"` records
`claims_used: ["ultra-quiet", "low-energy"]` and is derived from
`specs.power_w` and `specs.noise_db`. It fails in three separate ways when the
underlying wattage changes: the literal `45W` goes stale, `low-energy` loses its
substantiation above 50 W, and the asset's `built_at_version` no longer matches
the listing.

All three are reported. They are not collapsed into one finding, because
regenerating the bullet fixes the first and third and does nothing about the
second - a claim that no longer holds has to be withdrawn, not rewritten.

## Publishing and withholding

Publication is per listing. A listing withheld for an unsubstantiated claim
stays at its previously published version rather than going dark: the customer
sees the last known-good page, and the withheld state names the binding rule and
the entity so an approver knows what they are approving.

## Related

STD-001 (title formulas, bullet budget, claim rules), STD-002 (units),
CHN-004 (CH-PRINT, where the same correction behaves very differently),
POL-002 (correction handling), INC-2025-041.
