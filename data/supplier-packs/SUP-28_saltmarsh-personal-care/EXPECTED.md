# SUP-28 - Saltmarsh Personal Care

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (12)

- **HPC-124-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-132-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-132-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-148-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-164-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-210-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **SAL-901-A** - proposed new line (hpc.cleaning.bleach). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SAL-901-B** - proposed new line (hpc.cleaning.bleach). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SAL-902-B** - proposed new line (hpc.cleaning.dishwashing). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SAL-904-A** - proposed new line (hpc.cosmetics.haircare). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SAL-904-B** - proposed new line (hpc.cosmetics.haircare). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SAL-906-B** - proposed new line (hpc.paper.kitchen-roll). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (3)

- **HPC-116-A** - packaging.recyclable_pct arrives as '28 %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **HPC-132-A** - packaging.recyclable_pct arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **HPC-148-A** - packaging.recyclable_pct arrives as '100% %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (5)

- **HPC-180-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **HPC-222-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **HPC-237-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **SAL-902-A** - proposed new line (hpc.cleaning.dishwashing). packaging.recyclable_pct is blank on a proposed line; the catalog's other lines in hpc.cleaning.dishwashing are what a proposal would be scored against
- **SAL-906-A** - proposed new line (hpc.paper.kitchen-roll). pack.net_quantity is blank on a proposed line; the catalog's other lines in hpc.paper.kitchen-roll are what a proposal would be scored against

## A person has to look (5)

- **HPC-204-A** - the record holds no detail image and hpc cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HPC-216-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HPC-216-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **SAL-903-A** - proposed new line (hpc.cleaning.surface). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **SAL-905-A** - proposed new line (hpc.laundry.detergent). the sheet names a detail image the archive does not hold; hpc cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
