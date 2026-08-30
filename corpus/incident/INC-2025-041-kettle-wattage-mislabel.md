---
id: INC-2025-041
type: POSTMORTEM
title: Cascade Rapid Kettle wattage mislabel - a product-level correction applied to the wrong variant
owner: Product Data Governance
occurred: 2025-08-19
closed: 2025-09-11
severity: HIGH
entities: [PRD-04, VAR-04A, SUP-04, DOC-06, CH-WEB, CH-MKT-A, CH-PRINT, CH-SHELF, MKA-4102, PRD-01, VAR-01A, VAR-01B]
tags: [correction, scope, variant, wattage, unclear, mka-4102, supplier-query, recurrence]
---

# INC-2025-041 - Cascade Rapid Kettle wattage mislabel

## Summary

SUP-04 sent a spec sheet correction (DOC-06) stating that the rated power of
"the Cascade Rapid Kettle" was 3000 W and not the 2200 W we held. PRD-04 was at
that time listed as two variants: VAR-04A, the base kettle, and a
higher-capacity variant since delisted. The document named the product and not
the variant.

The correction was applied at PRODUCT scope to both variants. It was correct
for one of them. VAR-04A was published at 3000 W for nineteen days across
CH-WEB, CH-MKT-A, CH-PRINT and CH-SHELF while its actual rated power was
2200 W.

Final outcome: 41 shelf labels reprinted, one catalogue edition carrying the
wrong figure, 312 CH-MKT-A rows rejected as MKA-4102 during the correction, and
a two-week supplier query cycle to establish what should have been asked on day
one.

## Timeline

| Date | Event |
|---|---|
| 19 Aug, 09:40 | DOC-06 v2 received. Names "the Cascade Rapid Kettle", no variant. |
| 19 Aug, 11:05 | Applied at PRODUCT scope. Both variants set to 3000 W. |
| 19 Aug, 11:30 | CH-WEB, CH-MKT-A, CH-SHELF republished. CH-PRINT inside its freeze window; escalated and re-plated. |
| 21 Aug | CH-MKT-A rejections begin - MKA-4102 on `wattage`, from a downstream normalisation that sent `"3000 W"` as text. |
| 27 Aug | Store colleague queries a shelf label against the appliance's own rating plate. |
| 28 Aug | Supplier query raised. SUP-04 confirms 3000 W applies to the higher-capacity variant only. |
| 29 Aug | VAR-04A reverted by supersession to 2200 W. All four channels republished. |
| 11 Sep | Actions closed. |

## Root cause

**The document's scope was UNCLEAR and was recorded as PRODUCT.**

DOC-06 v2 named a product that had two variants and did not say which it meant.
That is the definition of an UNCLEAR scope in POL-002. Nothing in the process
distinguished "the supplier said this applies to the product" from "the supplier
did not say which variant", and once the correction was stored at PRODUCT scope
the ambiguity was gone from the record. Every downstream check saw a correction
with a named source document, a version, and a clean provenance chain.

Contributing factors:

1. **The wattage differed between the two variants at baseline.** A correction
   naming a single figure for a product whose variants held different figures
   should have been treated as self-evidently under-specified. Nobody compared
   the incoming value against both variants before applying it.
2. **No supplier query was raised.** POL-003 already required one. The
   correction looked unambiguous because it was internally consistent, which is
   a different property.
3. **Print was published in the same wave as the reversible channels.** The
   irreversible channel took the correction before anything had validated it.

## What worked

- Supersession. Reverting VAR-04A was a new fact row pointing at the 3000 W
  row, so the record shows a correction applied at the wrong scope and then
  narrowed. Had the value been overwritten, the nineteen days would have been
  unreconstructable.
- Impact was computed from `derived_from`, so the shelf labels were found. They
  are the assets most often missed, because a 40-character label does not look
  like content.

## What did not work

**Applying an under-specified correction to every variant.** The reasoning at
the time was that applying it broadly was the safer error, since the supplier
had told us our figure was wrong and leaving a known-wrong figure in place felt
worse. That reasoning is backwards. We knew one figure was wrong; we did not
know which. Applying the correction to both variants replaced one wrong value
with a different wrong value on the other, and did so with a provenance chain
that made it look sourced.

**Treating the MKA-4102 storm as the incident.** Three days were spent on the
feed defect - a text wattage where an integer was required, RUL-A03 - because
it was loud, measurable and had a rejection code. The actual defect was silent
and had no code. The marketplace rejections were a symptom of a hurried
republish, not of the scope error, and fixing them changed nothing.

## Remedy - when a specification names the product but not the variant

This is the guidance that came out of the incident and it is written to be
followed directly.

| Step | Action |
|---|---|
| 1 | Record the correction with scope **UNCLEAR**. Do not choose a variant. UNCLEAR is a scope with a meaning, not an absence of one. |
| 2 | List every variant of the named product as a candidate, and state for each one the value we currently hold and where it came from. |
| 3 | Apply the correction only where the attribute is **variant-invariant** - where every candidate variant already holds the same value from the same source. Where the candidates differ, the difference is the evidence that the document is under-specified, and nothing is applied. |
| 4 | Raise a supplier query under POL-003. Quote the document's exact wording, list the candidate variants by id and name, state the value each currently holds, and ask a closed question: which variant, or both. |
| 5 | Withhold channels where the ambiguous attribute is REQUIRED - CH-MKT-A (RUL-A02), CH-MKT-B (RUL-B02), CH-PRINT (RUL-P01). Leave channels that do not carry it published. |
| 6 | Hold CH-PRINT regardless of its freeze window. An unclear correction is never worth a re-plate, and a re-plate made on a guess cannot be undone. |
| 7 | Re-evaluate every claim on **all** candidate variants against both the held and the proposed value. A claim that fails under either is not safe to leave standing. |
| 8 | When the supplier answers, apply at VARIANT scope by supersession. Both steps stay in the record. |

The principle underneath it: **an ambiguous correction is not a correction with
a missing field, it is information about two variants at once.** Treat it as
evidence, not as an instruction, until the supplier resolves it.

## Actions

| # | Action | Status |
|---|---|---|
| 1 | UNCLEAR scope added to POL-002 with the candidate-listing requirement | Closed |
| 2 | Supplier query template naming candidate variants and quoting source wording | Closed |
| 3 | Publish reversible channels before CH-PRINT in every correction wave (CHN-004) | Closed |
| 4 | Warn when an incoming single value contradicts variants that currently differ | Closed |
| 5 | Wattage normalisation to integer before feed assembly (STD-002, RUL-A03) | Closed |

## Recurrence watch

The exposure is structural: it exists on any product with more than one variant
where a specification-bearing attribute differs between them.

**PRD-01 AeroPure 300 is the highest-risk listing in the catalogue on this
pattern.** VAR-01A "AeroPure 300" and VAR-01B "AeroPure 300 Max" differ in
`specs.coverage_m2`, share a supplier (SUP-01) and share a spec document
(DOC-01) whose earlier version mixed the two models together. A SUP-01
correction naming "the AeroPure 300" is ambiguous by construction, because that
string is both the product name and the base variant's name - and a reader who
takes it as the variant name will not notice they have made a choice.

VAR-01A's CH-WEB comparison table additionally quotes both variants' wattage
(CHN-001), so a correction to either variant changes content on the base
variant's page. Any PRD-01 wattage correction should be assumed to be
variant-ambiguous and to have cross-variant impact until proven otherwise.

## Related

POL-002 (scope and supersession), POL-003 (supplier queries),
CHN-001 (the cross-variant comparison table), CHN-002 (MKA-4102),
CHN-004 (print freeze window), STD-002 (integer wattage).
