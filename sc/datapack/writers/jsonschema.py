"""The machine-readable half of the contract.

A supplier integrating system to system does not want a spreadsheet, and a
spreadsheet is a poor place to state that a value is an ordered list of strings
whose order carries legal meaning. So the same derivation is emitted as JSON
Schema, one ``$defs`` entry per branch, and a supplier's own CI can reject a
payload before it is sent rather than after it is judged.

Draft 2020-12, because that is the draft whose ``prefixItems`` and
``dependentRequired`` a supplier's validator is most likely to already have.

Two things are deliberately *not* expressed here, and the schema says so in its
own ``description`` rather than leaving a reader to conclude they were
forgotten:

*   Channel requirements are conditional on what a product lists on, which this
    file cannot know. A column ``required_for`` a marketplace is described as
    required by that channel and is not in ``required``, because a schema that
    refused the payload would be refusing a product that is not going there.
*   Leaf-level applicability is a ``description``, not an ``if``/``then``. It
    could be written as one, and the resulting schema would be four hundred
    lines of conditionals restating the taxonomy - which is a second copy of
    the taxonomy, in the format hardest to read it in.
"""

from __future__ import annotations

from typing import Any

from sc.datapack.schema import LIST_SEPARATOR, Column, Pack, Sheet

SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"

#: Where a dtype lands in JSON. Everything arrives from a spreadsheet as text,
#: so the schema describes the *parsed* value: this is the contract for a
#: supplier posting JSON, and the CSV column note is the contract for one
#: filling in a sheet.
JSON_TYPE: dict[str, str] = {
    "int": "integer",
    "float": "number",
    "str": "string",
    "bool": "boolean",
    "list[str]": "array",
}


def _property(column: Column, pack: Pack) -> dict[str, Any]:
    body: dict[str, Any] = {"type": JSON_TYPE.get(column.dtype, "string")}
    if body["type"] == "array":
        body["items"] = {"type": "string"}
        if column.ordered:
            body["description"] = (
                "order is part of the value and is a legal declaration; do not "
                "sort")
    if column.unit:
        body["unit"] = column.unit
    if column.name == "identifiers.gtin":
        body["pattern"] = r"^\d{8}$|^\d{12,14}$"
        body["description"] = (
            "digits only, as a string - leading zeros are significant")

    notes = [column.marker()]
    values = pack.vocabulary.get(column.name)
    if values and column.dtype == "str":
        # An enum, not a hard one: these are the values the catalog has used,
        # and a supplier introducing a genuinely new plug type is not sending a
        # malformed payload. `examples` says so; `enum` would not.
        body["examples"] = list(values)
    if column.safety:
        notes.append(
            "safety class: an inferred value below the confidence threshold "
            "blocks publication rather than degrading it")
    body.setdefault("description", "; ".join(notes))
    return body


def _sheet_schema(sheet: Sheet, pack: Pack) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for column in sheet.columns:
        if column.kind == "identity":
            properties[column.name] = {
                "type": "boolean" if column.name == "is_base" else "string",
                "description": column.note,
            }
            if column.name != "is_base":
                required.append(column.name)
            continue
        if column.kind == "image":
            properties[column.name] = {
                "type": "string",
                "description": column.marker(),
            }
            continue
        properties[column.name] = _property(column, pack)

    properties["category"]["enum"] = list(sheet.leaves)
    return {
        "type": "object",
        "title": sheet.label,
        "description": (
            f"One SKU in {sheet.label}. Channel requirements are stated per "
            f"property and are not in `required`, because whether a channel "
            f"requires a value depends on where the product is listed, which "
            f"this document cannot know."
            + (" This branch is regulated." if sheet.regulated else "")),
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def write(pack: Pack) -> dict[str, Any]:
    """The whole pack as one schema document."""
    return {
        "$schema": SCHEMA_URI,
        "$id": f"urn:{pack.fascia.lower().replace(' ', '-')}:supplier-feed:1",
        "title": f"{pack.fascia} supplier product feed",
        "description": (
            "Derived from the retailer's attribute registry and assortment. "
            "One object per SKU; rows sharing a product_ref are variants of "
            "one line. List values in a flat file are separated by "
            f"'{LIST_SEPARATOR.strip()}'. The supplier is taken from the "
            "intake session and is deliberately not a field."),
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {"oneOf": [{"$ref": f"#/$defs/{s.branch}"}
                                    for s in pack.sheets]},
            },
        },
        "required": ["rows"],
        "$defs": {sheet.branch: _sheet_schema(sheet, pack)
                  for sheet in pack.sheets},
    }
