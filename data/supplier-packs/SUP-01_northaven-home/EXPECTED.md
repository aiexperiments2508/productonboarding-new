# SUP-01 - Northaven Home

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (6)

- **NAV-AP300-MAX** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **NOR-901-A** - proposed new line (home.air-treatment.fans). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-902-B** - proposed new line (home.air-treatment.purifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-903-B** - proposed new line (home.air-treatment.humidifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-904-A** - proposed new line (home.cookware.knives). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **NOR-904-B** - proposed new line (home.cookware.knives). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (2)

- **NOR-902-A** - proposed new line (home.air-treatment.purifiers). claims is blank on a proposed line; the catalog's other lines in home.air-treatment.purifiers are what a proposal would be scored against
- **NOR-906-A** - proposed new line (home.floorcare.vacuums). claims is blank on a proposed line; the catalog's other lines in home.floorcare.vacuums are what a proposal would be scored against

## A person has to look (4)

- **NAV-FAN-V2** - the record holds no in_situ image and home cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **NAV-AP300-STD** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **NOR-903-A** - proposed new line (home.air-treatment.humidifiers). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **NOR-905-A** - proposed new line (home.cookware.pans). the sheet names a in_situ image the archive does not hold; home cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `food.net_weight_g` is carried on the first two rows with the value `450`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
