"""The rest of the catalog.

Six products is the right size for a story and the wrong size for a system.
Every question the Ingest Fabric and Product 360 exist to answer - which
supplier is holding a launch up, how much of last week's intake came in clean,
which category the data pool keeps mangling - is a question about a population,
and a population of six answers all of them by pointing at the same two rows.

So this generates the background: a few hundred products the demo never talks
about, so that the six it does talk about have somewhere to be.

Three rules govern everything here.

**The hero products are untouched.** PRD-01 to PRD-06, their variants, their
attributes, their copy and the six arcs that move them are hand-authored and
stay that way. Background entities are numbered from 101 so the two are
distinguishable at a glance, and nothing here writes into the hero ranges.

**It draws from its own stream.** The generator's module-level `rng` is
consumed in a fixed order by the arcs, and a background catalog drawing from
it would shift every subsequent draw - changing which supplier sent which
routine feed, and with it every event id. A separate stream seeded off the same
seed keeps the pack reproducible without making the hero narrative depend on
how many background products there happen to be.

**Its damage is declared.** The point of the background is not volume, it is
*contrast*: some products are fit to publish and some are not, and the ones
that are not have to be wrong in ways the nine checks actually detect. Every
defect seeded here is drawn from that closed set and recorded in
`SEEDED_DEFECTS`, so the pack's own self-checks can assert that what the
catalog contains is exactly what was asked for - the same property the
extraction answer key has.

What is deliberately *not* done here is break a channel rule. The publish-time
validator's contract is that the untouched catalog produces zero violations,
and that is what makes the one seeded landmine meaningful. Background products
are publishable and some of them are not *ready*, which are different
questions asked by different code - which is the distinction the readiness
surface was built to draw.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The assortment, from the retailer profile
# ---------------------------------------------------------------------------
# None of this is hardcoded any more. `data/profiles/<id>.json` says who the
# retailer buys from, what it sells and how its categories are labelled, and
# `RETAILER_PROFILE` picks the file. A supplier is still a proper noun and a
# product is still a product line somebody could read off a shelf edge - what
# changed is that they are data, so pointing the demo at a different retailer
# is a new profile rather than an edit here.

import importlib.util as _ilu
from pathlib import Path as _Path

_spec = _ilu.spec_from_file_location(
    "seed_retailer", _Path(__file__).resolve().parent / "retailer.py")
retailer = _ilu.module_from_spec(_spec)          # type: ignore[arg-type]
_spec.loader.exec_module(retailer)               # type: ignore[union-attr]

PROFILE = retailer.PROFILE

#: id, name, branch - in profile order, because the draw walks it.
SUPPLIERS = retailer.suppliers()

#: Every node, including the branch roots. The generator merges this over its
#: own hand-authored hero nodes, so the profile is the source of truth for a
#: label the two might otherwise disagree about.
TAXONOMY = retailer.taxonomy()

def _interleave(rows: list[tuple[str, str, bool]]) -> list[tuple[str, str, bool]]:
    """Deal the assortment round-robin across branches.

    The profile lists lines branch by branch, because that is how somebody
    writes and reads one. Walking that order and stopping at `COUNT` would
    build a catalog of groceries and clothes with no pharmacy in it at all -
    the branches that happen to be written last would simply not exist.

    Dealing instead means the cut falls proportionally: every branch is
    represented, the big ones stay big, and which lines are left over is a
    property of the assortment rather than of the order somebody typed it in.
    """
    by_branch: dict[str, list[tuple[str, str, bool]]] = {}
    for row in rows:
        by_branch.setdefault(row[0].split(".")[0], []).append(row)
    order = sorted(by_branch)
    out: list[tuple[str, str, bool]] = []
    for i in range(max(len(v) for v in by_branch.values())):
        for branch in order:
            if i < len(by_branch[branch]):
                out.append(by_branch[branch][i])
    return out


#: The catalogue, as `(leaf, product line, is_own_brand)`. 180 lines for 144
#: products, so no line is used twice and the mix is a real assortment rather
#: than a formula with the numbers filed off.
LINES = _interleave(retailer.lines())

_BRANCHES = retailer.branches()
_VOCAB = PROFILE["vocabularies"]
_OWN = retailer.own_brand()


def _branch(leaf: str) -> str:
    return leaf.split(".")[0]


def _mkt_a_code(leaf: str) -> str:
    """Marketplace A's own category code for one of our leaves.

    Derived rather than hand-listed: the code is opaque to a reader either way,
    and 88 hand-written mappings is 88 chances to leave one out and discover it
    as a CATEGORY_MAPPED violation on a product nobody was looking at.
    """
    branch = _branch(leaf)
    base = 1000 + 100 * sorted(_BRANCHES).index(branch)
    within = 10 * (sorted(k for k in TAXONOMY if k.startswith(f"{branch}."))
                   .index(leaf) + 1)
    label = TAXONOMY[leaf].split(" > ")[-1]
    return f"{base}/{2000 + within} {label}"


def _mkt_b_path(leaf: str) -> str:
    """Marketplace B's taxonomy is flatter than ours - two levels, always."""
    parts = leaf.split(".")
    return f"{parts[0]}/{parts[-1]}"


#: Only leaves that carry a product line need a mapping; a node nothing sits in
#: cannot be listed against. Both marketplaces are given the same coverage, so
#: "this product is on one marketplace and not the other" stays a fact about
#: the channel draw rather than an artefact of a missing mapping.
_LEAVES_IN_USE = sorted({leaf for leaf, _n, _o in LINES})
MKT_A_CATS = {leaf: _mkt_a_code(leaf) for leaf in _LEAVES_IN_USE}
MKT_B_CATS = {leaf: _mkt_b_path(leaf) for leaf in _LEAVES_IN_USE}

# ---------------------------------------------------------------------------
# The vocabulary each branch's attributes are built from
# ---------------------------------------------------------------------------

FOOD = _VOCAB["food"]
INGREDIENTS = {k: list(v["ingredients"]) for k, v in FOOD.items()}
CONTAINS = {k: list(v["contains"]) for k, v in FOOD.items()}
MAY_CONTAIN = {k: list(v["may_contain"]) for k, v in FOOD.items()}

FILTERS = tuple(_VOCAB["filter_types"])
ENERGY = tuple(_VOCAB["energy_classes"])
FIBRES = tuple(tuple(f) for f in _VOCAB["fibre_composition"])
CARE_CODES = tuple(_VOCAB["care_codes"])
INCI = tuple(tuple(i) for i in _VOCAB["inci"])
ACTIVES = tuple(tuple(a) for a in _VOCAB["actives"])
PLUGS = tuple(_VOCAB["plug_types"])
BATTERIES = tuple(_VOCAB["battery_types"])
ORIGINS = tuple(_VOCAB["origins"])
CERT_PREFIXES = tuple(_VOCAB["certificate_prefixes"])

#: Which branches take a mains plug, a cell, a fibre label, an ingredient list.
#: Prefix tuples rather than branch names, because the line is drawn inside a
#: branch as often as between two - a kettle is mains and a knife is not.
MAINS = ("home.kitchen.", "home.laundry.", "home.floorcare.",
         "home.air-treatment.", "electronics.vision.",
         "electronics.computing.", "electronics.audio.soundbars")
CELLS = ("electronics.mobile.", "electronics.personal.", "electronics.audio.",
         "general.toys.", "baby.toys.", "health.devices.")
TEXTILE = ("apparel.", "home.textiles.")
COSMETIC = ("hpc.toiletries.", "hpc.cosmetics.")
MEDICINAL = ("health.medicines.", "health.supplements.")
CERTIFIED = ("electronics.", "home.kitchen.", "home.laundry.",
             "home.floorcare.", "home.air-treatment.", "general.toys.",
             "general.garden.", "general.diy.", "baby.toys.",
             "baby.feeding.bottles", "health.devices.")
#: Packaged goods declare a net quantity. A jumper does not.
PACKAGED = ("food.", "hpc.", "baby.feeding.", "baby.nappies.", "health.",
            "general.pet.", "general.diy.paint")

#: Copy that must never be published, planted so the forbidden-content check
#: has something to find outside the hand-authored six. Every phrase is one
#: `checks.FORBIDDEN_PHRASES` already knows, because a phrase no rule catches
#: is a defect nobody can act on.
BAD_SENTENCES = (
    "Clinically proven to improve the air you breathe.",
    "Completely safe for use around infants and pets.",
    "Guaranteed to cut your energy bill in half.",
    "Treats the causes of poor sleep, not just the symptoms.",
    "Prevents the build-up that causes odours, 100% effective.",
    "A harmless formulation that cures dry skin for good.",
)

# ---------------------------------------------------------------------------
# The declared damage
# ---------------------------------------------------------------------------
# Filled in as the catalog is built and read back by the generator's own
# checks, so "the background contains exactly the defects we asked for" is an
# assertion rather than a hope. Same idea as the extraction answer key: the key
# regenerates with the data instead of rotting behind it.

SEEDED_DEFECTS: dict[str, list[tuple[str, str]]] = {}


def _declare(entity_id: str, kind: str, subject: str) -> None:
    SEEDED_DEFECTS.setdefault(entity_id, []).append((kind, subject))


# ---------------------------------------------------------------------------
# Building it
# ---------------------------------------------------------------------------

#: How many background products. Enough that a tier of the map has to be paged
#: and a supplier filter has something to narrow; small enough that generating
#: the pack stays a few seconds and a full replay stays a demo rather than an
#: afternoon.
COUNT = 144

#: Roughly what share of background products are left short of something the
#: nine checks will find. The rest are clean, which is the half that makes the
#: finding meaningful - an estate where everything is suspect measures nothing.
DEFECT_SHARE = 0.42


def _gtin(n: int, broken: bool) -> str:
    """A GTIN-13, or something that is not one.

    The broken form is thirteen digits with a letter in the middle - which is
    what a spreadsheet export produces when a column was typed as text, and is
    caught by `declared_types` rather than by a checksum nobody has written.
    """
    body = f"50{n:011d}"
    return f"{body[:6]}X{body[7:]}" if broken else body


def build(rng, *, count: int = COUNT) -> dict:
    """Everything the background adds, as plain lists the generator splices in.

    `rng` is the caller's stream, not the module-level one - see the note at the
    top of this file about why that matters.
    """
    products: list[tuple] = []
    variants: list[tuple] = []
    skus: dict[str, str] = {}
    attr_rows: list[tuple] = []
    listing_channels: dict[str, list[str]] = {}
    prices: dict[str, float] = {}
    copy: dict[str, dict] = {}
    media_missing: set[tuple[str, str]] = set()
    source_docs: list[tuple] = []
    bad_assets: dict[str, str] = {}

    # One portal feed per background supplier. Every background attribute cites
    # it, so "which document asserted this" has an answer for these products
    # too - a value with no source is a value nobody can check.
    for i, (sid, name, _family) in enumerate(SUPPLIERS):
        source_docs.append((
            f"DOC-1{i:02d}", sid, "PORTAL_FEED", "v1",
            f"{name} portal attribute feed", -25 + i, 20, False))

    doc_of = {sid: f"DOC-1{i:02d}" for i, (sid, _n, _f) in enumerate(SUPPLIERS)}

    for n in range(count):
        pid = f"PRD-{101 + n}"
        # Walk the lines rather than sampling them: 180 lines for 144 products
        # means every product is a distinct thing somebody could buy, and no
        # two rows of the catalog are the same product with a different number
        # bolted on.
        leaf, line, own = LINES[n % len(LINES)]
        branch = _branch(leaf)
        candidates = [s for s in SUPPLIERS if s[2] == branch] or SUPPLIERS
        supplier = candidates[rng.randint(0, len(candidates) - 1)]
        name = f"{_OWN} {line}" if own else line
        regulated = retailer.is_regulated(leaf)

        products.append((pid, name, leaf, supplier[0], regulated))
        listing_channels[pid] = _channels_for(leaf, rng)

        # One to three variants. A catalog where every product has exactly one
        # cannot show the base-versus-variant question the whole correction
        # story turns on.
        for v in range(rng.randint(1, 3)):
            vid = f"VAR-{101 + n}{chr(ord('A') + v)}"
            variant_name = (name if v == 0
                            else f"{name} {_qualifier(leaf, v)}")
            variants.append((vid, pid, variant_name, v == 0))
            skus[vid] = f"{branch[:3].upper()}-{101 + n:03d}-{chr(ord('A') + v)}"
            prices[vid] = round(4 + rng.uniform(0, 180), 2)

            damaged = rng.chance(DEFECT_SHARE)
            rows = _attributes(vid, leaf, doc_of[supplier[0]], rng, damaged,
                               n + v)
            attr_rows.extend(rows)
            power = next((value for _e, path, value, *_r in rows
                          if path == "specs.power_w"), None)
            copy[vid] = _copy(variant_name, leaf, skus[vid], power)

            if damaged:
                _damage(vid, leaf, rng, media_missing, bad_assets, copy)

    return {
        "products": products,
        "variants": variants,
        "skus": skus,
        "attr_rows": attr_rows,
        "listing_channels": listing_channels,
        "prices": prices,
        "copy": copy,
        "media_missing": media_missing,
        "source_docs": source_docs,
        "bad_assets": bad_assets,
    }


#: How a second and third variant of one line differ. A jumper comes in
#: colours, a shampoo comes in sizes, a television comes in a bigger one -
#: and "Semi-Skimmed Milk 2 L Max" is the sort of name that tells a room the
#: catalog was generated.
_QUALIFIERS: tuple[tuple[tuple[str, ...], tuple[str, str]], ...] = (
    (("apparel.", "home.textiles."), ("Navy", "Charcoal")),
    (("food.", "hpc.", "baby.", "health.", "general.pet."),
     ("Multipack", "Large Pack")),
)


def _qualifier(leaf: str, v: int) -> str:
    for prefixes, words in _QUALIFIERS:
        if leaf.startswith(prefixes):
            return words[v - 1]
    return ("Plus", "Max")[v - 1]


def _declares_food(leaf: str) -> bool:
    """Does this leaf carry an ingredient and allergen declaration?

    Food does, and so does anything eaten that is not shelved with it - infant
    formula and weaning foods are in `baby.` because that is where a shopper
    looks for them, not because the labelling regime lets them off.
    """
    return leaf in FOOD


def _lists_allergens(leaf: str) -> bool:
    """Does this category have an allergen declaration to make?

    Marketplace A requires one and specifies its wording; Marketplace B
    requires the coded form. A product with nothing to declare cannot satisfy
    either, and that is the rule doing its job - a herbal tea genuinely does
    not belong on a feed whose schema assumes every food names an allergen. So
    it is kept off those two channels rather than given a declaration it has no
    basis for.
    """
    return not _declares_food(leaf) or bool(CONTAINS.get(leaf))


def _channels_for(leaf: str, rng) -> list[str]:
    """Which channels a background product is prepared for.

    Always the website, because everything has a product page. The rest varies,
    so that "this correction reaches four channels" and "this one reaches one"
    are both true of some product somebody can find.
    """
    channels = ["CH-WEB"]
    if rng.chance(0.55) and leaf in MKT_A_CATS and _lists_allergens(leaf):
        channels.append("CH-MKT-A")
    if rng.chance(0.40) and leaf in MKT_B_CATS and _lists_allergens(leaf):
        channels.append("CH-MKT-B")
    if rng.chance(0.30):
        channels.append("CH-SEARCH")
    if rng.chance(0.22):
        channels.append("CH-SHELF")
    if rng.chance(0.15):
        channels.append("CH-PRINT")
    return channels


#: Attributes whose declared type may be spoiled without breaking the
#: publish-time contract. Every one of these is optional at the category and
#: demanded by no channel, so a wrong type here is a readiness finding and
#: never a validator violation. `specs.power_w` is deliberately absent:
#: CH-MKT-A types it (RUL-A03), so spoiling it would break a listing.
_SPOILABLE = ("specs.noise_db", "specs.coverage_m2", "packaging.recyclable_pct",
              "food.net_weight_g", "food.fibre_g")

#: How each type is got wrong. Always the way a real export gets it wrong -
#: the unit typed into the cell, the percent sign kept - rather than noise,
#: because a reviewer has to recognise the mistake to fix it at source.
_SPOILED = {
    "specs.noise_db": lambda v: f"{v} dB",
    "specs.coverage_m2": lambda v: f"{v} m2",
    "packaging.recyclable_pct": lambda v: f"{v}%",
    "food.net_weight_g": lambda v: f"{v} g",
    "food.fibre_g": lambda v: f"{v}g",
}


def _spoil(path: str, value):
    return _SPOILED[path](value)


def _attributes(vid: str, leaf: str, doc: str, rng, damaged: bool,
                salt: int) -> list[tuple]:
    """One variant's values.

    Everything a channel *requires* is always present: a background product
    that could not be published would be breaking the validator's contract
    rather than failing a readiness check, and those are different claims made
    by different code. What gets left out is what the category declares and no
    channel demands - a sound level, a fibre label, a recyclability figure -
    which is exactly the gap `applicable_attributes` exists to report.

    The compliance attributes are the interesting half. `compliance.*` is
    safety-class, so a document that moves one inherits forced escalation,
    mandatory review, the fail-closed confidence gate and the redaction path
    without a line of new rule code. Here they are simply set to the state a
    product is in when nothing has gone wrong yet: on sale, correctly aged,
    not export-controlled. The arcs are what move them.
    """
    rows: list[tuple] = []

    def put(path: str, value) -> None:
        rows.append((vid, path, value, doc, "v1"))

    def pick(seq):
        return seq[rng.randint(0, len(seq) - 1)]

    # Required everywhere it applies, so it is never dropped.
    put("identifiers.gtin", _gtin(salt * 7 + 11, broken=False))

    # Every product is on sale until something says otherwise. Recorded rather
    # than inferred, so the fail-closed gate has nothing to fire on and the
    # baseline is publishable - which is what makes a later takedown legible
    # as a change rather than as a catalog that was always broken.
    put("compliance.sale_permitted", True)
    put("origin.country", pick(ORIGINS))

    age = retailer.minimum_age(leaf)
    if age is not None:
        put("compliance.min_age", age)

    if leaf in retailer.export_controlled():
        # "NONE" is a classification, not an absence. A product nobody has
        # classified and a product classified as unrestricted are different
        # states, and only one of them is safe to ship.
        put("compliance.export_control", "NONE")

    claimed: list[str] = []
    optional: list[str] = []
    values: dict[str, object] = {}

    def offer(path: str, value) -> None:
        """An attribute the category declares and no channel demands."""
        optional.append(path)
        values[path] = value

    if leaf.startswith(PACKAGED):
        put("pack.net_quantity", float(10 * rng.randint(3, 120)))
        put("pack.unit", "g" if rng.chance(0.7) else "ml")
        offer("packaging.recyclable_pct", 5 * rng.randint(4, 20))

    if leaf.startswith("home."):
        if leaf.startswith(MAINS):
            put("specs.power_w", 20 * rng.randint(2, 120))
            put("specs.plug_type", pick(PLUGS))
            offer("energy.class", pick(ENERGY))
        offer("specs.noise_db", rng.randint(28, 62))
        if leaf.startswith("home.air-treatment"):
            offer("specs.coverage_m2", 5 * rng.randint(4, 20))
            offer("specs.filter_type", pick(FILTERS))

    if leaf.startswith("electronics."):
        if leaf.startswith(MAINS):
            put("specs.power_w", rng.randint(15, 220))
            put("specs.plug_type", pick(PLUGS))
            offer("energy.class", pick(ENERGY))
        elif rng.chance(0.5):
            offer("specs.power_w", rng.randint(2, 40))

    if leaf.startswith(CELLS):
        put("specs.battery_type", pick(BATTERIES))

    if _declares_food(leaf):
        put("food.ingredients", list(INGREDIENTS[leaf]))
        put("food.allergens.contains", list(CONTAINS[leaf]))
        put("food.allergens.may_contain", list(MAY_CONTAIN[leaf]))
        if leaf.startswith("food."):
            # Declared against groceries only. Infant formula carries the same
            # ingredient and allergen statement, and its quantity is declared
            # as a pack net quantity rather than in the grocery vocabulary.
            offer("food.net_weight_g", 10 * rng.randint(3, 60))
            offer("food.fibre_g", round(rng.uniform(0.4, 9.5), 1))

    if leaf.startswith(TEXTILE):
        # Ordered, and the order is the declaration: a fibre label is read as
        # descending percentage, so reordering it says something different.
        put("textile.fibre_composition", list(pick(FIBRES)))
        offer("textile.care_code", pick(CARE_CODES))

    if leaf.startswith(COSMETIC):
        put("cosmetic.inci", list(pick(INCI)))

    if leaf.startswith(MEDICINAL):
        put("health.active_ingredient", list(pick(ACTIVES)))

    if leaf.startswith(CERTIFIED):
        offer("compliance.certificate_ref",
              f"{pick(CERT_PREFIXES)}-{2400 + rng.randint(1, 599)}")

    # The gap. One applicable attribute nobody sent, which is the single most
    # common thing wrong with a supplier's data and the reason
    # `applicable_attributes` is the first check in the list.
    #
    # Some of the time the supplier *did* answer and answered in the wrong
    # shape - a weight as "375 g", a percentage as "90%". That is a different
    # defect with a different remedy, and keeping the two apart is the whole
    # argument for a named finding over a quality score. Only attributes no
    # channel declares a dtype for are spoiled this way: a mistyped value the
    # publish-time validator would reject is a broken catalog, not a readiness
    # finding, and the two must not be confused.
    target = optional[rng.randint(0, len(optional) - 1)] if (
        damaged and optional) else None
    mistyped = (target is not None
                and target in _SPOILABLE
                and rng.chance(0.4))

    for path in optional:
        if path == target and not mistyped:
            _declare(vid, "applicable_attributes", path)
            continue
        if path == target:
            put(path, _spoil(path, values[path]))
            _declare(vid, "declared_types", path)
            continue
        put(path, values[path])

    # Claims apply to every category, so a variant with no claims value is a
    # variant with an open finding - which would have made "returned to source"
    # the verdict on almost the whole background and left nothing to contrast
    # it against. An empty list is the honest value: this supplier made no
    # claims about this product, which is a fact and not a gap.
    #
    # Anything actually claimed has to hold against the substantiation table,
    # because a claim the validator would refuse at publish is a claim the
    # reviewer approves and the channel rejects - the worst of both.
    held = {path: value for _e, path, value, *_r in rows}

    def figure(path: str):
        """The value as a number, or None if this variant's is spoiled.

        A claim rests on a value, and a value the supplier sent as "38 dB" is
        not one yet. Declining to claim on it is the correct reading: the
        record cannot substantiate what it cannot parse, and the wrong type is
        already reported as its own finding.
        """
        try:
            return float(str(held[path]).rstrip("%").strip())
        except (KeyError, TypeError, ValueError):
            return None

    if (noise := figure("specs.noise_db")) is not None and noise <= 40:
        claimed.append("ultra-quiet")
    if (power := figure("specs.power_w")) is not None and power <= 50:
        claimed.append("low-energy")
    if _declares_food(leaf):
        allergens = " ".join(str(a) for a in
                             (CONTAINS.get(leaf) or []) + (MAY_CONTAIN.get(leaf) or []))
        if "peanut" not in allergens:
            claimed.append("peanut-free")
        if "gluten" not in allergens and "wheat" not in " ".join(
                INGREDIENTS.get(leaf) or []):
            claimed.append("gluten-free")
        if (fibre := figure("food.fibre_g")) is not None and fibre >= 6:
            claimed.append("high-fibre")
    if held.get("origin.country") == "United Kingdom":
        claimed.append("made-in-britain")
    if (recyclable := figure("packaging.recyclable_pct")) is not None \
            and recyclable >= 90:
        claimed.append("recyclable-packaging")
    put("claims", claimed)

    return rows


def _declaration(leaf: str) -> str:
    """The allergen and ingredient sentence a food listing has to carry.

    Two rules bind here and both are safety rules, so neither is optional. Every
    allergen the record declares has to appear somewhere a shopper can read it,
    and any ingredient list written in prose has to be in the same order as the
    record's - because ingredient order is a declaration in itself, and a
    reordered one is a different declaration rather than the same one phrased
    differently.

    Empty for anything that is not food, which is why it composes.
    """
    if not _declares_food(leaf):
        return ""
    contains = CONTAINS.get(leaf) or []
    may = MAY_CONTAIN.get(leaf) or []
    parts = [f"Ingredients: {', '.join(INGREDIENTS[leaf])}."]
    if contains:
        parts.append(f"Contains: {', '.join(contains)}.")
    if may:
        parts.append(f"May contain: {', '.join(may)}.")
    return " " + " ".join(parts)


def _copy(name: str, leaf: str, sku: str, power: int | None = None) -> dict:
    """Prepared copy for a background product.

    Flat on purpose. Nobody reads it, it exists so the listing has something on
    it and so the blast radius of a correction has somewhere to land - and copy
    that tried to be interesting would quote figures, which would make every
    background product a landmine competing with the one the demo is about.
    """
    # "our biscuits range" reads better than "our food.bakery.biscuits range",
    # and the label the profile already carries is what a shopper would be
    # shown, so there is no second vocabulary to keep in step.
    words = TAXONOMY.get(leaf, leaf).split(" > ")[-1].lower()
    title = f"{name}"
    declaration = _declaration(leaf)
    return {
        "web_title": (title[:118], [], []),
        "mkt_title": (title[:78], [], []),
        "bullets": ([
            f"{name}, from our {words} range",
            "Supplied with a two-year manufacturer's warranty",
            "Backed by our standard returns policy",
        ], [], []),
        "description": (
            f"{name} ({sku}). Part of our {words} range. Full specification and "
            f"delivery options are shown on this page.{declaration}",
            (["food.ingredients", "food.allergens.contains",
              "food.allergens.may_contain"] if declaration else []), []),
        # RUL-S02: a shelf label for an appliance has to print the wattage,
        # because that is what the label is for. Trimmed to fit RUL-S01's
        # forty-character budget with the figure kept rather than the name.
        "shelf_text": (
            f"{name[:28]} {power}W" if power is not None else name[:38],
            ["specs.power_w"] if power is not None else [], []),
        "catalogue_copy": (
            f"{name}. Part of our {words} range.{declaration}"
            if declaration else
            f"{name}. Part of our {words} range, supplied with a two-year "
            f"manufacturer's warranty.",
            (["food.ingredients", "food.allergens.contains",
              "food.allergens.may_contain"] if declaration else []), []),
    }


def _damage(vid: str, leaf: str, rng, media_missing: set,
            bad_assets: dict, copy: dict) -> None:
    """The rest of what is wrong with a damaged product.

    Drawn from the same closed set the deterministic checks cover, because a
    defect no check detects is a defect nobody can act on - and one that only a
    human notices is worse, since it makes the check list look complete when it
    is not.
    """
    roll = rng.next()

    if roll < 0.45:
        # Imagery that never arrived. Which roles a category cannot launch
        # without is the profile's answer, the same way INT-001 is a reviewer's
        # - so a branch added to the profile gets a findable media gap without
        # anything here learning its name.
        needed = retailer.required_media().get(f"{_branch(leaf)}.", ("HERO",))
        role = needed[rng.randint(0, len(needed) - 1)]
        media_missing.add((vid, role))
        _declare(vid, "required_media", role)
    elif roll < 0.62:
        # A sentence that may never be published, whatever the supplier sent.
        # This is the one that produces BLOCKED rather than RETURN_TO_SOURCE,
        # because saleability is a statement about legality and not a tally.
        sentence = BAD_SENTENCES[rng.randint(0, len(BAD_SENTENCES) - 1)]
        text, refs, claims = copy[vid]["description"]
        copy[vid]["description"] = (f"{text} {sentence}", refs, claims)
        bad_assets[vid] = sentence
        _declare(vid, "forbidden_content", "description")
    # The remainder are damaged only by the attribute already dropped in
    # `_attributes`, which is a return to source on its own.


# ---------------------------------------------------------------------------
# Routine traffic for the rest of the catalog
# ---------------------------------------------------------------------------
# Two hundred and ninety-six events is what six products produce, and it is not
# what a flight recorder for a retailer looks like. This is the rest of the
# intake: price and stock feeds, publication telemetry, channel responses,
# localisation updates, dispatch confirmations and category signals, spread
# across the whole horizon.
#
# It draws from a stream of its own and touches only background entities, so
# the hero arcs' draws - and therefore the story - are byte-identical to what
# they were before any of this existed. That is the property that lets the
# volume grow without the demo having to be re-rehearsed.
#
# The event *types* are the six the tape already has, because ingestion reads
# those and an invented seventh would be a shape nothing downstream handles.
# What varies is who sends them and what they carry, which is where the systems
# tier gets its traffic: `emitter.owner_of` deals each event among the systems
# that declare they emit its type, so a COMMS event naming a product is what
# gives Market Signals an edge on the map instead of a box on its own.

#: Events per day of background traffic, before the per-kind draws. Sized so a
#: two-month horizon lands in the low thousands: enough that a day is busy and
#: a filter is worth having, not so much that the replay outlasts the demo.
PER_DAY = (55, 95)

SIGNAL_SUBJECTS = (
    "Category read: {name} moving on promotion",
    "Range review: {name} under consideration for delist",
    "Search demand up on {name}",
    "Competitor price move affecting {name}",
)

DISPATCH_NOTES = (
    "carrier booking confirmed",
    "pack configuration updated",
    "dispatch confirmed from the national distribution centre",
    "case dimensions restated by the carrier",
)


def traffic(rng, add, email, *, days: int, variants, listings, prices,
            product_of, supplier_of, name_of) -> None:
    """Emit the background's share of the tape through the caller's `add`.

    Deliberately written against the generator's own `add`/`email` closures
    rather than returning records: ids, ordering and the `@REF` resolution are
    the tape's business, and a second place that knew how to build an event
    record would be a second place to get it wrong.
    """
    variant_ids = [v[0] for v in variants]
    listing_ids = [l["id"] for l in listings]
    listing_by_id = {l["id"]: l for l in listings}
    if not variant_ids or not listing_ids:
        return

    for offset in range(days):
        for _ in range(rng.randint(*PER_DAY)):
            hour, minute = rng.randint(5, 22), rng.randint(0, 59)
            roll = rng.next()

            if roll < 0.34:
                vid = variant_ids[rng.randint(0, len(variant_ids) - 1)]
                supplier = supplier_of(vid)
                add(offset, hour, minute, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
                    "kind": "PRICE", "supplier": supplier, "entity_id": vid,
                    "doc_id": _doc_for(supplier), "doc_version": "v1",
                    "price": round(prices.get(vid, 10.0)
                                   * rng.uniform(0.94, 1.06), 2),
                    "currency": "GBP",
                })
            elif roll < 0.58:
                vid = variant_ids[rng.randint(0, len(variant_ids) - 1)]
                supplier = supplier_of(vid)
                add(offset, hour, minute, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
                    "kind": "STOCK", "supplier": supplier, "entity_id": vid,
                    "doc_id": _doc_for(supplier), "doc_version": "v1",
                    "on_hand": rng.randint(0, 6000),
                })
            elif roll < 0.76:
                lid = listing_ids[rng.randint(0, len(listing_ids) - 1)]
                listing = listing_by_id[lid]
                add(offset, hour, minute, "PUBLISH_TELEMETRY", "CHANNEL_GATEWAY", {
                    "listing_id": lid, "channel_id": listing["channel_id"],
                    "variant_id": listing["variant_id"], "status": "OK",
                    "impressions": rng.randint(40, 12000),
                    "published_version": "v1",
                })
            elif roll < 0.86:
                lid = listing_ids[rng.randint(0, len(listing_ids) - 1)]
                listing = listing_by_id[lid]
                add(offset, hour, minute, "CHANNEL_STATUS", "CHANNEL_GATEWAY", {
                    "listing_id": lid, "channel_id": listing["channel_id"],
                    "variant_id": listing["variant_id"], "status": "ACCEPTED",
                    "code": "", "detail": "", "feed_version": "v1",
                })
            elif roll < 0.94:
                # Localisation and logistics both arrive as catalog updates, and
                # both name the variant rather than describing it - which is
                # what the systems tier needs in order to draw an edge at all.
                vid = variant_ids[rng.randint(0, len(variant_ids) - 1)]
                add(offset, hour, minute, "CATALOG_UPDATE", "PIM", {
                    "entity_id": vid, "entities": [vid],
                    "product": product_of(vid),
                    "supplier": supplier_of(vid),
                    "doc_id": _doc_for(supplier_of(vid)), "doc_version": "v1",
                    "reason": DISPATCH_NOTES[
                        rng.randint(0, len(DISPATCH_NOTES) - 1)],
                    "status": "ACTIVE",
                })
            else:
                # Category management's read on a product. Advisory by
                # construction - it informs how a product is presented and
                # never what it is - but it names the product, which is what
                # stops Market Signals drawing as an island.
                vid = variant_ids[rng.randint(0, len(variant_ids) - 1)]
                product = product_of(vid)
                subject = SIGNAL_SUBJECTS[
                    rng.randint(0, len(SIGNAL_SUBJECTS) - 1)]
                email(offset, hour, minute,
                      subject.format(name=name_of(vid)),
                      "category.management@retailer.example",
                      f"Weekly category read for {name_of(vid)}.\n\n"
                      f"{subject.format(name=name_of(vid))}. No change to the "
                      f"product record is implied; this is a note about how it "
                      f"is selling.",
                      {"entities": [vid], "product": product,
                       "supplier": supplier_of(vid),
                       "material_hint": False, "applies_to": [vid]})


_DOC_BY_SUPPLIER: dict[str, str] = {}


def register_docs(mapping: dict[str, str]) -> None:
    """Which document each background supplier's routine feed arrives on."""
    _DOC_BY_SUPPLIER.update(mapping)


def _doc_for(supplier: str) -> str:
    return _DOC_BY_SUPPLIER.get(supplier, "DOC-100")
