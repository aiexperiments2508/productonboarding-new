# SUP-14 - Longmeadow Dairies

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (7)

- **FOO-176-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-200-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-200-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **LON-901-A** - proposed new line (food.bakery.bread). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LON-901-B** - proposed new line (food.bakery.bread). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LON-904-A** - proposed new line (food.dairy.milk). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **LON-906-B** - proposed new line (food.alcohol.beer). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **FOO-144-A** - packaging.recyclable_pct arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **FOO-144-B** - food.fibre_g arrives as '5,3' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (3)

- **FOO-168-A** - packaging.recyclable_pct is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **LON-902-A** - proposed new line (food.bakery.cakes). pack.net_quantity is blank on a proposed line; the catalog's other lines in food.bakery.cakes are what a proposal would be scored against
- **LON-906-A** - proposed new line (food.alcohol.beer). claims is blank on a proposed line; the catalog's other lines in food.alcohol.beer are what a proposal would be scored against

## A person has to look (4)

- **FOO-219-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **FOO-219-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **LON-903-A** - proposed new line (food.dairy.cheese). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **LON-905-A** - proposed new line (food.dairy.yoghurt). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
