---
id: REG-005
type: REGULATION
title: Cosmetic Products - Ingredient Declaration and Claims
owner: Market authority (transposed)
version: 4.1
effective: 2026-05-01
entities: []
tags: [regulation, cosmetic, hpc, inci, claims, saleability, mandatory]
---

# Cosmetic Products - Ingredient Declaration and Claims

## Scope

Every product whose category begins `hpc.toiletries.` or `hpc.cosmetics.`, and
any product in `baby.` applied to the skin.

## Mandatory particulars

A cosmetic product SHALL NOT be offered for sale unless the listing carries:

1. The function of the product, where it is not obvious from its presentation.
2. The list of ingredients in INCI nomenclature, in **descending order of
   weight** at the time they were added. Ingredients at 1% or less may be
   listed in any order after those above 1%.
3. The nominal content at the time of packaging.
4. A durability indication, or a period-after-opening symbol where the product
   is stable for more than thirty months.
5. Particular precautions for use.

`cosmetic.inci` is an **ordered** attribute for the reason given in section 2.
A reordered declaration is a different declaration.

## Amendments to the mandatory particulars

This regulation is amended more often than the others in this corpus, and an
amendment binds on its effective date whether or not the listing has been
touched since.

**A listing that was compliant when it was written and is not compliant now is
not defective and is not the supplier's fault.** It is also not saleable. The
distinction matters for what happens next: there is nothing to return to
source, no correction to request, and no incident to open against a supplier.
The retailer completes the declaration at its next content release and records
why.

This is the only class of correction in this system with no counterparty.

## Claims

A cosmetic claim SHALL be supported by evidence held on file and SHALL NOT
attribute to the product a characteristic it does not have.

- **"Dermatologically tested"** states that a test was done. It says nothing
  about the result, and it may not be published where the retailer does not
  hold the report.
- **"Hypoallergenic"** requires evidence of a reduced potential to cause
  allergy, not merely the absence of a common allergen.
- A **medical or therapeutic** claim on a cosmetic is prohibited outright, not
  restricted. `INT-002` governs it and no substantiation makes it publishable:
  a moisturiser does not treat eczema whatever the trial says, because a
  product that treated eczema would be a medicine and would be regulated as
  one.

## Related

`INT-002` for prohibited and restricted content, `STD-001` for the claim
substantiation table, `REG-003` where a cosmetic is withdrawn on safety
grounds rather than corrected.
