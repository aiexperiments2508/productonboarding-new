"""What a supplier is asked to send, derived from what the retailer enforces.

Every column of every template in the pack comes from two places and nowhere
else: the attribute registry the readiness checks read, and the branch
declarations in the retailer profile. Nothing here names a category, a column
or an enum value. Point ``RETAILER_PROFILE`` at a different profile, regenerate
the seed pack, and the templates change with it.

That is not tidiness. A hand-written template would be a third statement of
what a product record is, beside the registry and the checks, and the first
thing it would disagree about is the attribute somebody added last week - so a
supplier would fill in a column no check reads, or omit one that holds their
launch.

**Columns are per branch; applicability is per leaf.** A branch template
carries every attribute that applies to *any* leaf in that branch, because one
sheet per leaf would be seventy-eight sheets. Five attributes are named leaf by
leaf in the registry - a kettle is mains and a saucepan is not, and both are
``home.`` - so a column that does not cover the whole branch says which leaves
it does cover, and an empty cell on a row it does not cover is correct rather
than missing. ``sc.state.baseline.applies_to_category`` is the one predicate
that decides this, and the readiness check that would report the gap asks it
too.

**The supplier is not a column.** It is taken from the intake session, never
read from the file. A supplier id in a spreadsheet is a supplier id anybody can
type, and the vendor portal holds identity server-side for exactly that reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sc.contracts import MediaRole
from sc.state.baseline import applies_to_category

#: The identity block, ahead of every attribute column. ``product_ref`` groups
#: rows into products: two rows sharing one are two variants of one line, which
#: is how a supplier expresses a range without being handed a second file.
IDENTITY: tuple[tuple[str, str, str], ...] = (
    ("product_ref", "Product reference",
     "your own id for the line; rows sharing one are variants of it"),
    ("product_name", "Product name", "the line, as a shopper would see it"),
    ("sku", "SKU", "unique per row; what everybody outside your systems says"),
    ("variant_name", "Variant name",
     "what distinguishes this row from its siblings"),
    ("is_base", "Base variant", "true on exactly one row per product reference"),
    ("category", "Category", "one of the codes on the Categories sheet"),
)

#: Offered on every branch even where no category requires it. The seed pack
#: gives every variant one for the same reason: it keeps "has imagery" and "has
#: the imagery it needs" visibly different questions.
OPTIONAL_MEDIA: tuple[MediaRole, ...] = (MediaRole.DETAIL,)

#: How a list value is written in one cell. A spreadsheet has no list type, and
#: a comma is inside half the ingredient names this catalog holds.
LIST_SEPARATOR = " | "


@dataclass(frozen=True)
class Column:
    """One column, and everything the three header rows say about it."""

    name: str
    label: str
    kind: str                 # "identity" | "attribute" | "image"
    dtype: str = "str"
    unit: str | None = None
    required: bool = False
    safety: bool = False
    ordered: bool = False
    #: Channel ids that refuse to publish without it.
    required_for: tuple[str, ...] = ()
    #: Leaves this column covers, empty when it covers the whole branch.
    only_leaves: tuple[str, ...] = ()
    note: str = ""

    @property
    def heading(self) -> str:
        """Row two: the label, carrying its unit so the cell need not."""
        return f"{self.label} ({self.unit})" if self.unit else self.label

    def marker(self) -> str:
        """Row three: the one sentence a supplier needs about this column."""
        parts: list[str] = []
        if self.required_for:
            parts.append(f"required by {', '.join(self.required_for)}")
        elif self.required:
            parts.append("required")
        else:
            parts.append("optional")
        if self.safety:
            parts.append("safety - a person reviews any change")
        if self.ordered:
            parts.append("order is part of the value; do not sort")
        if self.only_leaves:
            shown = ", ".join(self.only_leaves[:4])
            if len(self.only_leaves) > 4:
                shown += f", and {len(self.only_leaves) - 4} more"
            parts.append(f"applies to {shown} only")
        if self.note:
            parts.append(self.note)
        return "; ".join(parts)


@dataclass(frozen=True)
class Sheet:
    """One branch's template."""

    branch: str
    label: str
    regulated: bool
    leaves: tuple[str, ...]
    columns: tuple[Column, ...]

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)

    @property
    def image_roles(self) -> tuple[str, ...]:
        return tuple(c.name.split(".", 1)[1] for c in self.columns
                     if c.kind == "image")


@dataclass
class Pack:
    """Every sheet, plus the taxonomy and vocabulary they reference."""

    fascia: str
    sheets: list[Sheet] = field(default_factory=list)
    taxonomy: dict[str, str] = field(default_factory=dict)
    #: Attribute path -> values the catalog has actually used, for dropdowns.
    vocabulary: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def sheet(self, branch: str) -> Sheet | None:
        return next((s for s in self.sheets if s.branch == branch), None)


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def taxonomy_of(base) -> dict[str, str]:
    """The internal taxonomy, code to display string."""
    taxonomy = getattr(base.catalog, "taxonomy", None) or {}
    return dict(taxonomy.get("internal", {}))


def branches_of(base) -> dict[str, dict]:
    return dict((getattr(base.catalog, "profile", None) or {}).get("branches", {}))


def leaves_for(branch: str, base) -> tuple[str, ...]:
    """The three-level codes under a branch.

    Read from the taxonomy rather than from the products, so a leaf the
    retailer trades but has not listed anything in yet still gets a column - a
    supplier onboarding the first line into a category is the case this pack
    exists for.
    """
    return tuple(sorted(code for code in taxonomy_of(base)
                        if code.startswith(f"{branch}.") and code.count(".") == 2))


def _dtype_note(dtype: str, unit: str | None) -> str:
    """The traps a spreadsheet causes, said at the column that causes them."""
    if dtype == "list[str]":
        return f"one entry per cell, separated by '{LIST_SEPARATOR.strip()}'"
    if unit:
        return f"the number only, in {unit} - never '65 {unit}'"
    if dtype == "bool":
        return "true or false"
    return ""


def columns_for(branch: str, base) -> tuple[Column, ...]:
    """Every column this branch's template carries, in order."""
    spec = branches_of(base).get(branch, {})
    leaves = leaves_for(branch, base)
    columns: list[Column] = [
        Column(name=name, label=label, kind="identity", required=True, note=note)
        for name, label, note in IDENTITY
    ]

    for path in sorted(base.attr_defs):
        definition = base.attr_defs[path]
        covered = tuple(leaf for leaf in leaves
                        if applies_to_category(definition, leaf))
        if not covered:
            continue
        note = _dtype_note(definition.dtype, definition.unit)
        if path == "identifiers.gtin":
            # Excel drops the leading zero and reformats the rest, silently
            # both times. The column is text, and the template says so.
            note = "14 digits, kept as text - leading zeros are significant"
        columns.append(Column(
            name=path, label=definition.label, kind="attribute",
            dtype=definition.dtype, unit=definition.unit,
            required=bool(definition.required_for),
            safety=definition.safety_class, ordered=definition.ordered,
            required_for=tuple(definition.required_for),
            only_leaves=() if len(covered) == len(leaves) else covered,
            note=note))

    required_roles = tuple(MediaRole(r) for r in spec.get("required_media", ()))
    optional = tuple(r for r in OPTIONAL_MEDIA if r not in required_roles)
    for role in required_roles + optional:
        columns.append(Column(
            name=f"image.{role.value}", label=f"Image - {role.value.lower()}",
            kind="image", required=role in required_roles,
            note="the file name as it appears in images/ inside the bundle"))
    return tuple(columns)


def build(base) -> Pack:
    """The whole pack's schema, one sheet per branch the retailer trades."""
    profile = getattr(base.catalog, "profile", None) or {}
    fascia = profile.get("fascia") or "the retailer"
    pack = Pack(fascia=fascia, taxonomy=taxonomy_of(base))
    for branch, spec in sorted(branches_of(base).items()):
        leaves = leaves_for(branch, base)
        if not leaves:
            continue
        pack.sheets.append(Sheet(
            branch=branch, label=spec.get("label", branch),
            regulated=bool(spec.get("regulated")), leaves=leaves,
            columns=columns_for(branch, base)))
    pack.vocabulary = observed_values(base)
    return pack


def observed_values(base, limit: int = 40) -> dict[str, tuple[str, ...]]:
    """Values the catalog has actually used, per string attribute.

    Drawn from the catalog rather than from a vocabulary list in the profile,
    because the question a dropdown answers is "what do we already accept
    here", and the catalog is the only place that has been checked. An
    attribute with more distinct values than ``limit`` gets no dropdown: a free
    text field with two hundred options is a free text field with a scrollbar.
    """
    seen: dict[str, set[str]] = {
        path: set() for path, definition in base.attr_defs.items()
        if definition.dtype == "str"
    }
    for (_entity, path), value in base.attr_values.items():
        if path in seen and isinstance(value, str) and value:
            seen[path].add(value)
    return {path: tuple(sorted(values))
            for path, values in sorted(seen.items()) if 0 < len(values) <= limit}
