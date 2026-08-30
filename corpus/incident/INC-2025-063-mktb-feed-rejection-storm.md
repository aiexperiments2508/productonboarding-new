---
id: INC-2025-063
type: POSTMORTEM
title: Marketplace B rejection storm - MKB-2201 and MKB-2208 across the food catalogue
owner: Marketplace Operations
occurred: 2025-11-12
closed: 2025-11-28
severity: HIGH
entities: [CH-MKT-B, MKB-2201, MKB-2208, PRD-02, VAR-02A, VAR-02B, PRD-05, VAR-05A, SUP-02, DOC-04]
tags: [rejection, mkb-2201, mkb-2208, feed, allergen-statement, ingredient-order, republish, rollback]
---

# INC-2025-063 - Marketplace B rejection storm

## Summary

A SUP-02 correction updated the allergen declaration and the ingredient
declaration order for PRD-02 and PRD-05 together. The republish to CH-MKT-B
produced 1,180 rejections over eleven hours: MKB-2201 on the allergen statement
format, then MKB-2208 on ingredient order once the first was fixed.

Every food listing on CH-MKT-B was suppressed for between nine and thirty-one
hours. Marketplace B suppresses rather than reverting, so the listings were off
sale rather than showing stale content.

The underlying correction was right throughout. Nothing about the incident was
caused by the corrected values; all of it was caused by how they were assembled
into a feed row and by what was done in response to the rejections.

## Timeline

| Date | Event |
|---|---|
| 12 Nov, 07:15 | Correction applied. Allergen lists and ingredient order both change. |
| 12 Nov, 07:40 | CH-MKT-A accepts. Synchronous validation, no defects. |
| 12 Nov, 07:45 | CH-MKT-B rows submitted and accepted at submission. |
| 12 Nov, 11:20 | First MKB-2201 rejections arrive. 3.5 hours after submission. |
| 12 Nov, 12:05 | Rows resubmitted unchanged, on the assumption of a transient fault. Rejected identically. |
| 12 Nov, 13:30 | Cause found: an empty `May contain:` sentence emitted when `may_contain` was empty. |
| 12 Nov, 15:10 | Statement assembly fixed. Resubmitted. MKB-2201 clears. |
| 12 Nov, 18:40 | MKB-2208 rejections begin on the same rows. |
| 12 Nov, 19:15 | A rollback of the ingredient order was proposed to clear the rejections. Refused. |
| 13 Nov, 09:00 | `food.ingredients` order corrected at source. Feed rebuilt from the attribute. |
| 13 Nov, 14:25 | All rows accepted. |
| 28 Nov | Actions closed. |

## Root cause

**Two channel fields were assembled independently from the same corrected
attributes, and neither was rebuilt from the attribute after the correction.**

`allergen_statement` was being composed by string concatenation that appended
the `May contain:` sentence unconditionally, producing `May contain: .` when
`may_contain` was empty. That string satisfies nothing:
`^Contains: .+\.(?: May contain: .+\.)?$` requires content between the label and
the full stop. The defect had existed for months and was invisible because no
food product had previously had an empty `may_contain` alongside a republish.

`ingredientList` was being carried forward from the previous feed row rather
than re-derived, so it still held the old order after `food.ingredients` was
reordered. RUL-B04 is an ORDERED_MATCH and compares element by element, so a
list with identical members in a different order fails every row.

Contributing factors:

1. **Asynchronous rejection.** Marketplace B accepts at submission and rejects
   hours later. Every defect therefore ships before it is known about, and the
   feedback loop is long enough that a second defect is not discovered until the
   first is cleared.
2. **Resubmitting an unchanged payload.** The 12:05 resubmission produced an
   identical rejection and doubled the error count against the feed, which is
   what escalated a defect into a suppression.
3. **Serial discovery.** MKB-2208 could not be seen until MKB-2201 cleared,
   because Marketplace B reports one failure per row. Eleven hours of the
   outage was the two defects being found one after another.

## What worked

**The rollback was refused.** At 19:15 the fastest way to clear MKB-2208 was to
restore the previous ingredient order, and it was proposed on those grounds.
Reverting would have restored an ingredient declaration the supplier had
explicitly corrected, on a regulated product, to make a marketplace stop
complaining. The corrected value was kept and the field was fixed instead. This
is now written into CHN-003 and POL-003 as a non-delegable decision.

CH-MKT-A's synchronous validation also worked exactly as designed - it accepted
cleanly, because its `allergen_statement` was assembled by a different path that
omitted the empty sentence correctly. The divergence between the two assembly
paths is the deeper defect.

## What did not work

**Treating a rejection code as a description of the fix.** MKB-2201 says the
statement format is invalid. It does not say which of the two marketplaces'
assembly paths produced it, whether the underlying allergen data is wrong, or
whether the fix is in the data or in the renderer. Two hours went into checking
the allergen attributes, which were correct.

**Rebuilding one field and shipping.** After MKB-2201 cleared, the rows were
resubmitted without re-deriving the rest of the payload from the attributes.
Had every field been rebuilt from source, MKB-2208 would have surfaced in the
same cycle instead of six hours later.

## Remedy - responding to a marketplace rejection

| Step | Action |
|---|---|
| 1 | Never resubmit an unchanged payload. An identical row produces an identical rejection and counts against the feed error rate. |
| 2 | Separate the question "is the value wrong" from "is the field malformed". A rejection code describes the field, and the field is derived. Check the attribute first, then the derivation. |
| 3 | Rebuild the **whole** row from the in-force attributes, not the field the code names. Serial rejections are a symptom of partial rebuilds. |
| 4 | Never roll back a corrected attribute to clear a rejection. Fix the field, keep the value, resubmit. Where that is impossible, withhold and escalate as HIGH. |
| 5 | Cross-check the other marketplace. Where one accepts and the other rejects the same correction, the divergence is in the assembly path, not in the data. |
| 6 | Expect a second code once the first clears. Marketplace B reports one failure per row, so a clean resubmission is not evidence of a clean payload. |

## Actions

| # | Action | Status |
|---|---|---|
| 1 | Single allergen statement assembly shared by CH-MKT-A and CH-MKT-B | Closed |
| 2 | `May contain:` sentence omitted entirely when `may_contain` is empty (CHN-003) | Closed |
| 3 | Feed rows rebuilt wholly from in-force attributes, never carried forward | Closed |
| 4 | Rollback-to-clear-a-rejection made non-delegable (POL-003) | Closed |
| 5 | Validate the assembled statement against RUL-A05 before submission, on both marketplaces | Closed |

## Recurrence watch

Action 5 validates format, not meaning. A statement that is well-formed and
wrong still passes. The remaining exposure is a correction that changes the
allergen position without changing the number of sentences - adding an allergen
to a non-empty `may_contain` - which no format check will catch on either
marketplace.

## Related

CHN-003 (MKB-2201, MKB-2208, ORDERED_MATCH), CHN-002 (allergen statement format),
STD-002 (ordered ingredient attribute), POL-001 (allergen policy),
POL-003 (approval authority), INC-2025-058.
