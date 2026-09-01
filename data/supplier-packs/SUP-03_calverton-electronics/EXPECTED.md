# SUP-03 - Calverton Electronics

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (7)

- **CAL-BT200** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **CAL-901-A** - proposed new line (electronics.audio.earbuds). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-901-B** - proposed new line (electronics.audio.earbuds). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-902-B** - proposed new line (electronics.audio.headphones). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-903-B** - proposed new line (electronics.audio.soundbars). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-904-A** - proposed new line (electronics.audio.speakers). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **CAL-905-B** - proposed new line (electronics.computing.laptops). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (2)

- **CAL-902-A** - proposed new line (electronics.audio.headphones). origin.country is blank on a proposed line; the catalog's other lines in electronics.audio.headphones are what a proposal would be scored against
- **CAL-906-A** - proposed new line (electronics.computing.tablets). claims is blank on a proposed line; the catalog's other lines in electronics.computing.tablets are what a proposal would be scored against

## A person has to look (2)

- **CAL-903-A** - proposed new line (electronics.audio.soundbars). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **CAL-905-A** - proposed new line (electronics.computing.laptops). the sheet names a hero image the archive does not hold; electronics cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.noise_db` is carried on the first two rows with the value `62`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
