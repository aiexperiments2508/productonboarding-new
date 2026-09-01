# SUP-11 - Bramblewood Bakery Ltd

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (7)

- **FOO-128-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-239-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-243-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **BRA-901-A** - proposed new line (food.bakery.bread). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **BRA-903-B** - proposed new line (food.alcohol.beer). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **BRA-904-A** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **BRA-904-B** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **FOO-128-A** - food.fibre_g arrives as '7,6' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **FOO-128-B** - food.fibre_g arrives as '9.0 g' - the unit is in the cell (g). The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (2)

- **BRA-902-A** - proposed new line (food.chilled.ready-meals). origin.country is blank on a proposed line; the catalog's other lines in food.chilled.ready-meals are what a proposal would be scored against
- **BRA-906-A** - proposed new line (food.ambient.cereals). claims is blank on a proposed line; the catalog's other lines in food.ambient.cereals are what a proposal would be scored against

## A person has to look (4)

- **FOO-243-A** - the record holds no ingredient_panel image and food cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **FOO-243-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **BRA-903-A** - proposed new line (food.alcohol.beer). compliance.min_age is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **BRA-905-A** - proposed new line (food.alcohol.wine). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `xlsx`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
