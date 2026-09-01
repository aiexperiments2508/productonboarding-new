# SUP-34 - Fenwold Garden & Outdoor

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (19)

- **GEN-129-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-137-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-137-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-137-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-169-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-177-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-185-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-185-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-185-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-193-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-193-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-193-C** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-214-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-220-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-226-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **FEN-901-A** - proposed new line (general.diy.handtools). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **FEN-904-A** - proposed new line (general.pet.accessories). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **FEN-904-B** - proposed new line (general.pet.accessories). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **FEN-905-B** - proposed new line (general.pet.dogfood). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A machine can correct it (2)

- **GEN-214-A** - pack.net_quantity arrives as 'N/A' - a placeholder where a number goes. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record
- **GEN-169-B** - pack.net_quantity arrives as '40,0' - a decimal comma from a European locale. The cell is rejected by line and column and the rest of the row lands. The catalog already holds a good value here, so the correction is to the file rather than to the record

## A little is missing, something agrees (7)

- **GEN-121-A** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **GEN-121-B** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **GEN-121-C** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **GEN-201-A** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **GEN-201-B** - compliance.certificate_ref is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **FEN-902-A** - proposed new line (general.diy.paint). identifiers.gtin is blank on a proposed line; the catalog's other lines in general.diy.paint are what a proposal would be scored against
- **FEN-906-A** - proposed new line (general.stationery.paper). identifiers.gtin is blank on a proposed line; the catalog's other lines in general.stationery.paper are what a proposal would be scored against

## A person has to look (5)

- **GEN-169-A** - the record holds no hero image and general cannot launch without one. The bundle carries the file; see the note on the portal's media path in the pack README before reading the verdict
- **GEN-226-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **GEN-226-C** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **FEN-903-A** - proposed new line (general.garden.tools). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **FEN-905-A** - proposed new line (general.pet.dogfood). the sheet names a hero image the archive does not hold; general cannot launch without it and no value fixes a missing photograph

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Buyer`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
