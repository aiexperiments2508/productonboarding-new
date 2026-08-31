"""Deterministic synthetic seed pack for the product-intelligence factory.

Run:  python scripts/generate_data.py

Byte-identical on every run for a given DATA_SEED, so a demo rehearsed on
Friday behaves identically on Sunday. The PRNG is implemented here rather than
taken from ``random`` because CPython does not guarantee that ``shuffle`` and
``sample`` keep their algorithms across versions, and "identical across
machines" is the whole point.

Entity ids are stable constants, not generated, so the authored corpus in
corpus/ and the supplier documents in data/docs/ can name PRD-01, VAR-01B and
CH-MKT-A literally and stay in sync with what the loader sees.

The catalog is shaped around the inject rather than being uniformly random.
DOC-01 v1 folded a measurement sheet for one Northaven AP300 model into the summary
table for the range, so the baseline genuinely carries 45 W on the Max and is
nonetheless internally consistent - the validator finds nothing wrong with it
until the correction lands. Every prepared PRD-01 asset that quotes wattage
writes the literal "45W", which is what makes the blast radius of a single
attribute correction real rather than notional.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = DATA / "docs"
COMMS = DATA / "comms"
MEDIA = DATA / "media"
GOLDEN = DATA / "golden"
CORPUS = ROOT / "corpus"

SEED = int(os.environ.get("DATA_SEED", "20802"))

# The retailer this pack is for. Loaded first, because the assortment decides
# what the constants below can say - which branches exist, which imagery each
# needs, which of them are regulated. `RETAILER_PROFILE` picks the file, the
# same way `DATA_SEED` picks the draw.
_retailer_spec = importlib.util.spec_from_file_location(
    "seed_retailer", Path(__file__).resolve().parent / "retailer.py")
retailer = importlib.util.module_from_spec(_retailer_spec)  # type: ignore[arg-type]
_retailer_spec.loader.exec_module(retailer)  # type: ignore[union-attr]
PROFILE = retailer.PROFILE
# The recorded flight: 1 July to 31 August 2026 inclusive. Two calendar months
# rather than eight arbitrary weeks, because this is a backup snapshot being
# replayed and a snapshot has a period somebody can name.
HORIZON_START = date(2026, 7, 1)
HORIZON_DAYS = 62  # 1 Jul .. 31 Aug inclusive

# The main inject lands five weeks in, leaving prepared content behind it and
# roughly a month of runway ahead for the three arcs that follow.
INJECT_DAY = 33
INJECT_DATE = HORIZON_START + timedelta(days=INJECT_DAY)
SCENARIO2_DAY = 35   # allergen change
REJECTION_DAY = 36   # marketplace bounce
FINALE_DAY = 37      # "Max only" clarification
#: The production week the allergen change takes effect from. Quoted by
#: name in DOC-04 v2 and in the email that announces it, so it lives here
#: rather than in three places that could disagree.
EFFECTIVE_DAY = 39

# Seed files from the supply-chain domain this pack replaced. Removed on every
# run so a re-generate leaves no mixture of the two vocabularies on disk.
STALE_FILES = [
    "network.json", "orders.jsonl", "capacity.jsonl", "inventory.jsonl",
    "supplier_commitments.jsonl", "baseline_plan.jsonl", "demand_forecast.jsonl",
]


# ---------------------------------------------------------------------------
# Deterministic PRNG (mulberry32)
# ---------------------------------------------------------------------------


class Rng:
    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.next()

    def randint(self, lo: int, hi: int) -> int:
        return lo + int(self.next() * (hi - lo + 1))

    def pick(self, items: list):
        return items[int(self.next() * len(items))]

    def chance(self, p: float) -> bool:
        return self.next() < p


rng = Rng(SEED)


def r2(x: float) -> float:
    return round(x, 2)


def d(offset: int) -> date:
    return HORIZON_START + timedelta(days=offset)


def ts(offset: int, hour: int, minute: int) -> str:
    return datetime.combine(d(offset), datetime.min.time()).replace(
        hour=hour, minute=minute).isoformat()


def dw(offset: int) -> str:
    """A date the way a supplier writes one in a document: "3 August 2026".

    Derived rather than typed. Eight issue dates and four sentences of
    narrative used to carry the month as a literal, so moving the horizon left
    the prose describing a different autumn from the one the timestamps were
    in - and nothing failed, which is the worst way for a document to be wrong.

    ``%-d`` is not portable to Windows, hence the explicit day.
    """
    when = d(offset)
    return f"{when.day} {when:%B %Y}"


# ---------------------------------------------------------------------------
# Catalog constants - hand-authored, never generated
# ---------------------------------------------------------------------------

SUPPLIERS = [
    # id,       name,                     family
    ("SUP-01", "Northaven Home",           "home"),
    ("SUP-02", "Harrowfield Foods",   "food"),
    ("SUP-03", "Calverton Electronics", "audio"),
    ("SUP-04", "Stonebridge Housewares",     "home"),
    # Not a supplier, and recorded here because the field this fills is "who
    # asserted this document" rather than "who do we buy from". A withdrawal
    # notice has an issuer, that issuer is not the supplier of the thing being
    # withdrawn, and a document with no attributable issuer is not evidence.
    # Its `regulatory` family matches no category, so nothing is ever sourced
    # from it.
    ("SUP-90", "Market Surveillance Authority", "regulatory"),
]

PRODUCTS = [
    # id,       name,                              category,                      supplier,  regulated
    ("PRD-01", "Northaven AP300 Air Purifier",       "home.air-treatment.purifiers", "SUP-01", False),
    ("PRD-02", "Harrowfield Trail Mix Bar",    "food.snacks.bars",             "SUP-02", True),
    ("PRD-03", "Calverton BT-200 Earbuds",       "electronics.audio.earbuds",    "SUP-03", False),
    ("PRD-04", "Stonebridge Rapid Kettle",            "home.kitchen.kettles",         "SUP-04", False),
    ("PRD-05", "Harrowfield Granola Clusters", "food.snacks.granola",          "SUP-02", True),
    ("PRD-06", "Northaven Desk Fan V2",             "home.air-treatment.fans",      "SUP-01", False),
]

VARIANTS = [
    # id,        product,  name,                            is_base
    ("VAR-01A", "PRD-01", "Northaven AP300",                   True),
    ("VAR-01B", "PRD-01", "Northaven AP300 Max",               False),
    ("VAR-02A", "PRD-02", "Trail Mix Bar 40g",              True),
    ("VAR-02B", "PRD-02", "Trail Mix Bar Multipack 6x40g",  False),
    ("VAR-03A", "PRD-03", "Calverton BT-200 Earbuds",      True),
    ("VAR-04A", "PRD-04", "Stonebridge Rapid Kettle 1.7L",      True),
    ("VAR-05A", "PRD-05", "Granola Clusters 300g",          True),
    ("VAR-06A", "PRD-06", "Northaven Desk Fan V2",            True),
]

# What everybody outside this system calls each variant. Hand-authored rather
# than generated from the id, because a SKU is a commercial identifier a buyer
# recognises and "VAR-01B" with a prefix bolted on is not one. Distinct by
# construction; a test asserts it stays that way.
SKUS = {
    "VAR-01A": "NAV-AP300-STD",
    "VAR-01B": "NAV-AP300-MAX",
    "VAR-02A": "HRF-TMB-40",
    "VAR-02B": "HRF-TMB-6PK",
    "VAR-03A": "CAL-BT200",
    "VAR-04A": "STB-KET-17",
    "VAR-05A": "HRF-GRC-300",
    "VAR-06A": "NAV-FAN-V2",
}

# Which image roles a category cannot launch without, mirroring INT-001 rather
# than inventing a second rule. Appliances are bought on how they look in a
# room; a food pack needs the panel a shopper with an allergy actually reads;
# a garment needs a detail shot because fabric does not photograph from three
# metres. Which is which is the retailer's own standard, so it comes from the
# profile and is written into catalog.json for the running system to read.
REQUIRED_MEDIA = retailer.required_media()

# Media that never arrived. Deliberate, and named here rather than sprinkled by
# the PRNG: the readiness check needs something to find, and a demo whose only
# gap is random is a demo that can rehearse clean.
#
# VAR-02B has no ingredient panel - a multipack whose imaging job was queued
# against the single and never redone, which is the commonest way this happens.
# VAR-06A has no in-situ shot: a second-generation fan reusing the first
# generation's cut-out.
MISSING_MEDIA = {
    ("VAR-02B", "INGREDIENT_PANEL"),
    ("VAR-06A", "IN_SITU"),
}

# The whole tree comes from the profile - the six hero products sit in nodes
# the assortment already declares rather than in six of their own, which is
# what stops the demo's products being visibly special before anybody clicks
# one. Left as an empty dict, and merged with the profile's below, so a
# retailer that genuinely needs a node no background product occupies still
# has somewhere to put it.
TAXONOMY: dict[str, str] = {}

MKT_A_MAP = {
    "specs.power_w": "wattage",
    "food.allergens.contains": "allergen_statement",
    "food.allergens.may_contain": "allergen_statement",
    "identifiers.gtin": "gtin",
    "food.ingredients": "ingredients",
}

MKT_B_MAP = {
    "specs.power_w": "powerConsumption",
    "food.allergens.contains": "allergenCodes",
    "food.allergens.may_contain": "allergenCodes",
    "identifiers.gtin": "globalTradeItemNumber",
    "food.ingredients": "ingredientList",
}

# The hero products' own mappings. The background derives the rest from the
# profile, but these five leaves are where the demo happens and their codes are
# quoted in CHN-002 and CHN-003, so they stay hand-written and stable.
MKT_A_CATS = {
    "home.air-treatment.purifiers": "1043/2210 Air Purifiers",
    "food.snacks.bars": "3120/4415 Cereal Bars",
    "food.snacks.granola": "3120/4460 Granola & Muesli",
    "electronics.audio.earbuds": "2255/6610 In-Ear Headphones",
}

MKT_B_CATS = {
    "food.snacks.bars": "snacks/bars",
    "home.kitchen.kettles": "kitchen/kettles",
    "home.air-treatment.fans": "climate/fans",
}

CHANNELS = [
    # id,          name,                       kind,          taxonomy,        freeze, attr map,  category map
    ("CH-WEB",    "Own Website PDP",           "WEB",         "internal",      0, {},        {}),
    ("CH-MKT-A",  "Marketplace A",             "MARKETPLACE", "marketplace-a", 0, MKT_A_MAP, MKT_A_CATS),
    ("CH-MKT-B",  "Marketplace B",             "MARKETPLACE", "marketplace-b", 0, MKT_B_MAP, MKT_B_CATS),
    ("CH-PRINT",  "Store Catalogue & Print",   "PRINT",       "internal",      7, {},        {}),
    ("CH-SHELF",  "Shelf-Edge Labels",         "SHELF",       "internal",      0, {},        {}),
    ("CH-SEARCH", "Search Facets",             "SEARCH",      "internal",      0, {},        {}),
]

ATTR_DEFS = [
    # path, label, dtype, unit, safety, ordered, required_for, applies_to
    # Mains appliances only, and named leaf by leaf rather than by branch. A
    # rated power is a declaration about something that plugs in; a saucepan
    # and a duvet are in `home.` and neither has one, and four channels
    # *require* this field wherever it applies - so a prefix that swept them
    # in would make the untouched catalog unpublishable.
    ("specs.power_w", "Rated power", "int", "W", False, False,
     ["CH-MKT-A", "CH-MKT-B", "CH-PRINT", "CH-SHELF"],
     ["home.kitchen.", "home.laundry.", "home.floorcare.",
      "home.air-treatment.", "electronics.vision.", "electronics.computing.",
      "electronics.audio.soundbars"]),
    ("specs.noise_db", "Sound level", "int", "dB", False, False, [],
     ["home.kitchen.", "home.laundry.", "home.floorcare.",
      "home.air-treatment."]),
    ("specs.coverage_m2", "Coverage area", "int", "m²", False, False,
     [], ["home.air-treatment"]),
    ("specs.filter_type", "Filter type", "str", None, False, False,
     [], ["home.air-treatment"]),
    ("energy.class", "Energy class", "str", None, False, False, [],
     ["home.kitchen.", "home.laundry.", "home.floorcare.",
      "home.air-treatment.", "electronics.vision.", "electronics.computing."]),
    # `baby.feeding.` is here on purpose. Infant formula and weaning foods are
    # shelved in Baby because that is where a parent looks for them, and the
    # labelling regime does not care where a retailer shelves things.
    ("food.ingredients", "Ingredients", "list[str]", None, False, True,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food.", "baby.feeding.formula", "baby.feeding.weaning"]),
    ("food.allergens.contains", "Allergens - contains", "list[str]", None, True, False,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food.", "baby.feeding.formula", "baby.feeding.weaning"]),
    ("food.allergens.may_contain", "Allergens - may contain", "list[str]", None, True, False,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food.", "baby.feeding.formula", "baby.feeding.weaning"]),
    ("food.net_weight_g", "Net weight", "int", "g", False, False, [], ["food."]),
    ("food.fibre_g", "Fibre", "float", "g", False, False, [], ["food."]),
    # No applies_to prefix means every category.
    ("identifiers.gtin", "GTIN", "str", None, False, False, ["CH-MKT-A", "CH-MKT-B"], []),
    ("claims", "Claims", "list[str]", None, False, False, [], []),

    # ---------------------------------------------------------------------
    # Compliance
    # ---------------------------------------------------------------------
    # These are the cheapest correct way to make a takedown, an age bar or an
    # export restriction behave properly. `safety_class` is one of the two
    # switches every escalation path keys off, so an attribute marked here
    # inherits forced escalation, mandatory review, the fail-closed confidence
    # floor, withholding rather than copy-rewriting, and the per-channel
    # redaction path - without a line of new rule code.
    ("compliance.sale_permitted", "Permitted for sale", "bool", None, True, False,
     [], []),
    ("compliance.min_age", "Minimum age", "int", "years", True, False,
     [], ["food.alcohol.", "home.cookware.knives", "general.diy.handtools",
          "hpc.cleaning.bleach"]),
    ("compliance.export_control", "Export control classification", "str", None,
     True, False, [], ["electronics.personal."]),
    ("compliance.certificate_ref", "Conformity certificate", "str", None,
     False, False, [],
     ["electronics.", "home.kitchen.", "home.laundry.", "home.floorcare.",
      "home.air-treatment.", "general.toys.", "general.garden.", "general.diy.",
      "baby.toys.", "baby.feeding.bottles", "health.devices."]),

    # ---------------------------------------------------------------------
    # Identity and pack
    # ---------------------------------------------------------------------
    ("origin.country", "Country of origin", "str", None, False, False, [], []),
    ("pack.net_quantity", "Net quantity", "float", None, False, False, [],
     ["food.", "hpc.", "baby.feeding.", "baby.nappies.", "health.",
      "general.pet.", "general.diy.paint"]),
    ("pack.unit", "Net quantity unit", "str", None, False, False, [],
     ["food.", "hpc.", "baby.feeding.", "baby.nappies.", "health.",
      "general.pet.", "general.diy.paint"]),
    ("packaging.recyclable_pct", "Recyclable packaging", "int", "%", False,
     False, [], ["food.", "hpc.", "baby."]),

    # ---------------------------------------------------------------------
    # Category-specific labelling
    # ---------------------------------------------------------------------
    # A fibre label and an ingredient list are the same kind of object: an
    # ordered declaration whose order is part of its meaning. Marking it
    # `ordered` reuses the ORDERED_MATCH machinery rather than growing a
    # second one for textiles.
    ("textile.fibre_composition", "Fibre composition", "list[str]", None,
     False, True, [], ["apparel.", "home.textiles."]),
    ("textile.care_code", "Care instructions", "str", None, False, False, [],
     ["apparel.", "home.textiles."]),
    ("cosmetic.inci", "Ingredients (INCI)", "list[str]", None, True, True, [],
     ["hpc.toiletries.", "hpc.cosmetics."]),
    ("health.active_ingredient", "Active ingredients", "list[str]", None, True,
     False, [], ["health.medicines.", "health.supplements."]),
    ("specs.plug_type", "Plug and supply", "str", None, True, False, [],
     ["home.kitchen.", "home.laundry.", "home.floorcare.",
      "home.air-treatment.", "electronics.vision.", "electronics.computing.",
      "electronics.audio.soundbars"]),
    ("specs.battery_type", "Cell type", "str", None, True, False, [],
     ["electronics.mobile.", "electronics.personal.", "electronics.audio.",
      "general.toys.", "baby.toys.", "health.devices."]),
]

RULES = [
    # id, channel, field, kind, attribute_path, value, severity, detail
    ("RUL-A01", "CH-MKT-A", "title", "MAX_LEN", None, 80, "HARD", "Marketplace A title budget"),
    ("RUL-A02", "CH-MKT-A", "wattage", "REQUIRED", "specs.power_w", None, "HARD", ""),
    ("RUL-A03", "CH-MKT-A", "wattage", "DTYPE", "specs.power_w", "int", "HARD", ""),
    ("RUL-A04", "CH-MKT-A", "allergen_statement", "REQUIRED", "food.allergens.contains",
     None, "HARD", ""),
    ("RUL-A05", "CH-MKT-A", "allergen_statement", "FORMAT", "food.allergens.contains",
     r"^Contains: .+\.(?: May contain: .+\.)?$", "HARD", "rejection code MKA-4102"),
    ("RUL-A06", "CH-MKT-A", "gtin", "REQUIRED", "identifiers.gtin", None, "HARD", ""),
    ("RUL-A07", "CH-MKT-A", "category", "CATEGORY_MAPPED", None, None, "HARD",
     "internal taxonomy node must map to a Marketplace A node"),
    ("RUL-B01", "CH-MKT-B", "title", "MAX_LEN", None, 120, "HARD", ""),
    ("RUL-B02", "CH-MKT-B", "powerConsumption", "REQUIRED", "specs.power_w", None, "HARD", ""),
    # The allowlist is the profile's code set, sorted, rather than six codes
    # written out here. An assortment that adds fish or sulphites adds them to
    # one file, and the marketplace's schema follows - which is the point of
    # rules being data.
    ("RUL-B03", "CH-MKT-B", "allergenCodes", "ENUM", "food.allergens.contains",
     sorted(set(retailer.allergen_codes().values())), "HARD",
     "rejection code MKB-2201"),
    ("RUL-B04", "CH-MKT-B", "ingredientList", "ORDERED_MATCH", "food.ingredients",
     "food.ingredients", "HARD", "rejection code MKB-2208"),
    ("RUL-B05", "CH-MKT-B", "globalTradeItemNumber", "REQUIRED", "identifiers.gtin",
     None, "HARD", ""),
    ("RUL-W01", "CH-WEB", "title", "MAX_LEN", None, 120, "HARD", ""),
    ("RUL-W02", "CH-WEB", "bullets", "MAX_LEN", None, 5, "SOFT", "3-5 bullets per PDP"),
    ("RUL-P01", "CH-PRINT", "specs.power_w", "REQUIRED", "specs.power_w", None, "HARD", ""),
    ("RUL-P02", "CH-PRINT", "catalogue_copy", "MAX_LEN", None, 240, "HARD", ""),
    ("RUL-S01", "CH-SHELF", "shelf_text", "MAX_LEN", None, 40, "HARD", ""),
    # attribute_path gates this to appliances: a shelf label for a snack bar has
    # no wattage to print, so the rule never binds there.
    ("RUL-S02", "CH-SHELF", "shelf_text", "FORMAT", "specs.power_w", r"\d+\s?W", "SOFT",
     "appliances only"),
]

# Claim substantiation, mirrored verbatim in STD-001. Each entry is a predicate
# over the entity's in-force attribute values.
CLAIM_RULES = {
    "ultra-quiet": lambda a: a.get("specs.noise_db") is not None and a["specs.noise_db"] <= 40,
    "low-energy": lambda a: a.get("specs.power_w") is not None and a["specs.power_w"] <= 50,
    "peanut-free": lambda a: not _has_allergen(a, ("peanut", "peanuts")),
    "gluten-free": lambda a: not _has_allergen(a, ("gluten", "wheat")),
    "high-fibre": lambda a: a.get("food.fibre_g") is not None and a["food.fibre_g"] >= 6,
    # Two claims the wider assortment makes. Both are "restricted, permitted
    # only with substantiation" under INT-002, and both now have a predicate
    # rather than an opinion - which is what moves them from something only a
    # model could notice to something the validator refuses.
    "made-in-britain": lambda a: a.get("origin.country") == "United Kingdom",
    "recyclable-packaging": lambda a: (
        a.get("packaging.recyclable_pct") is not None
        and _as_number(a["packaging.recyclable_pct"]) is not None
        and _as_number(a["packaging.recyclable_pct"]) >= 90),
}


def _as_number(value):
    """A figure, or None if the supplier sent something that is not one.

    A claim is evaluated against whatever is in force, and what is in force is
    sometimes "90%" typed into a cell. That is a defect the readiness checks
    report; it is not a reason for a claim rule to raise.
    """
    try:
        return float(str(value).rstrip("%").strip())
    except (TypeError, ValueError):
        return None

# Word to code, from the profile - the assortment decides which of the
# regulated allergens it can actually declare.
ALLERGEN_CODES = retailer.allergen_codes()


def _has_allergen(attrs: dict, words: tuple[str, ...]) -> bool:
    declared = set(attrs.get("food.allergens.contains") or [])
    declared |= set(attrs.get("food.allergens.may_contain") or [])
    return any(w in declared for w in words)


# ---------------------------------------------------------------------------
# Baseline attribute values
#
# VAR-01B carries 45 W and 38 dB because DOC-01 v1 gave rated power and sound
# level "for the range" - the mix-up is the premise of scenario one. The
# baseline is wrong about the world and perfectly consistent with itself, which
# is exactly the state a content team is in when the correction arrives.
# ---------------------------------------------------------------------------

BAR_INGREDIENTS = ["oats", "honey", "sugar", "almonds", "sunflower oil"]
BAR_INGREDIENTS_V2 = ["oats", "honey", "almonds", "sugar", "sunflower oil"]

ATTR_ROWS = [
    # entity, path, value, source doc, version
    ("VAR-01A", "specs.power_w", 45, "DOC-01", "v1"),
    ("VAR-01A", "specs.noise_db", 38, "DOC-01", "v1"),
    ("VAR-01A", "specs.coverage_m2", 40, "DOC-01", "v1"),
    ("VAR-01A", "specs.filter_type", "HEPA H13", "DOC-01", "v1"),
    ("VAR-01A", "energy.class", "A", "DOC-08", "v1"),
    ("VAR-01A", "identifiers.gtin", "05012345600018", "DOC-02", "v1"),
    ("VAR-01A", "claims", ["ultra-quiet", "low-energy"], "DOC-01", "v1"),

    ("VAR-01B", "specs.power_w", 45, "DOC-01", "v1"),
    ("VAR-01B", "specs.noise_db", 38, "DOC-01", "v1"),
    ("VAR-01B", "specs.coverage_m2", 65, "DOC-01", "v1"),
    ("VAR-01B", "specs.filter_type", "HEPA H13", "DOC-01", "v1"),
    ("VAR-01B", "energy.class", "A", "DOC-08", "v1"),
    ("VAR-01B", "identifiers.gtin", "05012345600025", "DOC-02", "v1"),
    ("VAR-01B", "claims", ["ultra-quiet", "low-energy"], "DOC-01", "v1"),

    ("VAR-02A", "food.ingredients", BAR_INGREDIENTS, "DOC-04", "v1"),
    ("VAR-02A", "food.allergens.contains", ["almonds"], "DOC-04", "v1"),
    ("VAR-02A", "food.allergens.may_contain", [], "DOC-04", "v1"),
    ("VAR-02A", "food.net_weight_g", 40, "DOC-03", "v1"),
    ("VAR-02A", "food.fibre_g", 6.5, "DOC-04", "v1"),
    ("VAR-02A", "identifiers.gtin", "05098765400011", "DOC-03", "v1"),
    ("VAR-02A", "claims", ["peanut-free", "high-fibre"], "DOC-04", "v1"),

    ("VAR-02B", "food.ingredients", BAR_INGREDIENTS, "DOC-04", "v1"),
    ("VAR-02B", "food.allergens.contains", ["almonds"], "DOC-04", "v1"),
    ("VAR-02B", "food.allergens.may_contain", [], "DOC-04", "v1"),
    ("VAR-02B", "food.net_weight_g", 240, "DOC-03", "v1"),
    ("VAR-02B", "food.fibre_g", 6.5, "DOC-04", "v1"),
    ("VAR-02B", "identifiers.gtin", "05098765400028", "DOC-03", "v1"),
    ("VAR-02B", "claims", ["peanut-free", "high-fibre"], "DOC-04", "v1"),

    ("VAR-03A", "identifiers.gtin", "05033445500012", "DOC-07", "v1"),
    ("VAR-03A", "claims", [], "DOC-07", "v1"),

    ("VAR-04A", "specs.power_w", 3000, "DOC-06", "v1"),
    ("VAR-04A", "specs.noise_db", 70, "DOC-06", "v1"),
    ("VAR-04A", "energy.class", "A", "DOC-06", "v1"),
    ("VAR-04A", "identifiers.gtin", "05044556600019", "DOC-06", "v1"),
    ("VAR-04A", "claims", [], "DOC-06", "v1"),

    ("VAR-05A", "food.ingredients",
     ["oats", "honey", "almonds", "sunflower oil", "dried cranberries"], "DOC-05", "v1"),
    ("VAR-05A", "food.allergens.contains", ["almonds"], "DOC-05", "v1"),
    ("VAR-05A", "food.allergens.may_contain", ["milk"], "DOC-05", "v1"),
    ("VAR-05A", "food.net_weight_g", 300, "DOC-05", "v1"),
    ("VAR-05A", "food.fibre_g", 7.2, "DOC-05", "v1"),
    ("VAR-05A", "identifiers.gtin", "05098765400035", "DOC-05", "v1"),
    ("VAR-05A", "claims", ["high-fibre"], "DOC-05", "v1"),

    ("VAR-06A", "specs.power_w", 28, "DOC-02", "v1"),
    ("VAR-06A", "specs.noise_db", 42, "DOC-02", "v1"),
    ("VAR-06A", "specs.coverage_m2", 22, "DOC-02", "v1"),
    ("VAR-06A", "specs.filter_type", "Not applicable", "DOC-02", "v1"),
    ("VAR-06A", "energy.class", "A", "DOC-02", "v1"),
    ("VAR-06A", "identifiers.gtin", "05012345600032", "DOC-02", "v1"),
    ("VAR-06A", "claims", [], "DOC-02", "v1"),

    # ---------------------------------------------------------------------
    # Compliance and pack, for the six the demo talks about
    # ---------------------------------------------------------------------
    # Every product is permitted for sale until something says otherwise, and
    # the value is RECORDED rather than inferred - so the baseline is
    # publishable and a later withdrawal notice reads as a change rather than
    # as a catalog that was always broken. `origin.country` is here for the
    # same reason: an origin nobody stated and an origin stated as the United
    # Kingdom are different facts, and only one of them supports a claim.
    ("VAR-01A", "compliance.sale_permitted", True, "DOC-08", "v1"),
    ("VAR-01B", "compliance.sale_permitted", True, "DOC-08", "v1"),
    ("VAR-02A", "compliance.sale_permitted", True, "DOC-03", "v1"),
    ("VAR-02B", "compliance.sale_permitted", True, "DOC-03", "v1"),
    ("VAR-03A", "compliance.sale_permitted", True, "DOC-07", "v1"),
    ("VAR-04A", "compliance.sale_permitted", True, "DOC-06", "v1"),
    ("VAR-05A", "compliance.sale_permitted", True, "DOC-05", "v1"),
    ("VAR-06A", "compliance.sale_permitted", True, "DOC-02", "v1"),

    ("VAR-01A", "origin.country", "United Kingdom", "DOC-08", "v1"),
    ("VAR-01B", "origin.country", "United Kingdom", "DOC-08", "v1"),
    ("VAR-02A", "origin.country", "United Kingdom", "DOC-03", "v1"),
    ("VAR-02B", "origin.country", "United Kingdom", "DOC-03", "v1"),
    ("VAR-03A", "origin.country", "Viet Nam", "DOC-07", "v1"),
    ("VAR-04A", "origin.country", "Poland", "DOC-06", "v1"),
    ("VAR-05A", "origin.country", "United Kingdom", "DOC-05", "v1"),
    ("VAR-06A", "origin.country", "China", "DOC-02", "v1"),

    # Mains appliances declare a supply; the earbuds declare a cell.
    ("VAR-01A", "specs.plug_type", "BS 1363 Type G", "DOC-08", "v1"),
    ("VAR-01B", "specs.plug_type", "BS 1363 Type G", "DOC-08", "v1"),
    ("VAR-04A", "specs.plug_type", "BS 1363 Type G (fused 13 A)", "DOC-06", "v1"),
    ("VAR-06A", "specs.plug_type", "BS 1363 Type G", "DOC-02", "v1"),
    ("VAR-03A", "specs.battery_type", "Lithium polymer 3.8 V", "DOC-07", "v1"),

    ("VAR-01A", "compliance.certificate_ref", "UKCA-2411", "DOC-08", "v1"),
    ("VAR-01B", "compliance.certificate_ref", "UKCA-2411", "DOC-08", "v1"),
    ("VAR-03A", "compliance.certificate_ref", "UKCA-2478", "DOC-07", "v1"),
    ("VAR-04A", "compliance.certificate_ref", "UKCA-2503", "DOC-06", "v1"),
    ("VAR-06A", "compliance.certificate_ref", "UKCA-2419", "DOC-02", "v1"),

    # The two food products declare a pack net quantity as well as the grocery
    # net weight. They are not the same statement: one is the mandatory
    # particular under REG-001 and the other is what the range card carries.
    ("VAR-02A", "pack.net_quantity", 40.0, "DOC-03", "v1"),
    ("VAR-02A", "pack.unit", "g", "DOC-03", "v1"),
    ("VAR-02B", "pack.net_quantity", 240.0, "DOC-03", "v1"),
    ("VAR-02B", "pack.unit", "g", "DOC-03", "v1"),
    ("VAR-05A", "pack.net_quantity", 300.0, "DOC-05", "v1"),
    ("VAR-05A", "pack.unit", "g", "DOC-05", "v1"),

    ("VAR-02A", "packaging.recyclable_pct", 85, "DOC-03", "v1"),
    ("VAR-02B", "packaging.recyclable_pct", 85, "DOC-03", "v1"),
    ("VAR-05A", "packaging.recyclable_pct", 90, "DOC-05", "v1"),
]

SOURCE_DOCS = [
    # id, supplier, kind, version, title, received (day offset from 2026-08-01),
    # precedence, has prose body
    ("DOC-01", "SUP-01", "SPEC_SHEET", "v1",
     "Northaven AP300 range technical specification", d(-20).isoformat(), 30, True),
    ("DOC-02", "SUP-01", "PORTAL_FEED", "v1",
     "Northaven Home portal attribute feed", d(-18).isoformat(), 20, False),
    ("DOC-03", "SUP-02", "LABEL_ARTWORK", "v1",
     "Trail Mix Bar pack label artwork", d(-16).isoformat(), 40, True),
    ("DOC-04", "SUP-02", "SPEC_SHEET", "v1",
     "Harrowfield allergen and ingredient notice", d(-16).isoformat(), 30, True),
    ("DOC-05", "SUP-02", "SPREADSHEET", "v1",
     "Harrowfield portal spreadsheet export", d(-15).isoformat(), 15, False),
    ("DOC-06", "SUP-04", "SPEC_SHEET", "v1",
     "Stonebridge Rapid Kettle dimensional drawing", d(-14).isoformat(), 30, True),
    ("DOC-07", "SUP-03", "PORTAL_FEED", "v1",
     "Calverton portal attribute feed", d(-13).isoformat(), 20, False),
    ("DOC-08", "SUP-01", "CERTIFICATE", "v1",
     "Northaven Home declaration of conformity", d(-12).isoformat(), 35, True),
]

LISTING_CHANNELS = {
    "PRD-01": ["CH-WEB", "CH-MKT-A", "CH-PRINT", "CH-SHELF"],
    "PRD-02": ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-SEARCH", "CH-SHELF"],
    "PRD-03": ["CH-WEB", "CH-MKT-A"],
    # The kettle and the granola are the two the late-change story runs on, so
    # they carry the breadth that story needs to be about anything. A
    # correction that reaches two web pages demonstrates a correction reaching
    # two web pages; the interesting cases are the channels that answer
    # differently - a shelf label somebody has to walk over and reprint, and a
    # print run that cannot be recalled at all.
    "PRD-04": ["CH-WEB", "CH-MKT-B", "CH-SHELF", "CH-SEARCH"],
    # All six kinds, deliberately. This is the safety-class arc, and the whole
    # point of it is that the same correction has five different right answers
    # depending on what the channel can physically do about it.
    "PRD-05": ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT", "CH-SHELF",
               "CH-SEARCH"],
    "PRD-06": ["CH-WEB", "CH-MKT-B"],
}

# Every listing carries the three copy assets; the channel adds its own.
CHANNEL_ASSETS = {
    "CH-WEB": ["title", "bullets", "description"],
    "CH-MKT-A": ["title", "bullets", "description", "feed_row"],
    "CH-MKT-B": ["title", "bullets", "description", "feed_row"],
    "CH-PRINT": ["title", "bullets", "description", "catalogue_copy"],
    "CH-SHELF": ["title", "bullets", "description", "shelf_text"],
    "CH-SEARCH": ["title", "bullets", "description", "facets"],
}

PRICES = {
    "VAR-01A": 149.00, "VAR-01B": 199.00, "VAR-02A": 1.25, "VAR-02B": 6.00,
    "VAR-03A": 59.00, "VAR-04A": 34.50, "VAR-05A": 3.75, "VAR-06A": 27.00,
}

# The supplier's routine feed document - what price and stock rows arrive on.
PRIMARY_DOC = {"SUP-01": "DOC-02", "SUP-02": "DOC-05",
               "SUP-03": "DOC-07", "SUP-04": "DOC-06"}
# The background suppliers each have one, added where they are declared. Kept
# in the same mapping rather than a second one, so "which document did this
# price arrive on" has one answer whoever is asking.


# ---------------------------------------------------------------------------
# Prepared copy
#
# Hand-authored rather than templated: the demo turns on a reviewer reading a
# real sentence and recognising the stale number in it. Each entry is
# (text, attribute paths quoted, claims made). The paths become ``derived_from``
# lineage, which is what makes propagation deterministic - correcting an
# attribute marks every asset naming it as stale with no model involved.
# ---------------------------------------------------------------------------

SPECS_ALL = ["specs.power_w", "specs.noise_db", "specs.coverage_m2",
             "specs.filter_type", "energy.class"]
AIR_CLAIMS = ["ultra-quiet", "low-energy"]
BAR_CLAIMS = ["peanut-free", "high-fibre"]
BAR_PATHS = ["food.ingredients", "food.allergens.contains",
             "food.net_weight_g", "food.fibre_g"]

COPY = {
    "VAR-01A": {
        "web_title": (
            "Northaven AP300 Air Purifier — HEPA H13 filtration for rooms up to 40 m²",
            ["specs.coverage_m2", "specs.filter_type"], []),
        "mkt_title": (
            "Northaven AP300 Air Purifier — HEPA H13, 40 m², 45W",
            ["specs.power_w", "specs.coverage_m2", "specs.filter_type"], []),
        "bullets": ([
            "Ultra-quiet 45W operation for bedrooms and studies",
            "True HEPA H13 filter captures 99.95% of particles down to 0.1 micron",
            "Covers rooms up to 40 m² with a full air change every 18 minutes",
            "Energy class A, with a filter-life indicator and a sleep mode",
        ], SPECS_ALL, AIR_CLAIMS),
        "description": (
            "The Northaven AP300 is a compact air purifier for bedrooms, studies and "
            "home offices of up to 40 m². A sealed True HEPA H13 filter removes "
            "99.95% of airborne particles down to 0.1 micron, including pollen, pet "
            "dander and smoke. At 45 W and 38 dB on the sleep setting it can be left "
            "running overnight without disturbing sleep. Energy class A.",
            SPECS_ALL, AIR_CLAIMS),
        "shelf_text": ("Northaven AP300 · 45W · HEPA H13",
                       ["specs.power_w", "specs.filter_type"], []),
        "catalogue_copy": (
            "Northaven AP300 Air Purifier. True HEPA H13 filtration for rooms up to "
            "40 m², a full air change every 18 minutes, ultra-quiet 45 W operation "
            "at 38 dB on the sleep setting, energy class A and a filter-life "
            "indicator.", SPECS_ALL, AIR_CLAIMS),
    },
    "VAR-01B": {
        "web_title": (
            "Northaven AP300 Max Air Purifier — HEPA H13 filtration for rooms up to 65 m²",
            ["specs.coverage_m2", "specs.filter_type"], []),
        "mkt_title": (
            "Northaven AP300 Max Air Purifier — HEPA H13, 65 m², 45W",
            ["specs.power_w", "specs.coverage_m2", "specs.filter_type"], []),
        "bullets": ([
            "Ultra-quiet 45W operation for bedrooms and studies",
            "True HEPA H13 filter captures 99.95% of particles down to 0.1 micron",
            "Covers larger rooms up to 65 m² with a full air change every 20 minutes",
            "Energy class A, with a filter-life indicator and a sleep mode",
        ], SPECS_ALL, AIR_CLAIMS),
        "description": (
            "The Northaven AP300 Max is the larger model in the Northaven AP300 range, "
            "sized for living rooms and open-plan spaces of up to 65 m². The sealed "
            "True HEPA H13 filter is the same grade as the standard model and removes "
            "99.95% of airborne particles down to 0.1 micron. At 45 W and 38 dB on the "
            "sleep setting it is quiet enough to leave running overnight. "
            "Energy class A.", SPECS_ALL, AIR_CLAIMS),
        "shelf_text": ("Northaven AP300 Max · 45W · HEPA H13",
                       ["specs.power_w", "specs.filter_type"], []),
        "catalogue_copy": (
            "Northaven AP300 Max Air Purifier. True HEPA H13 filtration for open-plan "
            "rooms up to 65 m², a full air change every 20 minutes, ultra-quiet 45 W "
            "operation at 38 dB on the sleep setting, energy class A and a "
            "filter-life indicator.", SPECS_ALL, AIR_CLAIMS),
    },
    "VAR-02A": {
        "web_title": ("Harrowfield Trail Mix Bar 40g — oats, honey and almonds",
                      ["food.net_weight_g", "food.ingredients"], []),
        "mkt_title": (
            "Harrowfield Trail Mix Bar 40g — Oats, Honey & Almonds, High Fibre",
            ["food.net_weight_g", "food.ingredients", "food.fibre_g"], ["high-fibre"]),
        "bullets": ([
            "Peanut-free recipe, made on a dedicated line",
            "High fibre: 6.5 g of fibre in every 40 g bar",
            "Rolled oats and honey with whole roasted almonds",
            "No artificial colours, flavours or preservatives",
        ], BAR_PATHS, BAR_CLAIMS),
        "description": (
            "A chewy oat and honey bar with whole roasted almonds. Each 40 g bar "
            "carries 6.5 g of fibre, and the recipe is peanut-free. Contains almonds. "
            "Ingredients: oats, honey, sugar, almonds, sunflower oil.",
            BAR_PATHS, BAR_CLAIMS),
        "shelf_text": ("Trail Mix Bar 40g · Contains almonds",
                       ["food.net_weight_g", "food.allergens.contains"], []),
        "facet_format": "single-bar",
    },
    "VAR-02B": {
        "web_title": (
            "Harrowfield Trail Mix Bar Multipack — 6 x 40g, oats, honey and almonds",
            ["food.net_weight_g", "food.ingredients"], []),
        "mkt_title": ("Harrowfield Trail Mix Bar Multipack 6 x 40g — High Fibre",
                      ["food.fibre_g"], ["high-fibre"]),
        "bullets": ([
            "Six 40 g bars in one 240 g pack",
            "Peanut-free recipe, made on a dedicated line",
            "High fibre: 6.5 g of fibre per bar",
            "Rolled oats and honey with whole roasted almonds",
        ], BAR_PATHS, BAR_CLAIMS),
        "description": (
            "Six of our oat and honey bars with whole roasted almonds, 40 g each and "
            "240 g to the pack. 6.5 g of fibre per bar, and the recipe is peanut-free. "
            "Contains almonds. Ingredients: oats, honey, sugar, almonds, sunflower oil.",
            BAR_PATHS, BAR_CLAIMS),
        "shelf_text": ("Trail Mix Bar 6x40g · Almonds",
                       ["food.net_weight_g", "food.allergens.contains"], []),
        "facet_format": "multipack",
    },
    "VAR-03A": {
        "web_title": (
            "Calverton BT-200 True Wireless Earbuds — 24 hours of playback", [], []),
        "mkt_title": ("Calverton BT-200 True Wireless Earbuds — 24h Battery, USB-C",
                      [], []),
        "bullets": ([
            "Six hours of playback, 24 hours with the charging case",
            "Bluetooth 5.3 with multipoint pairing",
            "USB-C charging and IPX4 splash resistance",
            "Touch controls with a low-latency gaming mode",
        ], [], []),
        "description": (
            "Compact true wireless earbuds with a six-hour battery and a case that "
            "carries another eighteen hours. Bluetooth 5.3 holds two devices at once, "
            "so a call on the phone interrupts the laptop without re-pairing. USB-C "
            "charging, IPX4 splash resistance and touch controls.", [], []),
    },
    "VAR-04A": {
        "web_title": ("Stonebridge Rapid Kettle 1.7L — 3000W rapid boil, brushed steel",
                      ["specs.power_w"], []),
        "mkt_title": ("Stonebridge Rapid Kettle 1.7L — 3000W Rapid Boil, Brushed Steel",
                      ["specs.power_w"], []),
        "bullets": ([
            "Boils a single cup in 45 seconds",
            "1.7 litre capacity with a washable limescale filter",
            "3000W concealed element in brushed stainless steel",
            "360° base with cord storage underneath",
        ], ["specs.power_w"], []),
        "description": (
            "A 1.7 litre kettle with a 3000 W concealed element that brings a single "
            "cup to the boil in 45 seconds. Brushed stainless steel body, washable "
            "limescale filter, a 360° base and cord storage underneath.",
            ["specs.power_w"], []),
        "shelf_text": ("Stonebridge Rapid Kettle 1.7L · 3000W",
                       ["specs.power_w"], []),
    },
    "VAR-05A": {
        "web_title": ("Harrowfield Granola Clusters 300g — honey and almond",
                      ["food.net_weight_g"], []),
        "mkt_title": (
            "Harrowfield Granola Clusters 300g — Honey & Almond, High Fibre",
            ["food.net_weight_g", "food.fibre_g"], ["high-fibre"]),
        "bullets": ([
            "High fibre: 7.2 g of fibre per 100 g",
            "Baked oat clusters with honey, almonds and dried cranberries",
            "No artificial colours or flavours",
            "Resealable 300 g pack",
        ], ["food.fibre_g", "food.net_weight_g", "food.ingredients"], ["high-fibre"]),
        "description": (
            "Baked oat clusters with honey, whole almonds and dried cranberries, "
            "7.2 g of fibre per 100 g. Contains almonds. May contain milk. "
            "Ingredients: oats, honey, almonds, sunflower oil, dried cranberries.",
            ["food.fibre_g", "food.ingredients", "food.allergens.contains",
             "food.allergens.may_contain"], ["high-fibre"]),
        # Terse because it has to be: RUL-S01 gives a shelf-edge label forty
        # characters, and a label that does not fit is not a label. It still
        # names both allergen paths, which is what puts it in the blast radius
        # of a correction to either.
        "shelf_text": ("Granola Clusters 300g · Almonds, milk",
                       ["food.net_weight_g", "food.allergens.contains",
                        "food.allergens.may_contain"], []),
        # The one that cannot be taken back. It quotes the allergen line, so a
        # correction to that line reaches a printed page - which is the whole
        # argument for an erratum being a different outcome from a redaction.
        "catalogue_copy": (
            "Harrowfield Granola Clusters 300 g. Baked oat clusters with honey, "
            "whole almonds and dried cranberries, 7.2 g of fibre per 100 g. "
            "Contains almonds. May contain milk.",
            ["food.net_weight_g", "food.fibre_g", "food.allergens.contains",
             "food.allergens.may_contain"], ["high-fibre"]),
    },
    "VAR-06A": {
        "web_title": ("Northaven Desk Fan V2 — 28W three-speed fan for desks and rooms",
                      ["specs.power_w"], []),
        "mkt_title": ("Northaven Desk Fan V2 — 28W, 3 Speeds, Quiet Night Mode",
                      ["specs.power_w"], []),
        "bullets": ([
            "28W three-speed motor",
            "Night mode measured at 42 dB",
            "Tilting head with 90° oscillation",
            "Effective across desks and rooms up to 22 m²",
        ], ["specs.power_w", "specs.noise_db", "specs.coverage_m2"], []),
        "description": (
            "A three-speed desk fan drawing 28 W, quiet enough at 42 dB on night mode "
            "to sit on a bedside table. The head tilts and oscillates through 90°, "
            "moving air across desks and rooms of up to 22 m².",
            ["specs.power_w", "specs.noise_db", "specs.coverage_m2"], []),
    },
}

# ---------------------------------------------------------------------------
# The rest of the catalog
# ---------------------------------------------------------------------------
# Everything above is hand-authored and carries the story. Everything the
# following block adds is background: a few hundred products the demo never
# mentions, so that the six it does mention have a population to stand in.
#
# It draws from a stream of its own rather than from `rng`. The arcs consume
# the module-level stream in a fixed order, and a background catalog drawing
# from it would shift every draw after it - changing which system carried which
# routine feed, and renumbering the tape. Seeded off the same seed, so the pack
# is still byte-identical per seed; separate, so adding a product does not
# rewrite the story.

# Loaded by path rather than by name. `scripts/` is not a package, and a bare
# import only resolves when this file is run as a script - the golden test
# loads it by path, and would have found no such module.
_background = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "seed_background", Path(__file__).resolve().parent / "background.py"))
_background.__loader__.exec_module(_background)  # type: ignore[union-attr]

_BG = _background.build(Rng(SEED ^ 0x5EED))

SUPPLIERS += _background.SUPPLIERS
TAXONOMY.update(_background.TAXONOMY)
MKT_A_CATS.update(_background.MKT_A_CATS)
MKT_B_CATS.update(_background.MKT_B_CATS)

#: The six the demo talks about, captured before the background is spliced in.
#:
#: This used to be inferred as "the ids that do not start with VAR-1", which
#: was true when the background stopped at VAR-199 and quietly stopped being
#: true when it reached VAR-200. Background variants numbered from 200 were
#: being treated as hero products - given the story's routine traffic and
#: excluded from the population's - which is the kind of bug that produces no
#: error and a slightly wrong screen. Membership is now recorded rather than
#: pattern-matched, so it cannot come untrue by the catalog growing.
HERO_PRODUCTS = frozenset(p[0] for p in PRODUCTS)
HERO_VARIANTS = frozenset(v[0] for v in VARIANTS)

PRODUCTS += _BG["products"]
VARIANTS += _BG["variants"]
SKUS.update(_BG["skus"])
PRICES.update(_BG["prices"])
ATTR_ROWS += _BG["attr_rows"]
LISTING_CHANNELS.update(_BG["listing_channels"])
COPY.update(_BG["copy"])
MISSING_MEDIA |= _BG["media_missing"]
PRIMARY_DOC.update({sup: doc for doc, sup, *_rest in _BG["source_docs"]})
_background.register_docs(
    {sup: doc for doc, sup, *_rest in _BG["source_docs"]})
SOURCE_DOCS += [
    (doc, sup, kind, ver, title, d(offset).isoformat(), prec, body)
    for doc, sup, kind, ver, title, offset, prec, body in _BG["source_docs"]
]

#: The documents the seven wider arcs arrive on.
#:
#: `NOTICE` sits at precedence 50, above label artwork's 40, and it is the only
#: kind that does. Artwork is the legal source for what a pack *says*; a notice
#: is the legal source for whether it may be sold at all, and nothing a
#: supplier can send outranks it. POL-002 carries the same table in prose.
ARC_SOURCE_DOCS = [
    ("DOC-20", "", "SPEC_SHEET", "v2", "Revised pack specification", -6, 30, True),
    ("DOC-21", "", "CERTIFICATE", "v2", "Declaration of conformity - withdrawn",
     -5, 35, True),
    ("DOC-22", "", "SPEC_SHEET", "v2", "Sourcing change notification", -4, 30, True),
    ("DOC-23", "SUP-90", "NOTICE", "v1",
     "Withdrawal notice MSN-2026-0418", -3, 50, True),
    ("DOC-24", "SUP-90", "NOTICE", "v1",
     "Export control classification", -3, 50, True),
    ("DOC-25", "", "LABEL_ARTWORK", "v2", "Revised fibre composition label",
     -2, 40, True),
    ("DOC-26", "SUP-90", "NOTICE", "v1",
     "Amendment to mandatory particulars", -2, 50, True),
]

#: What the background was asked to get wrong, by entity. Read back by
#: `check_seeded` so the pack can assert it contains exactly the damage it
#: declared - the same property the extraction answer key has, extended to the
#: half of the catalog nobody hand-wrote.
SEEDED_DEFECTS = _background.SEEDED_DEFECTS


COMPARISON_TABLE = (
    "Model | Rated power | Coverage | Filter | Sound level\n"
    "Northaven AP300 | 45 W | 40 m² | HEPA H13 | 38 dB\n"
    "Northaven AP300 Max | 45 W | 65 m² | HEPA H13 | 38 dB"
)


# ---------------------------------------------------------------------------
# Supplier documents
#
# Extracted text, as the ingestion pipeline would hold it. DOC-01 v2 is the
# whole problem: it corrects the rated power of "the Northaven AP300" and admits
# that one model's measurement sheet was folded into v1, without ever saying
# which model the corrected figure belongs to. v3 is the answer.
# ---------------------------------------------------------------------------

DOC_BODIES = {
    "DOC-01-v1": f"""VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER RANGE

Document reference: DOC-01
Revision: v1
Issued: {dw(-20)}
Prepared by: Specification Control, Northaven Home

1. MODELS COVERED

  Northaven AP300       (VAR-01A)
  Northaven AP300 Max   (VAR-01B)

2. SUMMARY SPECIFICATION

  Rated power                 45 W
  Sound level, sleep setting  38 dB(A)
  Filter                      True HEPA H13
  Coverage, Northaven AP300      40 m²
  Coverage, Northaven AP300 Max  65 m²
  Energy class                A

3. NOTES

Rated power and sound level are stated for the range. Coverage differs by
model as tabulated above. Figures are taken from the test reports held by
Specification Control.
""",

    "DOC-01-v2": f"""VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER

Document reference: DOC-01
Revision: v2
Supersedes: v1 (issued {dw(-20)})
Issued: {dw(INJECT_DAY)}
Prepared by: Specification Control, Northaven Home

1. SCOPE

This revision corrects the rated power figure published for the Northaven AP300
air purifier. It supersedes revision v1 in full.

2. CORRECTION

  Rated power (mains, maximum fan setting)    65 W

The figure of 45 W given in revision v1 is withdrawn and must not be used in
customer-facing material issued after the date of this document.

3. REASON FOR CORRECTION

While revision v1 was being compiled, a measurement sheet belonging to one
model in the Northaven AP300 range was transcribed into the summary table for the
range as a whole. The 45 W entry originates from that sheet. The rating stated
in section 2 is the correct rated power and should be applied to the published
specification.

4. UNCHANGED

Filter type (True HEPA H13), coverage area, energy class and all dimensional
data are unaffected by this revision.

5. ACTION REQUESTED

Please update published specifications and any derived material at the earliest
opportunity. Queries to Specification Control.
""",

    "DOC-01-v3": f"""VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER RANGE

Document reference: DOC-01
Revision: v3
Supersedes: v2 (issued {dw(INJECT_DAY)})
Issued: {dw(FINALE_DAY)}
Prepared by: Specification Control, Northaven Home

1. SCOPE

Revision v2 corrected the rated power published for the Northaven AP300 to 65 W
but did not identify the model to which the corrected figure applies. This
revision resolves that ambiguity and supersedes v2 in full.

2. RATED POWER BY MODEL

  Northaven AP300       (VAR-01A)    45 W
  Northaven AP300 Max   (VAR-01B)    65 W

The 65 W figure introduced in revision v2 applies to the Northaven AP300 Max
only. The rated power of the base Northaven AP300 is unchanged at 45 W, and the
figure published for it in revision v1 was correct.

3. MEASURED SOUND LEVEL - AEROPURE 300 MAX

  Northaven AP300 Max   (VAR-01B)    44 dB(A), maximum fan setting
  Northaven AP300       (VAR-01A)    38 dB(A), unchanged

The 44 dB(A) figure is issued for the first time in this revision. The
38 dB(A) published for the Northaven AP300 Max in revisions v1 and v2 was carried
across from the base model in error and is withdrawn.

4. UNCHANGED

Filter type, coverage area and energy class are unchanged for both models.
""",

    "DOC-03-v1": f"""ORCHARD VALLEY FOODS - PACK LABEL ARTWORK (EXTRACTED TEXT)

Document reference: DOC-03
Revision: v1
Issued: {dw(-16)}
Product: Trail Mix Bar (PRD-02)

FRONT OF PACK
  Harrowfield Trail Mix Bar
  Oats, honey and almonds
  NET WEIGHT 40 g

BACK OF PACK
  INGREDIENTS: oats, honey, sugar, almonds, sunflower oil.
  ALLERGY ADVICE: contains almonds.
  GTIN 05098765400011 (single bar)
  GTIN 05098765400028 (6 x 40 g multipack)
""",

    "DOC-03-v2": f"""ORCHARD VALLEY FOODS - PACK LABEL ARTWORK (EXTRACTED TEXT)

Document reference: DOC-03
Revision: v2
Supersedes: v1 (issued {dw(-16)})
Issued: {dw(18)}
Product: Trail Mix Bar (PRD-02)

CHANGE NOTE
  The declared net weight of the single bar is corrected from 40 g to 38 g
  following the recipe density review closed this month. Artwork has been
  re-originated and the plates are cut. The multipack declaration is
  unaffected pending its own artwork cycle.

FRONT OF PACK
  Harrowfield Trail Mix Bar
  Oats, honey and almonds
  NET WEIGHT 38 g

BACK OF PACK
  INGREDIENTS: oats, honey, sugar, almonds, sunflower oil.
  ALLERGY ADVICE: contains almonds.
""",

    "DOC-04-v1": f"""ORCHARD VALLEY FOODS
ALLERGEN AND INGREDIENT NOTICE

Document reference: DOC-04
Revision: v1
Issued: {dw(-16)}
Product: Trail Mix Bar (PRD-02), all pack formats

1. ALLERGEN DECLARATION

  Contains:      almonds
  May contain:   nothing declared

The Trail Mix Bar is produced on line 2 at our Ashford site. Line 2 runs no
peanut, sesame or gluten-containing recipe.

2. INGREDIENT DECLARATION

Declared in descending order of weight:

  oats, honey, sugar, almonds, sunflower oil

3. NUTRITION

  Fibre    6.5 g per 40 g bar

4. PERMITTED CLAIMS

  peanut-free, high-fibre
""",

    "DOC-04-v2": f"""ORCHARD VALLEY FOODS
ALLERGEN AND INGREDIENT NOTICE

Document reference: DOC-04
Revision: v2
Supersedes: v1 (issued {dw(-16)})
Issued: {dw(SCENARIO2_DAY)}
Product: Trail Mix Bar (PRD-02), all pack formats

1. CHANGE OF MANUFACTURING LINE

From the production week commencing {dw(EFFECTIVE_DAY)} the Trail Mix Bar is
produced on line 4 at our Ashford site. Line 4 also runs a peanut-containing
recipe. Changeover cleaning is validated, but cross-contact cannot be
excluded.

2. REVISED ALLERGEN DECLARATION

  Contains:      almonds
  May contain:   peanuts

The "may contain peanuts" advisory applies to every pack format of the Trail
Mix Bar, including the 40 g single bar and the 6 x 40 g multipack.

3. REVISED INGREDIENT DECLARATION

Ingredients must be declared in descending order of weight. The order given in
revision v1 was incorrect. The correct declaration is:

  oats, honey, almonds, sugar, sunflower oil

4. CLAIMS

Any claim of freedom from peanuts must be withdrawn from pack, shelf-edge and
online material before the first line 4 production reaches store.
""",

    "DOC-06-v1": f"""CASCADE HOUSEWARES
DIMENSIONAL DRAWING - RAPID KETTLE 1.7L

Document reference: DOC-06
Revision: v1
Issued: {dw(-14)}
Product: Stonebridge Rapid Kettle (PRD-04)

  Capacity          1.7 L
  Rated power       3000 W
  Height            255 mm
  Base diameter     160 mm
  Sound level       70 dB(A) at full boil
  Finish            brushed stainless steel
  Energy class      A
  GTIN              05044556600019
""",

    "DOC-06-v2": f"""CASCADE HOUSEWARES
DIMENSIONAL DRAWING - RAPID KETTLE 1.7L

Document reference: DOC-06
Revision: v2 - PROVISIONAL, NOT FOR PUBLICATION
Issued: {dw(10)}
Product: Stonebridge Rapid Kettle (PRD-04)

This revision is issued for review only, while a tooling audit is open. The
base diameter is under query. Every other figure is carried forward from v1
unchanged. Do not publish against this revision until the audit closes and a
confirming notice is issued.

  Capacity          1.7 L
  Rated power       3000 W
  Height            255 mm
  Base diameter     162 mm (under query)
  Sound level       70 dB(A) at full boil
  Finish            brushed stainless steel
  Energy class      A
""",

    "DOC-07-v2": f"""BRIGHTLINE ELECTRONICS
PORTAL ATTRIBUTE FEED - CHANGE REPORT

Document reference: DOC-07
Revision: v2
Issued: {dw(22)}
Supplier: Calverton Electronics (SUP-03)

Scheduled quarterly republication of the attribute feed for all Calverton
lines, including the BT-200 Earbuds (PRD-03).

CHANGES IN THIS REVISION

  None. Every attribute value in this revision is identical to v1. The
  revision number has advanced because the feed is republished on a fixed
  quarterly cycle, not because any value has moved.
""",

    "DOC-08-v1": f"""VOLTAIC HOME LIMITED
DECLARATION OF CONFORMITY

Document reference: DOC-08
Revision: v1
Issued: {dw(-12)}
Manufacturer: Northaven Home Limited (SUP-01)

Products covered:
  Northaven AP300       (VAR-01A)
  Northaven AP300 Max   (VAR-01B)
  Northaven Desk Fan V2 (VAR-06A)

The products above conform to the applicable electrical safety and
electromagnetic compatibility requirements. Energy class A is declared for
each on the basis of the test reports held on file.

This declaration covers energy class only. Rated power and sound level are
stated in the product technical specification (DOC-01) and are outside the
scope of this certificate.
""",
}


# ---------------------------------------------------------------------------
# Catalog assembly
# ---------------------------------------------------------------------------

PRODUCT_BY_ID = {p[0]: p for p in PRODUCTS}
VARIANT_BY_ID = {v[0]: v for v in VARIANTS}
CHANNEL_BY_ID = {c[0]: c for c in CHANNELS}
ATTR_BY_PATH = {a[0]: a for a in ATTR_DEFS}
ATTR_VALUES = {(r[0], r[1]): r[2] for r in ATTR_ROWS}
ATTR_SOURCE = {(r[0], r[1]): (r[3], r[4]) for r in ATTR_ROWS}


def category_of(variant_id: str) -> str:
    return PRODUCT_BY_ID[VARIANT_BY_ID[variant_id][1]][2]


def applies(path: str, category: str) -> bool:
    prefixes = ATTR_BY_PATH[path][7]
    return not prefixes or any(category.startswith(p) for p in prefixes)


def attrs_for(variant_id: str) -> dict:
    return {path: value for (eid, path), value in ATTR_VALUES.items()
            if eid == variant_id}


def applicable_paths(variant_id: str) -> list[str]:
    category = category_of(variant_id)
    return sorted(p for p in attrs_for(variant_id) if applies(p, category))


# ---------------------------------------------------------------------------
# What the wider arcs happen to
# ---------------------------------------------------------------------------
# The six hand-authored arcs happen to the six hand-authored products, because
# a story needs somewhere to be. The seven that follow are about the *rest* of
# the assortment - a takedown on a toy, an export restriction on a drone, a
# fibre label revised on a jumper - and those products are generated.
#
# So the target is selected rather than named: the first background variant in
# the right category that actually holds the attribute the arc moves. Selected
# from a sorted list, so it is the same variant on every run at this seed, and
# the arc can be written against a value the catalog genuinely has rather than
# against one it might.
#
# The alternative - hand-picking ids like VAR-137B - would tie the story to a
# draw, and the first person to add a product line would silently repoint an
# arc at a different product.


def pick_variant(prefix: str, path: str, *, skip: int = 0,
                 exclude: set[str] | None = None) -> str | None:
    """A background variant under ``prefix`` that holds ``path``.

    ``skip`` takes the next one along, so two arcs wanting the same kind of
    product do not land on the same row and make one of them invisible.
    """
    exclude = exclude or set()
    found = [vid for vid in sorted(VARIANT_BY_ID)
             if vid not in HERO_VARIANTS
             and vid not in exclude
             and category_of(vid).startswith(prefix)
             and (vid, path) in ATTR_VALUES]
    # Undamaged first. An arc landing on a variant the background already
    # broke would put the thing the arc is about third in a list of findings
    # about something else - a withdrawal notice reading as the least of a
    # product's problems, which is the opposite of the point.
    clean = [vid for vid in found if vid not in SEEDED_DEFECTS]
    ordered = clean + [vid for vid in found if vid in SEEDED_DEFECTS]
    return ordered[skip] if len(ordered) > skip else None


#: The seven wider arcs, and what each happens to. Selected once, here, so
#: `FROZEN_BY_ARC`, the documents, the events and the self-checks are all
#: talking about the same rows.
#:
#: Each entry is (day, key, category prefix, attribute path). The days sit in
#: the gaps the hero arcs leave - 13, 18, 33, 35, 36, 37 - so the demo script's
#: spine is untouched and a presenter who only wants the original story never
#: has to skip one of these.
WIDER_ARCS: tuple[tuple[int, str, str, str], ...] = (
    (8,  "net_quantity",   "food.",                 "pack.net_quantity"),
    (22, "certification",  "home.kitchen.",         "compliance.certificate_ref"),
    (27, "origin",         "apparel.",              "origin.country"),
    (44, "takedown",       "general.toys.",         "compliance.sale_permitted"),
    (48, "export",         "electronics.personal.", "compliance.export_control"),
    (52, "composition",    "apparel.",              "textile.fibre_composition"),
    (56, "rule_change",    "hpc.cosmetics.",        "cosmetic.inci"),
)


def _select_arc_targets() -> dict[str, str]:
    """One variant per wider arc, and no two arcs on the same product.

    Excluded by *product*, not by variant. Two arcs on two variants of one
    jumper would both be correct and would read, on the lifecycle board, as one
    product having a terrible month - which is a story the data is not telling.
    """
    chosen: dict[str, str] = {}
    used_products: set[str] = set()
    for _day, key, prefix, path in WIDER_ARCS:
        vid = None
        for skip in range(24):
            candidate = pick_variant(prefix, path, skip=skip)
            if candidate is None:
                break
            if VARIANT_BY_ID[candidate][1] not in used_products:
                vid = candidate
                break
        if vid is None:
            # A profile that does not trade this branch simply does not get
            # this arc. Silently skipping is right: the alternative is a pack
            # that refuses to build for a retailer with no cosmetics counter.
            continue
        chosen[key] = vid
        used_products.add(VARIANT_BY_ID[vid][1])
    return chosen


ARC_TARGET = _select_arc_targets()

# The arc documents, with the blanks filled in. A supplier document is issued
# by whoever supplies the product it describes, and that is only knowable once
# the arc knows which product it happens to. A notice already names its issuer.
SOURCE_DOCS += [
    (doc,
     supplier or PRODUCT_BY_ID[VARIANT_BY_ID[ARC_TARGET[key]][1]][3],
     kind, ver, title, d(offset).isoformat(), prec, body)
    for (doc, supplier, kind, ver, title, offset, prec, body), key
    in zip(ARC_SOURCE_DOCS, [k for _d, k, _p, _a in WIDER_ARCS])
    if key in ARC_TARGET
]


def docs_defining(variant_id: str) -> set[str]:
    return {doc for (eid, _), (doc, _) in ATTR_SOURCE.items() if eid == variant_id}


def build_media() -> list[dict]:
    """The imagery held against each variant, and the gaps.

    Roles come from the category rule in INT-001 rather than from taste, so a
    missing asset is a finding against a written requirement and not against a
    preference. What is absent is absent on purpose - see MISSING_MEDIA.
    """
    assets: list[dict] = []
    for vid, pid, name, _ in VARIANTS:
        category = PRODUCT_BY_ID[pid][2]
        roles: list[str] = []
        for prefix, required in REQUIRED_MEDIA.items():
            if category.startswith(prefix):
                roles = list(required)
                break
        # Everything gets a detail shot; nothing requires one. Present so that
        # "has media" and "has the media it needs" are visibly different
        # questions.
        roles.append("DETAIL")
        for role in roles:
            if (vid, role) in MISSING_MEDIA:
                continue
            assets.append({
                "id": f"IMG-{vid}-{role}",
                "entity_id": vid,
                "role": role,
                "uri": f"/media/{vid.lower()}-{role.lower()}.svg",
                "alt_text": f"{name} - {role.replace('_', ' ').lower()}",
                "width": 1200, "height": 1200,
                # The imaging system, named the way the estate names it.
                "system": "imaging-dam",
            })
    return assets


#: Hue per taxonomy root, so a food pack and a home appliance are
#: distinguishable at thumbnail size without anybody reading the caption.
# One hue per branch, from the profile. Generated imagery is not
# decoration - a reviewer scanning a grid should be able to tell a
# grocery pack from a garment without reading the caption.
FAMILY_HUE = retailer.hues()


def _hue(vid: str, category: str) -> int:
    """A stable hue for one variant.

    From the family, nudged by the identifier so two purifiers are not the same
    rectangle. Hashed rather than drawn from `rng`, because these are written
    outside the tape's draw order and must not shift it.
    """
    base = FAMILY_HUE.get(category.split(".")[0], 210)
    nudge = int(hashlib.sha256(vid.encode()).hexdigest()[:4], 16) % 40 - 20
    return (base + nudge) % 360


def _svg_escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _shape_for(role: str, hue: int) -> str:
    """The drawing itself, per role.

    Not decoration and not a stand-in for photography nobody has: the point is
    that a reviewer looking at the staging page can tell a pack front from an
    ingredient panel at a glance, which is the whole reason the roles are
    distinct in INT-001. A generic grey square in five places would have made
    the page look complete while saying nothing.
    """
    ink = f"hsl({hue} 45% 32%)"
    soft = f"hsl({hue} 40% 78%)"
    if role == "HERO":
        return (f'<ellipse cx="200" cy="330" rx="120" ry="14" fill="{soft}"/>'
                f'<rect x="130" y="110" width="140" height="215" rx="18" '
                f'fill="none" stroke="{ink}" stroke-width="5"/>'
                f'<circle cx="200" cy="180" r="34" fill="none" '
                f'stroke="{ink}" stroke-width="5"/>'
                f'<path d="M160 265h80M160 288h56" stroke="{ink}" '
                f'stroke-width="5" stroke-linecap="round"/>')
    if role == "IN_SITU":
        return (f'<path d="M40 300h320M70 300V150l130-70 130 70v150" '
                f'fill="none" stroke="{soft}" stroke-width="6" '
                f'stroke-linejoin="round"/>'
                f'<rect x="168" y="188" width="66" height="112" rx="10" '
                f'fill="none" stroke="{ink}" stroke-width="5"/>'
                f'<circle cx="201" cy="222" r="17" fill="none" '
                f'stroke="{ink}" stroke-width="5"/>')
    if role == "PACK_FRONT":
        return (f'<rect x="118" y="92" width="164" height="230" rx="12" '
                f'fill="none" stroke="{ink}" stroke-width="5"/>'
                f'<path d="M118 150h164" stroke="{ink}" stroke-width="5"/>'
                f'<path d="M146 196h108M146 224h84M146 252h108" '
                f'stroke="{soft}" stroke-width="8" stroke-linecap="round"/>')
    if role == "INGREDIENT_PANEL":
        rows = "".join(
            f'<path d="M132 {150 + i * 26}h136" stroke="{soft}" '
            f'stroke-width="7" stroke-linecap="round"/>' for i in range(6))
        return (f'<rect x="112" y="86" width="176" height="242" rx="8" '
                f'fill="none" stroke="{ink}" stroke-width="5"/>'
                f'<path d="M132 120h96" stroke="{ink}" stroke-width="7" '
                f'stroke-linecap="round"/>{rows}')
    # DETAIL, and anything a later role adds.
    return (f'<circle cx="200" cy="205" r="96" fill="none" stroke="{ink}" '
            f'stroke-width="5"/>'
            f'<path d="M160 205h80M200 165v80" stroke="{soft}" '
            f'stroke-width="8" stroke-linecap="round"/>')


def render_media_svg(asset: dict, variant_name: str, sku: str,
                     category: str) -> str:
    """One product image, as SVG.

    These are synthetic and say so - nobody should mistake them for
    photography. What they are not is *absent*: the catalog has always carried
    a uri for every asset it holds, the staging page has always been the last
    surface before publication, and until now that page rendered the word
    "hero" where the picture goes. A page that cannot show what it holds cannot
    show what it is missing either, because both look the same.

    Deterministic from the identifier alone, so a regenerated pack is
    byte-identical and a rehearsal cannot drift.
    """
    hue = _hue(asset["entity_id"], category)
    role = asset["role"]
    words = role.replace("_", " ").lower()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" '
        f'width="400" height="400" role="img" '
        f'aria-label="{_svg_escape(asset["alt_text"])}">'
        f'<rect width="400" height="400" fill="hsl({hue} 30% 96%)"/>'
        f'<rect x="10" y="10" width="380" height="380" rx="16" fill="none" '
        f'stroke="hsl({hue} 30% 84%)" stroke-width="2"/>'
        f'{_shape_for(role, hue)}'
        f'<text x="200" y="360" text-anchor="middle" font-family="system-ui, '
        f'sans-serif" font-size="17" fill="hsl({hue} 35% 30%)">'
        f'{_svg_escape(variant_name)}</text>'
        f'<text x="200" y="382" text-anchor="middle" font-family="ui-monospace, '
        f'monospace" font-size="13" fill="hsl({hue} 20% 52%)">'
        f'{_svg_escape(sku)} - {_svg_escape(words)}</text>'
        f'</svg>'
    )


def build_media_files(media: list[dict]) -> dict[str, str]:
    """Every held asset, drawn. Keyed by the path its uri resolves to."""
    files: dict[str, str] = {}
    for asset in media:
        vid = asset["entity_id"]
        variant = VARIANT_BY_ID[vid]
        category = PRODUCT_BY_ID[variant[1]][2]
        # The uri is the authority on the filename. Deriving it twice is how a
        # catalog ends up pointing at a file the generator wrote elsewhere.
        name = asset["uri"].removeprefix("/media/")
        files[f"media/{name}"] = render_media_svg(
            asset, variant[2], SKUS[vid], category)
    return files


def build_nodes() -> list[dict]:
    """The boxes on the map, without positions.

    Coordinates used to be written here. They stopped being tenable once a tier
    could gain and lose members while the application was running - a position
    written at generation time cannot describe a system that connected a minute
    ago. The UI computes each box's place from its tier and that tier's live
    membership, which also removes a way for the picture to disagree with the
    catalog it claims to draw.

    ``single_source`` falls out of the data rather than being asserted: an
    entity defined by exactly one supplier document has nothing to corroborate
    it, which is what the badge is warning about.
    """
    nodes: list[dict] = []

    for i, (sid, name, family) in enumerate(SUPPLIERS):
        owned = [doc[0] for doc in SOURCE_DOCS if doc[1] == sid]
        nodes.append({
            "id": sid, "kind": "SUPPLIER", "name": name, "group": family,
            "regulated": False, "single_source": len(owned) == 1,
        })

    for i, (pid, name, category, supplier, regulated) in enumerate(PRODUCTS):
        docs: set[str] = set()
        for vid, parent, _, _ in VARIANTS:
            if parent == pid:
                docs |= docs_defining(vid)
        nodes.append({
            "id": pid, "kind": "PRODUCT", "name": name,
            "group": category.split(".")[0],
            "regulated": regulated, "single_source": len(docs) == 1,
        })

    for i, (vid, pid, name, _) in enumerate(VARIANTS):
        product = PRODUCT_BY_ID[pid]
        nodes.append({
            "id": vid, "kind": "VARIANT", "name": name,
            "group": product[2].split(".")[0],
            "regulated": product[4], "single_source": len(docs_defining(vid)) == 1,
        })

    for i, (cid, name, kind, _, _, _, _) in enumerate(CHANNELS):
        nodes.append({
            "id": cid, "kind": "CHANNEL", "name": name, "group": kind,
            "regulated": False, "single_source": False,
        })

    return nodes


def build_listings() -> list[dict]:
    listings = []
    for pid, _, _, _, _ in PRODUCTS:
        for vid, parent, _, _ in VARIANTS:
            if parent != pid:
                continue
            for cid in LISTING_CHANNELS[pid]:
                listings.append({
                    "id": f"LST-{len(listings) + 1:02d}",
                    "variant_id": vid, "channel_id": cid,
                    "status": "PREPARED", "published_version": "v1",
                })
    return listings


# ---------------------------------------------------------------------------
# Channel projection
#
# One function decides what a variant looks like in a channel's own vocabulary,
# and both the feed rows written into the seed pack and the rule self-check
# read it. Two renderings of the same thing would drift apart the first time
# anybody edited one of them.
# ---------------------------------------------------------------------------


def allergen_statement(attrs: dict) -> str:
    contains = attrs.get("food.allergens.contains") or []
    may = attrs.get("food.allergens.may_contain") or []
    text = "Contains: " + ", ".join(contains) + "."
    if may:
        text += " May contain: " + ", ".join(may) + "."
    return text


def allergen_codes(attrs: dict) -> list[str]:
    declared = list(attrs.get("food.allergens.contains") or [])
    declared += list(attrs.get("food.allergens.may_contain") or [])
    codes = set()
    for item in declared:
        if item not in ALLERGEN_CODES:
            raise SystemExit(f"no marketplace code for allergen {item!r} - add it to "
                             "ALLERGEN_CODES rather than dropping it from the feed")
        codes.add(ALLERGEN_CODES[item])
    return sorted(codes)


def channel_view(variant_id: str, channel_id: str) -> dict:
    """The variant as this channel names it: mapped fields, mapped category."""
    channel = CHANNEL_BY_ID[channel_id]
    attribute_map, category_map = channel[5], channel[6]
    attrs = attrs_for(variant_id)
    category = category_of(variant_id)

    view: dict = {"category": category_map.get(category, category)}
    for path in applicable_paths(variant_id):
        # An attribute that applies to the category and has no value is the
        # single most common thing wrong with a supplier's data, and it is what
        # `applicable_attributes` exists to report. The channel view renders
        # what is held; a missing optional value is a gap in the record, not a
        # failure to build the page.
        if path in attrs:
            view[attribute_map.get(path, path)] = attrs[path]

    # Fields the channel expects as prose or as codes rather than as the raw
    # internal value.
    if "allergen_statement" in view:
        view["allergen_statement"] = allergen_statement(attrs)
    if "allergenCodes" in view:
        view["allergenCodes"] = allergen_codes(attrs)
    if "ingredients" in view:
        view["ingredients"] = ", ".join(attrs["food.ingredients"])
    return view


def feed_row(variant_id: str, channel_id: str, title: str) -> tuple[str, list[str]]:
    """The marketplace feed row, plus the attribute paths it draws on."""
    channel = CHANNEL_BY_ID[channel_id]
    attribute_map = channel[5]
    view = channel_view(variant_id, channel_id)
    fields = {"title": title, "category": view["category"]}
    paths = []
    for path in applicable_paths(variant_id):
        field = attribute_map.get(path)
        if field is None or field not in view:
            continue  # not in this marketplace's schema, or not held
        fields[field] = view[field]
        paths.append(path)
    text = json.dumps(fields, sort_keys=True, ensure_ascii=False,
                      separators=(", ", ": "))
    return text, sorted(paths)


def facet_text(variant_id: str) -> tuple[str, list[str]]:
    """Search facets, from whatever the record actually holds.

    Written for the one food product that had a search listing, and so it
    assumed a net weight and a hand-authored pack format. Neither is true of an
    iron, and neither is true of a product whose weight nobody sent - so it
    builds from what is present and names only the paths it used. A facet
    string that quoted an attribute the record does not hold would put a value
    on a search page that no document asserts.
    """
    attrs = attrs_for(variant_id)
    tokens: list[str] = []
    paths: list[str] = []

    def add(path: str, prefix: str, each: bool = False) -> None:
        if path not in attrs:
            return
        value = attrs[path]
        if each:
            tokens.extend(f"{prefix}:{v}" for v in value or [])
        else:
            tokens.append(f"{prefix}:{value}")
        paths.append(path)

    add("food.allergens.contains", "allergen", each=True)
    add("food.allergens.may_contain", "may-contain", each=True)
    add("claims", "dietary", each=True)
    if "food.net_weight_g" in attrs:
        tokens.append(f"weight:{attrs['food.net_weight_g']}g")
        paths.append("food.net_weight_g")
    if "specs.power_w" in attrs:
        tokens.append(f"power:{attrs['specs.power_w']}W")
        paths.append("specs.power_w")

    pack_format = COPY[variant_id].get("facet_format")
    if pack_format:
        tokens.append(f"format:{pack_format}")
    if not tokens:
        tokens.append(f"category:{category_of(variant_id)}")

    return " | ".join(sorted(tokens)), sorted(set(paths))


def build_assets(listings: list[dict]) -> list[dict]:
    assets: list[dict] = []

    def add(listing_id: str, field: str, text: str, refs: list[str],
            claims: list[str], regulated: bool) -> None:
        assets.append({
            "id": f"AST-{len(assets) + 1:03d}", "listing_id": listing_id,
            "field": field, "text": text,
            "derived_from": sorted(set(refs)), "claims_used": sorted(set(claims)),
            "built_at_version": "v1", "regulated": regulated,
        })

    for listing in listings:
        vid, cid = listing["variant_id"], listing["channel_id"]
        copy = COPY[vid]
        regulated = PRODUCT_BY_ID[VARIANT_BY_ID[vid][1]][4]

        def refs(paths: list[str]) -> list[str]:
            return [f"{vid}:{p}" for p in paths]

        for field in CHANNEL_ASSETS[cid]:
            if field == "title":
                text, paths, claims = copy["web_title" if cid == "CH-WEB" else "mkt_title"]
                add(listing["id"], "title", text, refs(paths), claims, regulated)
            elif field == "bullets":
                lines, paths, claims = copy["bullets"]
                add(listing["id"], "bullets", "\n".join(lines), refs(paths), claims,
                    regulated)
            elif field == "feed_row":
                title = copy["mkt_title"][0]
                text, paths = feed_row(vid, cid, title)
                add(listing["id"], "feed_row", text, refs(paths), [], regulated)
            elif field == "facets":
                text, paths = facet_text(vid)
                add(listing["id"], "facets", text, refs(paths),
                    attrs_for(vid).get("claims") or [], regulated)
            else:
                text, paths, claims = copy[field]
                add(listing["id"], field, text, refs(paths), claims, regulated)

        # The one cross-variant asset in the pack: the base model's page carries
        # a table quoting the Max's figures too, so a correction scoped to the
        # Max still lands on VAR-01A's listing. Anything that resolves scope by
        # walking listings alone will miss it.
        if vid == "VAR-01A" and cid == "CH-WEB":
            paths = ["specs.power_w", "specs.noise_db", "specs.coverage_m2",
                     "specs.filter_type"]
            add(listing["id"], "comparison_table", COMPARISON_TABLE,
                [f"VAR-01A:{p}" for p in paths] + [f"VAR-01B:{p}" for p in paths],
                [], regulated)

    return assets


def build_source_docs() -> list[dict]:
    rows = []
    for doc_id, supplier, kind, version, title, received, precedence, has_body in SOURCE_DOCS:
        rows.append({
            "id": doc_id, "supplier": supplier, "kind": kind, "version": version,
            "title": title,
            "received_at": datetime.fromisoformat(received + "T09:00:00").isoformat(),
            "status": "ACTIVE", "precedence": precedence,
            "body_path": f"docs/{doc_id}-{version}.txt" if has_body else None,
        })
    return rows


# ---------------------------------------------------------------------------
# Event tape
# ---------------------------------------------------------------------------

# Attribute values the arcs move. A routine feed still confirming 45 W on the
# Max on day 40 would contradict a correction the tape has already delivered,
# so the noise generator never re-asserts these.
FROZEN_BY_ARC = {
    ("VAR-01B", "specs.power_w"), ("VAR-01B", "specs.noise_db"),
    ("VAR-01B", "claims"),
    ("VAR-02A", "food.ingredients"), ("VAR-02B", "food.ingredients"),
    ("VAR-02A", "food.allergens.contains"), ("VAR-02B", "food.allergens.contains"),
    ("VAR-02A", "food.allergens.may_contain"), ("VAR-02B", "food.allergens.may_contain"),
    ("VAR-02A", "food.net_weight_g"), ("VAR-02B", "food.net_weight_g"),
    ("VAR-02A", "claims"), ("VAR-02B", "claims"),
    # The two the late-change story runs on. `confirmable` is built from every
    # hero (variant, path) NOT in this set, so without these a routine feed
    # would re-assert the old allergen line - and the correction a supplier
    # sent would be silently overwritten by noise carrying a later
    # recorded_at, the moment the clock advanced past it. The demo's premise
    # would evaporate mid-run, and nothing would report anything wrong.
    ("VAR-05A", "food.allergens.contains"),
    ("VAR-05A", "food.allergens.may_contain"),
    ("VAR-05A", "food.ingredients"),
    ("VAR-04A", "specs.power_w"),
}

MAILBOX_TO = "product-content@internal"


def build_events(listings: list[dict]) -> list[dict]:
    """The replay tape: continuous routine traffic with six arcs threaded in.

    Ids are handed out after the tape is sorted, so ``EVT-00123`` really is the
    hundred-and-twenty-third event. Arc events that have to point at an earlier
    one carry a ``@REF:`` token that is resolved in the same pass.
    """
    recs: list[dict] = []

    def add(day: int, hour: int, minute: int, etype: str, source: str,
            payload: dict, body: str | None = None, ref: str | None = None) -> str:
        recs.append({
            "order": len(recs), "ts": ts(day, hour, minute), "type": etype,
            "source": source, "payload": payload, "body": body, "ref": ref,
        })
        return f"@REF:{ref}" if ref else ""

    def email(day: int, hour: int, minute: int, subject: str, sender: str,
              body: str, payload: dict, ref: str | None = None) -> str:
        return add(day, hour, minute, "COMMS", "MAILBOX",
                   {**payload, "subject": subject, "from": sender, "to": MAILBOX_TO},
                   body, ref)

    # Arc 0 is the *story's* routine traffic and stays on the story's entities.
    # Left unscoped it would draw from the whole catalog, so the six products
    # the demo is about would get a fiftieth of the feed they used to - the
    # hero products would go quiet on a screen whose whole subject is which
    # products are moving. The rest of the catalog has its own traffic, emitted
    # above from its own stream.
    hero = set(HERO_VARIANTS)
    confirmable = sorted(
        (vid, path) for (vid, path) in ATTR_VALUES
        if vid in hero and (vid, path) not in FROZEN_BY_ARC
        and applies(path, category_of(vid))
    )
    variant_ids = [v for v in hero]
    variant_ids.sort()
    listing_ids = [l["id"] for l in listings if l["variant_id"] in hero]
    listing_by_id = {l["id"]: l for l in listings}

    # The rest of the catalog's routine traffic. Emitted from a stream of its
    # own and touching only background entities, so every draw the six arcs
    # below make is the draw they made before any of this existed - the volume
    # grew and the story did not move.
    _hero_variants = set(HERO_VARIANTS)
    _background.traffic(
        Rng(SEED ^ 0xBACC), add, email, days=HORIZON_DAYS,
        variants=[v for v in VARIANTS if v[0] not in _hero_variants],
        listings=[l for l in listings if l["variant_id"] not in _hero_variants],
        prices=PRICES,
        product_of=lambda vid: VARIANT_BY_ID[vid][1],
        supplier_of=lambda vid: PRODUCT_BY_ID[VARIANT_BY_ID[vid][1]][3],
        name_of=lambda vid: VARIANT_BY_ID[vid][2],
    )

    # --- arc 0: routine traffic on every day of the horizon -----------------
    for offset in range(HORIZON_DAYS):
        for _ in range(rng.randint(2, 5)):
            hour, minute = rng.randint(6, 20), rng.randint(0, 59)
            kind = rng.pick(["PRICE", "STOCK", "ATTRIBUTE_CONFIRM", "ATTRIBUTE_CONFIRM"])
            vid = rng.pick(variant_ids)
            supplier = PRODUCT_BY_ID[VARIANT_BY_ID[vid][1]][3]
            base = {"kind": kind, "supplier": supplier, "entity_id": vid,
                    "doc_id": PRIMARY_DOC[supplier], "doc_version": "v1"}
            if kind == "PRICE":
                add(offset, hour, minute, "SUPPLIER_FEED", "SUPPLIER_PORTAL",
                    {**base, "price": r2(PRICES[vid] * rng.uniform(0.97, 1.03)),
                     "currency": "GBP"})
            elif kind == "STOCK":
                add(offset, hour, minute, "SUPPLIER_FEED", "SUPPLIER_PORTAL",
                    {**base, "on_hand": rng.randint(40, 4000)})
            else:
                cvid, path = rng.pick(confirmable)
                csupplier = PRODUCT_BY_ID[VARIANT_BY_ID[cvid][1]][3]
                doc, version = ATTR_SOURCE[(cvid, path)]
                add(offset, hour, minute, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
                    "kind": "ATTRIBUTE_CONFIRM", "supplier": csupplier,
                    "entity_id": cvid, "path": path, "value": ATTR_VALUES[(cvid, path)],
                    "unchanged": True, "doc_id": doc, "doc_version": version,
                })

        if rng.chance(0.45):
            lid = rng.pick(listing_ids)
            listing = listing_by_id[lid]
            add(offset, rng.randint(5, 22), rng.randint(0, 59),
                "PUBLISH_TELEMETRY", "CHANNEL_GATEWAY", {
                    "listing_id": lid, "channel_id": listing["channel_id"],
                    "variant_id": listing["variant_id"], "status": "OK",
                    "impressions": rng.randint(120, 9000), "published_version": "v1",
                })

        if rng.chance(0.40):
            lid = rng.pick(listing_ids)
            listing = listing_by_id[lid]
            add(offset, rng.randint(5, 22), rng.randint(0, 59),
                "CHANNEL_STATUS", "CHANNEL_GATEWAY", {
                    "listing_id": lid, "channel_id": listing["channel_id"],
                    "variant_id": listing["variant_id"], "status": "ACCEPTED",
                    "code": "", "detail": "", "feed_version": "v1",
                })

    # Three notices that must be triaged as immaterial. The middle one names the
    # products by name on purpose - triage has to read what is being asked, not
    # match on an entity mention.
    email(3, 7, 15, "Supplier portal maintenance, Sunday 06:00-10:00",
          "noreply@supplier-portal.example",
          "The supplier portal will be unavailable this Sunday between 06:00 and "
          "10:00 while the attribute service moves to new hardware. Feeds queued "
          "during the window are delivered on completion.\n\nNo action is required "
          "and no product data changes.\n\nSupplier Portal Operations",
          {"material_hint": False})

    email(16, 13, 40, f"Summer range newsletter - what is landing in {d(46):%B}",
          "marketing@internal",
          f"Team,\n\nThe {d(20):%B} newsletter goes out on Friday. The featured lines "
          f"are "
          "the Northaven AP300 range and the Trail Mix Bar multipack. Copy is already "
          "signed off and we are not asking for any change to product data here - "
          "this note is for visibility only.\n\nMarketing",
          {"material_hint": False})

    email(44, 9, 50, "Reminder: quarterly supplier scorecards due", "spm@internal",
          "A reminder that supplier data-quality scorecards for the quarter are due "
          "at the end of next week. This is a process reminder and is unrelated to "
          "any open correction case.\n\nSupplier Performance Management",
          {"material_hint": False})

    # A document version that moves nothing. It exists so the triage path has to
    # distinguish "a new revision arrived" from "a value changed".
    add(22, 6, 30, "SPEC_DOC", "SUPPLIER_PORTAL", {
        "doc_id": "DOC-07", "doc_version": "v2", "supplier": "SUP-03",
        "kind": "PORTAL_FEED", "product": "PRD-03", "entities": ["VAR-03A"],
        "is_correction": False, "zero_delta": True, "material_hint": False,
        "summary": "quarterly republication, no attribute values changed",
    }, DOC_BODIES["DOC-07-v2"])

    # --- arc 1: warm-up. A provisional revision, withdrawn three days later ---
    arc1 = email(10, 8, 45, "Stonebridge Rapid Kettle - dimensions under review",
                 "product@sup-04.example",
                 "Dear Content Team,\n\n"
                 "Please treat the dimensional figures for the Stonebridge Rapid Kettle "
                 "(PRD-04) as provisional for the next few days. Our tooling supplier "
                 "has flagged a possible discrepancy on the base diameter and we have "
                 "opened a tooling audit to settle it.\n\n"
                 "We are issuing revision v2 of the drawing today so that you have the "
                 "figures under review on file, but please do not publish against it "
                 "until the audit closes. We expect to conclude within three working "
                 "days.\n\n"
                 "Kind regards,\n"
                 "Priya Raman\n"
                 "Product Data Manager, Stonebridge Housewares (SUP-04)",
                 {"product": "PRD-04", "entities": ["VAR-04A"], "doc_id": "DOC-06",
                  "doc_version": "v2", "supplier": "SUP-04", "provisional": True,
                  "is_correction": False, "applies_to": "PRODUCT",
                  "material_hint": True,
                  "summary": "kettle dimensions provisional pending a tooling audit"},
                 ref="arc1-notice")

    add(10, 8, 20, "SPEC_DOC", "SUPPLIER_PORTAL", {
        "doc_id": "DOC-06", "doc_version": "v2", "supplier": "SUP-04",
        "kind": "SPEC_SHEET", "product": "PRD-04", "entities": ["VAR-04A"],
        "provisional": True, "is_correction": False, "applies_to": "PRODUCT",
        "material_hint": True,
        "summary": "provisional revision, base diameter under query",
    }, DOC_BODIES["DOC-06-v2"])

    email(13, 10, 5, "RE: Stonebridge Rapid Kettle - dimensions confirmed unchanged",
          "product@sup-04.example",
          "Dear Content Team,\n\n"
          "The tooling audit closed this morning. The base diameter measured within "
          "tolerance and no dimension on the Rapid Kettle changes.\n\n"
          "Revision v2 of the drawing is withdrawn. Please continue to work from v1 "
          "and disregard our notice of the 11th. Nothing needs to be republished.\n\n"
          "Apologies for the interruption.\n\n"
          "Kind regards,\n"
          "Priya Raman\n"
          "Product Data Manager, Stonebridge Housewares (SUP-04)",
          {"product": "PRD-04", "entities": ["VAR-04A"], "doc_id": "DOC-06",
           "doc_version": "v2", "supplier": "SUP-04", "resolves_issue": True,
           "is_correction": False, "corrects": arc1, "withdraws": "DOC-06:v2",
           "material_hint": True})

    add(13, 10, 20, "CATALOG_UPDATE", "PIM", {
        "doc_id": "DOC-06", "doc_version": "v2", "status": "WITHDRAWN",
        "reason": "tooling_audit_closed", "entities": ["VAR-04A"],
        "corrects": arc1,
    })

    # --- arc 0 anchor: the portal certifies the base model at 45 W ----------
    # Corroboration that survives the finale: whatever DOC-01 v2 turns out to
    # mean, VAR-01A was independently confirmed at 45 W a fortnight earlier.
    add(14, 9, 15, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
        "kind": "ATTRIBUTE_CONFIRM", "supplier": "SUP-01", "entity_id": "VAR-01A",
        "path": "specs.power_w", "value": 45, "unit": "W", "unchanged": True,
        "certified": True, "doc_id": "DOC-02", "doc_version": "v1",
    })

    # --- arc 0 anchor, restated on the range's own document ------------------
    # The portal's certification above is corroboration, and it must not by
    # itself separate the two models. Before the clarification the record has
    # to be genuinely ambiguous about which Northaven AP300 the 65 W applies to - that
    # ambiguity is the whole scenario - and a base model whose wattage stands
    # on a different document from the Max's is a record that has quietly
    # resolved it. So the spec sheet restates the base model's 45 W after the
    # certification, putting both variants back on DOC-01 until v3 separates
    # them on purpose.
    #
    # Authored rather than left to the noise generator. It used to happen by
    # chance - routine traffic re-confirming this attribute somewhere in the
    # fortnight before the inject - and a scenario that turns on a coin flip is
    # a scenario that will one day come up tails in front of an audience.
    add(24, 11, 5, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
        "kind": "ATTRIBUTE_CONFIRM", "supplier": "SUP-01", "entity_id": "VAR-01A",
        "path": "specs.power_w", "value": 45, "unit": "W", "unchanged": True,
        "doc_id": "DOC-01", "doc_version": "v1",
    })

    # --- arc 2: two sources disagree about one number ------------------------
    add(18, 7, 40, "SUPPLIER_FEED", "SUPPLIER_PORTAL", {
        "kind": "ATTRIBUTE", "supplier": "SUP-02", "entity_id": "VAR-02A",
        "path": "food.net_weight_g", "value": 40, "unit": "g",
        "doc_id": "DOC-05", "doc_version": "v1", "is_correction": False,
    })

    add(18, 15, 10, "SPEC_DOC", "SUPPLIER_PORTAL", {
        "doc_id": "DOC-03", "doc_version": "v2", "supplier": "SUP-02",
        "kind": "LABEL_ARTWORK", "precedence": 40, "product": "PRD-02",
        "attribute_path": "food.net_weight_g", "old_value": 40, "new_value": 38,
        "unit": "g", "applies_to": "VARIANT", "entities": ["VAR-02A"],
        "is_correction": True, "supersedes_version": "v1", "material_hint": True,
    }, DOC_BODIES["DOC-03-v2"], ref="arc2-artwork")

    email(19, 11, 25, "Trail Mix Bar 40g - net weight query", "sales@sup-02.example",
          "Hello,\n\n"
          "Your merchandising team has come back to us on the net weight of the Trail "
          "Mix Bar, so let me confirm from our side. It is a 40 g bar and has been "
          "since launch. The portal spreadsheet we send you every week carries 40 g, "
          "and that is the figure we would want on the shelf edge and on the "
          "website.\n\n"
          "I understand artwork was reissued last week. I would treat the spreadsheet "
          "as the operative figure - artwork sits with a different team here and is "
          "often behind.\n\n"
          "Best regards,\n"
          "Tom Wheeler\n"
          "National Account Manager, Harrowfield Foods (SUP-02)",
          {"product": "PRD-02", "entities": ["VAR-02A"], "supplier": "SUP-02",
           "attribute_path": "food.net_weight_g", "new_value": 40, "unit": "g",
           "applies_to": "VARIANT", "is_correction": False,
           "doc_id": "DOC-05", "doc_version": "v1", "source_kind": "EMAIL",
           "precedence": 10, "conflicts_with": "DOC-03:v2", "material_hint": True})

    # --- arc 3: the main inject. Genuinely ambiguous, on purpose ------------
    arc3 = add(INJECT_DAY, 7, 5, "SPEC_DOC", "SUPPLIER_PORTAL", {
        "product": "PRD-01", "attribute_path": "specs.power_w", "new_value": 65,
        "unit": "W", "applies_to": "UNCLEAR", "is_correction": True,
        "old_value": 45, "doc_id": "DOC-01", "doc_version": "v2",
        "supersedes_version": "v1", "supplier": "SUP-01", "kind": "SPEC_SHEET",
        "precedence": 30, "entities": ["PRD-01"], "material_hint": True,
    }, DOC_BODIES["DOC-01-v2"], ref="arc3-doc01-v2")

    email(INJECT_DAY, 7, 20,
          "Northaven AP300 - corrected rated power (DOC-01 rev v2)",
          "specs@sup-01.example",
          "Dear Content Team,\n\n"
          "Attached is revision v2 of the Northaven AP300 technical specification, "
          "issued this morning.\n\n"
          "The correction is to the rated power. The Northaven AP300 draws 65 W, not "
          "the 45 W we published in revision v1. The 45 W figure came off a "
          "measurement sheet for one of the models in the range that was folded into "
          "the summary table by mistake when v1 was compiled, and it should never "
          "have been carried across.\n\n"
          "Everything else in the document is unchanged - filter grade, coverage, "
          "energy class, dimensions.\n\n"
          "I appreciate you will have copy prepared against the old figure. Please "
          "let me know what you need from us to get it corrected.\n\n"
          "Kind regards,\n"
          "Martin Ellery\n"
          "Quality Manager, Northaven Home (SUP-01)",
          {"product": "PRD-01", "attribute_path": "specs.power_w", "new_value": 65,
           "unit": "W", "applies_to": "UNCLEAR", "is_correction": True,
           "old_value": 45, "doc_id": "DOC-01", "doc_version": "v2",
           "supersedes_version": "v1", "supplier": "SUP-01", "entities": ["PRD-01"],
           "material_hint": True})

    # --- arc 4: the allergen change, and an ingredient reorder with it -------
    allergen_changes = [
        {"entity_id": "VAR-02A", "attribute_path": "food.allergens.may_contain",
         "old_value": [], "new_value": ["peanuts"]},
        {"entity_id": "VAR-02A", "attribute_path": "food.ingredients",
         "old_value": BAR_INGREDIENTS, "new_value": BAR_INGREDIENTS_V2},
        {"entity_id": "VAR-02B", "attribute_path": "food.allergens.may_contain",
         "old_value": [], "new_value": ["peanuts"]},
        {"entity_id": "VAR-02B", "attribute_path": "food.ingredients",
         "old_value": BAR_INGREDIENTS, "new_value": BAR_INGREDIENTS_V2},
    ]
    arc4_payload = {
        "product": "PRD-02", "attribute_path": "food.allergens.may_contain",
        "old_value": [], "new_value": ["peanuts"], "applies_to": "ALL",
        "entities": ["VAR-02A", "VAR-02B"], "is_correction": True, "safety": True,
        "changes": allergen_changes, "claims_withdrawn": ["peanut-free"],
        "doc_id": "DOC-04", "doc_version": "v2", "supersedes_version": "v1",
        "supplier": "SUP-02", "effective_from": d(EFFECTIVE_DAY).isoformat(), "material_hint": True,
    }

    add(SCENARIO2_DAY, 8, 10, "SPEC_DOC", "SUPPLIER_PORTAL",
        {**arc4_payload, "kind": "SPEC_SHEET", "precedence": 30},
        DOC_BODIES["DOC-04-v2"], ref="arc4-doc04-v2")

    email(SCENARIO2_DAY, 8, 30,
          "Trail Mix Bar - revised allergen declaration (DOC-04 rev v2)",
          "quality@sup-02.example",
          "Dear Content Team,\n\n"
          "We are moving the Trail Mix Bar onto line 4 at Ashford from the week "
          f"commencing {dw(EFFECTIVE_DAY)}. Line 4 also runs a peanut recipe. Our "
          f"changeover "
          "cleaning is validated, but we cannot exclude cross-contact, so from that "
          "production week the pack must carry \"may contain peanuts\".\n\n"
          "This applies to every format of the bar - the 40 g single and the 6 x 40 g "
          "multipack alike.\n\n"
          "Two further points, both on the same revision:\n\n"
          "- The ingredient declaration order in revision v1 was wrong. The correct "
          "descending-weight order is oats, honey, almonds, sugar, sunflower oil.\n"
          "- Any peanut-free claim has to come off pack, shelf edge and website "
          "before the first line 4 stock reaches store.\n\n"
          "I am sorry for the short notice. Please confirm receipt so I can close "
          "this out on our side.\n\n"
          "Kind regards,\n"
          "Dr Helen Ashworth\n"
          "Supplier Quality Manager, Harrowfield Foods (SUP-02)",
          arc4_payload)

    # --- arc 5: the marketplace bounces the republished food listings -------
    for listing in listings:
        if listing["channel_id"] == "CH-MKT-B" and listing["variant_id"].startswith("VAR-02"):
            add(REJECTION_DAY, 5, 12, "CHANNEL_STATUS", "CHANNEL_GATEWAY", {
                "listing_id": listing["id"], "channel_id": "CH-MKT-B",
                "variant_id": listing["variant_id"], "product": "PRD-02",
                "status": "REJECTED", "code": "MKB-2201",
                "field": "allergen_statement",
                "detail": "allergen_statement format invalid",
                "feed_version": "v1", "material_hint": True,
            })

    # --- arc 6: the finale. The ambiguity of arc 3 is resolved to the Max ----
    finale_changes = [
        {"entity_id": "VAR-01B", "attribute_path": "specs.power_w",
         "old_value": 45, "new_value": 65, "unit": "W"},
        {"entity_id": "VAR-01B", "attribute_path": "specs.noise_db",
         "old_value": 38, "new_value": 44, "unit": "dB"},
        {"entity_id": "VAR-01A", "attribute_path": "specs.power_w",
         "old_value": 45, "new_value": 45, "unit": "W"},
    ]
    finale_payload = {
        "product": "PRD-01", "attribute_path": "specs.power_w", "new_value": 65,
        "unit": "W", "applies_to": "VARIANT", "entities": ["VAR-01B"],
        "is_correction": True, "corrects": arc3, "changes": finale_changes,
        "doc_id": "DOC-01", "doc_version": "v3", "supersedes_version": "v2",
        "supplier": "SUP-01", "material_hint": True,
    }

    add(FINALE_DAY, 9, 0, "SPEC_DOC", "SUPPLIER_PORTAL",
        {**finale_payload, "kind": "SPEC_SHEET", "precedence": 30},
        DOC_BODIES["DOC-01-v3"])

    email(FINALE_DAY, 9, 10,
          "Northaven AP300 - rev v3, the 65 W applies to the Max only",
          "specs@sup-01.example",
          "Dear Content Team,\n\n"
          f"Following your question on my note of {dw(INJECT_DAY)}: I am sorry, "
          f"revision "
          "v2 was not clear and I should have said which model it referred to.\n\n"
          "The 65 W rating is the Northaven AP300 Max. The standard Northaven AP300 draws "
          "45 W and always has - the figure in revision v1 was right for that model "
          "and nothing needs to change on it.\n\n"
          "While we were checking, our test house also flagged that the sound "
          "measurement we gave you for the Max was taken from the base unit. The Max "
          "measures 44 dB(A) at maximum fan setting, not 38. That figure is new; it "
          "has not been published before.\n\n"
          "Revision v3 is attached and supersedes v2 in full. It lists both models "
          "side by side so there is no room for the same mistake twice.\n\n"
          "Again, my apologies for the churn.\n\n"
          "Kind regards,\n"
          "Martin Ellery\n"
          "Quality Manager, Northaven Home (SUP-01)",
          finale_payload)

    # ------------------------------------------------------------------
    # The wider arcs: seven things that happen to the rest of the catalog
    # ------------------------------------------------------------------
    # The six above are the story, and they happen to six hand-authored
    # products. These are the same machinery exercised on the assortment - a
    # withdrawal notice on a toy, an export restriction on a camera, a fibre
    # label revised on a jumper - and they exist because a demo that can only
    # show one kind of correction has not shown that the system handles a
    # correction, only that it handles *that* correction.
    #
    # They sit in the gaps the story leaves, so a presenter running the
    # original six never has to skip one.
    _wider_days = {key: day for day, key, _pre, _path in WIDER_ARCS}

    def _wider(key: str, hour: int, minute: int, payload: dict,
               doc_kind: str, precedence: int, body: str,
               subject: str = "", sender: str = "", email_body: str = "") -> None:
        """One wider arc, if the assortment gave it somewhere to happen."""
        vid = ARC_TARGET.get(key)
        if vid is None:
            return
        day = _wider_days[key]
        product = VARIANT_BY_ID[vid][1]
        full = {
            "product": product, "entities": [vid], "applies_to": "VARIANT",
            "is_correction": True, "material_hint": True,
            "supplier": PRODUCT_BY_ID[product][3],
            **payload,
        }
        # Registered as a document body as well as carried on the event. The
        # event body is what the extractor reads; the file is what a reviewer
        # opens when the finding cites it, and a notice nobody can read is a
        # citation that has to be taken on trust.
        DOC_BODIES[f'{full["doc_id"]}-{full["doc_version"]}'] = body
        add(day, hour, minute, "SPEC_DOC",
            "SUPPLIER_PORTAL" if doc_kind != "NOTICE" else "PIM",
            {**full, "kind": doc_kind, "precedence": precedence},
            body, ref=f"wider-{key}")
        if subject:
            # Twenty minutes behind the document, wrapping the hour rather than
            # running off the end of it - somebody reads the notice and then
            # writes to the content team, which is the order these actually
            # happen in.
            later = hour * 60 + minute + 20
            email(day, (later // 60) % 24, later % 60,
                  subject, sender, email_body, full)

    # --- day 8: a pack gets smaller ------------------------------------
    # Ordinary commercially and never immaterial. It is a mandatory particular
    # under REG-007, it is printed on the shelf edge, and the price per unit a
    # shopper compares on is computed from it.
    if (_nq := ARC_TARGET.get("net_quantity")):
        _old = ATTR_VALUES[(_nq, "pack.net_quantity")]
        _new = round(_old * 0.9, 1)
        _name = VARIANT_BY_ID[_nq][2]
        _wider(
            "net_quantity", 9, 5,
            {"attribute_path": "pack.net_quantity", "old_value": _old,
             "new_value": _new, "unit": ATTR_VALUES.get((_nq, "pack.unit"), "g"),
             "doc_id": "DOC-20", "doc_version": "v2", "supersedes_version": "v1",
             "changes": [{"entity_id": _nq, "attribute_path": "pack.net_quantity",
                          "old_value": _old, "new_value": _new}]},
            "SPEC_SHEET", 30,
            f"{_name}\n\nRevision v2. The declared net quantity for this line "
            f"changes from {_old:g} to {_new:g} with effect from the next "
            f"production run. The recipe is unchanged; the pack is not.\n\n"
            f"The shelf-edge label and the price-per-unit calculation both "
            f"quote this figure and both need reissuing.",
            f"{_name} - net quantity revised to {_new:g}",
            "technical@supplier.example",
            f"Please note a pack change on {_name}.\n\n"
            f"The declared net quantity moves from {_old:g} to {_new:g}. Nothing "
            f"else about the product changes - same recipe, same ingredients, "
            f"same allergens.\n\n"
            f"I am flagging it because the shelf edge prints the weight and the "
            f"price per unit is worked out from it, so both need to move on the "
            f"same day the new pack lands.\n\n"
            f"Regards,\nTechnical Services")

    # --- day 22: the evidence behind a claim expires -------------------
    # Nothing about the product changed. What changed is that the certificate
    # supporting it stopped existing, which is a different conversation to have
    # with a supplier and a different thing to explain to a reviewer.
    if (_ce := ARC_TARGET.get("certification")):
        _old_ref = ATTR_VALUES[(_ce, "compliance.certificate_ref")]
        _name = VARIANT_BY_ID[_ce][2]
        _wider(
            "certification", 11, 40,
            {"attribute_path": "compliance.certificate_ref",
             "old_value": _old_ref, "new_value": "",
             "doc_id": "DOC-21", "doc_version": "v2", "supersedes_version": "v1",
             "changes": [{"entity_id": _ce,
                          "attribute_path": "compliance.certificate_ref",
                          "old_value": _old_ref, "new_value": ""}]},
            "CERTIFICATE", 35,
            f"Declaration of conformity - {_name}\n\n"
            f"Certificate {_old_ref} has lapsed and is withdrawn. The product "
            f"is unchanged and remains on sale; what has expired is the "
            f"declaration on file, and no claim resting on it is substantiated "
            f"until a replacement is issued.\n\n"
            f"A retest has been booked. We will issue the replacement "
            f"reference when it completes.",
            f"{_name} - conformity declaration {_old_ref} has lapsed",
            "compliance@supplier.example",
            f"Our declaration of conformity {_old_ref} for {_name} expired and "
            f"has not yet been renewed.\n\n"
            f"To be clear about what this is and is not: the product has not "
            f"changed and we are not asking you to stop selling it. What we no "
            f"longer have is the paperwork behind it, so anything on the "
            f"listing that leans on that certificate is currently unsupported.\n\n"
            f"Retest is booked. I will send the new reference the day it lands.\n\n"
            f"Regards,\nCompliance")

    # --- day 27: where it was made changes -----------------------------
    if (_or := ARC_TARGET.get("origin")):
        _old_origin = ATTR_VALUES[(_or, "origin.country")]
        _name = VARIANT_BY_ID[_or][2]
        _wider(
            "origin", 10, 15,
            {"attribute_path": "origin.country", "old_value": _old_origin,
             "new_value": "Portugal",
             "doc_id": "DOC-22", "doc_version": "v2", "supersedes_version": "v1",
             "changes": [{"entity_id": _or, "attribute_path": "origin.country",
                          "old_value": _old_origin, "new_value": "Portugal"}]},
            "SPEC_SHEET", 30,
            f"{_name}\n\nProduction for this line moves from {_old_origin} to "
            f"Portugal from the next buy. The specification, the fibre "
            f"composition and the care instructions are unchanged.\n\n"
            f"Country of origin is a labelling particular and appears on the "
            f"listing, the swing ticket and the customs declaration.",
            f"{_name} - country of origin now Portugal",
            "sourcing@supplier.example",
            f"We are moving production of {_name} from {_old_origin} to "
            f"Portugal with effect from the next buy.\n\n"
            f"Same fabric, same construction, same care code. The only thing "
            f"that changes is the origin, and that is on the label and on the "
            f"website.\n\n"
            f"Regards,\nSourcing")

    # --- day 44: a market authority orders the listing down ------------
    # The one arc that is not a correction to anything. Every value in the
    # record may be accurate and the product still may not be sold - which is
    # why it needed a constraint of its own rather than riding the safety gate.
    if (_td := ARC_TARGET.get("takedown")):
        _name = VARIANT_BY_ID[_td][2]
        _wider(
            "takedown", 7, 30,
            {"attribute_path": "compliance.sale_permitted",
             "old_value": True, "new_value": False, "takedown": True,
             "safety": True, "applies_to": "ALL",
             "doc_id": "DOC-23", "doc_version": "v1",
             "changes": [{"entity_id": _td,
                          "attribute_path": "compliance.sale_permitted",
                          "old_value": True, "new_value": False}]},
            "NOTICE", 50,
            f"WITHDRAWAL NOTICE\n\n"
            f"Reference MSN-2026-0418\n"
            f"Issued to: the retailer named below\n"
            f"Product: {_name}\n\n"
            f"Market surveillance has identified a risk of small parts "
            f"detaching from this product in normal use. You are directed to "
            f"withdraw it from sale on every channel with immediate effect and "
            f"to cease supply.\n\n"
            f"This notice is effective on receipt. It is not conditional on "
            f"your own assessment and it does not await a corrected "
            f"specification from the supplier.\n\n"
            f"Where the product has been listed in print, an erratum is owed. "
            f"Where a search facet directs shoppers to it, that facet is to be "
            f"withdrawn.",
            f"URGENT: withdrawal notice MSN-2026-0418 - {_name}",
            "regulatory.affairs@internal",
            f"A withdrawal notice has been served on {_name}.\n\n"
            f"Reference MSN-2026-0418. It takes effect on receipt, which was "
            f"this morning. Every channel comes down now - this is not a "
            f"content fix and there is no wording that makes it publishable.\n\n"
            f"The print catalogue carries it, so an erratum is owed rather "
            f"than a redaction. The search facet needs withdrawing.\n\n"
            f"I have logged it against the product record. Please do not wait "
            f"for the supplier's response before acting.\n\n"
            f"Regulatory Affairs")

    # --- day 48: a destination restriction, not a safety one -----------
    # Lawful here, restricted elsewhere. The remedy is withholding a channel
    # rather than correcting a word, which is exactly what the propagation
    # step does when a constraint is marked unfixable by copy.
    if (_ex := ARC_TARGET.get("export")):
        _name = VARIANT_BY_ID[_ex][2]
        _wider(
            "export", 8, 50,
            {"attribute_path": "compliance.export_control",
             "old_value": "NONE", "new_value": "DUAL-USE 6A003",
             "export_restricted": True, "applies_to": "ALL",
             "doc_id": "DOC-24", "doc_version": "v1",
             "changes": [{"entity_id": _ex,
                          "attribute_path": "compliance.export_control",
                          "old_value": "NONE", "new_value": "DUAL-USE 6A003"}]},
            "NOTICE", 50,
            f"EXPORT CONTROL CLASSIFICATION\n\n"
            f"Product: {_name}\n"
            f"Classification: DUAL-USE 6A003\n\n"
            f"The imaging sensor in this product falls within the dual-use "
            f"control list. The product remains lawful to sell in the domestic "
            f"market and may not be shipped to a controlled destination "
            f"without a licence.\n\n"
            f"Marketplace listings that offer international delivery are to be "
            f"withheld until destination filtering is in place. The domestic "
            f"product page is unaffected.\n\n"
            f"This is a shipping restriction and not a safety finding. No "
            f"statement about product safety is to be made or implied.",
            f"{_name} classified DUAL-USE 6A003 - marketplace listings withheld",
            "regulatory.affairs@internal",
            f"{_name} has been classified DUAL-USE 6A003 on the strength of its "
            f"imaging sensor.\n\n"
            f"What this means in practice: we can still sell it here, and we "
            f"cannot ship it everywhere. The marketplaces offer international "
            f"delivery and cannot filter by destination on our behalf, so "
            f"those listings come down until they can.\n\n"
            f"Please do not describe this as a safety issue anywhere. It is "
            f"not one, and saying so would be its own problem.\n\n"
            f"Regulatory Affairs")

    # --- day 52: a fibre label is revised ------------------------------
    # The same act as an ingredient reorder, outside food. The declaration is
    # ordered and the order is part of its meaning, so this is a change and
    # not a rewording - which is the point of marking the attribute ordered.
    if (_co := ARC_TARGET.get("composition")):
        _old_fibre = ATTR_VALUES[(_co, "textile.fibre_composition")]
        _new_fibre = ["60% Cotton", "40% Polyester"]
        _name = VARIANT_BY_ID[_co][2]
        _wider(
            "composition", 13, 25,
            {"attribute_path": "textile.fibre_composition",
             "old_value": list(_old_fibre), "new_value": _new_fibre,
             "doc_id": "DOC-25", "doc_version": "v2", "supersedes_version": "v1",
             "changes": [{"entity_id": _co,
                          "attribute_path": "textile.fibre_composition",
                          "old_value": list(_old_fibre),
                          "new_value": _new_fibre}]},
            "LABEL_ARTWORK", 40,
            f"{_name} - revised fibre composition\n\n"
            f"The mill has changed the yarn blend. The declared composition "
            f"changes from {', '.join(_old_fibre)} to "
            f"{', '.join(_new_fibre)}.\n\n"
            f"Fibre composition is declared in descending percentage order and "
            f"that order is part of the declaration. The care code is "
            f"unchanged.",
            f"{_name} - fibre composition revised",
            "technical@supplier.example",
            f"The mill supplying {_name} has changed the blend.\n\n"
            f"Declared composition moves from {', '.join(_old_fibre)} to "
            f"{', '.join(_new_fibre)}. It goes on the label in that order, "
            f"descending by percentage - please do not let anyone tidy it "
            f"alphabetically, it is a declaration and not a list.\n\n"
            f"Care code is unchanged.\n\n"
            f"Regards,\nTechnical Services")

    # --- day 56: the rule moves, not the record ------------------------
    # Nobody did anything wrong. Copy that was compliant when it was written is
    # not compliant now, which is a correction with no supplier to return it to
    # - and the only arc here whose cause is a document version rather than a
    # product.
    if (_rc := ARC_TARGET.get("rule_change")):
        _old_inci = ATTR_VALUES[(_rc, "cosmetic.inci")]
        _new_inci = list(_old_inci) + ["Tocopherol"]
        _name = VARIANT_BY_ID[_rc][2]
        _wider(
            "rule_change", 9, 45,
            {"attribute_path": "cosmetic.inci",
             "old_value": list(_old_inci), "new_value": _new_inci,
             "rule_change": True, "applies_to": "ALL",
             "doc_id": "DOC-26", "doc_version": "v1",
             "changes": [{"entity_id": _rc, "attribute_path": "cosmetic.inci",
                          "old_value": list(_old_inci),
                          "new_value": _new_inci}]},
            "NOTICE", 50,
            f"AMENDMENT TO MANDATORY PARTICULARS\n\n"
            f"Effective from the date of this notice, the ingredient "
            f"declaration for leave-on cosmetic products must name every "
            f"antioxidant present, whether or not it exceeds the previous "
            f"threshold.\n\n"
            f"Affected in this catalogue: {_name}.\n\n"
            f"Listings prepared before this notice are not withdrawn and are "
            f"not defective. They are non-compliant from today, and the "
            f"declaration is to be completed at the next content release.",
            f"Ingredient declaration rules change - {_name} affected",
            "regulatory.affairs@internal",
            f"The mandatory particulars for leave-on cosmetics have changed.\n\n"
            f"Antioxidants now have to be named in the ingredient declaration "
            f"regardless of concentration. Our declaration for {_name} was "
            f"correct when it was written and is short by one line as of "
            f"today.\n\n"
            f"No supplier is at fault here and there is nothing to return. "
            f"This is ours to fix at the next release.\n\n"
            f"Regulatory Affairs")


    return _number(recs)


def _number(recs: list[dict]) -> list[dict]:
    """Sort by simulated time, then hand out sequence numbers and ids together.

    Ties keep insertion order, so a re-run cannot shuffle two events that share
    a timestamp.
    """
    recs.sort(key=lambda r: (r["ts"], r["order"]))
    ids = {r["ref"]: f"EVT-{i:05d}" for i, r in enumerate(recs, start=1) if r["ref"]}

    events = []
    for i, rec in enumerate(recs, start=1):
        events.append({
            "id": f"EVT-{i:05d}", "seq": i, "ts": rec["ts"], "type": rec["type"],
            "source": rec["source"], "payload": _resolve(rec["payload"], ids),
            "body": rec["body"],
        })
    return events


def _resolve(value, ids: dict[str, str]):
    """Replace @REF: tokens with the event id the tape actually assigned."""
    if isinstance(value, str) and value.startswith("@REF:"):
        ref = value[5:]
        if ref not in ids:
            raise SystemExit(f"event tape references unknown marker {ref!r}")
        return ids[ref]
    if isinstance(value, dict):
        return {k: _resolve(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, ids) for v in value]
    return value


# ---------------------------------------------------------------------------
# Answer key
#
# Every event already carries, beside its prose, the structured payload that
# prose was written from. That payload is exactly the set of fields the
# extractor is asked to recover, which makes it an answer key that nobody had
# to label - and writing it here, in the same pass as the tape, is the only way
# it stays true. A key kept in its own file drifts the first time an arc is
# edited, and a key that disagrees with the tape measures the wrong thing
# confidently.
#
# ``sc.graph.nodes._extraction_from_payload`` reads the same fields to build the
# deterministic fallback. tests/test_golden.py asserts the two agree, so the key
# cannot drift from the node either.
# ---------------------------------------------------------------------------

# The event types the graph's extract node reads. Feeds, telemetry and channel
# status arrive already structured and are never put in front of a model, so
# scoring them would flatter the number with 250 documents nobody asks it to
# read.
READ_BY_EXTRACT = ("SPEC_DOC", "COMMS")

# The payload speaks the catalog's vocabulary; the extraction prompt offers
# three answers. PRODUCT is the ambiguity the whole of scenario one exists for -
# a document that names the product has not named the model - and ALL is the
# opposite: a document that enumerates every format has named them all.
APPLIES_TO_CLASSES = ("BASE", "VARIANT", "UNCLEAR")
APPLIES_TO_MAP = {"VARIANT": "VARIANT", "ALL": "VARIANT",
                  "PRODUCT": "UNCLEAR", "UNCLEAR": "UNCLEAR"}


def _moved_by(payload: dict) -> list[dict]:
    """The changes a payload actually asserts, no-ops excluded.

    v3 restates the base model at 45 W to say it did not move. That names a
    variant without correcting it, so it is not a row the catalog ends up with
    and not part of the scope a resolver has to find.
    """
    out = [{"entity_id": str((payload.get("entities") or [""])[0] or ""),
            "attribute_path": payload.get("attribute_path"),
            "old_value": payload.get("old_value"),
            "new_value": payload.get("new_value"),
            "unit": payload.get("unit")}]
    out += [dict(c) for c in payload.get("changes") or [] if isinstance(c, dict)]
    return [c for c in out
            if c.get("attribute_path") and c.get("old_value") != c.get("new_value")]


def _golden_rows(payload: dict) -> list[dict]:
    """Every (entity, attribute, value) a correct reading should leave behind."""
    rows, seen = [], set()
    for change in _moved_by(payload):
        key = (str(change.get("entity_id") or ""), str(change["attribute_path"]))
        if key in seen:
            continue
        seen.add(key)
        rows.append({"entity_id": key[0], "attribute_path": key[1],
                     "new_value": change.get("new_value"),
                     "old_value": change.get("old_value"),
                     "unit": change.get("unit")})
    return rows


def _scope_truth(payload: dict) -> list[str]:
    """The variants the correction lands on, where the payload settles it."""
    named = {str(e) for e in payload.get("entities") or []}
    named |= {str(c.get("entity_id") or "") for c in _moved_by(payload)}
    return sorted(v for v in named if v in VARIANT_BY_ID)


def _applies_to_truth(payload: dict,
                      material: bool) -> tuple[str | None, list[str]]:
    """The 3-class answer, and every answer equally defensible on this document.

    A notice that changes nothing has no scope to get right, so it is scored on
    materiality alone. And a product that ships in one model cannot distinguish
    the three answers at all - BASE, VARIANT and "the product" name the same
    thing - so all three are accepted rather than one being called correct.
    """
    if not material:
        return None, []
    # A payload that states nothing has not said which model it means, which is
    # UNCLEAR - the same reading the deterministic fallback takes, so the key
    # and the fallback cannot disagree about a document neither was told about.
    stated = str(payload.get("applies_to") or "").upper()
    canonical = APPLIES_TO_MAP.get(stated, "UNCLEAR")
    variants = _scope_truth(payload)

    acceptable = {canonical}
    if variants:
        family = [v for v, p, _, _ in VARIANTS
                  if p == VARIANT_BY_ID[variants[0]][1]]
        if len(family) == 1:
            acceptable |= set(APPLIES_TO_CLASSES)
        elif all(VARIANT_BY_ID[v][3] for v in variants):
            acceptable.add("BASE")
    return canonical, sorted(acceptable)


#: Attribute path prefix to correction kind, most consequential first.
#:
#: This is the answer key's copy of `sc.graph.nodes.KIND_BY_PATH`, and
#: `tests/test_golden.py` asserts the two are identical. They cannot simply
#: share one definition: the generator does not import `sc`, and it must not -
#: a key that read its answers out of the implementation it grades would
#: measure nothing. So they are written twice and checked for agreement, which
#: is the only arrangement where a divergence is a test failure rather than a
#: quietly wrong score.
GOLDEN_KIND_BY_PATH = (
    ("compliance.sale_permitted", "REGULATORY_ORDER"),
    ("compliance.export_control", "EXPORT_RESTRICTION"),
    ("food.allergens", "ALLERGEN_CHANGE"),
    ("food.ingredients", "INGREDIENT_CHANGE"),
    ("cosmetic.inci", "COMPOSITION_CHANGE"),
    ("health.active_ingredient", "COMPOSITION_CHANGE"),
    ("textile.fibre_composition", "COMPOSITION_CHANGE"),
    ("compliance.certificate_ref", "CERTIFICATION_LAPSE"),
    ("compliance.min_age", "LEGAL_REQUIREMENT_CHANGE"),
    ("pack.net_quantity", "NET_QUANTITY_CHANGE"),
    ("food.net_weight_g", "NET_QUANTITY_CHANGE"),
    ("origin.country", "ORIGIN_CHANGE"),
)


def _kind_of_path(path: str) -> str:
    for prefix, kind in GOLDEN_KIND_BY_PATH:
        if path == prefix or path.startswith(f"{prefix}."):
            return kind
    return "SPEC_CORRECTION"


def _golden_kind(payload: dict) -> str:
    """Which class of correction the document asserts.

    The same order of precedence the extractor is given: a withdrawal outranks
    what it withdraws, a contradiction outranks the value it contradicts, an
    order not to sell outranks any value it arrives with, and an allergen
    outranks everything a supplier can say.
    """
    if payload.get("withdraws") or payload.get("resolves_issue"):
        return "DOC_WITHDRAWN"
    if payload.get("conflicts_with"):
        return "SOURCE_CONFLICT"
    if payload.get("takedown"):
        return "REGULATORY_ORDER"
    if payload.get("recall"):
        return "SAFETY_RECALL"
    if payload.get("export_restricted"):
        return "EXPORT_RESTRICTION"
    if payload.get("rule_change"):
        return "LEGAL_REQUIREMENT_CHANGE"
    paths = [str(c["attribute_path"]) for c in _moved_by(payload)]
    if not paths:
        return "SPEC_CORRECTION"
    ranked = sorted(
        (next((i for i, (_p, k) in enumerate(GOLDEN_KIND_BY_PATH)
               if k == _kind_of_path(p)), len(GOLDEN_KIND_BY_PATH)), n)
        for n, p in enumerate(paths))
    return _kind_of_path(paths[ranked[0][1]])


def _golden_label(payload: dict, material: bool) -> str:
    """What this document is, in four words - so the report reads as a table."""
    if payload.get("zero_delta"):
        return "republication, nothing moved"
    if not material:
        return "immaterial notice"
    if payload.get("withdraws") or payload.get("resolves_issue"):
        return "withdrawal"
    if payload.get("conflicts_with"):
        return "contradicts a current source"
    if payload.get("provisional"):
        return "provisional notice"
    return "correction" if payload.get("is_correction") else "notice"


#: How many immaterial background documents the answer key keeps.
#:
#: The key needs negatives - a category note that asserts nothing must not be
#: read as a correction, and an extractor that hallucinates one should score
#: badly for it. It does not need three hundred of them: a class that outnumbers
#: the positives thirty to one turns any aggregate score into a measure of how
#: often the model correctly says "nothing here", which is not the question the
#: eval is asking. So the negatives are sampled and the positives are all kept.
GOLDEN_NEGATIVES = 40


def build_golden(events: list[dict]) -> list[dict]:
    """The answer key, one row per document the extractor is asked to read."""
    rows = []
    negatives = 0
    for event in events:
        if event["type"] not in READ_BY_EXTRACT:
            continue
        payload = event["payload"]
        # Every material document, and a bounded sample of the rest.
        if not payload.get("material_hint", True):
            negatives += 1
            if negatives > GOLDEN_NEGATIVES:
                continue
        material = bool(payload.get("material_hint", True))
        applies_to, acceptable = _applies_to_truth(payload, material)
        scope = _scope_truth(payload)
        rows.append({
            "event_id": event["id"],
            "event_type": event["type"],
            "ts": event["ts"],
            "label": _golden_label(payload, material),
            "doc_id": payload.get("doc_id"),
            "doc_version": payload.get("doc_version"),
            "subject": str(payload.get("subject")
                           or payload.get("summary") or "")[:120],
            "material": material,
            "kind": _golden_kind(payload),
            "product": payload.get("product"),
            "entities": sorted(str(e) for e in payload.get("entities") or []),
            "attribute_path": payload.get("attribute_path"),
            "old_value": payload.get("old_value"),
            "new_value": payload.get("new_value"),
            "unit": payload.get("unit"),
            "effective": payload.get("effective_from"),
            "is_correction": bool(payload.get("is_correction")),
            "resolves_issue": bool(payload.get("resolves_issue")),
            "provisional": bool(payload.get("provisional")),
            "applies_to": applies_to,
            "applies_to_stated": str(payload.get("applies_to") or "") or None,
            "applies_to_acceptable": acceptable,
            "scope_entities": scope,
            "scope_determinate": bool(scope) and material,
            "rows": _golden_rows(payload),
        })
    return rows


def render_eml(event: dict) -> str:
    payload = event["payload"]
    return (
        f"Message-ID: <{event['id']}@productintel.local>\n"
        f"Date: {event['ts']}\n"
        f"From: {payload['from']}\n"
        f"To: {payload.get('to', MAILBOX_TO)}\n"
        f"Subject: {payload['subject']}\n"
        f"X-Event-Id: {event['id']}\n"
        + (f"X-Doc-Ref: {payload['doc_id']} {payload.get('doc_version', '')}\n"
           if payload.get("doc_id") else "")
        + f"\n{event['body']}\n"
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _jsonl_text(rows: list[dict]) -> str:
    return "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )


def _json_text(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_pack(seed: int) -> tuple[dict[str, str], dict]:
    """Everything the seed pack contains, as filename -> text plus the model.

    Returning the text rather than writing it is what makes the byte-identity
    assertion cheap: main builds the pack twice and compares before anything
    touches the disk.
    """
    global rng
    rng = Rng(seed)

    nodes = build_nodes()
    listings = build_listings()
    assets = build_assets(listings)
    source_docs = build_source_docs()
    events = build_events(listings)

    media = build_media()

    catalog = {
        "nodes": nodes,
        "products": [{"id": p, "name": n, "category": c, "supplier": s, "regulated": r}
                     for p, n, c, s, r in PRODUCTS],
        "variants": [{"id": v, "product_id": p, "name": n, "is_base": b,
                      "sku": SKUS[v]}
                     for v, p, n, b in VARIANTS],
        "media": media,
        "channels": [{"id": c, "name": n, "kind": k, "taxonomy": t, "freeze_days": f,
                      "attribute_map": am, "category_map": cm}
                     for c, n, k, t, f, am, cm in CHANNELS],
        "rules": [{"id": i, "channel_id": c, "field": f, "kind": k,
                   "attribute_path": ap, "value": v, "severity": s, "detail": dt}
                  for i, c, f, k, ap, v, s, dt in RULES],
        "listings": listings,
        "attributes": [{"path": p, "label": lb, "dtype": dt, "unit": u,
                        "safety_class": sc, "ordered": o, "required_for": rf,
                        "applies_to": at}
                       for p, lb, dt, u, sc, o, rf, at in ATTR_DEFS],
        "taxonomy": {"internal": TAXONOMY},
        # Which branches exist, what each is called, which imagery it cannot
        # launch without and which of them are regulated. Written here so the
        # running system reads one answer from the baseline rather than holding
        # a second copy in `sc/` that drifts from the assortment it describes.
        "profile": retailer.as_catalog_block(),
        "horizon_start": HORIZON_START.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "inject": {
            "day": INJECT_DAY, "date": INJECT_DATE.isoformat(), "main_doc": "DOC-01",
            "scenario2_day": SCENARIO2_DAY, "rejection_day": REJECTION_DAY,
            "finale_day": FINALE_DAY,
        },
    }

    attribute_rows = [
        {"entity_id": e, "path": p, "value": v, "source_doc": doc, "source_version": ver}
        for e, p, v, doc, ver in ATTR_ROWS
    ]

    golden = build_golden(events)

    files = {
        "catalog.json": _json_text(catalog),
        "attributes.jsonl": _jsonl_text(attribute_rows),
        "content_assets.jsonl": _jsonl_text(assets),
        "source_docs.jsonl": _jsonl_text(source_docs),
        "events.jsonl": _jsonl_text(events),
        # Regenerated with the data it grades, so it cannot rot behind it.
        "golden/extractions.jsonl": _jsonl_text(golden),
    }
    files.update(build_media_files(media))
    for name, body in DOC_BODIES.items():
        files[f"docs/{name}.txt"] = body
    for event in events:
        if event["type"] == "COMMS":
            files[f"comms/{event['id']}.eml"] = render_eml(event)

    model = {"catalog": catalog, "listings": listings, "assets": assets,
             "source_docs": source_docs, "events": events, "golden": golden}
    return files, model


def digest(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(files[name].encode("utf-8"))
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Self-validation
#
# The pack has to be clean on arrival: the validator must report zero
# violations against the untouched catalog, or the demo cannot tell the
# difference between damage the correction did and damage the generator did.
# The rule engine is re-implemented here against the same ChannelRule rows the
# runtime reads, so this file proves its own output rather than trusting one.
# ---------------------------------------------------------------------------

REQUIRED_ASSET_FIELDS = {
    "CH-WEB": {"title", "bullets", "description"},
    "CH-MKT-A": {"title", "bullets", "description", "feed_row"},
    "CH-MKT-B": {"title", "bullets", "description", "feed_row"},
    "CH-PRINT": {"title", "bullets", "description", "catalogue_copy"},
    "CH-SHELF": {"title", "bullets", "description", "shelf_text"},
    "CH-SEARCH": {"title", "bullets", "description", "facets"},
}

# Widths, not shapes: a catalog of a hundred and fifty products has three-digit
# product ids and four-digit assets, and a pattern that only matched two would
# silently stop checking most of the pack rather than failing loudly.
ID_PATTERN = re.compile(
    r"\b(?:PRD-\d{2,}|VAR-\d{2,}[A-Z]|LST-\d{2,}|AST-\d{3,}|DOC-\d{2,}"
    r"|RUL-[A-Z]\d{2}|SUP-\d{2,}|CH-[A-Z][A-Z-]*)\b"
)


def check_assets(listings: list[dict], assets: list[dict]) -> list[str]:
    by_listing: dict[str, set[str]] = {}
    for asset in assets:
        by_listing.setdefault(asset["listing_id"], set()).add(asset["field"])

    problems = []
    for listing in listings:
        have = by_listing.get(listing["id"], set())
        missing = REQUIRED_ASSET_FIELDS[listing["channel_id"]] - have
        if missing:
            problems.append(
                f"{listing['id']} ({listing['channel_id']}) is missing "
                f"{sorted(missing)}")
    return problems


def check_rules(listings: list[dict], assets: list[dict]) -> list[str]:
    by_listing: dict[str, dict[str, dict]] = {}
    for asset in assets:
        by_listing.setdefault(asset["listing_id"], {})[asset["field"]] = asset

    problems = []
    for listing in listings:
        vid, cid = listing["variant_id"], listing["channel_id"]
        category = category_of(vid)
        attrs = attrs_for(vid)
        view = dict(channel_view(vid, cid))
        for field, asset in by_listing.get(listing["id"], {}).items():
            view[field] = asset["text"]

        for rid, rule_cid, field, kind, path, value, severity, _ in RULES:
            if rule_cid != cid:
                continue
            # A rule bound to an attribute only applies where that attribute does.
            if path and not applies(path, category):
                continue

            if kind == "CATEGORY_MAPPED":
                if category not in CHANNEL_BY_ID[cid][6]:
                    problems.append(f"{rid} {listing['id']}: {category} unmapped")
                continue

            if field not in view:
                if kind == "REQUIRED":
                    problems.append(f"{rid} {listing['id']}: {field} missing")
                continue

            actual = view[field]
            if kind == "REQUIRED" and actual in (None, "", []):
                problems.append(f"{rid} {listing['id']}: {field} empty")
            elif kind == "DTYPE" and value == "int" and not isinstance(actual, int):
                problems.append(f"{rid} {listing['id']}: {field} is not an int")
            elif kind == "MAX_LEN":
                size = (len(actual.split("\n")) if field == "bullets"
                        else len(str(actual)))
                if size > value:
                    problems.append(
                        f"{rid} {listing['id']}: {field} is {size}, budget {value}")
            elif kind == "FORMAT" and not re.search(value, str(actual)):
                problems.append(f"{rid} {listing['id']}: {field} fails {value}")
            elif kind == "ENUM":
                bad = [m for m in actual if m not in value]
                if bad:
                    problems.append(f"{rid} {listing['id']}: {field} has {bad}")
            elif kind == "ORDERED_MATCH" and list(actual) != list(attrs[value]):
                problems.append(f"{rid} {listing['id']}: {field} order differs")

        # Every mandatory attribute for this channel must have a value on file.
        for apath, _, _, _, _, _, required_for, _ in ATTR_DEFS:
            if cid in required_for and applies(apath, category) and apath not in attrs:
                problems.append(
                    f"{listing['id']}: {apath} is required on {cid} and has no value")

    return problems


def check_claims(listings: list[dict], assets: list[dict]) -> list[str]:
    """A claim on a variant, or used in a sentence, must be substantiated."""
    problems = []
    for vid, _, _, _ in VARIANTS:
        attrs = attrs_for(vid)
        for claim in attrs.get("claims") or []:
            if claim in CLAIM_RULES and not CLAIM_RULES[claim](attrs):
                problems.append(f"{vid}: claims {claim} but the rule fails")

    variant_of = {l["id"]: l["variant_id"] for l in listings}
    for asset in assets:
        attrs = attrs_for(variant_of[asset["listing_id"]])
        for claim in asset["claims_used"]:
            if claim in CLAIM_RULES and not CLAIM_RULES[claim](attrs):
                problems.append(f"{asset['id']}: uses {claim}, which does not hold")
    return problems


def check_landmine(listings: list[dict], assets: list[dict]) -> list[str]:
    """The 45 W literal has to be in the copy, or the blast radius is notional."""
    variant_of = {l["id"]: l["variant_id"] for l in listings}
    channel_of = {l["id"]: l["channel_id"] for l in listings}
    problems = []
    quoting = 0

    for asset in assets:
        vid = variant_of[asset["listing_id"]]
        if not vid.startswith("VAR-01"):
            continue
        if not any(ref.endswith(":specs.power_w") for ref in asset["derived_from"]):
            continue
        if asset["field"] in ("feed_row", "facets"):
            continue  # structured: the wattage is an int, not a literal
        quoting += 1
        if "45W" not in asset["text"] and "45 W" not in asset["text"]:
            problems.append(f"{asset['id']} ({asset['field']}) quotes power without "
                            "writing 45W")

    if quoting < 8:
        problems.append(f"only {quoting} PRD-01 assets quote the wattage literally")

    bullet = "Ultra-quiet 45W operation for bedrooms and studies"
    for asset in assets:
        vid = variant_of[asset["listing_id"]]
        if (vid.startswith("VAR-01") and channel_of[asset["listing_id"]] == "CH-WEB"
                and asset["field"] == "bullets" and bullet not in asset["text"]):
            problems.append(f"{asset['id']}: CH-WEB bullets must open with {bullet!r}")

    table = [a for a in assets if a["field"] == "comparison_table"]
    if len(table) != 1:
        problems.append(f"expected exactly one comparison_table, found {len(table)}")
    else:
        listing = table[0]["listing_id"]
        if variant_of[listing] != "VAR-01A" or channel_of[listing] != "CH-WEB":
            problems.append("comparison_table is not on VAR-01A's CH-WEB listing")
        for ref in ("VAR-01A:specs.power_w", "VAR-01B:specs.power_w"):
            if ref not in table[0]["derived_from"]:
                problems.append(f"comparison_table does not name {ref}")

    return problems


def check_golden(events: list[dict], golden: list[dict]) -> list[str]:
    """The answer key has to be usable, and it has to still contain the question.

    An eval whose key has quietly lost its ambiguous correction reports a clean
    UNCLEAR column and has measured nothing - so the classes the scenario turns
    on are asserted here rather than assumed to survive an edit to an arc.
    """
    problems = []
    readable = [e for e in events if e["type"] in READ_BY_EXTRACT]
    on_tape = {e["id"] for e in readable}
    keyed = [g["event_id"] for g in golden]

    # Every material document is keyed. This is the half that must not slip:
    # a correction the tape carries and the key has forgotten is a correction
    # the eval will mark a model wrong for finding.
    material = [e["id"] for e in readable
                if e["payload"].get("material_hint", True)]
    missing = [e for e in material if e not in set(keyed)]
    if missing:
        problems.append(f"the answer key is missing {len(missing)} material "
                        f"document(s), first {missing[0]}")

    # The other half is that the key cannot invent one, or drift out of tape
    # order - both of which would make it a second account of the tape rather
    # than a view of it. The immaterial documents are deliberately sampled; see
    # GOLDEN_NEGATIVES.
    stray = [g for g in keyed if g not in on_tape]
    if stray:
        problems.append(f"the answer key names {len(stray)} document(s) the "
                        f"tape does not carry, first {stray[0]}")
    if keyed != sorted(keyed):
        problems.append("the answer key is not in tape order")
    if len(golden) < 12:
        problems.append(f"answer key has {len(golden)} rows, wanted at least 12")

    for g in golden:
        if g["applies_to"] not in (None, *APPLIES_TO_CLASSES):
            problems.append(f"{g['event_id']} keys applies_to {g['applies_to']!r}")
        for row in g["rows"]:
            if row["attribute_path"] not in ATTR_BY_PATH:
                problems.append(f"{g['event_id']} keys unknown attribute "
                                f"{row['attribute_path']!r}")
            if (row["entity_id"] not in VARIANT_BY_ID
                    and row["entity_id"] not in PRODUCT_BY_ID):
                problems.append(f"{g['event_id']} keys unknown entity "
                                f"{row['entity_id']!r}")

    if not any(not g["material"] for g in golden):
        problems.append("no immaterial notice in the key: precision on "
                        "materiality would be unmeasurable")
    if not any(g["applies_to"] == "UNCLEAR" and g["is_correction"] for g in golden):
        problems.append("no ambiguous correction in the key: the UNCLEAR class "
                        "is what scenario one exists to protect")
    if not any(g["scope_determinate"] and len(g["scope_entities"]) == 1
               for g in golden):
        problems.append("no correction with a single named variant in the key")
    if not any(len(g["rows"]) > 1 for g in golden):
        problems.append("no multi-field correction in the key")
    return problems


def check_ids(model: dict, files: dict[str, str]) -> tuple[list[str], list[str]]:
    """Nothing may name an entity the catalog does not have.

    The corpus is rewritten by a separate work package. It is only checked once
    it speaks this domain at all - before then every id in it belongs to the
    previous one by definition, and failing here would block the seed pack on
    somebody else's file.
    """
    known = {n["id"] for n in model["catalog"]["nodes"]}
    known |= {l["id"] for l in model["listings"]}
    known |= {a["id"] for a in model["assets"]}
    known |= {d["id"] for d in model["source_docs"]}
    known |= {r["id"] for r in model["catalog"]["rules"]}

    def unknown(text: str) -> set[str]:
        return {m for m in ID_PATTERN.findall(text) if m not in known}

    problems = []
    for event in model["events"]:
        text = json.dumps(event["payload"], sort_keys=True) + (event["body"] or "")
        for bad in sorted(unknown(text)):
            problems.append(f"{event['id']} names unknown entity {bad}")
    for name, body in sorted(files.items()):
        if name.startswith(("docs/", "comms/")):
            for bad in sorted(unknown(body)):
                problems.append(f"{name} names unknown entity {bad}")

    corpus_notes = []
    if CORPUS.is_dir():
        text = "".join(p.read_text(encoding="utf-8")
                       for p in sorted(CORPUS.rglob("*.md")))
        migrated = any(marker in text for marker in ("PRD-0", "VAR-0", "CH-MKT"))
        bad = sorted(unknown(text))
        if migrated and bad:
            problems.append(f"corpus names unknown entities {bad}")
        elif bad:
            corpus_notes.append(
                f"corpus still on the previous domain ({len(bad)} foreign ids) - "
                "not checked")
    return problems, corpus_notes


def check_seeded(media: list[dict], assets: list[dict],
                 listings: list[dict]) -> list[str]:
    """The background contains exactly the damage it declared.

    The background is generated, so "some products are broken" is easy to say
    and impossible to rely on: a refactor that silently stopped seeding
    anything would leave a catalog where every product is clean and a demo
    where the readiness screen has nothing to show, and nothing would fail.

    So the damage has an answer key of its own, written as it is seeded and
    read back here - the same property `check_golden` gives the extraction key,
    extended to the half of the catalog nobody hand-wrote. Both directions are
    checked: everything declared is present, and the counts are large enough to
    be worth having.
    """
    problems: list[str] = []
    held = {(a["entity_id"], a["role"]) for a in media}
    by_variant: dict[str, set[str]] = {}
    variant_of = {l["id"]: l["variant_id"] for l in listings}
    for asset in assets:
        by_variant.setdefault(variant_of[asset["listing_id"]], set()).add(
            asset["text"])

    counts: dict[str, int] = {}
    for entity_id, declared in sorted(SEEDED_DEFECTS.items()):
        for kind, subject in declared:
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "required_media":
                if (entity_id, subject) in held:
                    problems.append(
                        f"{entity_id} declares a missing {subject} image and "
                        f"the catalog holds one")
            elif kind == "applicable_attributes":
                if (entity_id, subject) in ATTR_VALUES:
                    problems.append(
                        f"{entity_id} declares {subject} missing and the "
                        f"catalog holds a value for it")
            elif kind == "forbidden_content":
                texts = by_variant.get(entity_id, set())
                if not any(_has_forbidden(t) for t in texts):
                    problems.append(
                        f"{entity_id} declares forbidden copy and none of its "
                        f"assets carries any")
            elif kind == "declared_types":
                # The supplier answered, in the wrong shape. Present and
                # unparseable is the assertion; a value that still parses as
                # its declared type would mean the spoiling silently stopped
                # working and the check list would look complete when it is not.
                value = ATTR_VALUES.get((entity_id, subject))
                if value is None:
                    problems.append(
                        f"{entity_id} declares {subject} mistyped and the "
                        f"catalog holds no value for it")
                elif _parses_as(value, _DTYPE_OF.get(subject, "str")):
                    problems.append(
                        f"{entity_id} declares {subject} mistyped and "
                        f"{value!r} is a valid "
                        f"{_DTYPE_OF.get(subject, 'str')}")
            else:
                problems.append(f"{entity_id} declares unknown defect {kind!r}")

    # Contrast, not just presence. An estate where three products are wrong
    # measures nothing, and one where all of them are measures nothing either.
    for kind, least in (("applicable_attributes", 20), ("required_media", 20),
                        ("forbidden_content", 5), ("declared_types", 10)):
        if counts.get(kind, 0) < least:
            problems.append(f"only {counts.get(kind, 0)} seeded {kind} "
                            f"defect(s), wanted at least {least}")
    seeded = len(SEEDED_DEFECTS)
    if not 0.15 * len(VARIANTS) <= seeded <= 0.65 * len(VARIANTS):
        problems.append(
            f"{seeded} of {len(VARIANTS)} variants carry a seeded defect, "
            f"which is either too few to find or too many to contrast against")
    return problems


#: Declared type per attribute, read off the definitions rather than repeated,
#: so an attribute whose dtype changes cannot leave this check grading against
#: the old one.
_DTYPE_OF = {row[0]: row[2] for row in ATTR_DEFS}


def _parses_as(value: object, dtype: str) -> bool:
    """Would the readiness check accept this value as its declared type?

    Mirrors `sc.readiness.checks._is_dtype` rather than approximating it: a
    generator that graded mistyping more leniently than the check does would
    seed defects the check then failed to find, which is the one thing the
    answer key exists to prevent.
    """
    if dtype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if dtype == "bool":
        return isinstance(value, bool)
    if dtype == "list[str]":
        return isinstance(value, list)
    return isinstance(value, str)


#: The phrases the readiness check refuses, mirrored here so the generator can
#: assert it planted one. Kept short and matched on whole words, the same way
#: `checks.FORBIDDEN_PHRASES` is.
_FORBIDDEN = ("cures", "treats", "prevents", "clinically proven",
              "completely safe", "harmless", "guaranteed to", "100% effective")


def _has_forbidden(text: str) -> bool:
    haystack = f" {text.lower()} "
    return any(f" {phrase} " in haystack or f" {phrase}." in haystack
               for phrase in _FORBIDDEN)


def check_tape(events: list[dict]) -> list[str]:
    """The tape is the right size, in order, and still carries every arc.

    The size band is derived from the catalog rather than written down. It used
    to be "250 to 320", which was a true statement about six products and
    became a false one the moment there were a hundred and fifty - and the
    interesting property was never the number, it was that routine traffic had
    not swamped the story or dried up.
    """
    problems = []
    low = 200 + 25 * HORIZON_DAYS
    high = 200 + 130 * HORIZON_DAYS
    if not low <= len(events) <= high:
        problems.append(f"tape has {len(events)} events, wanted {low}-{high}")
    previous = ""
    for i, event in enumerate(events, start=1):
        if event["seq"] != i:
            problems.append(f"{event['id']} has seq {event['seq']}, expected {i}")
        if event["ts"] < previous:
            problems.append(f"{event['id']} goes backwards in simulated time")
        previous = event["ts"]

    for arc, matcher in (
        ("arc 3", lambda e: e["payload"].get("doc_version") == "v2"
                            and e["payload"].get("doc_id") == "DOC-01"),
        ("arc 4", lambda e: e["payload"].get("doc_id") == "DOC-04"),
        ("arc 5", lambda e: e["payload"].get("code") == "MKB-2201"),
        ("arc 6", lambda e: e["payload"].get("doc_version") == "v3"),
    ):
        if not any(matcher(e) for e in events):
            problems.append(f"{arc} is missing from the tape")

    # The seven wider arcs, matched on the document each arrives on. An arc
    # whose target the assortment does not contain is skipped rather than
    # missing - a retailer with no cosmetics counter cannot have the cosmetics
    # arc, and failing the build over it would be the profile seam refusing to
    # be used. What is checked is that an arc with a target actually landed.
    for (_day, key, _prefix, path), (doc, *_rest) in zip(
            WIDER_ARCS, ARC_SOURCE_DOCS):
        if key not in ARC_TARGET:
            continue
        carried = [e for e in events if e["payload"].get("doc_id") == doc]
        if not carried:
            problems.append(f"wider arc {key!r} is missing from the tape")
            continue
        target = ARC_TARGET[key]
        if not any(target in (e["payload"].get("entities") or [])
                   for e in carried):
            problems.append(
                f"wider arc {key!r} does not name {target}, the variant it "
                f"was selected for")
        if not any(e["payload"].get("attribute_path") == path
                   for e in carried):
            problems.append(
                f"wider arc {key!r} does not move {path}, which is the whole "
                f"reason it exists")

    # The three that are orders rather than corrections have to say so in the
    # payload, because that flag is what the deterministic fallback reads to
    # classify them - and a takedown misread as a spec correction publishes.
    for key, flag in (("takedown", "takedown"),
                      ("export", "export_restricted"),
                      ("rule_change", "rule_change")):
        if key not in ARC_TARGET:
            continue
        if not any(e["payload"].get(flag) for e in events):
            problems.append(f"wider arc {key!r} carries no {flag!r} flag")

    finale = [e for e in events if e["payload"].get("doc_version") == "v3"]
    inject = {e["id"] for e in events if e["payload"].get("doc_id") == "DOC-01"
              and e["payload"].get("doc_version") == "v2"}
    for event in finale:
        if event["payload"].get("corrects") not in inject:
            problems.append(f"{event['id']} does not point back at the DOC-01 v2 event")
        if event["payload"].get("entities") != ["VAR-01B"]:
            problems.append(f"{event['id']} must resolve to VAR-01B only")
    for event in events:
        if (event["payload"].get("doc_id") == "DOC-01"
                and event["payload"].get("doc_version") == "v2"
                and event["payload"].get("applies_to") != "UNCLEAR"):
            problems.append(f"{event['id']} must leave the scope unclear")
    return problems


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_pack(files: dict[str, str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in STALE_FILES:
        (DATA / name).unlink(missing_ok=True)
    for directory in (DOCS, COMMS, GOLDEN, MEDIA):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    for name in sorted(files):
        path = DATA / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding="utf-8", newline="\n")


def drop_accepted_lines(out: Path) -> None:
    """Remove any lines accepted into the previous pack.

    A reseed is a new world. A product a reviewer accepted from a supplier's
    proposal happened in the old one, and carrying it across would leave the
    catalog holding an entity no document in the new pack has ever mentioned -
    which is the one thing the generator's own checks cannot catch, because
    they are computed from what it wrote.
    """
    extension = out / "catalog.live.json"
    if extension.exists():
        extension.unlink()


def main() -> None:
    print(f"Generating seed pack (seed={SEED}, horizon={HORIZON_DAYS}d "
          f"from {HORIZON_START})")

    files, model = build_pack(SEED)
    again, _ = build_pack(SEED)
    if files != again:
        differing = sorted(set(files) ^ set(again)) or sorted(
            n for n in files if files[n] != again[n])
        raise SystemExit(f"the generator is not deterministic: {differing}")

    problems: list[str] = []
    problems += check_assets(model["listings"], model["assets"])
    problems += check_rules(model["listings"], model["assets"])
    problems += check_claims(model["listings"], model["assets"])
    problems += check_landmine(model["listings"], model["assets"])
    problems += check_seeded(model["catalog"]["media"], model["assets"],
                             model["listings"])
    problems += check_tape(model["events"])
    problems += check_golden(model["events"], model["golden"])
    id_problems, notes = check_ids(model, files)
    problems += id_problems

    write_pack(files)
    drop_accepted_lines(DATA)

    events = model["events"]
    comms = sum(1 for e in events if e["type"] == "COMMS")
    docs = sum(1 for e in events if e["type"] == "SPEC_DOC")
    for name in ("catalog.json", "attributes.jsonl", "content_assets.jsonl",
                 "source_docs.jsonl", "events.jsonl"):
        print(f"  {name:24s} {(DATA / name).stat().st_size:7d} bytes")
    print(f"  golden/extractions.jsonl "
          f"{(DATA / 'golden/extractions.jsonl').stat().st_size:7d} bytes")
    print(f"  docs/*.txt               {len(DOC_BODIES):7d} files")
    print(f"  comms/*.eml              {comms:7d} files")
    print(f"\n  {len(model['listings'])} listings, {len(model['assets'])} content "
          f"assets, {len(ATTR_ROWS)} attribute values")
    print(f"  {len(events)} events, {comms} comms, {docs} document versions, "
          f"inject at day {INJECT_DAY} ({INJECT_DATE})")
    keyed = model["golden"]
    print(f"  {len(keyed)} documents in the extraction answer key "
          f"({sum(1 for g in keyed if g['material'])} material, "
          f"{sum(1 for g in keyed if g['scope_determinate'])} with a settled scope)")
    print(f"  pack digest {digest(files)} (identical across runs at this seed)")
    for note in notes:
        print(f"  note: {note}")

    if problems:
        print("\nThe baseline is not clean:")
        for line in problems:
            print(f"  - {line}")
        raise SystemExit(
            f"{len(problems)} problem(s) in the generated pack. The untouched "
            "catalog must validate with zero violations, or the demo cannot tell "
            "the correction's damage from the generator's.")

    print("  baseline validates clean: 0 violations against the untouched catalog")


if __name__ == "__main__":
    main()
