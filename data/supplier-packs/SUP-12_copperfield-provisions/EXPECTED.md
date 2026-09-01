# SUP-12 - Copperfield Provisions

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (8)

- **COP-901-A** - proposed new line (food.bakery.biscuits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-901-B** - proposed new line (food.bakery.biscuits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-902-B** - proposed new line (food.bakery.cakes). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-903-B** - proposed new line (food.alcohol.beer). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-904-A** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-904-B** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-905-B** - proposed new line (food.alcohol.wine). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **COP-906-B** - proposed new line (food.ambient.cereals). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (1)

- **FOO-152-A** - food.net_weight_g arrives as '202,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (2)

- **COP-902-A** - proposed new line (food.bakery.cakes). pack.net_quantity is blank on a proposed line; the catalog's other lines in food.bakery.cakes are what a proposal would be scored against
- **COP-906-A** - proposed new line (food.ambient.cereals). food.ingredients is blank on a proposed line; the catalog's other lines in food.ambient.cereals are what a proposal would be scored against

## A person has to look (4)

- **FOO-112-A** - the record holds no ingredient_panel image and food cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **FOO-152-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **COP-903-A** - proposed new line (food.alcohol.beer). compliance.min_age is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **COP-905-A** - proposed new line (food.alcohol.wine). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
