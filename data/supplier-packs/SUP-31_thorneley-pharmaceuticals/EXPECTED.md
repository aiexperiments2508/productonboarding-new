# SUP-31 - Thorneley Pharmaceuticals

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (11)

- **HEA-122-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-122-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-146-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-146-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-162-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-162-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-170-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-170-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **THO-901-A** - proposed new line (health.devices.firstaid). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **THO-904-A** - proposed new line (health.supplements.minerals). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **THO-904-B** - proposed new line (health.supplements.minerals). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HEA-194-A** - pack.net_quantity arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **HEA-122-A** - pack.net_quantity arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (2)

- **THO-902-A** - proposed new line (health.medicines.allergy). pack.unit is blank on a proposed line; the catalog's other lines in health.medicines.allergy are what a proposal would be scored against
- **THO-906-A** - proposed new line (health.devices.thermometers). compliance.certificate_ref is blank on a proposed line; the catalog's other lines in health.devices.thermometers are what a proposal would be scored against

## A person has to look (5)

- **HEA-138-A** - the record holds no detail image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-170-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HEA-202-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **THO-903-A** - proposed new line (health.medicines.cold-flu). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **THO-905-A** - proposed new line (health.supplements.vitamins). the sheet names a detail image the archive does not hold; health cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `xlsx`
- a spare column (`Supplier Notes`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
