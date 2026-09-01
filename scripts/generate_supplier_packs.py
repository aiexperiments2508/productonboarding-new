"""One uploadable bundle per supplier, arranged so every outcome is reachable.

The vendor portal accepts a .zip per supplier and the onboarding report grades
what is inside it. Until now there was test data for two suppliers, which is
enough to prove the endpoint parses and not enough to show what the report is
*for*: a bundle where everything passes says nothing about a system whose whole
argument is about what happens when things do not.

So this writes a pack for every supplier the catalog trades, and each pack is
built to land in four places on purpose.

**The four outcomes, and the lever each one actually uses.** These are not
labels stuck on rows afterwards - each is a mechanism in the code, verified by
``--verify`` running the real intake and the real report over the bundle it
just wrote.

*   **Clears.** Every attribute the category declares is supplied, correctly
    typed, with the imagery the branch requires. ``readiness`` finds nothing and
    the verdict is ``READY_TO_LAUNCH``.
*   **A machine can correct it.** The value is *there* and unreadable - a unit
    typed into a numeric cell, a thousands separator, a date where a number
    goes. ``read._read_values`` rejects the cell by line and column and keeps
    the rest of the row, so the bundle report names the correction without
    anybody guessing at it. The same file carries columns in a sending system's
    own vocabulary, which arrive as ``unknown_columns``.
*   **A little is missing, and something already on file agrees.** A non-safety
    attribute is left blank on one variant while a sibling variant of the same
    product carries it. That is the ``SIBLING`` prior in ``onboarding.history``,
    which is what ``suggest`` scores a proposal from - so the gap arrives with
    corroboration rather than as a blank a person has to research.
*   **A person has to look.** Two levers, deliberately different in kind.
    ``compliance.sale_permitted = false`` is a withdrawal notice: ``checks``
    raises it ``BLOCKING`` and ``gate`` stops onboarding on the authority of a
    regulation. A blank safety-class attribute is the quieter one - ``fixable``
    refuses to make it a candidate at all, whatever else agrees with it, so it
    can only ever be answered by the supplier.

**Why the values are drawn from the catalog rather than invented.** Every value
this writes for an existing attribute is one the catalog already holds
somewhere - the same country names, the same pack units, the same allergen
codes. A generator inventing its own vocabulary would produce a data set whose
failures were all its own: a reviewer could not tell a rule firing correctly
from a bundle written by somebody who had not read the profile.

**The mess is on purpose and is bounded.** Enterprise files arrive with
trailing spaces, ``TRUE`` and ``Yes`` in one boolean column, a spare "Notes"
column somebody added, an image named in the sheet that is not in the archive
and two images in the archive no row names. All of that is here. What is *not*
here is damage nothing downstream can name: the defect classes are the closed
set in ``sc.estate.defects``, for the reason that file gives.

Run::

    python scripts/generate_supplier_packs.py            # write the packs
    python scripts/generate_supplier_packs.py --verify   # write, then grade

``--verify`` submits every bundle through ``intake.submit_product_feed`` against
a scratch database and prints what the onboarding report actually said, which is
the only claim about this data worth making.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Its own database, before anything under ``sc`` is imported and reads these.
# The packs are built from what the record actually holds, which means reading
# the estate - and reading it must not mean writing over the one the app is
# serving. ``setdefault`` so a caller who wants a different one still gets it.
os.environ.setdefault("DB_PATH", "data/supplier_packs.db")
os.environ.setdefault("CATALOG_EXTENSION", "supplier_packs.live.json")
os.environ.setdefault("ENV_FILE", "data/supplier_packs.env")

from scripts import supplier_packs_readme as readme_mod  # noqa: E402
from scripts.supplier_packs_names import (  # noqa: E402
    COUNTRIES, VARIANT_WORDS, nouns_for,
)

#: Where the packs land. Generated output, rewritten wholesale on every run.
OUT = Path("data/supplier-packs")

#: Same shape as the rest of the generated estate: one seed, one data set.
SEED = 20802

#: The supplier the catalog carries for the regulator rather than for trade. It
#: sends withdrawal notices; it does not send a product feed, and writing it a
#: bundle would put a supplier in the queue that nobody can onboard.
NOT_A_TRADING_SUPPLIER = {"SUP-90"}

#: How the data file is written, per supplier. A portal that only ever sees the
#: CSV it handed out is a portal that has not met a supplier whose system
#: predates commas.
FORMATS = ("csv", "csv", "csv", "txt", "xlsx")

#: Columns a sending system uses instead of ours. Read back as
#: ``unknown_columns`` - reported, never fatal, which is the behaviour
#: ``read.py`` documents and the one worth demonstrating.
FOREIGN_COLUMNS: dict[str, tuple[str, str]] = {
    "pack.net_quantity": ("netContent", "the GDSN field for the same number"),
    "identifiers.gtin": ("GTIN_14", "the pool's own identifier column"),
    "origin.country": ("countryOfOrigin", "the sending system's spelling"),
    "food.ingredients": ("ingredientStatement", "a marketplace field name"),
    "specs.power_w": ("ratedPowerWatts", "the spec sheet's column heading"),
}

#: Spare columns somebody added to the sheet and nobody removed. Harmless and
#: extremely common, and the portal has to say so rather than refuse the file.
SPARE_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Supplier Notes", ("", "checked 02/26", "as agreed with buying", "")),
    ("internal_ref", ("", "", "REF-8841", "REF-8842")),
    ("Case Qty", ("6", "12", "", "24")),
    ("Buyer", ("A. Whitfield", "", "R. Okonjo", "")),
)

#: Claims that may never be published, from ``checks.FORBIDDEN_PHRASES``. Put
#: on a small number of rows so the copy checks have something true to find.
FORBIDDEN_CLAIMS: tuple[str, ...] = (
    "clinically proven", "cures dry skin", "completely safe",
    "guaranteed to last", "100% effective",
)

#: The dtypes a parser can actually turn down, established by reading
#: ``read._read_values`` rather than by assuming. A ``str`` attribute takes any
#: text; a ``bool`` goes through ``_truthy``, which reads anything as false
#: rather than failing; and a ``list[str]`` is *split*, so a comma-separated
#: cell arrives as one long item and is still a valid list. Only a number can
#: be refused - so only a number is used to demonstrate a refusal, and a defect
#: the answer key claimed but nothing reported would be worse than no example.
CORRUPTIBLE = ("int", "float")

#: An attribute belonging to another branch, mapped in by a supplier that keeps
#: one sheet for its whole catalogue. The parser knows the column - it is a real
#: attribute path - and the category does not take it, so every row carrying one
#: is reported by line and column. This is the machine-correctable defect for a
#: branch with no number in it: Clothing & Footwear declares no numeric
#: attribute at all, so there is nothing there to mistype.
STRAY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("specs.power_w", "1400"),
    ("specs.noise_db", "62"),
    ("food.net_weight_g", "450"),
    ("packaging.recyclable_pct", "70"),
)

#: What a withdrawal notice says. Written into the covering note so the reason a
#: row is blocked is legible outside this repository.
WITHDRAWAL_NOTES: tuple[str, ...] = (
    "batch recall in progress - do not list pending investigation",
    "held by our QA pending a supplier audit finding",
    "artwork under regulatory review; not for sale this period",
    "withdrawn from sale following a customer safety report",
)


# ---------------------------------------------------------------------------
# Values, drawn from the catalog rather than invented
# ---------------------------------------------------------------------------


def value_bank(base, branch: str = "") -> dict[str, list]:
    """Every distinct value the catalog holds, per attribute.

    The one source of vocabulary for everything written below. A country, a
    pack unit or an allergen code that appears in a generated row appears
    because this catalog already uses it, so a finding raised against one of
    these files is a finding about the file rather than about the generator.

    **Scoped to a branch wherever the branch has used the attribute.** Five of
    the twenty-six attributes apply to everything the retailer sells, and
    ``claims`` is the loud one: drawn across the whole catalog it will put
    "peanut-free" on a kettle. That value is in the retailer's own vocabulary
    and is nonsense on the product, which is the one kind of wrongness this
    data set must not manufacture - it reads as a rule misfiring rather than as
    a generator being careless, and somebody would go and look at the rule.
    """
    scoped: dict[str, list] = {}
    everywhere: dict[str, list] = {}

    def add(bank: dict[str, list], path: str, value) -> None:
        seen = bank.setdefault(path, [])
        if value not in seen:
            seen.append(value)

    for (entity, path), value in base.attr_values.items():
        if value in (None, "", []):
            continue
        add(everywhere, path, value)
        if not branch:
            continue
        product = base.products.get(
            base.product_of_variant.get(entity, entity))
        if product is not None and product.category.startswith(f"{branch}."):
            add(scoped, path, value)
    return {path: scoped.get(path) or values
            for path, values in everywhere.items()}


def _gtin(rng: random.Random) -> str:
    """A 14-digit identifier, kept as text.

    Well formed on purpose. The malformed one is injected where the defect is
    wanted, so a GTIN being wrong is always a decision this file made rather
    than a rounding accident.
    """
    return "0" + "".join(str(rng.randint(0, 9)) for _ in range(13))


def synth(path: str, definition, category: str, bank: dict[str, list],
          rng: random.Random):
    """A plausible value for one attribute, in the catalog's own vocabulary."""
    if path == "identifiers.gtin":
        return _gtin(rng)
    if path == "origin.country":
        return rng.choice(COUNTRIES)
    if path == "compliance.sale_permitted":
        return True
    if path == "compliance.certificate_ref":
        return f"CE-{rng.randint(2024, 2026)}-{rng.randint(10000, 99999)}"
    if path == "compliance.export_control":
        return rng.choice(["NOT_CONTROLLED", "DUAL_USE_REVIEW"])
    if path == "compliance.min_age":
        return 18 if category.startswith("food.alcohol.") else 16

    held = bank.get(path)
    if held:
        picked = rng.choice(held)
        if definition.dtype == "int" and isinstance(picked, (int, float)):
            return max(1, int(picked) + rng.choice([-2, -1, 0, 1, 2]))
        if definition.dtype == "float" and isinstance(picked, (int, float)):
            return round(float(picked) * rng.choice([0.9, 1.0, 1.1]), 1)
        return picked

    # Nothing on file for this attribute anywhere in the catalog. Rare, and the
    # dtype is still enough to write something the checks can read.
    if definition.dtype == "int":
        return rng.randint(20, 900)
    if definition.dtype == "float":
        return round(rng.uniform(10, 900), 1)
    if definition.dtype == "bool":
        return True
    if definition.dtype == "list[str]":
        return ["unspecified"]
    return "unspecified"


def render(value, dtype: str) -> str:
    """One value as a supplier would type it into a cell."""
    if value is None:
        return ""
    if dtype == "bool":
        return "true" if value else "false"
    if dtype.startswith("list["):
        items = value if isinstance(value, list) else [value]
        return " | ".join(str(v) for v in items)
    return str(value)


# ---------------------------------------------------------------------------
# The corruptions a machine can undo
# ---------------------------------------------------------------------------


def corrupt(text: str, definition, rng: random.Random) -> tuple[str, str]:
    """One readable value made unreadable, and what a person would call it.

    Every one of these is a real export artefact rather than random damage: the
    unit typed into the cell is what a spreadsheet column formatted as text
    produces, and the thousands separator is what Excel writes when the locale
    says to. Both are ``WRONG_TYPE`` - the supplier answered, and the answer
    cannot be parsed.
    """
    unit = definition.unit or ""
    if definition.dtype in ("int", "float"):
        choices = []
        if unit:
            choices.append((f"{text} {unit}", f"the unit is in the cell ({unit})"))
        try:
            number = float(text)
            if number >= 1000:
                whole = f"{int(number):,}"
                choices.append((whole, "a thousands separator from the export"))
        except ValueError:
            pass
        choices.append((text.replace(".", ",") if "." in text else f"{text},0",
                        "a decimal comma from a European locale"))
        choices.append(("N/A", "a placeholder where a number goes"))
        return rng.choice(choices)
    return (text, "unchanged")


# ---------------------------------------------------------------------------
# Building one supplier's rows
# ---------------------------------------------------------------------------


class Plan:
    """One supplier's bundle, before it is written to anything."""

    def __init__(self, supplier: str, name: str, branch: str, fmt: str):
        self.supplier = supplier
        self.name = name
        self.branch = branch
        self.fmt = fmt
        self.rows: list[dict[str, str]] = []
        #: Row band -> what it should do, for the answer key.
        self.expected: list[dict] = []
        self.images: dict[str, str] = {}
        self.declared_images: set[str] = set()
        self.foreign: dict[str, str] = {}
        self.spare: dict[str, tuple[str, ...]] = {}
        #: Attribute path -> the value, on the first rows only. A column from
        #: another branch that this category does not take.
        self.stray: dict[str, str] = {}
        #: Attributes carrying a deliberately unparseable value. Held so the
        #: foreign-vocabulary rename below cannot take one of them: a bad number
        #: sent under a column name the parser does not know is an unknown
        #: column and nothing else - the cell is never read, so it is never
        #: refused, and the answer key would be claiming a rejection that could
        #: not happen.
        self.fix_targets: set[str] = set()
        self.notes: list[str] = []


def _messy(text: str, rng: random.Random) -> str:
    """A cell as it survives a real export.

    Trailing space, a stray non-breaking space, inconsistent capitalisation of
    a boolean. All of it is stripped or coerced on the way in, which is the
    point: this is the noise a portal has to absorb silently, kept separate
    from the damage it has to report.
    """
    roll = rng.random()
    if roll < 0.06:
        return text + " "
    if roll < 0.10:
        return " " + text
    if text in ("true", "false") and roll < 0.24:
        return {"true": rng.choice(["TRUE", "Yes", "Y", "true "]),
                "false": rng.choice(["FALSE", "No", "N"])}[text]
    return text


def build_plan(supplier: str, sup_name: str, branch: str, fmt: str, base,
               state: list[dict], bank: dict[str, list], pack, rng) -> Plan:
    """Every row this supplier sends, and what each one is there to prove."""
    from sc.datapack.schema import columns_for
    from sc.readiness.checks import _is_dtype
    from sc.state.baseline import applies_to_category

    plan = Plan(supplier, sup_name, branch, fmt)
    sheet_columns = columns_for(branch, base)
    attr_columns = [c for c in sheet_columns if c.kind == "attribute"]
    image_roles = [c.name.split(".", 1)[1] for c in sheet_columns
                   if c.kind == "image"]
    required_roles = [c.name.split(".", 1)[1] for c in sheet_columns
                      if c.kind == "image" and c.required]

    def blank_row() -> dict[str, str]:
        return {c.name: "" for c in sheet_columns}

    def fill(row: dict, category: str, held: dict, *, skip: set[str] = frozenset(),
             malformed: dict[str, str] | None = None) -> None:
        """Every attribute the category declares, from the record or synthesised."""
        for column in attr_columns:
            definition = base.attr_defs.get(column.name)
            if definition is None:
                continue
            if not applies_to_category(definition, category):
                continue
            if column.name in skip:
                continue
            value = held.get(column.name)
            # A held value that is not the dtype it declares is a defect the
            # seed pack put there, and echoing it back would make every clean
            # row carry somebody else's broken cell. The supplier correcting
            # its own earlier export is the realistic reading and the useful
            # one - so it is replaced, and the corruption below stays the only
            # deliberate damage in the file.
            if value is not None and not _is_dtype(value, definition.dtype):
                value = None
            if value is None:
                value = synth(column.name, definition, category, bank, rng)
            text = render(value, definition.dtype)
            if malformed and column.name in malformed:
                text = malformed[column.name]
            row[column.name] = text

    def attach(row: dict, sku: str, name: str, category: str, *,
               roles: list[str] | None = None, declare_missing: str = "") -> None:
        """Name the imagery, and write the files the row actually names."""
        for role in (roles if roles is not None else image_roles):
            filename = f"{sku.lower()}-{role.lower()}.svg"
            row[f"image.{role}"] = filename
            plan.declared_images.add(filename)
            plan.images[filename] = svg(sku, name, role, category)
        if declare_missing:
            filename = f"{sku.lower()}-{declare_missing.lower()}.svg"
            row[f"image.{declare_missing}"] = filename
            plan.declared_images.add(filename)   # named, and deliberately absent

    # ---- rows against lines the catalog already holds ---------------------
    existing = [s for s in state if s["cat"].startswith(f"{branch}.")]
    existing.sort(key=lambda s: s["sku"])

    with_gap = [s for s in existing if s["miss_open"]]
    # Imagery is judged apart from attributes, because it is a different
    # question with a different owner. A line short of a required role cannot
    # be a clearing row whatever its attributes say - and putting it in the
    # clearing band would make the answer key wrong in the one place a reader
    # would check it first.
    def has_media(item: dict) -> bool:
        return all(role in item["media"] for role in required_roles)

    complete = [s for s in existing if not s["miss_open"] and has_media(s)]
    media_short = [s for s in existing if not s["miss_open"] and not has_media(s)]

    def corruptible(item: dict, prefer: list[str]) -> str:
        """An attribute whose cell the parser will actually refuse.

        Only three dtypes can carry this band. ``_coerce`` takes any text for a
        ``str`` attribute, so "damaging" a country name produces a file that
        parses cleanly and a row that claims a defect nothing reported - which
        is worse than no example, because the answer key would then be wrong.
        Numbers and lists are the ones a parser can turn down, so those are the
        ones this picks.
        """
        for path in prefer:
            definition = base.attr_defs.get(path)
            if (definition is not None and not definition.safety_class
                    and definition.dtype in CORRUPTIBLE):
                return path
        for column in attr_columns:
            definition = base.attr_defs[column.name]
            if (not definition.safety_class
                    and definition.dtype in CORRUPTIBLE
                    and column.name in item["held"]
                    and applies_to_category(definition, item["cat"])):
                return column.name
        return ""

    # A machine can correct it: the value is present and unreadable. Taken from
    # variants that are *missing* it where possible, so the same row is also a
    # readiness gap with a sibling behind it - one row, both halves of the
    # story.
    ai_fix: list[tuple[dict, str, bool]] = []
    gap_rows: list[dict] = []
    for item in with_gap:
        target = corruptible(item, item["miss_open"])
        if target and len(ai_fix) < max(1, len(with_gap) // 2):
            ai_fix.append((item, target, target in item["miss_open"]))
        else:
            gap_rows.append(item)

    # A withdrawal never takes the last clearing line, and never the only line
    # a supplier has. A report that cleared nothing reads as a broken supplier
    # rather than as a withdrawn product, and the whole point of the blocked
    # row is that it stands out against rows that did not block. So the
    # candidates are everything except the first complete line, and a supplier
    # with one or two lines gets no withdrawal at all - which the answer key
    # says, rather than the file quietly not having one.
    want = 2 if len(existing) >= 8 else 1 if len(existing) >= 3 else 0
    spare_complete = complete[1:] if len(complete) > 1 else []
    blocked = spare_complete[len(spare_complete)
                             - min(want, len(spare_complete)):]
    # A gap row may be spent on the withdrawal, but only while something else
    # is still there to clear or to be corrected. A supplier whose every line
    # came back blocked is a report about nothing.
    keep_back = 0 if (complete or ai_fix) else 1
    if len(blocked) < want and len(gap_rows) > keep_back:
        # Falling back to a line that is short of a value, and only ever while
        # leaving one behind. A withdrawal is assessed before its gaps are
        # collected - `assess` stops at the gate - so a blocked row spends a
        # gap the report would otherwise have shown, and spending the last one
        # trades a whole band for a duplicate of one already present.
        extra = min(want - len(blocked), len(gap_rows) - keep_back)
        blocked = blocked + gap_rows[len(gap_rows) - extra:]
    gap_rows = [g for g in gap_rows if g not in blocked]
    clean = [s for s in complete if s not in blocked]

    # The machine-correctable band is the one every supplier can show, because
    # it is a fact about the *file* rather than about the record: a value that
    # will not parse is reported by line and column whether or not the catalog
    # already holds a good one. Where every line a supplier owns is already
    # complete there is no gap to demonstrate it on, so the example moves onto
    # a clearing row - and the answer key says which of the two it is, because
    # the difference is exactly whether anything downstream is left to fix.
    for item in list(clean):
        # Never the last clearing line: this band moves a row out of "clears"
        # and into "a cell was refused", and a supplier with nothing left in
        # the first column has been made to look worse than its file is.
        if len(ai_fix) >= 2 or len(clean) <= 1:
            break
        target = corruptible(item, [])
        if not target:
            continue
        ai_fix.append((item, target, False))
        clean.remove(item)

    # Still nothing to mistype. Clothing & Footwear declares no numeric
    # attribute, so the demonstration moves from a bad value to a column that
    # does not belong here - which is the same class of problem arriving a
    # different way, and the commoner one in a house that keeps one sheet for
    # everything.
    if len(ai_fix) < 2:
        held_columns = {c.name for c in attr_columns}
        for path, value in STRAY_COLUMNS:
            if path not in held_columns and path in base.attr_defs:
                plan.stray[path] = value
                break

    def row_for(item: dict) -> dict:
        row = blank_row()
        product = base.products[item["pid"]]
        variant = base.variants[item["vid"]]
        row["product_ref"] = product.id
        row["product_name"] = product.name
        row["sku"] = item["sku"]
        row["variant_name"] = variant.name or product.name
        row["is_base"] = "true" if variant.id.endswith("A") else "false"
        row["category"] = item["cat"]
        return row

    for item in clean:
        row = row_for(item)
        fill(row, item["cat"], item["held"])
        attach(row, item["sku"], row["variant_name"], item["cat"])
        plan.rows.append(row)
        plan.expected.append({
            "sku": item["sku"], "band": "CLEARS",
            "why": "every attribute the category declares is supplied and "
                   "typed correctly, with the imagery the branch requires"})

    for item, target, opens_a_gap in ai_fix:
        row = row_for(item)
        plan.fix_targets.add(target)
        definition = base.attr_defs[target]
        good = render(item["held"].get(target)
                      if not opens_a_gap
                      else synth(target, definition, item["cat"], bank, rng),
                      definition.dtype)
        bad, why = corrupt(good, definition, rng)
        fill(row, item["cat"], item["held"], malformed={target: bad})
        attach(row, item["sku"], row["variant_name"], item["cat"])
        plan.rows.append(row)
        plan.expected.append({
            "sku": item["sku"], "band": "MACHINE_CORRECTABLE",
            "why": f"{target} arrives as {bad!r} - {why}. The cell is rejected "
                   f"by line and column and the rest of the row lands. "
                   + ("The record has no value for this attribute either, so "
                      "the correction closes a readiness gap as well as a "
                      "cell" if opens_a_gap else
                      "The catalog already holds a good value here, so the "
                      "correction is to the file rather than to the record")})

    for item in media_short:
        row = row_for(item)
        fill(row, item["cat"], item["held"])
        attach(row, item["sku"], row["variant_name"], item["cat"])
        plan.rows.append(row)
        wanted = [r for r in required_roles if r not in item["media"]]
        plan.expected.append({
            "sku": item["sku"], "band": "NEEDS_A_PERSON",
            "why": f"the record holds no {', '.join(w.lower() for w in wanted)} "
                   f"image and {branch} cannot launch without one. The bundle "
                   f"carries the file; see the note on the portal's media path "
                   f"in the pack README before reading the verdict"})

    for item in gap_rows:
        row = row_for(item)
        target = item["miss_open"][0]
        fill(row, item["cat"], item["held"], skip={target})
        attach(row, item["sku"], row["variant_name"], item["cat"])
        plan.rows.append(row)
        backed = target in item["sib_backed"]
        plan.expected.append({
            "sku": item["sku"], "band": "SMALL_GAP_CORROBORATED",
            "why": f"{target} is blank" + (
                "; a sibling variant of the same product holds it, which is the "
                "SIBLING prior a proposal is scored from"
                if backed else "; nothing on file corroborates it, so it goes "
                               "to the supplier rather than to a proposal")})

    for index, item in enumerate(blocked):
        row = row_for(item)
        fill(row, item["cat"], item["held"],
             malformed={"compliance.sale_permitted": "false"})
        note = WITHDRAWAL_NOTES[index % len(WITHDRAWAL_NOTES)]
        if "claims" in row:
            row["claims"] = FORBIDDEN_CLAIMS[index % len(FORBIDDEN_CLAIMS)]
        attach(row, item["sku"], row["variant_name"], item["cat"])
        plan.rows.append(row)
        plan.notes.append(f"{item['sku']}: {note}")
        plan.expected.append({
            "sku": item["sku"], "band": "NEEDS_A_PERSON",
            "why": "compliance.sale_permitted is false - a withdrawal notice. "
                   "checks.sale_permitted raises it BLOCKING and gate stops "
                   "onboarding on the authority of a regulation"})

    # ---- new lines the catalog does not hold ------------------------------
    leaves = sorted({c for c in pack.taxonomy
                     if c.startswith(f"{branch}.") and c.count(".") == 2})
    own = sorted({s["cat"] for s in existing}) or leaves[:2]
    # What they already sell first, then the nearest thing they do not: a
    # supplier's next line is usually beside its last one.
    ordered = own + [leaf for leaf in leaves if leaf not in own]
    prefix = re.sub(r"[^A-Z]", "", sup_name.upper())[:3] or "SUP"
    serial = 900

    def new_line(category: str, kind: str) -> None:
        nonlocal serial
        serial += 1
        label = pack.taxonomy.get(category, category)
        noun = rng.choice(nouns_for(category, label))
        product_name = f"{sup_name.split()[0]} {noun}"
        ref = f"PRD-{prefix}{serial}"
        variants = 2 if rng.random() < 0.45 else 1
        for index in range(variants):
            sku = f"{prefix}-{serial}-{chr(ord('A') + index)}"
            row = blank_row()
            row["product_ref"] = ref
            row["product_name"] = product_name
            row["sku"] = sku
            row["variant_name"] = (product_name if index == 0
                                   else f"{product_name} "
                                        f"{rng.choice(VARIANT_WORDS)}")
            row["is_base"] = "true" if index == 0 else "false"
            row["category"] = category

            skip: set[str] = set()
            malformed: dict[str, str] = {}
            band, why = "CLEARS", ("a new line with everything the category "
                                   "declares; a reviewer accepts it and it is "
                                   "complete on arrival")
            if kind == "safety" and index == 0:
                safety = [c.name for c in attr_columns
                          if base.attr_defs[c.name].safety_class
                          and applies_to_category(base.attr_defs[c.name],
                                                  category)]
                if safety:
                    skip.add(safety[0])
                    band = "NEEDS_A_PERSON"
                    why = (f"{safety[0]} is a safety-class declaration and is "
                           f"blank. fixable.assess refuses to make it a "
                           f"candidate at all - only the supplier can answer it")
            elif kind == "gap" and index == 0:
                open_attrs = [c.name for c in attr_columns
                              if not base.attr_defs[c.name].safety_class
                              and applies_to_category(base.attr_defs[c.name],
                                                      category)]
                if open_attrs:
                    skip.add(rng.choice(open_attrs))
                    band = "SMALL_GAP_CORROBORATED"
                    why = (f"{sorted(skip)[0]} is blank on a proposed line; "
                           f"the catalog's other lines in {category} are what "
                           f"a proposal would be scored against")

            fill(row, category, {}, skip=skip, malformed=malformed)
            missing_role = ""
            if kind == "media" and index == 0 and required_roles:
                missing_role = required_roles[-1]
                band = "NEEDS_A_PERSON"
                why = (f"the sheet names a {missing_role.lower()} image the "
                       f"archive does not hold; {branch} cannot launch without "
                       f"it and no value fixes a missing photograph")
            roles = [r for r in image_roles if r != missing_role]
            attach(row, sku, row["variant_name"], category, roles=roles,
                   declare_missing=missing_role)
            plan.rows.append(row)
            plan.expected.append({
                "sku": sku, "band": band,
                "why": f"proposed new line ({category}). {why}"})

    kinds = ["clean", "gap", "safety", "clean", "media", "gap"]
    for index, kind in enumerate(kinds):
        new_line(ordered[index % len(ordered)], kind)

    # ---- the file's own untidiness ----------------------------------------
    present = {c.name for c in attr_columns}
    for path, (column, why) in FOREIGN_COLUMNS.items():
        if path in plan.fix_targets:
            continue
        if path in present and len(plan.foreign) < 2:
            plan.foreign[column] = path
            plan.notes.append(f"column {column!r} is {path} - {why}")
    spare_name, spare_values = SPARE_COLUMNS[
        int(hashlib.sha256(supplier.encode()).hexdigest()[:4], 16)
        % len(SPARE_COLUMNS)]
    plan.spare[spare_name] = spare_values

    # Two photographs nobody named. Sent by the studio, referenced by nothing:
    # reported as unreferenced rather than silently dropped.
    for role in required_roles[:1]:
        for tag in ("supersede", "alt"):
            name = f"{plan.supplier.lower()}-{tag}-{role.lower()}.svg"
            plan.images[name] = svg(f"{plan.supplier}-{tag}", sup_name, role,
                                    f"{branch}.")
    return plan


# ---------------------------------------------------------------------------
# Imagery
# ---------------------------------------------------------------------------


def svg(sku: str, name: str, role: str, category: str) -> str:
    """One product image, in the same hand the catalog's own media is drawn in.

    Imported rather than reimplemented: a second renderer is a second visual
    language, and the point of the roles being distinct is that a reviewer can
    tell a pack front from an ingredient panel at a glance.
    """
    from scripts.generate_data import render_media_svg

    words = role.replace("_", " ").lower()
    return render_media_svg(
        {"entity_id": sku, "role": role, "alt_text": f"{name} - {words}"},
        name, sku, category)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def matrix(plan: Plan, base) -> list[list[str]]:
    """The whole data file as rows of strings, header block included."""
    from sc.datapack.schema import columns_for

    columns = list(columns_for(plan.branch, base))
    names, labels, markers = [], [], []
    for column in columns:
        if column.name in plan.foreign.values():
            continue          # sent under the sending system's own name below
        names.append(column.name)
        labels.append(column.heading)
        markers.append(column.marker())
    for foreign, path in plan.foreign.items():
        definition = base.attr_defs[path]
        names.append(foreign)
        labels.append(definition.label)
        markers.append("optional")
    for spare in plan.spare:
        names.append(spare)
        labels.append(spare)
        markers.append("optional")
    for path in plan.stray:
        names.append(path)
        labels.append(base.attr_defs[path].label)
        markers.append("optional")

    rng = random.Random(f"{SEED}:{plan.supplier}:cells")
    out = [names, labels, markers]
    for index, row in enumerate(plan.rows):
        line = []
        for name in names:
            if name in plan.foreign:
                value = row.get(plan.foreign[name], "")
            elif name in plan.spare:
                pool = plan.spare[name]
                value = pool[index % len(pool)]
            elif name in plan.stray:
                # Two rows only. A column mapped in by mistake is a mistake in
                # the mapping, not in every product, and twenty identical
                # rejections would bury the rest of the report.
                value = plan.stray[name] if index < 2 else ""
            else:
                value = row.get(name, "")
            line.append(_messy(value, rng) if value else value)
        out.append(line)
    return out


def write_csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def write_txt(rows: list[list[str]]) -> bytes:
    lines = [" | ".join(str(cell).replace("|", "/") for cell in row)
             for row in rows]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def write_xlsx(rows: list[list[str]]) -> bytes:
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Products"
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


WRITERS = {"csv": write_csv, "txt": write_txt, "xlsx": write_xlsx}


def covering_note(plan: Plan) -> str:
    lines = [
        f"From: {plan.name} ({plan.supplier})",
        f"Subject: product data submission - {len(plan.rows)} lines",
        "",
        "Please find our latest product file attached. The sheet covers the",
        "lines we currently supply plus the new lines we discussed.",
        "",
    ]
    if plan.notes:
        lines.append("Notes on this submission:")
        lines += [f"  - {note}" for note in plan.notes]
        lines.append("")
    lines += [
        "Anything missing from the sheet we can send separately - some of the",
        "fields you ask for are not held in our system in the shape you want",
        "them, and we have sent what we have.",
        "",
        "Regards,",
        f"Data & Compliance, {plan.name}",
    ]
    return "\r\n".join(lines) + "\r\n"


def specification(plan: Plan, base) -> str:
    lines = [f"# {plan.name} - product specification",
             "",
             f"Supplier: {plan.supplier}",
             f"Branch: {plan.branch}",
             f"Lines in this submission: {len(plan.rows)}",
             "",
             "| SKU | Product | Category |",
             "| --- | ------- | -------- |"]
    for row in plan.rows:
        lines.append(f"| {row['sku']} | {row['product_name']} | "
                     f"{row['category']} |")
    lines += ["", "Values are as held in our own system. Where a field is",
              "blank we do not hold it in the format requested.", ""]
    return "\n".join(lines)


def price_list(plan: Plan, rng: random.Random) -> str:
    """A second file in the supplier's own shape, deliberately not the feed.

    Lives under ``docs/`` rather than at the root, because the root is where
    ``read._data_member`` looks for the one data file and a second one there
    refuses the whole bundle by name. That refusal is correct - picking one
    would be picking a supplier's catalogue for them - so the price list is
    carried where a person can open it and the parser will not.
    """
    out = ["Item Code,Description,Pack,Cost Price,Currency,Lead Time (days)"]
    for row in plan.rows:
        out.append(f"{row['sku']},{row['product_name']},"
                   f"{rng.choice(['1','6','12','24'])},"
                   f"{rng.uniform(0.8, 240):.2f},GBP,{rng.randint(3, 45)}")
    return "\r\n".join(out) + "\r\n"


def expected_md(plan: Plan) -> str:
    order = ["CLEARS", "MACHINE_CORRECTABLE", "SMALL_GAP_CORROBORATED",
             "NEEDS_A_PERSON"]
    heading = {
        "CLEARS": "Clears on arrival",
        "MACHINE_CORRECTABLE": "A machine can correct it",
        "SMALL_GAP_CORROBORATED": "A little is missing, something agrees",
        "NEEDS_A_PERSON": "A person has to look",
    }
    lines = [f"# {plan.supplier} - {plan.name}", "",
             "What each row in this bundle is here to do. This file is **not**",
             "inside the .zip: it is the answer key, not part of the submission.",
             ""]
    for band in order:
        rows = [e for e in plan.expected if e["band"] == band]
        if not rows:
            continue
        lines += [f"## {heading[band]} ({len(rows)})", ""]
        for entry in rows:
            lines.append(f"- **{entry['sku']}** - {entry['why']}")
        lines.append("")
    if plan.stray:
        lines += ["## A column from another branch", ""]
        for path, value in plan.stray.items():
            lines.append(
                f"- `{path}` is carried on the first two rows with the value "
                f"`{value}`. The parser knows the column and the category does "
                f"not take it, so each is reported by line and column as "
                f"*does not apply*. This is the machine-correctable defect for "
                f"a branch that declares no numeric attribute to mistype.")
        lines.append("")
    if plan.foreign:
        lines += ["## Columns in a sending system's vocabulary", ""]
        for column, path in plan.foreign.items():
            lines.append(f"- `{column}` carries `{path}`. Reported as an "
                         f"unknown column; the bundle is not refused over it.")
        lines.append("")
    lines += ["## Also in this file", "",
              f"- format: `{plan.fmt}`",
              f"- a spare column (`{', '.join(plan.spare)}`) nobody removed",
              "- two images in `images/` that no row names",
              "- trailing spaces, and `TRUE`/`Yes`/`Y` in one boolean column",
              ""]
    return "\n".join(lines)


def slug(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", text)


def write_pack(plan: Plan, base) -> dict:
    """One supplier's folder and the .zip beside it."""
    folder = OUT / f"{plan.supplier}_{slug(plan.name)}"
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "images").mkdir(parents=True)
    (folder / "docs").mkdir()

    data_name = f"{plan.branch}.{plan.fmt}"
    payload = WRITERS[plan.fmt](matrix(plan, base))
    (folder / data_name).write_bytes(payload)

    for name, body in sorted(plan.images.items()):
        if name in plan.declared_images and name not in plan.images:
            continue
        (folder / "images" / name).write_text(body, encoding="utf-8")

    rng = random.Random(f"{SEED}:{plan.supplier}:price")
    docs = {
        f"{slug(plan.name)}-covering-note.txt": covering_note(plan),
        f"{slug(plan.name)}-specification.md": specification(plan, base),
        "price-list.csv": price_list(plan, rng),
    }
    for name, body in docs.items():
        (folder / "docs" / name).write_text(body, encoding="utf-8")

    (folder / "EXPECTED.md").write_text(expected_md(plan), encoding="utf-8")

    # The archive: exactly one data file at the root, images beside it, and the
    # supplier's own paperwork under docs/ where the parser will not look.
    archive_path = OUT / f"{plan.supplier}_{slug(plan.name)}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(data_name, payload)
        for name, body in sorted(plan.images.items()):
            archive.writestr(f"images/{name}", body.encode("utf-8"))
        for name, body in docs.items():
            archive.writestr(f"docs/{name}", body.encode("utf-8"))

    counts: dict[str, int] = {}
    for entry in plan.expected:
        counts[entry["band"]] = counts.get(entry["band"], 0) + 1
    return {
        "supplier": plan.supplier, "name": plan.name, "branch": plan.branch,
        "format": plan.fmt, "rows": len(plan.rows),
        "images": len(plan.images),
        "missing_images": len(plan.declared_images - set(plan.images)),
        "zip": archive_path.name, "folder": folder.name, "bands": counts,
    }


# ---------------------------------------------------------------------------
# Measuring the estate, so a band is grounded rather than asserted
# ---------------------------------------------------------------------------


def measure(base) -> dict[str, list[dict]]:
    """Every supplier's variants, with what the record actually holds.

    The bands below are built from this rather than from a guess. A bundle
    cannot *remove* a value - intake only ever adds - so "leave it blank and a
    gap appears" is only true where the record is already short of it, and the
    only way to know that is to read the record.
    """
    import sc.readiness as readiness
    from sc.readiness import record as record_mod
    from sc.state import overlay as overlay_mod
    from sc.state.baseline import applies_to_category

    overlay = overlay_mod.cached(record_mod._instant(None), None)
    ids = list(base.variants)
    records = record_mod.build_many(ids, overlay=overlay, base=base)

    by_supplier: dict[str, list[dict]] = {}
    grouped: dict[str, list[str]] = {}
    for vid in ids:
        product = base.products.get(base.product_of_variant.get(vid, ""))
        if product is None:
            continue
        grouped.setdefault(product.supplier, []).append(vid)

    for supplier, vids in grouped.items():
        rows = []
        for vid in sorted(vids):
            record = records.get(vid)
            if record is None:
                continue
            product = base.products[base.product_of_variant[vid]]
            summary = readiness.assess(vid, use_model=False,
                                       include_record=False, record=record,
                                       base=base)
            applicable = [p for p, d in base.attr_defs.items()
                          if applies_to_category(d, product.category)]
            missing = [p for p in applicable if p not in record.values]
            siblings = [o for o in vids
                        if base.product_of_variant.get(o) == product.id
                        and o != vid and o in records]
            rows.append({
                "vid": vid, "sku": base.variants[vid].sku, "pid": product.id,
                "cat": product.category,
                "verdict": (summary or {}).get("verdict", ""),
                "held": dict(record.values),
                "miss_open": [p for p in missing
                              if not base.attr_defs[p].safety_class],
                "miss_safe": [p for p in missing
                              if base.attr_defs[p].safety_class],
                "sib_backed": [p for p in missing
                               if any(p in records[o].values for o in siblings)],
                "media": sorted(str(a.role) for a in record.media),
            })
        by_supplier[supplier] = rows
    return by_supplier


# ---------------------------------------------------------------------------
# Grading what was written, with the real intake and the real report
# ---------------------------------------------------------------------------


def verify(results: list[dict]) -> int:
    """Submit every bundle and print what the system said about it.

    Runs against a scratch database seeded from the tape. The bundles land
    with the clock short of the end and are graded after it is wound on, which
    is the sequence a live venue is in by simply continuing to play - and the
    only sequence in which a submission's own values are visible to the as-of
    read that grades them.
    """
    import base64

    from sc import db
    from sc.estate import intake
    from sc.onboarding import assess as assess_mod
    from sc.replay import tape

    db.init_db(drop=True)
    tape.load_tape(reset=True)
    # Short of the end on purpose. A submission is stamped with the replay
    # clock and does not move it, so a report read at the same instant is read
    # a microsecond *before* the bundle it is grading - which is why a bundle
    # looks like it changed nothing until the tape moves on. Landing the
    # bundles here and winding to the end afterwards is what a live venue does
    # by simply continuing to play, and it is the only way this grader sees
    # the file it just wrote.
    tape.jump_to(max(0, tape.last_tape_seq() - 3))
    print(f"\nsubmitting with the clock at {tape.sim_now()}")
    header = (f"{'supplier':9} {'rows':>4} {'ok':>3} {'rej':>4} {'unk':>4} "
              f"{'img?':>4} {'new':>4} | {'clear':>5} {'return':>6} "
              f"{'block':>5} {'stop':>4} {'gaps':>4}")

    failures = 0
    landed: list[tuple[dict, dict]] = []
    totals = {k: 0 for k in ("clear", "return", "block", "stop", "gaps",
                             "rejected", "unknown", "drafts")}
    for entry in results:
        path = OUT / entry["zip"]
        raw = path.read_bytes()
        result = intake.submit_product_feed(
            supplier=entry["supplier"], system_id="supplier-portal",
            filename=path.name, content_base64=base64.b64encode(raw).decode())
        if not result.get("accepted"):
            print(f"{entry['supplier']:9} REFUSED: {result.get('error')}")
            failures += 1
            continue
        landed.append((entry, result))

    tape.jump_to(10 ** 6)
    print(f"grading with the clock at {tape.sim_now()}\n")
    print(header)
    print("-" * len(header))

    for entry, result in landed:
        rows = result["rows"]
        report = assess_mod.report(result["batch_id"]) or {}
        tally = report.get("totals") or {}
        products = report.get("products") or []
        stopped = sum(1 for p in products
                      if (p.get("gate") or {}).get("outcome") == "STOPPED")
        gaps = sum(p.get("gaps", 0) for p in products)
        print(f"{entry['supplier']:9} {rows['read']:4} {rows['accepted']:3} "
              f"{rows['rejected_cells']:4} {len(rows['unknown_columns']):4} "
              f"{len(result['images']['missing']):4} {rows['drafts']:4} | "
              f"{tally.get('cleared', 0):5} {tally.get('returned', 0):6} "
              f"{tally.get('blocked', 0):5} {stopped:4} {gaps:4}")
        totals["clear"] += tally.get("cleared", 0)
        totals["return"] += tally.get("returned", 0)
        totals["block"] += tally.get("blocked", 0)
        totals["stop"] += stopped
        totals["gaps"] += gaps
        totals["rejected"] += rows["rejected_cells"]
        totals["unknown"] += len(rows["unknown_columns"])
        totals["drafts"] += rows["drafts"]

    print("-" * len(header))
    print(f"totals: {json.dumps(totals)}")
    db.close()
    return failures


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="submit every bundle through the real intake and "
                             "print what the onboarding report said")
    parser.add_argument("--only", default="",
                        help="one supplier id, for a quick loop")
    args = parser.parse_args()

    from sc import db
    from sc.datapack import schema
    from sc.replay import tape
    from sc.state import baseline as baseline_mod

    # Seeded from the tape and wound to the end. Two reasons, both load
    # bearing: the record state a band is built from is then reproducible
    # rather than whatever the app happened to have replayed, and it is the
    # same state ``--verify`` grades in - so the answer key and the grader
    # cannot be looking at two different catalogs.
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    tape.jump_to(10 ** 6)
    print(f"catalog wound to {tape.sim_now()} in "
          f"{os.environ['DB_PATH']}")


    base = baseline_mod.get()
    pack = schema.build(base)
    profile = base.catalog.profile or {}
    roster = {s["id"]: s for s in (profile.get("suppliers") or [])}
    for node in base.catalog.nodes:
        if str(getattr(node, "kind", "")).endswith("SUPPLIER"):
            roster.setdefault(node.id, {"id": node.id,
                                        "name": node.name or node.id,
                                        "branch": node.group or ""})

    state = measure(base)
    suppliers = sorted(s for s in roster
                       if s not in NOT_A_TRADING_SUPPLIER and s in state)
    if args.only:
        suppliers = [s for s in suppliers if s == args.only]

    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for index, supplier in enumerate(suppliers):
        rows = state[supplier]
        # The branch they actually trade in, taken from their own lines rather
        # than from the roster's label: the roster calls Wrenfield "apparel"
        # and its lines are home textiles, and the template has to match the
        # lines.
        branches = {}
        for row in rows:
            head = row["cat"].split(".")[0]
            branches[head] = branches.get(head, 0) + 1
        branch = max(branches, key=lambda b: branches[b])
        name = roster[supplier].get("name") or supplier
        fmt = FORMATS[index % len(FORMATS)]
        rng = random.Random(f"{SEED}:{supplier}")
        plan = build_plan(supplier, name, branch, fmt, base, rows,
                          value_bank(base, branch), pack, rng)
        results.append(write_pack(plan, base))
        print(f"  {supplier:8} {name:32} {branch:12} {fmt:5} "
              f"{len(plan.rows):3} rows  {len(plan.images):3} images")

    (OUT / "MANIFEST.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    with (OUT / "MANIFEST.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["supplier", "name", "branch", "format", "rows",
                         "images", "zip", "clears", "machine_correctable",
                         "small_gap", "needs_a_person"])
        for entry in results:
            bands = entry["bands"]
            writer.writerow([
                entry["supplier"], entry["name"], entry["branch"],
                entry["format"], entry["rows"], entry["images"], entry["zip"],
                bands.get("CLEARS", 0), bands.get("MACHINE_CORRECTABLE", 0),
                bands.get("SMALL_GAP_CORROBORATED", 0),
                bands.get("NEEDS_A_PERSON", 0)])

    readme_mod.write(results, OUT)
    print(f"\n{len(results)} packs written to {OUT}")
    if args.verify:
        return verify(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
