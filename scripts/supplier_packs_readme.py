"""The page somebody reads before uploading any of the packs.

Kept out of the generator because it is prose about the generator's output
rather than part of producing it, and because the two things change for
different reasons: a new defect class changes the generator, a new reader
changes this.

Two of the sections are the important ones and neither is about the data. The
replay clock and the media payload shape are both properties of the system the
bundles are sent to, both invisible until somebody uploads a file and reads a
verdict that seems wrong, and both cheap to explain once. A data set that
produced a confusing result and said nothing about why would waste more time
than it saved.
"""

from __future__ import annotations

from pathlib import Path

BANDS = ("CLEARS", "MACHINE_CORRECTABLE", "SMALL_GAP_CORROBORATED",
         "NEEDS_A_PERSON")

#: Measured by running the same 28 bundles twice through the real intake, once
#: as the code stands and once with the list in ``intake._bundle_events``
#: unwrapped into one ``_media_row`` call per image. Nothing else differed.
MEDIA_MEASURED = (
    ("as the code stands", 134, 86, 61, 53),
    ("with the list unwrapped", 157, 63, 61, 0),
)

CURL = """```bash
curl -X POST localhost:8000/api/intake/product-feed \\
  -H 'content-type: application/json' \\
  -d "{\\"supplier\\":\\"SUP-15\\",\\"system_id\\":\\"supplier-portal\\",\\
\\"filename\\":\\"sup15.zip\\",\\"content_base64\\":\\"$(base64 -w0 FILE.zip)\\"}"
```"""

LAYOUT = """```
SUP-NN_<supplier>.zip         <- upload this
SUP-NN_<supplier>/            <- the same contents, unpacked, to read
    <branch>.csv|.txt|.xlsx       the feed - exactly one data file
    images/                       the photographs the rows name
    docs/                         covering note, spec sheet, price list
    EXPECTED.md                   the answer key. NOT inside the .zip
MANIFEST.csv / MANIFEST.json  every pack, with its band counts
```"""


def write(results: list[dict], out: Path) -> None:
    """Write ``README.md`` beside the packs."""
    total = {band: sum(e["bands"].get(band, 0) for e in results)
             for band in BANDS}
    rows = sum(e["rows"] for e in results)

    lines: list[str] = [
        "# Supplier packs",
        "",
        f"One uploadable bundle per supplier - {len(results)} of them, {rows} "
        f"rows in total - built",
        "so that every outcome the onboarding report can reach is reachable "
        "from real data",
        "rather than from a label.",
        "",
        "Generated. Rewritten wholesale by:",
        "",
        "```bash",
        "python scripts/generate_supplier_packs.py --verify",
        "```",
        "",
        "`--verify` submits every bundle through the real "
        "`intake.submit_product_feed` against",
        "a scratch database and prints what the report actually said. Nothing "
        "in this",
        "directory is a claim the generator has not graded itself on.",
        "",
        "## What is here",
        "",
        LAYOUT,
        "",
        "The archive holds **exactly one** data file at its root, because "
        "`read._data_member`",
        "refuses a bundle with two - and is right to, since picking one would "
        "be picking a",
        "supplier's catalogue for them. The price list therefore lives under "
        "`docs/`, where a",
        "person can open it and the parser will not look.",
        "",
        "## How to send one",
        "",
        "Through the vendor portal, or directly:",
        "",
        CURL,
        "",
        "## The four outcomes, and the lever each one uses",
        "",
        "| Outcome | Rows | What makes it happen |",
        "| ------- | ---: | -------------------- |",
        f"| Clears | {total['CLEARS']} | every attribute the category "
        f"declares, correctly typed, with the imagery the branch requires. "
        f"`readiness` finds nothing and the verdict is `READY_TO_LAUNCH` |",
        f"| A machine can correct it | {total['MACHINE_CORRECTABLE']} | a unit "
        f"typed into a numeric cell, a thousands separator, a decimal comma, "
        f"`N/A`, or a column belonging to another branch. `read._read_values` "
        f"rejects the **cell** by line and column and keeps the rest of the "
        f"row |",
        f"| A little is missing, something agrees | "
        f"{total['SMALL_GAP_CORROBORATED']} | a non-safety attribute left "
        f"blank while a sibling variant of the same product holds it - the "
        f"`SIBLING` prior in `onboarding.history` that `suggest` scores a "
        f"proposal from |",
        f"| A person has to look | {total['NEEDS_A_PERSON']} | "
        f"`compliance.sale_permitted = false`, a withdrawal notice: `BLOCKING`, "
        f"and `gate` stops onboarding on the authority of a regulation. Or a "
        f"blank safety-class attribute, which `fixable` refuses to make a "
        f"candidate at all. Or imagery the category cannot launch without |",
        "",
        "Only `int` and `float` cells can actually be refused by the parser. A "
        "`str` takes any",
        "text, a `bool` goes through `_truthy`, and a `list[str]` is *split* "
        "rather than",
        "validated - so a comma-separated cell arrives as one long item and is "
        "still a valid",
        "list. Numbers are therefore what the machine-correctable band is "
        "built on, and a",
        "branch that declares no numeric attribute at all (Clothing & "
        "Footwear) gets a column",
        "from another branch instead, reported per row as *does not apply*.",
        "",
        "## What is deliberately untidy",
        "",
        "- three file formats across the estate: `.csv`, pipe-delimited "
        "`.txt`, and `.xlsx`",
        "- two columns per file in a sending system's own vocabulary "
        "(`netContent`, `GTIN_14`, `ingredientStatement`, `ratedPowerWatts`, "
        "`countryOfOrigin`) - reported as unknown columns, never fatal",
        "- a spare column somebody added and nobody removed",
        "- one image named in the sheet that the archive does not hold",
        "- two images in the archive that no row names",
        "- trailing spaces, and `TRUE` / `Yes` / `Y` in one boolean column",
        "- proposed new lines whose SKUs are not in the catalog, held as "
        "drafts for a reviewer",
        "",
        "Every defect class is one of the closed set in `sc.estate.defects`. "
        "Damage nothing",
        "downstream can name would look the same whether the validator caught "
        "it or not, which",
        "is the argument that file already makes.",
        "",
        "## Two things to know before reading a verdict",
        "",
        "**1. The replay clock.** A submission is stamped with "
        "`tape.sim_now()` and does not",
        "move it, and every readiness read defaults to `sim_now()`. So a "
        "report opened at the",
        "same instant is read a microsecond *before* the bundle it is "
        "grading, and the bundle",
        "looks like it changed nothing. Let the replay advance one step after "
        "uploading.",
        "`--verify` models this: it lands the bundles with the clock short of "
        "the end of the",
        "tape and winds it on before grading.",
        "",
        "**2. Bundle imagery does not currently reach the record.** "
        "`intake._bundle_events`",
        "emits `\"media\": [{...}]`, a list, at `sc/estate/intake.py:951`. "
        "`ingest._media_row`",
        "returns early unless that payload is a dict "
        "(`sc/replay/ingest.py:211`). The",
        "single-image endpoint at `intake.py:669` sends a dict and works; the "
        "bundle path does",
        "not. The effect is the one `_media_for`'s own docstring says must not "
        "happen - a",
        "supplier uploads the missing ingredient panel and is still told, "
        "correctly formatted",
        "and in detail, that no ingredient panel is held.",
        "",
        "Measured over these bundles, with the list unwrapped into one "
        "`_media_row` call per",
        "image and nothing else changed:",
        "",
        "| | cleared | returned | blocked | `required_media` findings |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, cleared, returned, blocked, findings in MEDIA_MEASURED:
        lines.append(f"| {label} | {cleared} | {returned} | {blocked} | "
                     f"{findings} |")
    lines += [
        "",
        "Rows in the *a person has to look* band that name a **missing** "
        "photograph are",
        "labelled as such in each `EXPECTED.md` and read the same either way: "
        "the archive",
        "genuinely does not hold those files.",
        "",
        "## The packs",
        "",
        "| Supplier | Name | Branch | Format | Rows | Clears | Machine | Gap | "
        "Person |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in results:
        bands = entry["bands"]
        lines.append(
            f"| {entry['supplier']} | {entry['name']} | {entry['branch']} | "
            f"{entry['format']} | {entry['rows']} | "
            f"{bands.get('CLEARS', 0)} | {bands.get('MACHINE_CORRECTABLE', 0)} "
            f"| {bands.get('SMALL_GAP_CORROBORATED', 0)} | "
            f"{bands.get('NEEDS_A_PERSON', 0)} |")
    lines += [
        "",
        "Counts are of rows *written* into each band - existing lines and "
        "proposed new lines",
        "together. A proposed line is not assessed until a reviewer accepts "
        "it, so the report's",
        "own totals count fewer products than this table does. That is the "
        "undercount `assess`",
        "keeps `proposals` separate in order to avoid, rather than a "
        "disagreement.",
        "",
        "Two suppliers - SUP-03 and SUP-04 - own a single catalog line each, "
        "so their packs",
        "carry no withdrawal: blocking their only line would produce a report "
        "that cleared",
        "nothing, which says less about the gate than one blocked row among "
        "several does.",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
