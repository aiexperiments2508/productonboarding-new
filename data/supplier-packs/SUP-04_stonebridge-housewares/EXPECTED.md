# SUP-04 - Stonebridge Housewares

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (6)

- **STB-KET-17** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **STO-901-A** - proposed new line (home.kitchen.kettles). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **STO-902-B** - proposed new line (home.air-treatment.fans). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **STO-904-A** - proposed new line (home.air-treatment.purifiers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **STO-905-B** - proposed new line (home.cookware.knives). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **STO-906-B** - proposed new line (home.cookware.pans). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (2)

- **STO-902-A** - proposed new line (home.air-treatment.fans). identifiers.gtin is blank on a proposed line; the catalog's other lines in home.air-treatment.fans are what a proposal would be scored against
- **STO-906-A** - proposed new line (home.cookware.pans). origin.country is blank on a proposed line; the catalog's other lines in home.cookware.pans are what a proposal would be scored against

## A person has to look (2)

- **STO-903-A** - proposed new line (home.air-treatment.humidifiers). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **STO-905-A** - proposed new line (home.cookware.knives). the sheet names a in_situ image the archive does not hold; home cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `food.net_weight_g` is carried on the first two rows with the value `450`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `txt`
- a spare column (`Case Qty`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
