# SUP-30 - Larkspur Baby Products

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (8)

- **BAB-126-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **BAB-150-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **BAB-150-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **LAR-901-A** - proposed new line (baby.feeding.formula). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LAR-902-B** - proposed new line (baby.feeding.weaning). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LAR-904-A** - proposed new line (baby.nappies.wipes). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LAR-904-B** - proposed new line (baby.nappies.wipes). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LAR-906-B** - proposed new line (baby.feeding.bottles). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **BAB-126-B** - packaging.recyclable_pct arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **BAB-102-A** - pack.net_quantity arrives as '780,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (3)

- **BAB-190-A** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **LAR-902-A** - proposed new line (baby.feeding.weaning). identifiers.gtin is blank on a proposed line; the catalog's other lines in baby.feeding.weaning are what a proposal would be scored against
- **LAR-906-A** - proposed new line (baby.feeding.bottles). compliance.certificate_ref is blank on a proposed line; the catalog's other lines in baby.feeding.bottles are what a proposal would be scored against

## A person has to look (6)

- **BAB-118-A** - the record holds no detail image and baby cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **BAB-166-A** - the record holds no pack_front image and baby cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **BAB-166-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **BAB-166-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **LAR-903-A** - proposed new line (baby.nappies.nappies). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **LAR-905-A** - proposed new line (baby.toys.activity). the sheet names a detail image the archive does not hold; baby cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `txt`
- a spare column (`Case Qty`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
