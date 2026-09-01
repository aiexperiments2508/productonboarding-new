# SUP-27 - Petrichor Household Products

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (15)

- **HPC-140-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-140-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-156-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-156-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-172-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-188-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-228-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-228-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-228-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HPC-233-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **PET-901-A** - proposed new line (hpc.cleaning.dishwashing). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **PET-901-B** - proposed new line (hpc.cleaning.dishwashing). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **PET-903-B** - proposed new line (hpc.cosmetics.haircare). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **PET-904-A** - proposed new line (hpc.cosmetics.skincare). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **PET-905-B** - proposed new line (hpc.laundry.detergent). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HPC-108-A** - packaging.recyclable_pct arrives as '68 %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **HPC-108-B** - packaging.recyclable_pct arrives as '20% %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (4)

- **HPC-140-B** - packaging.recyclable_pct is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HPC-156-A** - packaging.recyclable_pct is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **PET-902-A** - proposed new line (hpc.cleaning.surface). pack.net_quantity is blank on a proposed line; the catalog's other lines in hpc.cleaning.surface are what a proposal would be scored against
- **PET-906-A** - proposed new line (hpc.paper.kitchen-roll). claims is blank on a proposed line; the catalog's other lines in hpc.paper.kitchen-roll are what a proposal would be scored against

## A person has to look (5)

- **HPC-196-A** - the record holds no detail image and hpc cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HPC-241-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HPC-241-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **PET-903-A** - proposed new line (hpc.cosmetics.haircare). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **PET-905-A** - proposed new line (hpc.laundry.detergent). the sheet names a detail image the archive does not hold; hpc cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
