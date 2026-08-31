"""The two flat formats: comma-separated, and pipe-delimited for older systems.

Both carry the same three header rows, because the contract is in the header
and a supplier who opens the pipe file must not get a narrower document than
one who opens the CSV.

Row 1 is the machine name and is the only row the parser reads. Rows 2 and 3
are for the person filling it in - the label with its unit, then one sentence
saying whether the column is required, by whom, and what will go wrong. A
parser that read row 2 would break the moment somebody translated a label, so
it does not.

Written with the standard library. A dependency to join strings with commas
would be a dependency to regret.
"""

from __future__ import annotations

import csv
import io

from sc.datapack.sample import NOTE_COLUMN, Example
from sc.datapack.schema import Sheet

#: What the pipe-delimited variant separates cells with. Space-padded so a
#: human reading it in a terminal can see the columns, and stripped on the way
#: back in.
PIPE = " | "


def header_rows(sheet: Sheet, *, with_note: bool) -> list[list[str]]:
    """The three rows above the data, in every flat format."""
    columns = list(sheet.columns)
    names = [c.name for c in columns]
    labels = [c.heading for c in columns]
    markers = [c.marker() for c in columns]
    if with_note:
        names.append(NOTE_COLUMN)
        labels.append("What this row demonstrates")
        markers.append("ignored on the way in; delete the column or leave it")
    return [names, labels, markers]


def _matrix(sheet: Sheet, example: Example | None) -> list[list[str]]:
    with_note = example is not None and bool(example.rows)
    rows = header_rows(sheet, with_note=with_note)
    for row in (example.rows if example else []):
        line = [row.get(c.name, "") for c in sheet.columns]
        line.append(row.get(NOTE_COLUMN, ""))
        rows.append(line)
    return rows


def write_csv(sheet: Sheet, example: Example | None = None) -> str:
    """One branch as CSV. Excel's dialect, so Excel opens it without a wizard."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerows(_matrix(sheet, example))
    return buffer.getvalue()


def write_txt(sheet: Sheet, example: Example | None = None) -> str:
    """One branch as a pipe-delimited flat file.

    For a supplier whose system predates the idea of quoting a comma. Cells are
    stripped of the delimiter rather than escaped, because an escape convention
    is the thing those systems get wrong.
    """
    lines = []
    for row in _matrix(sheet, example):
        lines.append(PIPE.join(str(cell).replace("|", "/") for cell in row))
    return "\r\n".join(lines) + "\r\n"


def read_rows(text: str, *, delimiter: str = ",") -> list[dict[str, str]]:
    """A flat file back into rows, keyed by the machine names in row 1.

    The two label rows are skipped by position rather than by inspection: a
    supplier who deletes them has still sent a valid file, and one who leaves
    them has not sent two products called "Product name". Skipping is decided
    by whether row 2 looks like a data row, which is what the ``sku`` column
    tells us - a label row's ``sku`` cell reads "SKU".
    """
    if delimiter == "|":
        raw = [[cell.strip() for cell in line.split("|")]
               for line in text.splitlines() if line.strip()]
    else:
        raw = [row for row in csv.reader(io.StringIO(text)) if any(
            cell.strip() for cell in row)]
    if not raw:
        return []

    names = [cell.strip() for cell in raw[0]]
    body = raw[1:]
    # Drop the two annotation rows if they are still there. They are identified
    # by matching the header block this module writes, never by their position
    # alone, so a file that never had them loses nothing.
    while body and _looks_annotated(names, body[0]):
        body.pop(0)

    rows = []
    for line in body:
        padded = list(line) + [""] * (len(names) - len(line))
        rows.append({name: padded[index].strip()
                     for index, name in enumerate(names) if name})
    return rows


def _looks_annotated(names: list[str], row: list[str]) -> bool:
    """Is this one of the two rows written for a person rather than a parser?"""
    if not row:
        return False
    cells = {cell.strip().lower() for cell in row if cell.strip()}
    if not cells:
        return False
    # Row two repeats the labels; row three always contains the word the marker
    # is built from. Both are things no product row would say in every cell.
    markers = ("required", "optional", "safety - a person reviews any change")
    if any(cell.startswith(markers) for cell in cells):
        return True
    lowered = [n.lower() for n in names]
    if "sku" in lowered:
        # Exactly the label, never merely blank. A row with no SKU is a row to
        # refuse by name, and dropping it here would report a bundle of
        # thirty-nine as complete when the supplier sent forty.
        return row[lowered.index("sku")].strip().lower() == "sku"
    return False
