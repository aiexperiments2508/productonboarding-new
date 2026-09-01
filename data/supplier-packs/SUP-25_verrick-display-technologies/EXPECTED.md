# SUP-25 - Verrick Display Technologies

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (9)

- **ELE-127-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-127-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-135-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-167-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-167-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **VER-901-A** - proposed new line (electronics.audio.headphones). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **VER-901-B** - proposed new line (electronics.audio.headphones). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **VER-904-A** - proposed new line (electronics.personal.cameras). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **VER-905-B** - proposed new line (electronics.vision.projectors). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **ELE-119-A** - specs.power_w arrives as '64,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **ELE-167-A** - specs.power_w arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (5)

- **ELE-127-C** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **ELE-135-B** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **ELE-212-A** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **VER-902-A** - proposed new line (electronics.computing.laptops). compliance.certificate_ref is blank on a proposed line; the catalog's other lines in electronics.computing.laptops are what a proposal would be scored against
- **VER-906-A** - proposed new line (electronics.audio.earbuds). identifiers.gtin is blank on a proposed line; the catalog's other lines in electronics.audio.earbuds are what a proposal would be scored against

## A person has to look (4)

- **ELE-191-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **ELE-191-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **VER-903-A** - proposed new line (electronics.mobile.smartwatches). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **VER-905-A** - proposed new line (electronics.vision.projectors). the sheet names a hero image the archive does not hold; electronics cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `txt`
- a spare column (`Supplier Notes`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
