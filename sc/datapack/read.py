"""Reading a bundle a supplier sent back.

A bundle is one .zip: exactly one data file at the root, and an optional
``images/`` folder. The data file is a CSV, a pipe-delimited flat file, or the
workbook - the three things the pack hands out - and the columns it is read
against are the ones ``sc.datapack.schema`` derived, never a second list.

Everything is parsed and judged **before** anything is appended. A bundle that
half-lands is worse than one refused, because the half that landed is invisible
until somebody counts.

**Three refusal scales, deliberately different.** A malformed archive refuses
the bundle. A column nobody recognises is reported and the bundle continues - a
supplier who added a "Notes" column has not made an unsafe submission, and
refusing two hundred good rows over one spare column is how a portal stops
being used. A row that cannot be resolved is rejected by line number, named,
and the rest still land.

**A row is not a fact.** This module returns what the file said. Whether any of
it becomes a value in the catalog is decided by the platform's own ingestion,
under the same precedence policy as everything else - see ``sc.estate.intake``.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sc.datapack.sample import NOTE_COLUMN
from sc.datapack.schema import LIST_SEPARATOR, columns_for
from sc.datapack.writers import csv_txt

#: The decoded archive. Twelve photographs and a spreadsheet, with room.
MAX_BUNDLE_BYTES = 24 * 1024 * 1024

#: What the members *declare* they inflate to, checked before anything is
#: inflated. A zip that says it holds ninety megabytes is refused on its own
#: word rather than on the memory it would take to disprove it.
MAX_BUNDLE_UNCOMPRESSED_BYTES = 96 * 1024 * 1024

MAX_BUNDLE_MEMBERS = 400

#: One supplier's onboarding batch. Above this it is an integration, and an
#: integration is what the PIM and the data pool endpoints are for.
MAX_BUNDLE_ROWS = 200

#: Per photograph. Deliberately still the single-upload limit: two megabytes is
#: the right size for one image and arriving inside an archive does not make it
#: a different image.
MAX_IMAGE_BYTES = 2 * 1024 * 1024

DATA_SUFFIXES = (".csv", ".txt", ".xlsx")
IMAGE_DIR = "images"

#: Columns the pack itself emits that are for the reader rather than the
#: parser. Reported as ignored rather than unknown, so the loud case stays loud.
ECHO_COLUMNS = frozenset({"product_name", "variant_name", NOTE_COLUMN})


@dataclass
class Row:
    """One line of the data file, resolved as far as it can be."""

    line: int
    sku: str
    product_ref: str = ""
    product_name: str = ""
    variant_name: str = ""
    category: str = ""
    is_base: bool = False
    #: Resolved catalog variant, when this SKU is one the supplier already owns.
    entity_id: str = ""
    values: dict[str, object] = field(default_factory=dict)
    #: MediaRole -> the file name the row named.
    images: dict[str, str] = field(default_factory=dict)
    #: True when no catalog variant carries this SKU: a proposed new line.
    draft: bool = False


@dataclass
class Rejection:
    line: int
    sku: str
    column: str
    why: str

    def as_dict(self) -> dict:
        return {"line": self.line, "sku": self.sku, "column": self.column,
                "why": self.why}


@dataclass
class Bundle:
    """What the archive turned out to contain."""

    filename: str = ""
    rows: list[Row] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    read: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)
    #: File name -> bytes, only for images some row actually named.
    images: dict[str, bytes] = field(default_factory=dict)
    #: Images in the archive that no row named.
    unreferenced: list[str] = field(default_factory=list)
    #: (line, role, filename) a row named and the archive did not hold.
    missing_images: list[tuple[int, str, str]] = field(default_factory=list)
    #: Set when the whole bundle is refused. Everything else is then empty.
    refusal: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return not self.refusal

    def summary(self) -> dict:
        """The counts, with rows and cells kept apart.

        "Three rejected" reads as three lost products, and three lost *cells*
        on rows that otherwise landed is a different and much smaller thing.
        Two numbers, because they are two facts.
        """
        landed = {r.line for r in self.rows}
        return {
            "read": self.read,
            "accepted": len(self.rows),
            "rejected_rows": len([r for r in self.rejected
                                  if r.line not in landed and r.line]),
            "rejected_cells": len([r for r in self.rejected
                                   if r.line in landed]),
            "rejected": [r.as_dict() for r in self.rejected],
            "unknown_columns": self.unknown_columns,
            "ignored_columns": self.ignored_columns,
            "drafts": sum(1 for r in self.rows if r.draft),
        }

    def image_summary(self) -> dict:
        return {
            "matched": len(self.images),
            "unreferenced": self.unreferenced,
            "missing": [{"line": line, "role": role, "filename": name}
                        for line, role, name in self.missing_images],
        }


def _refuse(reason: str, **detail) -> Bundle:
    return Bundle(refusal=reason, detail=detail)


def _unsafe(name: str) -> bool:
    """Would extracting this member escape the directory it belongs in?

    Nothing here extracts, so this is belt and braces - but the member name is
    also used to build a stored file name, and a name that walks out of the
    inbox would walk into the catalog's own media directory, where the
    generator would then overwrite it and nobody would ever know it had been
    there.
    """
    if not name or name.startswith("/") or name.startswith("\\"):
        return True
    if "\\" in name or ".." in PurePosixPath(name).parts:
        return True
    return len(name) > 2 and name[1] == ":"


def open_bundle(raw: bytes) -> tuple[zipfile.ZipFile | None, Bundle | None]:
    """The archive, or the reason it is not one."""
    if len(raw) > MAX_BUNDLE_BYTES:
        return None, _refuse(
            f"the bundle is {len(raw)} bytes; this endpoint accepts up to "
            f"{MAX_BUNDLE_BYTES}", bytes=len(raw), limit=MAX_BUNDLE_BYTES)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None, _refuse("the attachment is not a zip archive")

    members = [i for i in archive.infolist() if not i.is_dir()]
    if len(members) > MAX_BUNDLE_MEMBERS:
        return None, _refuse(
            f"the bundle holds {len(members)} files; this endpoint accepts up "
            f"to {MAX_BUNDLE_MEMBERS}")

    for info in members:
        if _unsafe(info.filename):
            return None, _refuse(
                f"the bundle contains a file path that leaves the archive: "
                f"{info.filename!r}")

    declared = sum(i.file_size for i in members)
    if declared > MAX_BUNDLE_UNCOMPRESSED_BYTES:
        # Checked against what the directory declares, before inflating
        # anything. A bundle that says it holds ninety megabytes is refused on
        # its own word.
        return None, _refuse(
            f"the bundle declares {declared} bytes uncompressed; this endpoint "
            f"accepts up to {MAX_BUNDLE_UNCOMPRESSED_BYTES}")
    return archive, None


def _data_member(archive: zipfile.ZipFile) -> tuple[str, Bundle | None]:
    """The one data file at the root, or the reason there is not one."""
    roots = [i.filename for i in archive.infolist()
             if not i.is_dir()
             and "/" not in i.filename.strip("/")
             and i.filename.lower().endswith(DATA_SUFFIXES)
             and not PurePosixPath(i.filename).name.startswith(("~", "."))]
    if not roots:
        return "", _refuse(
            "the bundle has no data file at its root. Send one .csv, .txt or "
            ".xlsx beside the images/ folder")
    if len(roots) > 1:
        # Named, never guessed. Picking one would be picking a supplier's
        # catalogue for them.
        return "", _refuse(
            f"the bundle has {len(roots)} data files at its root and only one "
            f"is read: {', '.join(sorted(roots))}")
    return roots[0], None


def _rows_from_xlsx(raw: bytes) -> tuple[list[dict[str, str]], str]:
    try:
        import openpyxl
    except ImportError:
        return [], ("this installation cannot read .xlsx - openpyxl is not "
                    "installed. Send the same data as .csv, which is read with "
                    "the standard library and always works")
    book = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    rows: list[dict[str, str]] = []
    for sheet in book.worksheets:
        if sheet.sheet_state != "visible":
            continue
        matrix = [["" if c is None else str(c).strip() for c in row]
                  for row in sheet.iter_rows(values_only=True)]
        matrix = [r for r in matrix if any(r)]
        if len(matrix) < 2:
            continue
        names = matrix[0]
        if "sku" not in [n.lower() for n in names]:
            continue
        body = matrix[1:]
        while body and csv_txt._looks_annotated(names, body[0]):
            body.pop(0)
        for line in body:
            padded = list(line) + [""] * (len(names) - len(line))
            rows.append({name: padded[i] for i, name in enumerate(names) if name})
    return rows, ""


def parse_rows(name: str, raw: bytes) -> tuple[list[dict[str, str]], str]:
    """The data file as raw string rows, keyed by the machine names in row 1."""
    lower = name.lower()
    if lower.endswith(".xlsx"):
        return _rows_from_xlsx(raw)
    # utf-8-sig strips the byte-order mark Excel writes and leaves a file
    # without one untouched, so the first column name is `product_ref` rather
    # than `﻿product_ref` - which would otherwise be an unknown column and
    # every row would be missing its product reference.
    text = raw.decode("utf-8-sig", errors="replace")
    delimiter = "|" if lower.endswith(".txt") else ","
    return csv_txt.read_rows(text, delimiter=delimiter), ""


def _known_columns(base) -> set[str]:
    """Every column any branch's template could carry."""
    from sc.datapack.schema import IDENTITY, branches_of

    known = {name for name, _label, _note in IDENTITY} | set(ECHO_COLUMNS)
    for branch in branches_of(base):
        known.update(c.name for c in columns_for(branch, base))
    return known


def _variant_by_sku(base) -> dict[str, str]:
    return {(v.sku or "").strip().lower(): v.id
            for v in base.variants.values() if (v.sku or "").strip()}


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "yes", "y", "1", "t")


def read(raw: bytes, *, supplier: str, base,
         accepts_images: bool = True) -> Bundle:
    """A bundle's bytes into rows, images and refusals.

    Pure: reads the archive and the catalog, appends nothing, writes nothing.
    That is what lets the portal offer a "check my file" that costs the same as
    sending it.
    """
    archive, refused = open_bundle(raw)
    if refused is not None:
        return refused
    assert archive is not None

    name, refused = _data_member(archive)
    if refused is not None:
        return refused

    raw_rows, why = parse_rows(name, archive.read(name))
    if why:
        return _refuse(why)
    if not raw_rows:
        return _refuse("the data file has a header and no rows")
    if len(raw_rows) > MAX_BUNDLE_ROWS:
        return _refuse(
            f"the data file has {len(raw_rows)} rows; this endpoint accepts up "
            f"to {MAX_BUNDLE_ROWS} in one bundle")

    bundle = Bundle(filename=name, read=len(raw_rows))
    known = _known_columns(base)
    seen_columns = {c for row in raw_rows for c in row}
    bundle.ignored_columns = sorted(seen_columns & ECHO_COLUMNS)
    bundle.unknown_columns = sorted(
        c for c in seen_columns if c not in known and c not in ECHO_COLUMNS)

    by_sku = _variant_by_sku(base)
    members = {i.filename.lower(): i.filename
               for i in archive.infolist() if not i.is_dir()}
    wanted: dict[str, str] = {}

    for offset, raw_row in enumerate(raw_rows):
        # Line 1 is the header and rows 2 and 3 are the annotation block the
        # template writes, so a supplier looking at their own file finds the
        # row this names.
        line = offset + 4
        sku = (raw_row.get("sku") or "").strip()
        if not sku:
            bundle.rejected.append(Rejection(line, "", "sku", "the row has no SKU"))
            continue

        row = Row(line=line, sku=sku,
                  product_ref=(raw_row.get("product_ref") or "").strip(),
                  product_name=(raw_row.get("product_name") or "").strip(),
                  variant_name=(raw_row.get("variant_name") or "").strip(),
                  category=(raw_row.get("category") or "").strip(),
                  is_base=_truthy(raw_row.get("is_base", "")))

        entity_id = by_sku.get(sku.lower(), "")
        if entity_id:
            product_id = base.product_of_variant.get(entity_id, "")
            product = base.products.get(product_id)
            if product is not None and product.supplier != supplier:
                # The same rule the single-attribute form applies. A portal
                # where any supplier can assert against any SKU is one catalog
                # with eighteen front doors.
                bundle.rejected.append(Rejection(
                    line, sku, "sku",
                    f"{sku} belongs to another supplier"))
                continue
            row.entity_id = entity_id
            if not row.category and product is not None:
                row.category = product.category
        else:
            row.draft = True
            if not row.category:
                bundle.rejected.append(Rejection(
                    line, sku, "category",
                    "this SKU is not in the catalog, so it is a proposed new "
                    "line and needs a category"))
                continue
            if row.category not in (getattr(base.catalog, "taxonomy", None)
                                    or {}).get("internal", {}):
                bundle.rejected.append(Rejection(
                    line, sku, "category",
                    f"{row.category!r} is not a category we trade"))
                continue

        problem = _read_values(row, raw_row, base, bundle)
        if problem:
            continue

        for role, filename in _read_images(row, raw_row).items():
            if not accepts_images:
                continue
            member = members.get(f"{IMAGE_DIR}/{filename}".lower())
            if member is None:
                bundle.missing_images.append((line, role, filename))
                continue
            wanted[member] = filename
            row.images[role] = filename

        bundle.rows.append(row)

    if accepts_images:
        _load_images(archive, wanted, bundle, members)
    return bundle


def _read_values(row: Row, raw_row: dict[str, str], base,
                 bundle: Bundle) -> bool:
    """Coerce every attribute cell, reporting the ones that will not.

    **A bad cell loses the cell, not the row.** A row of twelve values with a
    unit typed into one of them is eleven values we can use and one we cannot,
    and rejecting all twelve would throw away good data to punish a typo. The
    cell is reported by line and column, and the value simply does not arrive -
    at which point ``applicable_attributes`` or ``mandatory_information``
    reports it as missing, through the same check that would have reported it
    had the supplier left the cell blank. Which is the truth: a value that
    cannot be read is a value we do not have.

    Returns True only when the row itself cannot stand.
    """
    from sc.estate.intake import _coerce
    from sc.state.baseline import applies_to_category

    for column, cell in sorted(raw_row.items()):
        definition = base.attr_defs.get(column)
        if definition is None or not str(cell).strip():
            continue
        if row.category and not applies_to_category(definition, row.category):
            # Not an error. A branch template carries every attribute any of its
            # categories uses, so a saucepan row in the Home sheet legitimately
            # leaves the wattage column alone - and a supplier who typed one
            # anyway has said something about a product that cannot have it.
            bundle.rejected.append(Rejection(
                row.line, row.sku, column,
                f"{column} does not apply to {row.category}"))
            continue
        raw_value: object = str(cell).strip()
        if definition.dtype == "list[str]":
            raw_value = [v.strip() for v in str(cell).split(LIST_SEPARATOR.strip())
                         if v.strip()]
        elif definition.dtype == "bool":
            raw_value = _truthy(str(cell))
        value, why = _coerce(raw_value, definition.dtype)
        if why:
            bundle.rejected.append(Rejection(
                row.line, row.sku, column, f"{why}, got {str(cell)[:40]!r}"))
            continue
        row.values[column] = value
    return False


def _read_images(row: Row, raw_row: dict[str, str]) -> dict[str, str]:
    named: dict[str, str] = {}
    for column, cell in raw_row.items():
        if not column.startswith("image.") or not str(cell).strip():
            continue
        named[column.split(".", 1)[1]] = str(cell).strip()
    return named


def _load_images(archive: zipfile.ZipFile, wanted: dict[str, str],
                 bundle: Bundle, members: dict[str, str]) -> None:
    for member, filename in sorted(wanted.items()):
        info = archive.getinfo(member)
        if info.file_size > MAX_IMAGE_BYTES:
            bundle.rejected.append(Rejection(
                0, "", filename,
                f"the image is {info.file_size} bytes; this endpoint accepts "
                f"up to {MAX_IMAGE_BYTES} per image"))
            continue
        bundle.images[filename] = archive.read(member)

    held = {m.lower() for m in wanted}
    bundle.unreferenced = sorted(
        original for lower, original in members.items()
        if lower.startswith(f"{IMAGE_DIR}/") and lower not in held)
