---
id: CHN-004
type: CHANNEL
title: CH-PRINT - Store Catalogue and Print
owner: Retail Marketing
version: 4.3
effective: 2026-02-20
entities: [CH-PRINT, PRD-01, VAR-01A, VAR-01B, PRD-06]
tags: [channel, print, catalogue, freeze, stale-version, irreversible]
---

# CH-PRINT - Store Catalogue and Print

## Channel profile

| property | value |
|---|---|
| id | CH-PRINT |
| kind | PRINT |
| freeze window | **7 days** |
| publishes | in batches, to a press date |
| reversible | no |

CH-PRINT is the only channel where publishing is irreversible. Every other
channel can be corrected in minutes at the cost of having been wrong briefly.
A catalogue is wrong for its whole print run, in stores, in customers' hands,
for the life of the edition.

## Field rules

| rule | field | kind | value | severity |
|---|---|---|---|---|
| RUL-P01 | `specs.power_w` | REQUIRED | - | HARD |
| RUL-P02 | catalogue_copy | MAX_LEN | 240 | HARD |

RUL-P02 is a hard physical limit, not a guideline: 240 characters is the space
on the page and there is no overflow behaviour.

## The 7-day freeze window

**No content change may be applied to a CH-PRINT listing within 7 days of its
press date.** Inside the window the listing is frozen; the file has left
prepress and a change costs a re-plate, a re-run, or an edition pulled.

A correction that arrives inside the window is not discarded and is not applied
quietly at the next opportunity. It takes one of three routes:

| situation | route |
|---|---|
| Correction is material and the value is printed | Escalate under POL-003 for a re-plate decision. Do not decide this at planner level. |
| Correction is material and the value is not printed in this edition | Apply to the attribute, mark the listing for the next edition, publish the other channels now. |
| Correction is immaterial | Record the fact, leave the edition alone, note it against the next cycle. |

The window is measured from the press date, not from the on-sale date, and it
is not shortened by the correction being urgent. Urgency is an argument for
escalating faster, not for skipping the escalation.

## The stale-version rule

Every CH-PRINT listing records the `published_version` it went to press with.
Every asset records the `built_at_version` it was generated from.

**Where a listing's `published_version` is older than the in-force version of
any attribute it was built from, the listing is a `stale_version` violation.**

This is deliberately different from `stale_asset`. A stale asset is content that
can be regenerated; a stale version is a physical artefact in the world that
already carries a superseded figure and cannot be regenerated at all. The two
violations are raised separately and answered separately:

- `stale_asset` on CH-WEB means regenerate and republish.
- `stale_version` on CH-PRINT means decide what to do about copies already
  printed, and stop the next run from repeating it.

A `stale_version` finding is never cleared by regenerating content. It is
cleared by a press decision, recorded with an approver.

## Sequencing a correction that touches print

1. Apply the attribute correction at source. The correction is a new fact with
   `supersedes_id` set; the superseded value is retained, not overwritten.
2. Compute impact across all channels from `derived_from`. Do not stop at the
   corrected variant - see CHN-001 on the cross-variant comparison table.
3. Publish the reversible channels first: CH-WEB, then the marketplaces, then
   CH-SHELF and CH-SEARCH. Their exposure is minutes.
4. Test CH-PRINT against the freeze window last, when the correction is already
   proven on channels that can be undone if it turns out to be wrong.

Publishing print first inverts the risk: the irreversible channel takes the
correction before anything has validated it.

## Related

STD-002 (wattage as an integer), CHN-001 (CH-WEB and the comparison table),
POL-002 (materiality and supersession), POL-003 (who approves a re-plate),
INC-2026-002 (a stale specification printed inside the freeze window).
