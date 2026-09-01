# SUP-29 - Hollowbrook Nutrition

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (5)

- **BAB-110-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOL-901-A** - proposed new line (baby.feeding.bottles). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HOL-902-B** - proposed new line (baby.feeding.formula). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HOL-904-A** - proposed new line (baby.toys.activity). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HOL-906-B** - proposed new line (baby.feeding.weaning). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (5)

- **BAB-142-A** - packaging.recyclable_pct arrives as '79 %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **BAB-142-C** - pack.net_quantity arrives as '1,050' - a thousands separator from the export. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **BAB-158-A** - packaging.recyclable_pct arrives as '94 %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **BAB-174-A** - packaging.recyclable_pct arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **BAB-174-B** - packaging.recyclable_pct arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (8)

- **BAB-174-C** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **BAB-182-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **BAB-182-B** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **BAB-182-C** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **BAB-198-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **BAB-198-B** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HOL-902-A** - proposed new line (baby.feeding.formula). packaging.recyclable_pct is blank on a proposed line; the catalog's other lines in baby.feeding.formula are what a proposal would be scored against
- **HOL-906-A** - proposed new line (baby.feeding.weaning). food.ingredients is blank on a proposed line; the catalog's other lines in baby.feeding.weaning are what a proposal would be scored against

## A person has to look (4)

- **BAB-134-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **BAB-142-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HOL-903-A** - proposed new line (baby.nappies.nappies). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **HOL-905-A** - proposed new line (baby.toys.soft). the sheet names a detail image the archive does not hold; baby cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Supplier Notes`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
