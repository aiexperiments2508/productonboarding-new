# SUP-16 - Marlowe & Fenn Wine Merchants

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (6)

- **FOO-230-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **MAR-901-A** - proposed new line (food.dairy.yoghurt). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **MAR-903-B** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **MAR-904-A** - proposed new line (food.alcohol.wine). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **MAR-904-B** - proposed new line (food.alcohol.wine). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **MAR-906-B** - proposed new line (food.ambient.pasta-rice). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (1)

- **FOO-230-A** - packaging.recyclable_pct arrives as '42 %' - the unit is in the cell (%). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (2)

- **MAR-902-A** - proposed new line (food.alcohol.beer). pack.net_quantity is blank on a proposed line; the catalog's other lines in food.alcohol.beer are what a proposal would be scored against
- **MAR-906-A** - proposed new line (food.ambient.pasta-rice). packaging.recyclable_pct is blank on a proposed line; the catalog's other lines in food.ambient.pasta-rice are what a proposal would be scored against

## A person has to look (3)

- **FOO-230-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **MAR-903-A** - proposed new line (food.alcohol.spirits). compliance.min_age is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **MAR-905-A** - proposed new line (food.ambient.cereals). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `xlsx`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
