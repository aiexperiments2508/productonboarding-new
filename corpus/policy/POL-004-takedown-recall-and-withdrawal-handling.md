---
id: POL-004
type: POLICY
title: Handling a Withdrawal, Recall or Restriction Notice
owner: Regulatory affairs
version: 1.1
effective: 2026-06-15
entities: []
tags: [policy, takedown, recall, withdrawal, export-control, escalation, erratum]
---

# Handling a Withdrawal, Recall or Restriction Notice

This is the retailer's procedure. `REG-003` is the requirement it is written to
satisfy and `REG-008` is the requirement for the restriction cases; where this
document and either of those are read together, they govern.

## Recognising one

A notice is not a correction and does not arrive like one. Three things
distinguish it:

- **It comes from `regulatory-feed`.** No supplier system can carry one. A
  supplier email announcing that a product has been withdrawn is a supplier
  telling us about a notice, not the notice.
- **It does not propose a value.** A correction says a figure was wrong and
  offers the right one. A notice says stop.
- **It is not answerable.** A supplier's disagreement is not evidence against
  it, and there is no reading of the record that discharges it.

A notice ranks at precedence 50 in `POL-002`, above every supplier document
including label artwork, and it is the only kind that does.

## What happens immediately

On receipt, and before any assessment of our own:

1. Every channel carrying the product is taken down or withheld.
2. Any search facet directing shoppers to it is withdrawn.
3. Where the product has been printed, an **erratum** obligation is opened -
   owned, dated, and not closed by taking the web listing down.
4. Where a shelf-edge label carries it, a **reprint** is queued with a date.

Steps 3 and 4 are the ones people want to skip, and they are the ones that
matter. Two hundred thousand catalogues cannot be recalled. Reporting them as
redacted because the digital channels came down is a false statement about a
legal obligation, and it is the single report this system may never make.
`INC-2026-002` is why that sentence is in this policy.

## Approval

A notice is not held for approval before the takedown. The takedown happens on
the authority of the notice.

**Restoration is held for approval, and the authority is Regulatory Affairs.**
The act of stopping a sale is not symmetrical with the act of resuming one: a
withdrawal executed wrongly costs a week of trade, and a restoration executed
wrongly puts an unsafe product back in front of a customer. A supplier's
assurance that the matter is closed is not a lifting of the notice.

## What not to say

- Do not describe an export control classification as a safety matter. It is
  not one. See `REG-008`.
- Do not describe a lapsed certificate as a withdrawal. The product is on sale;
  a claim is unsupported. See `REG-006`.
- Do not tell a supplier we are investigating a defect when the notice names
  none. Ask what they know and say what we have been told.

## Escalation

| what arrived | severity | who decides |
|---|---|---|
| Withdrawal notice | CRITICAL | Regulatory Affairs; not delegable |
| Recall notice | CRITICAL | Regulatory Affairs and Head of Retail; not delegable |
| Export control classification | CRITICAL | Regulatory Affairs |
| Age restriction added to a line | HIGH | Category Manager, with Legal informed |
| Certificate lapsed | MEDIUM | Category Manager |
| Mandatory particulars amended | MEDIUM | Content Standards |

`POL-003` carries the rest of the escalation matrix and this table extends it;
where the two overlap, the higher severity applies.

## Related

`REG-003`, `REG-008`, `POL-002` for precedence, `POL-003` for the general
matrix, `INC-2026-002` for the print obligation.
