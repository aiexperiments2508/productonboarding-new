---
id: POL-002
type: POLICY
title: Correction Handling and Source Precedence
owner: Product Data Governance
version: 6.1
effective: 2026-02-10
entities: [DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, PRD-01, VAR-01A, VAR-01B, VAR-02A]
tags: [correction, precedence, supersession, conflict, materiality, provenance]
---

# Correction Handling and Source Precedence

## Purpose

Governs what happens when a supplier tells us something different from what we
already hold. Corrections arrive constantly and most are routine; the policy
exists for the ones that are not, and for the case where two live documents
disagree.

## Source precedence

Every attribute value is attributed to the document that produced it. Where two
**active** documents assign different values to the same attribute of the same
entity, the higher precedence wins.

| source kind | precedence |
|---|---|
| `LABEL_ARTWORK` | 40 |
| `CERTIFICATE` | 35 |
| `SPEC_SHEET` | 30 |
| `PORTAL_FEED` | 20 |
| `SPREADSHEET` | 15 |
| `EMAIL` | 10 |

The ordering follows how close a document is to the physical product. Label
artwork is what is printed on the pack a customer holds, so it outranks a spec
sheet describing the same pack. A spreadsheet emailed by an account manager and
the account manager's covering note are the two weakest sources in the system,
and they are weak regardless of how recently they were sent or how confidently
they are written.

**Recency does not override precedence.** A newer version of a lower-precedence
document does not displace a higher-precedence one; it only displaces earlier
versions of itself.

Worked example: DOC-05, the SUP-02 portal spreadsheet, sets
`VAR-02A.food.net_weight_g` to 40 g. DOC-03 v2, the pack label artwork, reads
38 g. A subsequent email from SUP-02 sales insists on 40 g. Label artwork at 40
outranks the spreadsheet at 15 and the email at 10, so the in-force value is
38 g. The 40 g readings are not deleted - they remain recorded, superseded, and
attributed - and the disagreement is raised as a **SOURCE_CONFLICT** naming
DOC-03, DOC-05 and the entity, because a precedence rule resolves which value to
publish and does not establish that the supplier agrees with itself.

Where two documents of **equal** precedence disagree, precedence cannot decide
it and the conflict escalates under POL-003. It is never broken by timestamp.

## No silent overwrites

**A correction never mutates a stored value.** Applying a correction writes a
*new* fact row carrying the new value, its source document, its version and its
provenance, with `supersedes_id` pointing at the row it replaces. The superseded
row stays exactly as it was.

This is what makes the catalogue answerable. Three questions have to be
answerable at any point and none of them can be answered by a mutated field:

- what do we currently publish for this attribute;
- what did we publish for it at the time a given asset was generated;
- which document told us to change it, and when.

The same rule governs withdrawal. A correction that a supplier retracts - as
DOC-06 v2 was retracted for PRD-04 - is marked WITHDRAWN, not deleted. The
in-force value reverts to the superseded row by supersession, not by editing the
value back.

## Supersession semantics

| situation | effect |
|---|---|
| new version of the same document, changed value | new fact supersedes the old; document version increments |
| new version of the same document, identical value | zero-delta; recorded as a confirmation, no supersession, no impact |
| higher-precedence document contradicts a lower one | higher-precedence fact becomes in-force; lower is superseded, not removed |
| lower-precedence document contradicts a higher one | no supersession; raise SOURCE_CONFLICT |
| document withdrawn | its facts become WITHDRAWN; the previously superseded fact returns to force |
| correction that narrows scope | supersedes only the entities in the narrowed scope |

The last row is the one that is routinely got wrong. A correction stated at
product level and later narrowed to a single variant does not retroactively
become a variant-level correction: the product-level fact stands, is superseded
where the narrowing applies, and remains in force elsewhere. Both steps are
recorded, so the history shows what we believed at each point rather than what
we eventually concluded.

## Scope

A correction carries a scope, and the scope is often the only genuinely
uncertain part of it.

| scope | meaning |
|---|---|
| PRODUCT | applies to every variant of the product |
| VARIANT | applies to the named variants only |
| LISTING | applies to one variant on one channel |
| UNCLEAR | the document names a product that has more than one variant, and does not say which is meant |

**UNCLEAR is a scope, not a missing one.** A correction whose scope is UNCLEAR
is not applied to every variant on the assumption that the supplier meant all of
them, and it is not applied to the base variant on the assumption that the
supplier meant the main one. It is recorded, the ambiguity is named, the
variants it might apply to are listed, and a supplier query is raised under
POL-003. Channels are held where the ambiguous attribute is required.

Guessing a scope is the single most expensive error available here, because the
guess is invisible afterwards: the value looks sourced, the provenance looks
clean, and nothing records that a choice was made.

## Materiality

Materiality decides urgency and approval, never whether the correction is
recorded. Every correction is recorded.

| condition | material |
|---|---|
| change to a safety-classed attribute | **always**, at any magnitude |
| change that invalidates a substantiated claim | **always** |
| change that crosses a facet band or channel rule threshold | **always** |
| numeric change of 5% or more of the in-force value | yes |
| numeric change below 5%, no threshold crossed | no |
| ingredient reorder, no membership change | yes - CH-MKT-B rejects on it |
| price, stock or lead-time only | no - not product content |
| restatement of an unchanged value | no - zero-delta |

An immaterial correction is applied, recorded and published on the next normal
cycle. A material correction is scoped, impact-assessed across every channel,
and routed through POL-003.

Magnitude is the weakest of these tests and is listed last deliberately.
VAR-01B moving 38 dB to 44 dB is 16% and would be material on magnitude alone,
but it is material for the reason that matters: it crosses the 40 dB line under
`ultra-quiet` and withdraws a claim.

## Related

STD-001 (claim rules), STD-002 (normalisation before comparison),
CHN-004 (corrections inside the print freeze window),
POL-001 (regulated corrections), POL-003 (escalation and supplier queries),
INC-2025-041 (an UNCLEAR scope applied as PRODUCT),
INC-2026-002 (a correction that arrived inside the freeze window).
