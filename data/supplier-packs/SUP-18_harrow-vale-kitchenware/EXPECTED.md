# SUP-18 - Harrow & Vale Kitchenware

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (8)

- **HOM-147-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-155-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-155-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-195-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HAR-901-A** - proposed new line (home.kitchen.blenders). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HAR-902-B** - proposed new line (home.kitchen.microwaves). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HAR-903-B** - proposed new line (home.laundry.irons). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **HAR-904-A** - proposed new line (home.textiles.bedding). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HOM-139-A** - specs.noise_db arrives as '41 dB' - the unit is in the cell (dB). The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **HOM-155-B** - specs.noise_db arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (5)

- **HOM-195-B** - energy.class is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HOM-195-C** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HOM-227-B** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HAR-902-A** - proposed new line (home.kitchen.microwaves). specs.power_w is blank on a proposed line; the catalog's other lines in home.kitchen.microwaves are what a proposal would be scored against
- **HAR-906-A** - proposed new line (home.air-treatment.humidifiers). claims is blank on a proposed line; the catalog's other lines in home.air-treatment.humidifiers are what a proposal would be scored against

## A person has to look (4)

- **HOM-227-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HOM-227-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HAR-903-A** - proposed new line (home.laundry.irons). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **HAR-905-A** - proposed new line (home.air-treatment.fans). the sheet names a in_situ image the archive does not hold; home cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
