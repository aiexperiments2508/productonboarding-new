---
id: INT-002
type: INTERNAL
title: Prohibited and Restricted Content in Product Records
owner: Legal and compliance
version: 4.0
effective: 2026-03-01
entities: []
tags: [internal, prohibited, illegal, claims, medical, restricted]
---

# Prohibited and Restricted Content in Product Records

What may not appear in a product record, whatever a supplier sends. These are
absolute: they are not weighed against completeness and they are not gradeable.

## Never publishable

- **Medical or therapeutic claims** on a product that is not a registered
  medical device or medicine. "Treats", "cures", "prevents", "relieves",
  "clinically proven to" and their near neighbours. An air purifier does not
  treat asthma, whatever the supplier's brochure says.
- **Absolute safety claims.** "Completely safe", "harmless", "no risk".
- **Guaranteed outcomes.** "Guaranteed to", "will eliminate", "100% effective".
- **Comparative claims naming a competitor** without substantiation held on file.
- **Personal data.** A supplier contact's name, direct line or email address in
  a description field. This happens more often than it should, usually because
  a spreadsheet cell was copied whole.
- **Internal pricing, margin or cost commentary.** Also usually a copy-paste.

## Restricted, and permitted only with substantiation

- Environmental claims - "recyclable", "biodegradable", "carbon neutral".
  Where a figure exists, the claim is checked against it: `recyclable-packaging`
  holds only above 90% by weight.
- Origin claims - "made in", "sourced from". `made-in-britain` is checked
  against `origin.country`, and a production move invalidates it on the day it
  happens rather than at the next content review. See `REG-004`.
- Performance superlatives - "quietest", "most powerful", "longest lasting".
- Care and durability claims on textiles - "machine washable", "colourfast" -
  which rest on the care code and not on the copywriter.
- Testing claims on cosmetics - "dermatologically tested" states that a test
  was done and says nothing about its result. It may not be published where
  the retailer does not hold the report. See `REG-005`.

A claim resting on a certificate is unsupported the moment that certificate
lapses. Nothing about the product changed and the claim is still not
publishable, which is the case people find hardest to accept - see `REG-006`.

A restricted claim with nothing behind it is treated as prohibited until the
substantiation is on file. The claim is severable: the product may launch with
it removed.

## Why this is separate from the claim substantiation table

`STD-001` decides whether a claim the catalogue *knows about* is supported by
the values in force - it is a table of predicates over attributes. This document
covers claims the catalogue has no predicate for, because the answer does not
depend on any attribute value. No wattage makes "cures asthma" publishable.
