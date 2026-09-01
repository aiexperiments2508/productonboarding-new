# SUP-33 - Draycott Toys & Leisure

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (11)

- **GEN-105-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-113-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-113-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-145-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-153-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-161-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **GEN-208-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **DRA-901-A** - proposed new line (general.diy.handtools). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **DRA-903-B** - proposed new line (general.garden.tools). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **DRA-904-A** - proposed new line (general.stationery.paper). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **DRA-906-B** - proposed new line (general.diy.paint). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (4)

- **GEN-105-A** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **GEN-208-B** - compliance.certificate_ref is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **DRA-902-A** - proposed new line (general.garden.bbq). origin.country is blank on a proposed line; the catalog's other lines in general.garden.bbq are what a proposal would be scored against
- **DRA-906-A** - proposed new line (general.diy.paint). origin.country is blank on a proposed line; the catalog's other lines in general.diy.paint are what a proposal would be scored against

## A person has to look (4)

- **GEN-231-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **GEN-231-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **DRA-903-A** - proposed new line (general.garden.tools). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **DRA-905-A** - proposed new line (general.toys.games). the sheet names a hero image the archive does not hold; general cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `netContent` carries `pack.net_quantity`. Reported as an unknown column; the bundle is not refused over it.
- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `csv`
- a spare column (`Case Qty`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
