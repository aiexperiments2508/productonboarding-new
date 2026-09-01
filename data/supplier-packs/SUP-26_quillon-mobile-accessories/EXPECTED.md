# SUP-26 - Quillon Mobile Accessories

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (9)

- **ELE-159-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-199-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **ELE-218-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **QUI-901-A** - proposed new line (electronics.audio.soundbars). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **QUI-901-B** - proposed new line (electronics.audio.soundbars). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **QUI-902-B** - proposed new line (electronics.mobile.powerbanks). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **QUI-904-A** - proposed new line (electronics.vision.televisions). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **QUI-904-B** - proposed new line (electronics.vision.televisions). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **QUI-906-B** - proposed new line (electronics.audio.headphones). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **ELE-103-A** - specs.power_w arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **ELE-103-B** - specs.power_w arrives as '175,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (3)

- **ELE-103-C** - energy.class is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **QUI-902-A** - proposed new line (electronics.mobile.powerbanks). origin.country is blank on a proposed line; the catalog's other lines in electronics.mobile.powerbanks are what a proposal would be scored against
- **QUI-906-A** - proposed new line (electronics.audio.headphones). claims is blank on a proposed line; the catalog's other lines in electronics.audio.headphones are what a proposal would be scored against

## A person has to look (3)

- **ELE-224-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **QUI-903-A** - proposed new line (electronics.personal.drones). compliance.export_control is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **QUI-905-A** - proposed new line (electronics.audio.earbuds). the sheet names a hero image the archive does not hold; electronics cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `xlsx`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
