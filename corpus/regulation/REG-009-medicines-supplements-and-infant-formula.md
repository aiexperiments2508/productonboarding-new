---
id: REG-009
type: REGULATION
title: Medicines, Food Supplements and Infant Formula
owner: Market authority (transposed)
version: 2.3
effective: 2026-02-20
entities: []
tags: [regulation, health, medicines, supplements, baby, formula, claims, saleability]
---

# Medicines, Food Supplements and Infant Formula

## Scope

Every product whose category begins `health.` or `baby.feeding.`. These are the
two branches where the ordinary rule - that a claim may be made if it can be
substantiated - is replaced by a narrower one: a claim may be made only if it
appears on a permitted list.

## Medicines available without prescription

A medicine SHALL carry its active ingredient and strength, the conditions it is
authorised for, and its authorisation number. None of these may be inferred and
none may be paraphrased for readability.

The indications are those in the authorisation and no others. A product
authorised for headache is not thereby a product for migraine, and copy
describing it as one is an unauthorised indication rather than a loose
sentence.

`health.active_ingredient` is safety-class for this reason: it is what a
pharmacist checks against, and a wrong value is a dispensing error rather than
a data-quality defect.

## Food supplements

A supplement is a food and not a medicine, and the boundary is the whole point.

- It SHALL carry the nutrients it declares, the recommended daily portion, and
  a statement not to exceed it.
- It SHALL carry a statement that supplements do not replace a varied diet.
- It SHALL NOT state or imply that it prevents, treats or cures any disease.

The last is absolute and is the same prohibition `INT-002` states. A vitamin
D supplement may say what vitamin D contributes to; it may not say what it
protects the shopper from.

## Infant formula

The most heavily restricted category in this catalogue, and restricted in a way
that surprises people: the restrictions are on **marketing**, not on the
product.

For infant formula - the first-stage product, not follow-on:

- The listing SHALL NOT carry an image idealising the use of the product.
- It SHALL NOT carry a nutrition or health claim, including on the pack shot.
- It SHALL carry a statement on the superiority of breastfeeding.
- It SHALL NOT be discounted, promoted, or included in a multibuy.

Follow-on formula is less restricted and is routinely confused with it. A
listing that presents the two as a range, or that lets copy written for one
apply to the other, has made the first-stage product carry a promotion it may
not carry.

**A promotional mechanic applied to infant formula is a compliance failure
before it is a pricing decision**, and it will not be caught by any rule about
content, because nothing in the copy is wrong.

## Related

`INT-002` for prohibited medical claims across every category, `REG-001` for
the food particulars formula also carries, `STD-001` for the claim
substantiation table, which does not apply here - a permitted-list regime is
not a substantiation regime.
