"""Write the supplier data pack.

    python scripts/build_datapack.py [--out data/datapack] [--branch food]

Reads the catalog the seed pack produced and writes, for every branch the
retailer trades, a blank template and a worked example in each flat format,
plus one workbook, one Word specification and one JSON Schema covering all of
them. Also writes a sample bundle - a .zip of the kind a supplier sends back -
so the intake has something real to be pointed at.

Reproducible: same catalog and same ``DATA_SEED``, same bytes. Run it after
``generate_data.py`` and before serving, exactly as the index build is run.

Everything except the workbook needs nothing installed. Without ``openpyxl``
the workbook is skipped and the run says so and still succeeds, because a pack
missing one of five formats is more useful than no pack.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sc import bootstrap  # noqa: E402
from sc.datapack import formats, schema  # noqa: E402
from sc.datapack import sample as sample_mod  # noqa: E402
from sc.datapack.writers import csv_txt, jsonschema, specdoc, workbook  # noqa: E402


def _write(path: Path, payload: str | bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        # utf-8-sig: Excel opens a plain UTF-8 CSV as Windows-1252 and turns
        # every m² and µg into mojibake, silently, in the one column where a
        # unit matters.
        path.write_text(payload, encoding="utf-8-sig", newline="")
    else:
        path.write_bytes(payload)
    return path.stat().st_size


def baseline_data_dir() -> Path:
    from sc.state import baseline as baseline_mod

    return Path(baseline_mod.data_dir())


def _sample_bundle(out: Path, sheet, example, base) -> Path:
    """A .zip of the shape a supplier sends back: one data file, one images/."""
    path = out / "bundles" / f"{sheet.branch}-sample-bundle.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    media_dir = baseline_data_dir() / "media"

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(f"{sheet.branch}.csv", date_time=(1980, 1, 1, 0, 0, 0))
        archive.writestr(info, csv_txt.write_csv(sheet, example).encode("utf-8-sig"))
        for filename, uri in sorted(example.images.items()):
            source = media_dir / Path(uri).name
            if not source.exists():
                continue
            member = zipfile.ZipInfo(f"images/{filename}",
                                     date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(member, source.read_bytes())
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/datapack",
                        help="where to write, relative to the repository root")
    parser.add_argument("--branch", default="",
                        help="one branch only; default is every branch")
    args = parser.parse_args()

    bootstrap.load_env()
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    pack = schema.build(base)
    if args.branch:
        pack.sheets = [s for s in pack.sheets if s.branch == args.branch]
        if not pack.sheets:
            print(f"  no branch called {args.branch!r}")
            return 1

    out = ROOT / args.out
    print(f"\n  {pack.fascia} supplier data pack")
    print(f"  {'-' * (len(pack.fascia) + 25)}")
    print(f"  {len(pack.sheets)} branches -> {out}\n")

    written = 0
    examples: dict[str, sample_mod.Example] = {}
    for sheet in pack.sheets:
        example = sample_mod.build(sheet, base)
        examples[sheet.branch] = example
        attrs = sum(1 for c in sheet.columns if c.kind == "attribute")

        _write(out / "templates" / f"{sheet.branch}.csv",
               csv_txt.write_csv(sheet))
        _write(out / "templates" / f"{sheet.branch}.txt",
               csv_txt.write_txt(sheet))
        _write(out / "examples" / f"{sheet.branch}-example.csv",
               csv_txt.write_csv(sheet, example))
        _write(out / "examples" / f"{sheet.branch}-example.txt",
               csv_txt.write_txt(sheet, example))
        bundle = _sample_bundle(out, sheet, example, base)
        written += 5

        shown = sum(1 for r in example.rows if r.get(sample_mod.NOTE_COLUMN))
        print(f"    {sheet.label:28} {len(sheet.leaves):3} categories  "
              f"{attrs:2} attributes  {len(example.rows):2} example rows "
              f"({shown} broken)  bundle {bundle.stat().st_size // 1024} KB")
        if example.unshown:
            for defect in sorted(example.unshown):
                print(f"      {'':26} no column to demonstrate {defect}")

    size = _write(out / "supplier-feed.schema.json",
                  json.dumps(jsonschema.write(pack), indent=2) + "\n")
    print(f"\n    supplier-feed.schema.json    {size // 1024} KB")

    size = _write(out / "supplier-specification.docx", specdoc.write(pack))
    print(f"    supplier-specification.docx  {size // 1024} KB")
    written += 2

    if workbook.available():
        size = _write(out / "supplier-feed.xlsx", workbook.write(pack, examples))
        print(f"    supplier-feed.xlsx           {size // 1024} KB")
        written += 1
    else:
        print(f"    supplier-feed.xlsx           skipped: "
              f"{formats()['xlsx']['why']}")

    print(f"\n  {written} files.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
