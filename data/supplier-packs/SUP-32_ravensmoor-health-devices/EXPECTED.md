# SUP-32 - Ravensmoor Health Devices

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (7)

- **HEA-114-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-114-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HEA-130-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **RAV-901-A** - proposed new line (health.devices.thermometers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **RAV-903-B** - proposed new line (health.medicines.pain-relief). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **RAV-904-A** - proposed new line (health.supplements.vitamins). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **RAV-906-B** - proposed new line (health.medicines.cold-flu). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HEA-106-B** - pack.net_quantity arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **HEA-114-A** - pack.net_quantity arrives as '220,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (2)

- **RAV-902-A** - proposed new line (health.medicines.allergy). pack.net_quantity is blank on a proposed line; the catalog's other lines in health.medicines.allergy are what a proposal would be scored against
- **RAV-906-A** - proposed new line (health.medicines.cold-flu). pack.unit is blank on a proposed line; the catalog's other lines in health.medicines.cold-flu are what a proposal would be scored against

## A person has to look (9)

- **HEA-106-A** - the record holds no detail image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-106-C** - the record holds no detail image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-130-B** - the record holds no pack_front image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-178-B** - the record holds no detail image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-186-A** - the record holds no detail image and health cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HEA-154-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HEA-178-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **RAV-903-A** - proposed new line (health.medicines.pain-relief). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **RAV-905-A** - proposed new line (health.devices.firstaid). the sheet names a detail image the archive does not hold; health cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
