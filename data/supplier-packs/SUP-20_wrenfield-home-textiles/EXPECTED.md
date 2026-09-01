# SUP-20 - Wrenfield Home Textiles

What each row in this bundle is here to do. This file is **not**
inside the .zip: it is the answer key, not part of the submission.

## Clears on arrival (10)

- **APP-117-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **APP-117-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **APP-133-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **APP-149-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **APP-149-B** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **APP-173-A** - every attribute the category declares is supplied and typed correctly, with the imagery the branch requires
- **WRE-901-A** - proposed new line (apparel.accessories.bags). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **WRE-904-A** - proposed new line (apparel.mens.knitwear). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **WRE-904-B** - proposed new line (apparel.mens.knitwear). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival
- **WRE-906-B** - proposed new line (apparel.womens.denim). a new line with everything the category declares; a reviewer accepts it and it is complete on arrival

## A little is missing, something agrees (8)

- **APP-133-A** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **APP-173-B** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **APP-217-B** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **APP-229-A** - textile.care_code is blank; a sibling variant of the same product holds it, which is the SIBLING prior a proposal is scored from
- **APP-242-A** - textile.care_code is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **APP-244-A** - textile.care_code is blank; nothing on file corroborates it, so it goes to the supplier rather than to a proposal
- **WRE-902-A** - proposed new line (apparel.footwear.trainers). origin.country is blank on a proposed line; the catalog's other lines in apparel.footwear.trainers are what a proposal would be scored against
- **WRE-906-A** - proposed new line (apparel.womens.denim). textile.fibre_composition is blank on a proposed line; the catalog's other lines in apparel.womens.denim are what a proposal would be scored against

## A person has to look (4)

- **APP-217-A** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **APP-229-B** - compliance.sale_permitted is false - a withdrawal notice. checks.sale_permitted raises it BLOCKING and gate stops onboarding on the authority of a regulation
- **WRE-903-A** - proposed new line (apparel.kids.sleepwear). compliance.sale_permitted is a safety-class declaration and is blank. fixable.assess refuses to make it a candidate at all - only the supplier can answer it
- **WRE-905-A** - proposed new line (apparel.mens.shirts). the sheet names a detail image the archive does not hold; apparel cannot launch without it and no value fixes a missing photograph

## A column from another branch

- `specs.power_w` is carried on the first two rows with the value `1400`. The parser knows the column and the category does not take it, so each is reported by line and column as *does not apply*. This is the machine-correctable defect for a branch that declares no numeric attribute to mistype.

## Columns in a sending system's vocabulary

- `GTIN_14` carries `identifiers.gtin`. Reported as an unknown column; the bundle is not refused over it.
- `countryOfOrigin` carries `origin.country`. Reported as an unknown column; the bundle is not refused over it.

## Also in this file

- format: `txt`
- a spare column (`internal_ref`) nobody removed
- two images in `images/` that no row names
- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column
