# SUP-24 - Lumen Audio Works

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (12)

- **ELE-111-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-143-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-143-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-151-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-151-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **LUM-901-A** - proposed new line (electronics.audio.speakers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-902-B** - proposed new line (electronics.computing.tablets). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-903-B** - proposed new line (electronics.mobile.powerbanks). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-904-A** - proposed new line (electronics.mobile.smartwatches). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-904-B** - proposed new line (electronics.mobile.smartwatches). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-905-B** - proposed new line (electronics.vision.televisions). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LUM-906-B** - proposed new line (electronics.audio.earbuds). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **ELE-111-A** - specs.power_w arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **ELE-111-C** - specs.power_w arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (5)

- **ELE-151-C** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **ELE-175-A** - energy.class is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **ELE-206-A** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **LUM-902-A** - proposed new line (electronics.computing.tablets). identifiers.gtin is blank on a proposed line; the catalog's other lines in electronics.computing.tablets are what a proposal would be scored against
- **LUM-906-A** - proposed new line (electronics.audio.earbuds). origin.country is blank on a proposed line; the catalog's other lines in electronics.audio.earbuds are what a proposal would be scored against

## A person has to look (4)

- **ELE-183-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **ELE-206-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **LUM-903-A** - proposed new line (electronics.mobile.powerbanks). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **LUM-905-A** - proposed new line (electronics.vision.televisions). the sheet names a hero image the archive does not hold; electronics cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`internal_ref`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
