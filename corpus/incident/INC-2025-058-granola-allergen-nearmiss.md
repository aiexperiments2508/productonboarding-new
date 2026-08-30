---
id: INC-2025-058
type: POSTMORTEM
title: Orchard Valley Granola Clusters - peanut-free claim left standing after a shared-line change
owner: Regulatory Affairs
occurred: 2025-10-07
closed: 2025-10-24
severity: CRITICAL
entities: [PRD-05, VAR-05A, SUP-02, DOC-04, CH-WEB, CH-MKT-A, CH-MKT-B, CH-SEARCH, CH-SHELF, PRD-02, VAR-02A]
tags: [allergen, peanut-free, claim, near-miss, fail-closed, facets, may-contain, regulated]
---

# INC-2025-058 - Granola Clusters peanut-free claim left standing

## Summary

SUP-02 notified a shared-line change at its Hallow Lane site: the line
producing PRD-05 Orchard Valley Granola Clusters would also run a peanut
product, requiring "may contain peanuts" on every format.

The allergen attribute was updated correctly. `food.allergens.may_contain` on
VAR-05A gained "peanuts" within two hours of the notice, and CH-MKT-A and
CH-MKT-B carried the revised statement the same afternoon.

The `peanut-free` claim was not withdrawn. It remained in the variant's
`claims`, in the CH-WEB bullets, and - the part that made this CRITICAL rather
than embarrassing - as an `allergen_free:peanut` facet on CH-SEARCH. For six
days a customer filtering for peanut-free products was shown a product whose own
label said it might contain peanuts.

No customer report and no reaction. It was found internally. That is the only
reason this is a near-miss.

## Timeline

| Date | Event |
|---|---|
| 07 Oct, 08:20 | SUP-02 notice received. Shared line, all formats, effective immediately. |
| 07 Oct, 10:05 | `food.allergens.may_contain` set to `["peanuts"]` on VAR-05A. |
| 07 Oct, 14:30 | CH-MKT-A and CH-MKT-B republished with the revised allergen statement. |
| 07 Oct - 13 Oct | CH-WEB bullets continue to read "peanut-free". CH-SEARCH continues to return VAR-05A under `allergen_free:peanut`. |
| 13 Oct, 16:10 | Found during an unrelated facet audit. |
| 13 Oct, 16:25 | All PRD-05 listings withheld. Facet removed first. |
| 14 Oct | Copy regenerated without the claim. Regulatory review completed. Listings restored. |
| 24 Oct | Actions closed. |

## Root cause

**The attribute change and the claim that depended on it were treated as
separate pieces of work, and only one of them had an owner.**

The allergen update was a data task with a clear trigger and a clear
destination: the two marketplace fields that name allergens. The claim was
content, and nothing connected the attribute to the copy that rested on it. The
`peanut-free` rule in STD-001 was already written and already correct. It was
not evaluated, because nothing invoked it.

Contributing factors:

1. **"May contain" was read as weaker than "contains".** The notice was
   handled as a labelling refinement rather than an allergen change. Under
   POL-001 the two carry identical weight, and `peanut-free` fails on either.
2. **Facets were assumed to follow the attribute.** They do not follow it
   automatically; they are derived, and the derivation ran on a nightly cycle
   that had been disabled during an unrelated migration.
3. **The channels that mattered least were fixed first.** The marketplaces
   were updated because they have required allergen fields and reject without
   them. CH-WEB and CH-SEARCH have no such field, so nothing forced them, and
   they are where the claim actually lived.

## What worked

- The allergen attribute itself was never wrong. The declaration on both
  marketplaces was correct from the same afternoon, which is why this remained a
  near-miss rather than a misdeclaration.
- Withholding first and investigating second. Six days of exposure did not
  become seven while somebody decided how serious it was.
- Facet removal was ordered before republication, so the search channel stopped
  routing peanut-free traffic to the product before anything else was touched.

## What did not work

**Updating the fields a channel requires, and calling that the correction.** The
required-field view of an allergen change covers `allergen_statement` on
CH-MKT-A and `allergenCodes` on CH-MKT-B, and misses every place the allergen
position is asserted rather than stated: a claim word in a bullet, a claim in
the variant's `claims` list, a derived facet, a shelf label. The channels with
no allergen field are the ones with no automatic check.

**Assuming a regulated change is finished when the regulated fields are right.**
An allergen change invalidates claims. That is a second consequence with its own
propagation, and it needs to be computed rather than remembered.

## Remedy - an allergen change is a claim event

| Step | Action |
|---|---|
| 1 | Withhold every listing of the affected variants immediately, on every channel. Fail closed (POL-001); do not triage first. |
| 2 | Update both allergen attributes to the full declaration the supplier stated. If the notice does not state the resulting declaration in full, do not infer it - query the supplier (POL-003). |
| 3 | Remove invalidated facets **before** anything is republished. `allergen_free:<allergen>` is the highest-harm stale artefact in the system. |
| 4 | Re-evaluate every claim in `claims_used` and in the variant's `claims` against the new allergen lists. `peanut-free` and `gluten-free` both key off contains and may-contain together. |
| 5 | Withdraw failing claims outright. Do not reword them (POL-001). Regenerate the copy that carried them. |
| 6 | Check sibling variants and sibling products on the same production line. A shared-line change is a site fact, not a product fact - PRD-02 shares SUP-02 and was checked here, correctly, and was unaffected at the time. |
| 7 | Regulatory review before republication, mandatory, for the declaration and the claim withdrawal both. |

## Actions

| # | Action | Status |
|---|---|---|
| 1 | Claim re-evaluation triggered automatically by any allergen attribute change | Closed |
| 2 | Facet derivation moved from nightly to on-change, with removal before addition (CHN-005) | Closed |
| 3 | "May contain" given equal weight to "contains" throughout POL-001 | Closed |
| 4 | Withhold-first standing instruction for regulated products | Closed |
| 5 | Line-sharing map from SUP-02 covering PRD-02 and PRD-05 | Open at Q1 2026 |

## Recurrence watch

Action 5 remains open, so a shared-line notice naming one SUP-02 product still
cannot be checked against the other automatically. **PRD-02 Orchard Valley Trail
Mix Bar carries `peanut-free` on both VAR-02A and VAR-02B and is produced by the
same supplier.** Any SUP-02 shared-line notice should be assumed to reach both
products until the supplier confirms otherwise, and the trail mix bar's
`peanut-free` claim should be re-evaluated on every such notice regardless of
which product is named.

## Related

POL-001 (fail-closed, mandatory review), STD-001 (claim substantiation),
CHN-005 (facet derivation and removal order), CHN-003 (allergenCodes),
POL-003 (supplier queries), INC-2025-063.
