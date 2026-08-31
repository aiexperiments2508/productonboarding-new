---
id: POL-001
type: POLICY
title: Allergen and Regulated Claim Policy
owner: Regulatory Affairs
version: 7.0
effective: 2026-01-05
entities: [PRD-02, VAR-02A, VAR-02B, PRD-05, SUP-02, DOC-03, DOC-04, CH-MKT-A, CH-MKT-B]
tags: [allergen, regulated, fail-closed, safety, confidence, review, peanut-free]
---

# Allergen and Regulated Claim Policy

## Scope

Applies to every product whose category begins `food.` and therefore to PRD-02
Harrowfield Trail Mix Bar (VAR-02A, VAR-02B) and PRD-05 Harrowfield
Granola Clusters, both supplied by SUP-02 and both flagged `regulated`.

The regulated flag is not a label on the product. It changes how every value on
that product is handled: which attributes are safety-classed, what confidence
is required to act on them, and who may approve a publication.

## Safety-classed attributes

`food.allergens.contains` and `food.allergens.may_contain` are the two
safety-classed attributes in the catalogue. Everything in this policy follows
from that classification and applies to both equally. A "may contain" statement
is a declaration with the same regulatory weight as a "contains" statement; it
is not a softer version of one.

## The fail-closed rule

**Where the allergen position of a regulated product is uncertain, the listing
is withheld. Uncertainty never resolves to publication.**

Uncertainty means any of:

- an allergen attribute has no in-force value;
- the in-force value is INFERRED - read out of prose, not out of a structured
  field - with confidence below the threshold below, and no DECIDED value
  overrides it;
- two active source documents disagree about the allergen position and the
  conflict is unresolved;
- a supplier notice announces an allergen change without stating the resulting
  declaration in full.

Withholding is not a failure state and is not escalated as one. It is the
correct outcome and it names the binding rule and the entity, so that the person
who lifts it knows precisely what they are asserting.

The rule is asymmetric on purpose. Publishing a product with an undeclared
allergen harms a customer; withholding one costs a day of sales. These are not
comparable and are not traded off.

## Confidence threshold

| condition | threshold |
|---|---|
| safety-classed attribute, INFERRED value | confidence >= **0.9** to be actionable |
| safety-classed attribute, INFERRED below 0.9, no DECIDED override | **blocks every listing of that entity** |
| non-safety attribute | no floor; low confidence is a warning |

`SAFETY_CONFIDENCE = 0.9` is the constant the validator enforces and this
document is its source. A safety-classed value inferred below it raises
`safety_confidence` and the block is total: it applies to every listing of that
entity on every channel, including channels that do not carry the allergen
field, because a product that we cannot describe correctly on CH-MKT-A is not a
product we should be selling on CH-WEB.

A human DECIDED value clears the block. Raising the model's confidence does
not, and neither does a second inference from the same document.

## Mandatory review for regulated claims

The following changes require regulatory review before publication, regardless
of size, materiality or channel:

| change | review |
|---|---|
| any addition to `food.allergens.contains` | mandatory, before any channel publishes |
| any addition to `food.allergens.may_contain` | mandatory, before any channel publishes |
| any removal from either allergen list | mandatory, and requires the supplier document that supports the removal |
| withdrawal of `peanut-free` or `gluten-free` | mandatory |
| assertion of `peanut-free` or `gluten-free` on a product that did not previously carry it | mandatory |
| ingredient reorder with no membership change | not mandatory - it is a schema matter, see CHN-003 |

Removals are reviewed at least as strictly as additions. An allergen quietly
dropped from a declaration is the one failure mode that looks like tidying up.

## Claims are withdrawn, not rewritten

`peanut-free` fails the moment "peanut" or "peanuts" appears in either allergen
list (STD-001). When it fails, the claim is **withdrawn** from `claims_used` and
from the variant's `claims`, and the copy that carried it is regenerated without
it. It is never restated as "no peanut ingredients", "not made with peanuts" or
any other formulation that preserves the impression while evading the rule.

Withdrawal propagates to CH-SEARCH: the `allergen_free:peanut` facet is removed
before anything else is published, because a stale facet routes exactly the
wrong customer to the product (CHN-005).

## Related

STD-001 (claim rules), CHN-002 (allergen_statement, RUL-A05),
CHN-003 (allergenCodes, MKB-2201), CHN-005 (allergen facets),
POL-002 (source precedence between DOC-03 and DOC-05),
POL-003 (escalation), INC-2025-058 (a peanut-free claim left standing).
