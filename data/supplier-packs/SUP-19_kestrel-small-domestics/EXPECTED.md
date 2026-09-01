# SUP-19 - Kestrel Small Domestics

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (14)

- **HOM-115-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-163-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-163-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-203-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-203-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-221-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-221-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-221-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-232-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-232-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **KES-901-A** - proposed new line (home.air-treatment.humidifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **KES-901-B** - proposed new line (home.air-treatment.humidifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **KES-904-A** - proposed new line (home.floorcare.vacuums). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **KES-906-B** - proposed new line (home.textiles.bedding). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HOM-115-B** - specs.coverage_m2 arrives as '70,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **HOM-163-C** - specs.noise_db arrives as '51 dB' - the unit is in the cell (dB). The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (5)

- **HOM-171-A** - specs.noise_db is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **HOM-179-A** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **HOM-232-C** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **KES-902-A** - proposed new line (home.cookware.knives). identifiers.gtin is blank on a proposed line; the catalog's other lines in home.cookware.knives are what a proposal would be scored against
- **KES-906-A** - proposed new line (home.textiles.bedding). origin.country is blank on a proposed line; the catalog's other lines in home.textiles.bedding are what a proposal would be scored against

## A person has to look (4)

- **HOM-236-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HOM-236-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **KES-903-A** - proposed new line (home.cookware.pans). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **KES-905-A** - proposed new line (home.kitchen.microwaves). the sheet names a in_situ image the archive does not hold; home cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`internal_ref`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
