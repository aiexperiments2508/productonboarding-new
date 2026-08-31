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
# Who else the retailer buys from
# ---------------------------------------------------------------------------
# Hand-authored rather than generated. A supplier is a proper noun, and
# "Supplier 47" in a demo about knowing who to chase reads as a system that
# does not know who it buys from.

SUPPLIERS = [
    # id,        name,                        family
    ("SUP-11", "Northgate Appliance Co.",     "home"),
    ("SUP-12", "Harrow & Vale Kitchenware",   "home"),
    ("SUP-13", "Bramblewood Bakery",          "food"),
    ("SUP-14", "Copperfield Provisions",      "food"),
    ("SUP-15", "Lumen Audio Works",           "audio"),
    ("SUP-16", "Petrichor Home Fragrance",    "home"),
    ("SUP-17", "Kestrel Small Domestics",     "home"),
    ("SUP-18", "Silverbrook Foods",           "food"),
]

# ---------------------------------------------------------------------------
# Where they sit in the taxonomy
# ---------------------------------------------------------------------------
# Two of these leaves sit outside every prefix in REQUIRED_MEDIA on purpose.
# "this category needs no imagery" and "this category is missing its imagery"
# are different states, and a catalog where every category required pictures
# could not show the difference.

TAXONOMY = {
    "home.laundry": "Home > Laundry",
    "home.laundry.irons": "Home > Laundry > Irons & Steamers",
    "home.floorcare": "Home > Floorcare",
    "home.floorcare.vacuums": "Home > Floorcare > Vacuum Cleaners",
    "home.kitchen.toasters": "Home > Kitchen > Toasters",
    "home.kitchen.blenders": "Home > Kitchen > Blenders",
    "home.air-treatment.humidifiers": "Home > Air Treatment > Humidifiers",
    "food.bakery": "Food > Bakery",
    "food.bakery.biscuits": "Food > Bakery > Biscuits",
    "food.beverages": "Food > Beverages",
    "food.beverages.tea": "Food > Beverages > Tea",
    "food.snacks.nuts": "Food > Snacks > Nuts & Seeds",
    "audio.speakers": "Audio > Speakers",
    "audio.speakers.portable": "Audio > Speakers > Portable Speakers",
    "audio.headphones.over-ear": "Audio > Headphones > Over-Ear",
}

#: Leaves background products are drawn from, with the words used to name them.
#: Ordered, because the draw walks it and a set would not be reproducible.
LEAVES: list[tuple[str, str, tuple[str, ...]]] = [
    ("home.laundry.irons", "Steam Iron", ("Glide", "Crease", "Vapour", "Sleek")),
    ("home.floorcare.vacuums", "Vacuum Cleaner",
     ("Whirl", "Dustline", "Cyclo", "Sweep")),
    ("home.kitchen.toasters", "Toaster", ("Amber", "Crust", "Morningside")),
    ("home.kitchen.blenders", "Blender", ("Vortex", "Smoothline", "Blitz")),
    ("home.kitchen.kettles", "Kettle", ("Brookvale", "Steamwell")),
    ("home.air-treatment.humidifiers", "Humidifier",
     ("Mistral", "Dewpoint", "Vapourfield")),
    ("home.air-treatment.fans", "Desk Fan", ("Zephyr", "Breezeline")),
    ("food.bakery.biscuits", "Biscuits", ("Hearthstone", "Butterfield")),
    ("food.beverages.tea", "Tea", ("Cloudleaf", "Rosehill")),
    ("food.snacks.nuts", "Nut Mix", ("Grovewell", "Saltbrook")),
    ("food.snacks.bars", "Snack Bar", ("Trailhead", "Meadowcut")),
    ("audio.speakers.portable", "Portable Speaker", ("Resonate", "Palmwave")),
    ("audio.headphones.over-ear", "Headphones", ("Halcyon", "Deepfield")),
]

#: Marketplace category mappings for the new leaves. Without these a listing on
#: Marketplace A fails CATEGORY_MAPPED, which is a real rule and not one to
#: route around by keeping background products off the channel.
MKT_A_CATS = {
    "home.laundry.irons": "1043/2280 Irons & Steamers",
    "home.floorcare.vacuums": "1043/2150 Vacuum Cleaners",
    "home.kitchen.toasters": "1043/3310 Toasters",
    "home.kitchen.blenders": "1043/3340 Blenders",
    "home.air-treatment.humidifiers": "1043/2240 Humidifiers",
    "home.air-treatment.fans": "1043/2260 Fans",
    "home.kitchen.kettles": "1043/3320 Kettles",
    "food.bakery.biscuits": "3120/4510 Biscuits",
    "food.beverages.tea": "3120/4720 Tea",
    "food.snacks.nuts": "3120/4430 Nuts & Seeds",
    "audio.speakers.portable": "2255/6720 Portable Speakers",
    "audio.headphones.over-ear": "2255/6620 Over-Ear Headphones",
}

MKT_B_CATS = {
    "home.laundry.irons": "laundry/irons",
    "home.floorcare.vacuums": "floorcare/vacuums",
    "home.kitchen.toasters": "kitchen/toasters",
    "home.kitchen.blenders": "kitchen/blenders",
    "home.air-treatment.humidifiers": "climate/humidifiers",
    "food.bakery.biscuits": "snacks/biscuits",
    "food.beverages.tea": "drinks/tea",
    "food.snacks.nuts": "snacks/nuts",
    "audio.speakers.portable": "audio/speakers",
    "audio.headphones.over-ear": "audio/headphones",
}

# ---------------------------------------------------------------------------
# The vocabulary each family's copy and attributes are built from
# ---------------------------------------------------------------------------

FILTERS = ("HEPA H13", "HEPA H12", "Carbon + HEPA", "Washable mesh")
ENERGY = ("A", "A", "A", "B", "B", "C")

INGREDIENTS = {
    "food.bakery.biscuits": ["wheat flour", "butter", "sugar", "eggs", "salt"],
    "food.beverages.tea": ["black tea", "bergamot oil"],
    "food.snacks.nuts": ["almonds", "cashews", "sea salt", "sunflower oil"],
    "food.snacks.bars": ["oats", "honey", "raisins", "sunflower oil"],
}
CONTAINS = {
    "food.bakery.biscuits": ["gluten", "milk", "egg"],
    "food.beverages.tea": [],
    "food.snacks.nuts": ["nuts"],
    "food.snacks.bars": ["oats"],
}
MAY_CONTAIN = {
    "food.bakery.biscuits": ["nuts"],
    "food.beverages.tea": [],
    "food.snacks.nuts": ["peanuts"],
    "food.snacks.bars": ["nuts"],
}

#: Copy that must never be published, planted so the forbidden-content check
#: has something to find outside the hand-authored six. Every phrase is one
#: `checks.FORBIDDEN_PHRASES` already knows, because a phrase no rule catches
#: is a defect nobody can act on.
BAD_SENTENCES = (
    "Clinically proven to improve the air you breathe.",
    "Completely safe for use around infants and pets.",
    "Guaranteed to cut your energy bill in half.",
    "Treats the causes of poor sleep, not just the symptoms.",
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
        leaf, noun, names = LEAVES[n % len(LEAVES)]
        family = leaf.split(".")[0]
        candidates = [s for s in SUPPLIERS if s[2] == family] or SUPPLIERS
        supplier = candidates[rng.randint(0, len(candidates) - 1)]
        stem = names[rng.randint(0, len(names) - 1)]
        model = 100 + rng.randint(1, 899)
        name = f"{stem} {model} {noun}"
        regulated = family == "food"

        products.append((pid, name, leaf, supplier[0], regulated))
        listing_channels[pid] = _channels_for(leaf, rng)

        # One to three variants. A catalog where every product has exactly one
        # cannot show the base-versus-variant question the whole correction
        # story turns on.
        for v in range(rng.randint(1, 3)):
            vid = f"VAR-{101 + n}{chr(ord('A') + v)}"
            variant_name = name if v == 0 else f"{name} {('Plus', 'Max')[v - 1]}"
            variants.append((vid, pid, variant_name, v == 0))
            skus[vid] = f"{stem[:3].upper()}-{model}-{chr(ord('A') + v)}"
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


def _lists_allergens(leaf: str) -> bool:
    """Does this category have an allergen declaration to make?

    Marketplace A requires one and specifies its wording; Marketplace B
    requires the coded form. A product with nothing to declare cannot satisfy
    either, and that is the rule doing its job - a herbal tea genuinely does
    not belong on a feed whose schema assumes every food names an allergen. So
    it is kept off those two channels rather than given a declaration it has no
    basis for.
    """
    return not leaf.startswith("food.") or bool(CONTAINS.get(leaf))


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


def _attributes(vid: str, leaf: str, doc: str, rng, damaged: bool,
                salt: int) -> list[tuple]:
    """One variant's values.

    Everything a channel *requires* is always present: a background product
    that could not be published would be breaking the validator's contract
    rather than failing a readiness check, and those are different claims made
    by different code. What gets left out is what the category declares and no
    channel demands - a sound level, an energy class, a fibre figure - which is
    exactly the gap `applicable_attributes` exists to report.
    """
    rows: list[tuple] = []

    def put(path: str, value) -> None:
        rows.append((vid, path, value, doc, "v1"))

    # Required everywhere it applies, so it is never dropped.
    put("identifiers.gtin", _gtin(salt * 7 + 11, broken=False))

    # Claims apply to every category, so a variant with no claims value is a
    # variant with an open finding - which would have made "returned to source"
    # the verdict on almost the whole background and left nothing to contrast
    # it against. An empty list is the honest value: this supplier made no
    # claims about this product, which is a fact and not a gap.
    #
    # Anything actually claimed has to hold against the substantiation table,
    # because a claim the validator would refuse at publish is a claim the
    # reviewer approves and the channel rejects - the worst of both.
    claimed: list[str] = []

    if leaf.startswith("home."):
        put("specs.power_w", 20 * rng.randint(2, 120))
        optional = ["specs.noise_db", "energy.class"]
        if leaf.startswith("home.air-treatment"):
            optional += ["specs.coverage_m2", "specs.filter_type"]
        values = {
            "specs.noise_db": rng.randint(28, 62),
            "energy.class": ENERGY[rng.randint(0, len(ENERGY) - 1)],
            "specs.coverage_m2": 5 * rng.randint(4, 20),
            "specs.filter_type": FILTERS[rng.randint(0, len(FILTERS) - 1)],
        }
        # The gap. One applicable attribute nobody sent, which is the single
        # most common thing wrong with a supplier's data and the reason
        # `applicable_attributes` is the first check in the list.
        dropped = optional[rng.randint(0, len(optional) - 1)] if damaged else None
        for path in optional:
            if path == dropped:
                _declare(vid, "applicable_attributes", path)
                continue
            put(path, values[path])

    if leaf.startswith("food."):
        put("food.ingredients", list(INGREDIENTS[leaf]))
        put("food.allergens.contains", list(CONTAINS[leaf]))
        put("food.allergens.may_contain", list(MAY_CONTAIN[leaf]))
        optional = ["food.net_weight_g", "food.fibre_g"]
        values = {
            "food.net_weight_g": 10 * rng.randint(3, 60),
            "food.fibre_g": round(rng.uniform(0.4, 9.5), 1),
        }
        dropped = optional[rng.randint(0, len(optional) - 1)] if damaged else None
        for path in optional:
            if path == dropped:
                _declare(vid, "applicable_attributes", path)
                continue
            put(path, values[path])

    if leaf.startswith("audio.") and rng.chance(0.5):
        put("specs.power_w", rng.randint(2, 40))

    held = {path: value for _e, path, value, *_r in rows}
    if held.get("specs.noise_db") is not None and held["specs.noise_db"] <= 40:
        claimed.append("ultra-quiet")
    if held.get("specs.power_w") is not None and held["specs.power_w"] <= 50:
        claimed.append("low-energy")
    if leaf.startswith("food."):
        allergens = " ".join(str(a) for a in
                             (CONTAINS.get(leaf) or []) + (MAY_CONTAIN.get(leaf) or []))
        if "peanut" not in allergens:
            claimed.append("peanut-free")
        if "gluten" not in allergens and "wheat" not in " ".join(
                INGREDIENTS.get(leaf) or []):
            claimed.append("gluten-free")
        if held.get("food.fibre_g") is not None and held["food.fibre_g"] >= 6:
            claimed.append("high-fibre")
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
    if not leaf.startswith("food."):
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
    words = leaf.split(".")[-1].replace("-", " ")
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
        # Imagery that never arrived. Which role depends on the category, the
        # same way INT-001 does.
        role = ("PACK_FRONT" if leaf.startswith("food.") and rng.chance(0.5)
                else "INGREDIENT_PANEL" if leaf.startswith("food.")
                else "HERO" if rng.chance(0.4) else "IN_SITU")
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
