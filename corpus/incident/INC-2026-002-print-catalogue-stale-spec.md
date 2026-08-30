---
id: INC-2026-002
type: POSTMORTEM
title: Spring catalogue printed with a superseded specification - the origin of the 7-day freeze window
owner: Retail Marketing
occurred: 2026-01-16
closed: 2026-02-04
severity: CRITICAL
entities: [CH-PRINT, PRD-06, VAR-06A, SUP-01, DOC-01, DOC-08, CH-WEB, CH-MKT-A, CH-SHELF]
tags: [print, catalogue, freeze-window, stale-version, irreversible, sequencing, re-plate]
---

# INC-2026-002 - Spring catalogue printed with a superseded specification

## Summary

A SUP-01 correction to PRD-06 Voltaic Desk Fan V2 raised its rated power from
40 W to 55 W. The correction arrived three days before the spring catalogue's
press date. It was applied to the attribute, propagated to CH-WEB, CH-MKT-A and
CH-SHELF within the hour, and applied to the CH-PRINT catalogue copy as well -
after the file had left prepress.

The catalogue printed with 40 W. 214,000 copies, distributed to 168 stores.
The listing's `published_version` was v3; the in-force attribute was v4; nothing
in the system reported it, because the CH-PRINT asset had been regenerated and
therefore no longer looked stale.

There was no freeze window at the time. This incident is why there is one.

## Timeline

| Date | Event |
|---|---|
| 13 Jan | Catalogue file signed off at v3 and released to prepress. |
| 16 Jan, 10:20 | DOC-01 correction received: PRD-06 rated power 40 W to 55 W. |
| 16 Jan, 10:55 | Attribute corrected. CH-WEB, CH-MKT-A, CH-SHELF republished. Correct. |
| 16 Jan, 11:10 | CH-PRINT `catalogue_copy` regenerated at 55 W. Listing marked as republished. |
| 16 Jan, 11:10 | No check against the press date. None existed. |
| 19 Jan | Press run begins from the v3 file held at prepress. |
| 27 Jan | Catalogues in stores. |
| 29 Jan | Store colleague reports the catalogue and the shelf label disagreeing. |
| 30 Jan | 168 stores issued a correction slip. Digital edition re-rendered and reissued. |
| 04 Feb | Actions closed. |

## Root cause

**The system tracked whether content had been regenerated, and the printer
tracked what had been sent to press, and nothing compared the two.**

Regenerating `catalogue_copy` cleared the only signal that existed. A stale
asset check asks whether the content was built from current attributes; that
check passed, because the asset had been rebuilt at 11:10. The catalogue in the
press was built from v3 and had no representation in the system at all.

Contributing factors:

1. **No freeze window.** There was no concept of a point after which a
   CH-PRINT listing could not usefully be changed. Applying a correction to a
   file that has left prepress is not a publication; it is an edit to a document
   nobody will read.
2. **Print was published in the same wave as the reversible channels.** The
   correction reached the irreversible channel simultaneously with the ones that
   could be undone, so nothing had validated it and nothing had a chance to.
3. **`published_version` was not compared against attribute versions.** The
   field existed and was maintained. Nothing read it.

## What worked

Very little, and it is worth being exact about that. The correction itself was
right, was applied promptly, and was correct on three of four channels within
forty minutes. Every part of the process that could be undone worked. The one
part that could not, failed.

The supersession record did allow the exposure to be reconstructed precisely -
which listing, which version, which attribute, which press date - which made
the store correction slip accurate and quick to produce.

## What did not work

**Regenerating content as the response to a correction on an irreversible
channel.** Regeneration is the right response where publication is cheap and
reversible. On CH-PRINT it destroys the evidence of the problem: the asset stops
looking stale at exactly the moment the printed artefact becomes wrong.

**Measuring staleness against the asset rather than against the artefact.** A
stale asset is content that can be regenerated. A stale version is a physical
object already in the world carrying a superseded figure. Only the second one
was true here, and only the first one was being checked.

## Remedy - the 7-day freeze window and the stale-version rule

Both rules in CHN-004 came from this incident.

| Rule | What it does |
|---|---|
| **7-day freeze window** | No content change is applied to a CH-PRINT listing within 7 days of its press date. Inside the window a correction is recorded, escalated for a re-plate decision under POL-003, or deferred to the next edition. It is never applied quietly. |
| **`stale_version`** | Where a listing's `published_version` is older than the in-force version of any attribute it was built from, the listing is in violation - separately from `stale_asset`, and not cleared by regenerating anything. |

The two work together and neither is sufficient alone. The freeze window stops
the pointless edit; the stale-version rule makes the resulting divergence
visible instead of letting a regenerated asset conceal it.

Sequencing follows from the same logic: publish CH-WEB, then the marketplaces,
then CH-SHELF and CH-SEARCH, and test CH-PRINT against its freeze window last.
The irreversible channel takes a correction only once the reversible ones have
proved it.

## Actions

| # | Action | Status |
|---|---|---|
| 1 | 7-day freeze window on CH-PRINT (CHN-004) | Closed |
| 2 | `stale_version` violation, raised separately from `stale_asset` | Closed |
| 3 | Reversible channels published before CH-PRINT in every correction wave | Closed |
| 4 | Press date held against the listing and compared on every correction | Closed |
| 5 | Re-plate authority set at head of retail marketing (POL-003) | Closed |

## Recurrence watch

The freeze window protects the interval before a press date. It does nothing
about a correction that arrives after a press run and before distribution, where
the artefact exists, is wrong, and has not yet reached a customer. That window
is short and has no owner. A correction landing in it should be escalated as
CRITICAL on the same footing as this incident.

## Related

CHN-004 (freeze window, stale-version rule, sequencing),
POL-002 (supersession and materiality), POL-003 (re-plate authority),
CHN-001 (reversible publication), INC-2025-041.
