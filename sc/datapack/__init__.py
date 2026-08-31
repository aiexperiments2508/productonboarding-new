"""The supplier data pack: what a supplier is handed, and what comes back.

Two directions, one definition of the columns.

*   ``schema`` derives the column set for every branch from the attribute
    registry and the retailer profile. Nothing else in this package decides
    what a column is.
*   ``sample`` fills it from the catalog, with a deliberately broken row per
    defect a supplier file can carry.
*   ``writers`` emits it as CSV, a pipe-delimited flat file, an XLSX workbook,
    a Word specification and a JSON Schema.
*   ``read`` parses what comes back.

The derivation is shared between the two directions on purpose. A template
written by one definition and validated by another is two definitions, and the
first thing they would disagree about is the attribute somebody added last
week - which is the same objection ``sc/readiness/checks.py`` makes about a
rule with two implementations, applied to a schema.

Building the pack needs ``openpyxl`` for the workbook and nothing else;
``requirements-datapack.txt`` says why that one dependency is taken. Reading a
returned bundle needs it only when the supplier sends the workbook back rather
than a CSV, and the refusal says so rather than failing obscurely.
"""

from __future__ import annotations

from sc.datapack.schema import Column, Pack, Sheet, build, columns_for

__all__ = ["Column", "Pack", "Sheet", "build", "columns_for", "formats"]

#: What the pack contains, and which of them need the optional dependency.
#: Read by the build script and by the intake tool that offers a template, so
#: "which formats can this installation actually produce" has one answer.
FORMATS: tuple[tuple[str, str, bool], ...] = (
    ("csv", "text/csv", False),
    ("txt", "text/plain", False),
    ("json", "application/schema+json", False),
    ("docx", "application/vnd.openxmlformats-officedocument."
             "wordprocessingml.document", False),
    ("xlsx", "application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet", True),
)


def formats() -> dict[str, dict]:
    """Each format, its media type, and whether it can be produced here."""
    from sc.datapack.writers import workbook

    have_openpyxl = workbook.available()
    return {
        name: {
            "media_type": media_type,
            "available": have_openpyxl or not needs_openpyxl,
            "why": ("" if have_openpyxl or not needs_openpyxl else
                    "openpyxl is not installed; "
                    "pip install -r requirements-datapack.txt"),
        }
        for name, media_type, needs_openpyxl in FORMATS
    }
