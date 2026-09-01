# Supplier packs

One uploadable bundle per supplier - 28 of them, 525 rows in total - built
so that every outcome the onboarding report can reach is reachable from real data
rather than from a label.

Generated. Rewritten wholesale by:

```bash
python scripts/generate_supplier_packs.py --verify
```

`--verify` submits every bundle through the real `intake.submit_product_feed` against
a scratch database and prints what the report actually said. Nothing in this
directory is a claim the generator has not graded itself on.

## What is here

```
SUP-NN_<supplier>.zip         <- upload this
SUP-NN_<supplier>/            <- the same contents, unpacked, to read
    <branch>.csv|.txt|.xlsx       the feed - exactly one data file
    images/                       the photographs the rows name
    docs/                         covering note, spec sheet, price list
    EXPECTED.md                   the answer key. NOT inside the .zip
MANIFEST.csv / MANIFEST.json  every pack, with its band counts
```

The archive holds **exactly one** data file at its root, because `read._data_member`
refuses a bundle with two - and is right to, since picking one would be picking a
supplier's catalogue for them. The price list therefore lives under `docs/`, where a
person can open it and the parser will not look.

## How to send one

Through the vendor portal, or directly:

```bash
curl -X POST localhost:8000/api/intake/product-feed \
  -H 'content-type: application/json' \
  -d "{\"supplier\":\"SUP-15\",\"system_id\":\"supplier-portal\",\
\"filename\":\"sup15.zip\",\"content_base64\":\"$(base64 -w0 FILE.zip)\"}"
```

## The four outcomes, and the lever each one uses

| Outcome | Rows | What makes it happen |
| ------- | ---: | -------------------- |
| Clears | 260 | every attribute the category declares, correctly typed, with the imagery the branch requires. `readiness` finds nothing and the verdict is `READY_TO_LAUNCH` |
| A machine can correct it | 38 | a unit typed into a numeric cell, a thousands separator, a decimal comma, `N/A`, or a column belonging to another branch. `read._read_values` rejects the **cell** by line and column and keeps the rest of the row |
| A little is missing, something agrees | 110 | a non-safety attribute left blank while a sibling variant of the same product holds it - the `SIBLING` prior in `onboarding.history` that `suggest` scores a proposal from |
| A person has to look | 117 | `compliance.sale_permitted = false`, a withdrawal notice: `BLOCKING`, and `gate` stops onboarding on the authority of a regulation. Or a blank safety-class attribute, which `fixable` refuses to make a candidate at all. Or imagery the category cannot launch without |

Only `int` and `float` cells can actually be refused by the parser. A `str` takes any
text, a `bool` goes through `_truthy`, and a `list[str]` is *split* rather than
validated - so a comma-separated cell arrives as one long item and is still a valid
list. Numbers are therefore what the machine-correctable band is built on, and a
branch that declares no numeric attribute at all (Clothing & Footwear) gets a column
from another branch instead, reported per row as *does not apply*.

## What is deliberately untidy

- three file formats across the estate: `.csv`, pipe-delimited `.txt`, and `.xlsx`
- two columns per file in a sending system's own vocabulary (`netContent`, `GTIN_14`, `ingredientStatement`, `ratedPowerWatts`, `countryOfOrigin`) - reported as unknown columns, never fatal
- a spare column somebody added and nobody removed
- one image named in the sheet that the archive does not hold
- two images in the archive that no row names
- trailing spaces, and `TRUE` / `Yes` / `Y` in one boolean column
- proposed new lines whose SKUs are not in the catalog, held as drafts for a reviewer

Every defect class is one of the closed set in `sc.estate.defects`. Damage nothing
downstream can name would look the same whether the validator caught it or not, which
is the argument that file already makes.

## Two things to know before reading a verdict

**1. The replay clock.** A submission is stamped with `tape.sim_now()` and does not
move it, and every readiness read defaults to `sim_now()`. So a report opened at the
same instant is read a microsecond *before* the bundle it is grading, and the bundle
looks like it changed nothing. Let the replay advance one step after uploading.
`--verify` models this: it lands the bundles with the clock short of the end of the
tape and winds it on before grading.

**2. Bundle imagery does not currently reach the record.** `intake._bundle_events`
emits `"media": [{...}]`, a list, at `sc/estate/intake.py:951`. `ingest._media_row`
returns early unless that payload is a dict (`sc/replay/ingest.py:211`). The
single-image endpoint at `intake.py:669` sends a dict and works; the bundle path does
not. The effect is the one `_media_for`'s own docstring says must not happen - a
supplier uploads the missing ingredient panel and is still told, correctly formatted
and in detail, that no ingredient panel is held.

Measured over these bundles, with the list unwrapped into one `_media_row` call per
image and nothing else changed:

| | cleared | returned | blocked | `required_media` findings |
| --- | ---: | ---: | ---: | ---: |
| as the code stands | 134 | 86 | 61 | 53 |
| with the list unwrapped | 157 | 63 | 61 | 0 |

Rows in the *a person has to look* band that name a **missing** photograph are
labelled as such in each `EXPECTED.md` and read the same either way: the archive
genuinely does not hold those files.

## The packs

| Supplier | Name | Branch | Format | Rows | Clears | Machine | Gap | Person |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| SUP-01 | Northaven Home | home | csv | 12 | 6 | 0 | 2 | 4 |
| SUP-02 | Harrowfield Foods | food | csv | 13 | 7 | 0 | 2 | 4 |
| SUP-03 | Calverton Electronics | electronics | csv | 11 | 7 | 0 | 2 | 2 |
| SUP-04 | Stonebridge Housewares | home | txt | 10 | 6 | 0 | 2 | 2 |
| SUP-11 | Bramblewood Bakery Ltd | food | xlsx | 15 | 7 | 2 | 2 | 4 |
| SUP-12 | Copperfield Provisions | food | csv | 15 | 8 | 1 | 2 | 4 |
| SUP-13 | Silverbrook Chilled Foods | food | csv | 10 | 5 | 0 | 2 | 3 |
| SUP-14 | Longmeadow Dairies | food | csv | 16 | 7 | 2 | 3 | 4 |
| SUP-15 | Tessington Beverage Co. | food | txt | 26 | 15 | 2 | 4 | 5 |
| SUP-16 | Marlowe & Fenn Wine Merchants | food | xlsx | 12 | 6 | 1 | 2 | 3 |
| SUP-17 | Northgate Appliance Co. | home | csv | 22 | 10 | 2 | 4 | 6 |
| SUP-18 | Harrow & Vale Kitchenware | home | csv | 19 | 8 | 2 | 5 | 4 |
| SUP-19 | Kestrel Small Domestics | home | csv | 25 | 14 | 2 | 5 | 4 |
| SUP-20 | Wrenfield Home Textiles | apparel | txt | 22 | 10 | 0 | 8 | 4 |
| SUP-21 | Calderstone Garments | apparel | xlsx | 13 | 7 | 0 | 3 | 3 |
| SUP-22 | Pemberton Knitwear | apparel | csv | 13 | 6 | 0 | 4 | 3 |
| SUP-23 | Ashfleet Footwear | apparel | csv | 27 | 13 | 0 | 10 | 4 |
| SUP-24 | Lumen Audio Works | electronics | csv | 23 | 12 | 2 | 5 | 4 |
| SUP-25 | Verrick Display Technologies | electronics | txt | 20 | 9 | 2 | 5 | 4 |
| SUP-26 | Quillon Mobile Accessories | electronics | xlsx | 17 | 9 | 2 | 3 | 3 |
| SUP-27 | Petrichor Household Products | hpc | csv | 26 | 15 | 2 | 4 | 5 |
| SUP-28 | Saltmarsh Personal Care | hpc | csv | 25 | 12 | 3 | 5 | 5 |
| SUP-29 | Hollowbrook Nutrition | baby | csv | 22 | 5 | 5 | 8 | 4 |
| SUP-30 | Larkspur Baby Products | baby | txt | 19 | 8 | 2 | 3 | 6 |
| SUP-31 | Thorneley Pharmaceuticals | health | xlsx | 20 | 11 | 2 | 2 | 5 |
| SUP-32 | Ravensmoor Health Devices | health | csv | 20 | 7 | 2 | 2 | 9 |
| SUP-33 | Draycott Toys & Leisure | general | csv | 19 | 11 | 0 | 4 | 4 |
| SUP-34 | Fenwold Garden & Outdoor | general | csv | 33 | 19 | 2 | 7 | 5 |

Counts are of rows *written* into each band - existing lines and proposed new lines
together. A proposed line is not assessed until a reviewer accepts it, so the report's
own totals count fewer products than this table does. That is the undercount `assess`
keeps `proposals` separate in order to avoid, rather than a disagreement.

Two suppliers - SUP-03 and SUP-04 - own a single catalog line each, so their packs
carry no withdrawal: blocking their only line would produce a report that cleared
nothing, which says less about the gate than one blocked row among several does.
