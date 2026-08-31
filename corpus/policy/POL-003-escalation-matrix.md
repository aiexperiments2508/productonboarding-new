---
id: POL-003
type: POLICY
title: Escalation, Supplier Queries and Approval Authority
owner: Product Data Governance
version: 5.2
effective: 2026-02-10
entities: [SUP-01, SUP-02, SUP-04, CH-PRINT, CH-MKT-B, PRD-01, PRD-02]
tags: [escalation, approval, authority, supplier-query, severity, governance]
---

# Escalation, Supplier Queries and Approval Authority

## Severity classification

| Severity | Definition |
|---|---|
| CRITICAL | A regulated attribute is wrong or unresolved, or an irreversible channel has published a superseded value |
| HIGH | A substantiated claim has been invalidated, or a HARD channel rule is failing on a live listing |
| MEDIUM | Content is stale on reversible channels only, and no claim or regulated attribute is affected |
| LOW | Informational; the correction is immaterial and publishes on the normal cycle |

Concurrent corrections on one product are classified on their **combined**
exposure. Two MEDIUM corrections that together invalidate a claim are one HIGH
incident, not two MEDIUM ones.

## Response times

| Severity | Acknowledge | Impact assessment | Decision |
|---|---|---|---|
| CRITICAL | 1 hour | 4 hours | 8 hours |
| HIGH | 4 hours | 1 working day | 2 working days |
| MEDIUM | 1 working day | 3 working days | 5 working days |

The clock starts when the document arrives, not when it is read.

## When to ask the supplier

A supplier query is raised - not guessed around - in each of these cases. It
names the entity, quotes the exact wording that is ambiguous, states every
interpretation being held open, and asks a closed question.

| condition | example | ask |
|---|---|---|
| Correction names a product with several variants and does not say which | "the rated power of the Northaven AP300 is 65 W" against VAR-01A and VAR-01B | which variant, or both |
| A value arrives as a range or a qualified figure | `60-70 W`, "typical", "in boost mode" | the single rated figure |
| Allergen change announced without the resulting declaration | "shared line now handles peanuts" | the full contains and may-contain lists per format |
| Two equal-precedence documents disagree | two SPEC_SHEET versions from one supplier | which document is current |
| A lower-precedence source contradicts a higher one | sales email against label artwork | confirmation the artwork is correct |
| An allergen is removed from a declaration | `may_contain` shortened | the document supporting the removal |

Hold the ambiguity while the query is open. A held correction is recorded with
its scope marked UNCLEAR (POL-002) and the affected channels withheld; it is not
half-applied to the variants we happen to be more confident about.

**Do not ask the supplier to confirm something we can determine ourselves.** A
query costs a day or more of channel availability, and a supplier who is asked
routine questions answers the important ones more slowly.

## Approval authority

| Decision | Approver |
|---|---|
| Publish an immaterial correction | Content operations, no approval |
| Publish a material correction, reversible channels | Category manager |
| Withdraw a substantiated claim | Category manager |
| Add to or remove from an allergen declaration | Regulatory affairs, mandatory (POL-001) |
| Lift a fail-closed withhold on a regulated product | Regulatory affairs, and only against a DECIDED value |
| Apply a correction inside the CH-PRINT freeze window | Head of retail marketing |
| Authorise a catalogue re-plate or a pulled edition | Head of retail marketing and category director jointly |
| Roll back a corrected attribute to clear a channel rejection | Not delegable - see below |

Rolling back a corrected attribute to clear a marketplace rejection restores a
value the supplier has told us is wrong. It is never the answer to a rejection
code; the field the code names is fixed and the corrected value is kept
(CHN-003). Where a rejection genuinely cannot be cleared without reverting, the
listing is withheld and the case escalates as HIGH.

## What an approver must be shown

- the recommended action and at least one considered alternative;
- the entities and channels affected, computed from `derived_from` rather than
  from the corrected variant's own listings;
- the source document, its version, and its precedence against anything it
  contradicts;
- which values are recorded fact, which are inferred, and the confidence of
  each;
- what is still unknown, stated plainly.

An inference presented as a recorded fact is a control breach regardless of
whether it later proves correct. The same applies to a scope: a scope that was
chosen must be presented as chosen, with the alternatives it was chosen over.

## Related

POL-001 (regulated review), POL-002 (scope, precedence and materiality),
CHN-004 (the print freeze window), CHN-003 (rejections),
INC-2025-041 (a supplier query that was not raised).
