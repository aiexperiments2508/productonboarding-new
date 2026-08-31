---
id: REG-008
type: REGULATION
title: Export Control, Dual-Use Goods and Age-Restricted Supply
owner: Market authority (transposed)
version: 2.2
effective: 2026-06-01
entities: []
tags: [regulation, export-control, dual-use, age-restricted, channel, withholding]
---

# Export Control, Dual-Use Goods and Age-Restricted Supply

Two restrictions that share a shape and are commonly confused with a third.
Neither says a product is unsafe. Both say it may not be supplied **to
somebody**, and the remedy for both is refusing a supply route rather than
correcting a description.

## Dual-use classification

Goods with both civil and military application are classified against the
control list. A classification SHALL be recorded against the product, and
"unclassified" is not a classification: a product nobody has assessed and a
product assessed as unrestricted are different states, and only one of them is
safe to ship.

A controlled product:

- remains lawful to sell in the domestic market,
- SHALL NOT be exported to a controlled destination without a licence,
- SHALL NOT be listed on a channel that offers delivery to a controlled
  destination and cannot filter by destination.

The third point is the operative one for this system. A marketplace that ships
internationally on the retailer's behalf, and gives the retailer no way to
exclude a destination, is a route the retailer cannot control - so the listing
is **withheld** on that channel while the domestic product page continues
unaffected.

**A control classification is not a safety finding and must not be reported as
one.** Saying so would misdescribe the product to a shopper, and it would send
the supplier to investigate a defect that does not exist. Typical controlled
characteristics - a thermal sensor, a high-resolution imager, a cryptographic
module - are the product working correctly.

## Age-restricted supply

Where the law sets a minimum age, the product SHALL NOT be supplied below it,
and the listing SHALL declare the restriction.

In this catalogue that covers alcohol, bladed articles including kitchen
knives, certain solvents and bleaches, and some garden and DIY tools. The
minimum age is recorded on the product as `compliance.min_age`.

An age bar restricts **who** may buy, not **where** it may go. It therefore
does not withhold a channel; it constrains the channel's checkout, and a
channel that cannot enforce it is a channel the product does not list on.

## Why both are withholding rather than correction

A withdrawal under `REG-003` says the product may not be sold at all. These two
say it may not be sold to a particular person or into a particular place. In
every case the record may be perfect, and in every case no amount of rewriting
changes the answer - which is why all three resolve to withholding a channel
rather than regenerating its content.

## Related

`REG-003` for withdrawal, which is the stronger instruction, `REG-006` for the
conformity evidence a controlled product still needs, `CHN-002` and `CHN-003`
for what each marketplace can and cannot enforce.
