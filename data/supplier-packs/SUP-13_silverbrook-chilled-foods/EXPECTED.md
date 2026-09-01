# SUP-13 - Silverbrook Chilled Foods

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (5)

- **FOO-192-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **SIL-901-A** - proposed new line (food.dairy.cheese). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SIL-901-B** - proposed new line (food.dairy.cheese). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SIL-902-B** - proposed new line (food.dairy.milk). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **SIL-904-A** - proposed new line (food.alcohol.spirits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (2)

- **SIL-902-A** - proposed new line (food.dairy.milk). pack.unit is blank on a proposed line; the catalog's other lines in food.dairy.milk are what a proposal would be scored against
- **SIL-906-A** - proposed new line (food.ambient.cereals). claims is blank on a proposed line; the catalog's other lines in food.ambient.cereals are what a proposal would be scored against

## A person has to look (3)

- **FOO-213-A** - the record holds no ingredient_panel image and food cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **SIL-903-A** - proposed new line (food.alcohol.beer). compliance.min_age is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **SIL-905-A** - proposed new line (food.alcohol.wine). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`internal_ref`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
