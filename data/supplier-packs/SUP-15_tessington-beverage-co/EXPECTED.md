# SUP-15 - Tessington Beverage Co.

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (15)

- **FOO-120-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-136-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-136-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-136-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-160-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-160-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-184-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-184-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-207-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-207-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FOO-235-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **TES-901-A** - proposed new line (food.bakery.biscuits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **TES-901-B** - proposed new line (food.bakery.biscuits). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **TES-904-A** - proposed new line (food.chilled.ready-meals). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **TES-905-B** - proposed new line (food.dairy.cheese). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **FOO-104-A** - food.net_weight_g arrives as '272 g' - the unit is in the cell (g). The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell
- **FOO-120-B** - food.fibre_g arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The record has no value for this attribute either, so the correction closes a readiness gap as well as a cell

## A little is missing, something agrees (4)

- **FOO-184-B** - food.net_weight_g is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **FOO-207-B** - food.net_weight_g is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **TES-902-A** - proposed new line (food.bakery.bread). food.fibre_g is blank on a proposed line; the catalog's other lines in food.bakery.bread are what a proposal would be scored against
- **TES-906-A** - proposed new line (food.dairy.milk). food.ingredients is blank on a proposed line; the catalog's other lines in food.dairy.milk are what a proposal would be scored against

## A person has to look (5)

- **FOO-225-A** - the record holds no ingredient_panel image and food cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **FOO-235-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **FOO-235-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **TES-903-A** - proposed new line (food.bakery.cakes). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **TES-905-A** - proposed new line (food.dairy.cheese). the sheet names a ingredient_panel image the archive does not hold; food cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `txt`
- a spare column (`Supplier Notes`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
