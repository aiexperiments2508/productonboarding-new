# SUP-17 - Northgate Appliance Co.

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (10)

- **HOM-107-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-123-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-131-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-187-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **HOM-209-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **NOR-901-A** - proposed new line (home.air-treatment.humidifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-902-B** - proposed new line (home.cookware.knives). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-903-B** - proposed new line (home.cookware.pans). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-904-A** - proposed new line (home.kitchen.toasters). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-904-B** - proposed new line (home.kitchen.toasters). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **HOM-131-A** - specs.noise_db arrives as '38,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **HOM-107-A** - specs.coverage_m2 arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (4)

- **HOM-187-A** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **HOM-187-C** - energy.class is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **NOR-902-A** - proposed new line (home.cookware.knives). claims is blank on a proposed line; the catalog's other lines in home.cookware.knives are what a proposal would be scored against
- **NOR-906-A** - proposed new line (home.textiles.towels). claims is blank on a proposed line; the catalog's other lines in home.textiles.towels are what a proposal would be scored against

## A person has to look (6)

- **HOM-209-B** - the record holds no hero image and home cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HOM-215-B** - the record holds no in_situ image and home cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **HOM-215-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **HOM-240-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **NOR-903-A** - proposed new line (home.cookware.pans). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **NOR-905-A** - proposed new line (home.laundry.irons). the sheet names a in_situ image the archive does not hold; home cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Supplier Notes`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
