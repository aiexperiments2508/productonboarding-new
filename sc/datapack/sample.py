"""A filled example, drawn from the catalog rather than invented.

A blank template teaches a supplier the column names and nothing about what
goes in them. So every branch ships a worked example, and the rows are real
lines out of this catalog: the values are in the retailer's own vocabulary, the
categories exist, the units are the declared ones, and none of it had to be
kept in step with the registry by hand.

**Some rows are deliberately wrong.** A sample where everything passes teaches
a supplier that everything passes. Each branch's example carries one row per
defect a supplier file can genuinely carry, drawn from the closed set in
``sc.estate.defects`` so the damage is the damage the checks already know how
to name. The example's own last column says which row is broken and how, so
this is a worked example rather than a trap.

Two of the seven defects are not representable here and the README says so
rather than quietly shipping five and calling it seven. ``STALE_VERSION`` is an
assertion against a superseded document version, and a new line has no prior
version to be stale against; ``CONTRADICTS_SOURCE`` needs a higher-precedence
source already in the estate, which is a fact about the retailer's other feeds
rather than about this file.

The draw is seeded from ``DATA_SEED``, so the same catalog produces the same
example every time and a diff of two packs is a real difference.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from sc.datapack.schema import LIST_SEPARATOR, Sheet
from sc.estate.defects import Defect
from sc.rng import stream

#: Same default as ``scripts/generate_data.py``, read the same way, so the
#: example and the catalog it is drawn from come off one seed.
SEED = int(os.environ.get("DATA_SEED", "20802"))

#: How many good rows before the broken ones. Enough to show a range - two
#: variants of one product - without turning the example into a data set.
GOOD_ROWS = 6

#: The defects a supplier's own file can carry. The other two need the estate
#: around it, and claiming them here would be a worked example of something
#: this file cannot demonstrate.
REPRESENTABLE: tuple[Defect, ...] = (
    Defect.MISSING_MANDATORY,
    Defect.WRONG_TYPE,
    Defect.FOREIGN_VOCABULARY,
    Defect.BROKEN_FORMAT,
    Defect.MISSING_MEDIA,
)

NOT_REPRESENTABLE: dict[Defect, str] = {
    Defect.STALE_VERSION:
        "an assertion against a superseded document version - a new line has "
        "no earlier version to be stale against",
    Defect.CONTRADICTS_SOURCE:
        "a disagreement with a higher-precedence source already held - a fact "
        "about the retailer's other feeds rather than about this file",
}

#: The column the example uses to say what it is demonstrating. Stripped before
#: a bundle is parsed, so pasting the example straight back in still works.
NOTE_COLUMN = "example_note"


@dataclass
class Example:
    """One branch's worked example."""

    branch: str
    #: Whose lines these are. A bundle is one supplier's submission.
    supplier: str
    rows: list[dict[str, str]]
    #: Image file name -> the variant it belongs to, for the bundle's images/.
    images: dict[str, str]
    #: Defects this branch has no column to demonstrate, and why not.
    unshown: dict[str, str] = field(default_factory=dict)


def render(value: object, dtype: str) -> str:
    """One catalog value as a supplier would type it into a cell.

    Lists are joined with the separator the template declares rather than a
    comma, because a comma is inside half the ingredient names this catalog
    holds and a supplier splitting on one would declare 'sunflower oil' as two
    ingredients.
    """
    if value is None:
        return ""
    if dtype == "bool":
        return "true" if value else "false"
    if dtype.startswith("list["):
        items = value if isinstance(value, list) else [value]
        return LIST_SEPARATOR.join(str(v) for v in items)
    return str(value)


def _variants_for(sheet: Sheet, base) -> tuple[str, list[str]]:
    """One supplier's variants in this branch, and which supplier.

    One supplier, because a bundle is one supplier's submission and the intake
    refuses a row naming a SKU somebody else owns. A worked example drawn from
    across the branch would be an example that is mostly rejected on arrival,
    which teaches the wrong thing about the format and the right thing about
    nothing.

    The supplier with the most lines in the branch, so the example has a range
    in it - two variants of one product is the case the product reference
    column exists for.
    """
    by_supplier: dict[str, list[str]] = {}
    for variant_id in base.variants:
        product = base.products.get(base.product_of_variant.get(variant_id, ""))
        if product is None or not product.category.startswith(f"{sheet.branch}."):
            continue
        by_supplier.setdefault(product.supplier, []).append(variant_id)
    if not by_supplier:
        return "", []
    supplier = max(sorted(by_supplier), key=lambda s: len(by_supplier[s]))
    return supplier, sorted(
        by_supplier[supplier],
        key=lambda v: (base.product_of_variant[v],
                       not base.variants[v].is_base, v))


def _row_for(variant_id: str, sheet: Sheet, base) -> tuple[dict[str, str], dict]:
    """One good row, and the images it names."""
    variant = base.variants[variant_id]
    product = base.products[base.product_of_variant[variant_id]]
    row: dict[str, str] = {
        "product_ref": product.id,
        "product_name": product.name,
        "sku": variant.sku or variant_id,
        "variant_name": variant.name,
        "is_base": "true" if variant.is_base else "false",
        "category": product.category,
    }
    for column in sheet.columns:
        if column.kind != "attribute":
            continue
        row[column.name] = render(
            base.attr_values.get((variant_id, column.name)), column.dtype)

    images: dict[str, str] = {}
    held = {getattr(asset, "role", ""): asset
            for asset in base.media_by_entity.get(variant_id, [])}
    for role in sheet.image_roles:
        asset = held.get(role)
        if asset is None:
            row[f"image.{role}"] = ""
            continue
        name = f"{variant.sku or variant_id}-{role.lower()}.svg".lower()
        row[f"image.{role}"] = name
        images[name] = getattr(asset, "uri", "")
    return row, images


def _first(sheet: Sheet, kind: str) -> str | None:
    """A column to demonstrate one defect on.

    Safety-class columns are passed over. A worked example that blanks the
    allergen declaration to show what a missing value looks like is teaching
    the wrong lesson on the one attribute where the lesson has to be the other
    one - and a supplier who copies the example is a supplier who has copied a
    row with no allergens on it.
    """
    for column in sheet.columns:
        if column.kind != "attribute" or column.safety:
            continue
        if kind == "required" and column.required_for:
            return column.name
        if kind == "number" and column.dtype in ("int", "float") and column.unit:
            return column.name
    return None


def _break(row: dict[str, str], defect: Defect,
           sheet: Sheet) -> dict[str, str] | None:
    """Damage one row in exactly one named way.

    Returns ``None`` when this branch has no column the defect can be shown
    on - Clothing declares no numeric attribute, so there is nowhere to put a
    unit in a cell. An example row carrying a defect it does not actually
    exhibit would be worse than one fewer row.
    """
    broken = dict(row)
    broken["sku"] = f"{row['sku']}-EG{REPRESENTABLE.index(defect) + 1}"

    if defect is Defect.MISSING_MANDATORY:
        target = _first(sheet, "required")
        if not target:
            return None
        broken[target] = ""
        broken[NOTE_COLUMN] = (
            f"MISSING_MANDATORY - {target} is blank, and a channel refuses "
            f"the listing without it")

    elif defect is Defect.WRONG_TYPE:
        target = _first(sheet, "number")
        column = sheet.column(target) if target else None
        if column is None:
            return None
        broken[target] = f"{row.get(target) or '40'} {column.unit}"
        broken[NOTE_COLUMN] = (
            f"WRONG_TYPE - the unit is in the cell. {target} is a number; "
            f"'{broken[target]}' is a string")

    elif defect is Defect.FOREIGN_VOCABULARY:
        broken[NOTE_COLUMN] = (
            "FOREIGN_VOCABULARY - this row is fine, but a file whose header "
            "reads 'netContent' instead of 'pack.net_quantity' is rejected "
            "with the column named. Rename the column to see it")

    elif defect is Defect.BROKEN_FORMAT:
        gtin = row.get("identifiers.gtin") or "05012345600018"
        broken["identifiers.gtin"] = gtin[:6] + "X" + gtin[7:13]
        broken[NOTE_COLUMN] = (
            "BROKEN_FORMAT - a 13-character GTIN with a letter in it, which is "
            "what a spreadsheet export produces when the column was typed as "
            "text and edited by hand")

    elif defect is Defect.MISSING_MEDIA:
        roles = [c.name for c in sheet.columns if c.kind == "image" and c.required]
        if not roles:
            return None
        for name in roles:
            broken[name] = ""
        broken[NOTE_COLUMN] = (
            f"MISSING_MEDIA - {', '.join(roles)} is blank, and this category "
            f"cannot launch without it")

    return broken


def build(sheet: Sheet, base, *, good_rows: int = GOOD_ROWS) -> Example:
    """A worked example for one branch: good rows, then one per defect."""
    supplier, candidates = _variants_for(sheet, base)
    if not candidates:
        return Example(branch=sheet.branch, supplier="", rows=[], images={})

    draw = stream(SEED, "datapack.sample", sheet.branch)
    rows: list[dict[str, str]] = []
    images: dict[str, str] = {}
    chosen = candidates[:good_rows]
    for variant_id in chosen:
        row, named = _row_for(variant_id, sheet, base)
        row[NOTE_COLUMN] = ""
        rows.append(row)
        images.update(named)

    # The damaged rows are copies of a *good* one, so the only difference
    # between a row that passes and a row that does not is the thing being
    # demonstrated. Drawing from `rows` after the first append would start
    # breaking already-broken rows, and a row with two defects on it
    # demonstrates neither.
    good = list(rows)
    unshown: dict[str, str] = {}
    for defect in REPRESENTABLE:
        broken = _break(draw.pick(good), defect, sheet)
        if broken is None:
            unshown[defect.value] = (
                f"{sheet.label} declares no column this defect can be shown on")
            continue
        rows.append(broken)
    return Example(branch=sheet.branch, supplier=supplier, rows=rows,
                   images=images, unshown=unshown)
