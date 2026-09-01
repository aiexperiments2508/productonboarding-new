# SUP-21 - Calderstone Garments

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (7)

- **APP-165-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **CAL-901-A** - proposed new line (apparel.mens.knitwear). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-903-B** - proposed new line (apparel.footwear.boots). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-904-A** - proposed new line (apparel.footwear.trainers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-904-B** - proposed new line (apparel.footwear.trainers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-905-B** - proposed new line (apparel.kids.sleepwear). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-906-B** - proposed new line (apparel.kids.tops). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (3)

- **APP-165-B** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **CAL-902-A** - proposed new line (apparel.accessories.bags). identifiers.gtin is blank on a proposed line; the catalog's other lines in apparel.accessories.bags are what a proposal would be scored against
- **CAL-906-A** - proposed new line (apparel.kids.tops). textile.care_code is blank on a proposed line; the catalog's other lines in apparel.kids.tops are what a proposal would be scored against

## A person has to look (3)

- **APP-165-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **CAL-903-A** - proposed new line (apparel.footwear.boots). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **CAL-905-A** - proposed new line (apparel.kids.sleepwear). the sheet names a detail image the archive does not hold; apparel cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `xlsx`
- a spare column (`internal_ref`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
