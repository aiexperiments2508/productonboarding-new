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
DOC-01 v1 folded a measurement sheet for one AeroPure model into the summary
table for the range, so the baseline genuinely carries 45 W on the Max and is
nonetheless internally consistent - the validator finds nothing wrong with it
until the correction lands. Every prepared PRD-01 asset that quotes wattage
writes the literal "45W", which is what makes the blast radius of a single
attribute correction real rather than notional.
"""

from __future__ import annotations

import hashlib
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
GOLDEN = DATA / "golden"
CORPUS = ROOT / "corpus"

SEED = int(os.environ.get("DATA_SEED", "20802"))
HORIZON_START = date(2026, 9, 1)
HORIZON_DAYS = 56  # 8 weeks

# The main inject lands four weeks in, leaving prepared content behind it and
# three more arcs of runway ahead.
INJECT_DAY = 28
INJECT_DATE = HORIZON_START + timedelta(days=INJECT_DAY)
SCENARIO2_DAY = 30   # allergen change
REJECTION_DAY = 31   # marketplace bounce
FINALE_DAY = 32      # "Max only" clarification

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


# ---------------------------------------------------------------------------
# Catalog constants - hand-authored, never generated
# ---------------------------------------------------------------------------

SUPPLIERS = [
    # id,       name,                     family
    ("SUP-01", "Voltaic Home",           "home"),
    ("SUP-02", "Orchard Valley Foods",   "food"),
    ("SUP-03", "Brightline Electronics", "audio"),
    ("SUP-04", "Cascade Housewares",     "home"),
]

PRODUCTS = [
    # id,       name,                              category,                      supplier,  regulated
    ("PRD-01", "AeroPure 300 Air Purifier",       "home.air-treatment.purifiers", "SUP-01", False),
    ("PRD-02", "Orchard Valley Trail Mix Bar",    "food.snacks.bars",             "SUP-02", True),
    ("PRD-03", "Brightline BT-200 Earbuds",       "audio.headphones.earbuds",     "SUP-03", False),
    ("PRD-04", "Cascade Rapid Kettle",            "home.kitchen.kettles",         "SUP-04", False),
    ("PRD-05", "Orchard Valley Granola Clusters", "food.snacks.granola",          "SUP-02", True),
    ("PRD-06", "Voltaic Desk Fan V2",             "home.air-treatment.fans",      "SUP-01", False),
]

VARIANTS = [
    # id,        product,  name,                            is_base
    ("VAR-01A", "PRD-01", "AeroPure 300",                   True),
    ("VAR-01B", "PRD-01", "AeroPure 300 Max",               False),
    ("VAR-02A", "PRD-02", "Trail Mix Bar 40g",              True),
    ("VAR-02B", "PRD-02", "Trail Mix Bar Multipack 6x40g",  False),
    ("VAR-03A", "PRD-03", "Brightline BT-200 Earbuds",      True),
    ("VAR-04A", "PRD-04", "Cascade Rapid Kettle 1.7L",      True),
    ("VAR-05A", "PRD-05", "Granola Clusters 300g",          True),
    ("VAR-06A", "PRD-06", "Voltaic Desk Fan V2",            True),
]

TAXONOMY = {
    "home": "Home",
    "home.air-treatment": "Home > Air Treatment",
    "home.air-treatment.purifiers": "Home > Air Treatment > Air Purifiers",
    "home.air-treatment.fans": "Home > Air Treatment > Fans",
    "home.kitchen": "Home > Kitchen",
    "home.kitchen.kettles": "Home > Kitchen > Kettles",
    "food": "Food",
    "food.snacks": "Food > Snacks",
    "food.snacks.bars": "Food > Snacks > Cereal & Snack Bars",
    "food.snacks.granola": "Food > Snacks > Granola",
    "audio": "Audio",
    "audio.headphones": "Audio > Headphones",
    "audio.headphones.earbuds": "Audio > Headphones > Earbuds",
}

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

MKT_A_CATS = {
    "home.air-treatment.purifiers": "1043/2210 Air Purifiers",
    "food.snacks.bars": "3120/4415 Cereal Bars",
    "food.snacks.granola": "3120/4460 Granola & Muesli",
    "audio.headphones.earbuds": "2255/6610 In-Ear Headphones",
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
    ("specs.power_w", "Rated power", "int", "W", False, False,
     ["CH-MKT-A", "CH-MKT-B", "CH-PRINT", "CH-SHELF"], ["home."]),
    ("specs.noise_db", "Sound level", "int", "dB", False, False, [], ["home."]),
    ("specs.coverage_m2", "Coverage area", "int", "m²", False, False,
     [], ["home.air-treatment"]),
    ("specs.filter_type", "Filter type", "str", None, False, False,
     [], ["home.air-treatment"]),
    ("energy.class", "Energy class", "str", None, False, False, [], ["home."]),
    ("food.ingredients", "Ingredients", "list[str]", None, False, True,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food."]),
    ("food.allergens.contains", "Allergens - contains", "list[str]", None, True, False,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food."]),
    ("food.allergens.may_contain", "Allergens - may contain", "list[str]", None, True, False,
     ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-PRINT"], ["food."]),
    ("food.net_weight_g", "Net weight", "int", "g", False, False, [], ["food."]),
    ("food.fibre_g", "Fibre", "float", "g", False, False, [], ["food."]),
    # No applies_to prefix means every category.
    ("identifiers.gtin", "GTIN", "str", None, False, False, ["CH-MKT-A", "CH-MKT-B"], []),
    ("claims", "Claims", "list[str]", None, False, False, [], []),
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
    ("RUL-B03", "CH-MKT-B", "allergenCodes", "ENUM", "food.allergens.contains",
     ["AL-PEANUT", "AL-NUT", "AL-MILK", "AL-GLUTEN", "AL-SOY", "AL-EGG"], "HARD",
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
}

ALLERGEN_CODES = {
    "almonds": "AL-NUT", "hazelnuts": "AL-NUT", "nuts": "AL-NUT",
    "peanut": "AL-PEANUT", "peanuts": "AL-PEANUT",
    "milk": "AL-MILK", "gluten": "AL-GLUTEN", "wheat": "AL-GLUTEN",
    "barley": "AL-GLUTEN", "soy": "AL-SOY", "soya": "AL-SOY",
    "egg": "AL-EGG", "eggs": "AL-EGG",
}


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
]

SOURCE_DOCS = [
    # id, supplier, kind, version, title, received (day offset from 2026-08-01),
    # precedence, has prose body
    ("DOC-01", "SUP-01", "SPEC_SHEET", "v1",
     "AeroPure 300 range technical specification", "2026-08-12", 30, True),
    ("DOC-02", "SUP-01", "PORTAL_FEED", "v1",
     "Voltaic Home portal attribute feed", "2026-08-14", 20, False),
    ("DOC-03", "SUP-02", "LABEL_ARTWORK", "v1",
     "Trail Mix Bar pack label artwork", "2026-08-16", 40, True),
    ("DOC-04", "SUP-02", "SPEC_SHEET", "v1",
     "Orchard Valley allergen and ingredient notice", "2026-08-16", 30, True),
    ("DOC-05", "SUP-02", "SPREADSHEET", "v1",
     "Orchard Valley portal spreadsheet export", "2026-08-17", 15, False),
    ("DOC-06", "SUP-04", "SPEC_SHEET", "v1",
     "Cascade Rapid Kettle dimensional drawing", "2026-08-18", 30, True),
    ("DOC-07", "SUP-03", "PORTAL_FEED", "v1",
     "Brightline portal attribute feed", "2026-08-19", 20, False),
    ("DOC-08", "SUP-01", "CERTIFICATE", "v1",
     "Voltaic Home declaration of conformity", "2026-08-20", 35, True),
]

LISTING_CHANNELS = {
    "PRD-01": ["CH-WEB", "CH-MKT-A", "CH-PRINT", "CH-SHELF"],
    "PRD-02": ["CH-WEB", "CH-MKT-A", "CH-MKT-B", "CH-SEARCH", "CH-SHELF"],
    "PRD-03": ["CH-WEB", "CH-MKT-A"],
    "PRD-04": ["CH-WEB", "CH-MKT-B"],
    "PRD-05": ["CH-WEB", "CH-MKT-A"],
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
            "AeroPure 300 Air Purifier — HEPA H13 filtration for rooms up to 40 m²",
            ["specs.coverage_m2", "specs.filter_type"], []),
        "mkt_title": (
            "Voltaic AeroPure 300 Air Purifier — HEPA H13, 40 m², 45W",
            ["specs.power_w", "specs.coverage_m2", "specs.filter_type"], []),
        "bullets": ([
            "Ultra-quiet 45W operation for bedrooms and studies",
            "True HEPA H13 filter captures 99.95% of particles down to 0.1 micron",
            "Covers rooms up to 40 m² with a full air change every 18 minutes",
            "Energy class A, with a filter-life indicator and a sleep mode",
        ], SPECS_ALL, AIR_CLAIMS),
        "description": (
            "The AeroPure 300 is a compact air purifier for bedrooms, studies and "
            "home offices of up to 40 m². A sealed True HEPA H13 filter removes "
            "99.95% of airborne particles down to 0.1 micron, including pollen, pet "
            "dander and smoke. At 45 W and 38 dB on the sleep setting it can be left "
            "running overnight without disturbing sleep. Energy class A.",
            SPECS_ALL, AIR_CLAIMS),
        "shelf_text": ("AeroPure 300 · 45W · HEPA H13",
                       ["specs.power_w", "specs.filter_type"], []),
        "catalogue_copy": (
            "AeroPure 300 Air Purifier. True HEPA H13 filtration for rooms up to "
            "40 m², a full air change every 18 minutes, ultra-quiet 45 W operation "
            "at 38 dB on the sleep setting, energy class A and a filter-life "
            "indicator.", SPECS_ALL, AIR_CLAIMS),
    },
    "VAR-01B": {
        "web_title": (
            "AeroPure 300 Max Air Purifier — HEPA H13 filtration for rooms up to 65 m²",
            ["specs.coverage_m2", "specs.filter_type"], []),
        "mkt_title": (
            "Voltaic AeroPure 300 Max Air Purifier — HEPA H13, 65 m², 45W",
            ["specs.power_w", "specs.coverage_m2", "specs.filter_type"], []),
        "bullets": ([
            "Ultra-quiet 45W operation for bedrooms and studies",
            "True HEPA H13 filter captures 99.95% of particles down to 0.1 micron",
            "Covers larger rooms up to 65 m² with a full air change every 20 minutes",
            "Energy class A, with a filter-life indicator and a sleep mode",
        ], SPECS_ALL, AIR_CLAIMS),
        "description": (
            "The AeroPure 300 Max is the larger model in the AeroPure 300 range, "
            "sized for living rooms and open-plan spaces of up to 65 m². The sealed "
            "True HEPA H13 filter is the same grade as the standard model and removes "
            "99.95% of airborne particles down to 0.1 micron. At 45 W and 38 dB on the "
            "sleep setting it is quiet enough to leave running overnight. "
            "Energy class A.", SPECS_ALL, AIR_CLAIMS),
        "shelf_text": ("AeroPure 300 Max · 45W · HEPA H13",
                       ["specs.power_w", "specs.filter_type"], []),
        "catalogue_copy": (
            "AeroPure 300 Max Air Purifier. True HEPA H13 filtration for open-plan "
            "rooms up to 65 m², a full air change every 20 minutes, ultra-quiet 45 W "
            "operation at 38 dB on the sleep setting, energy class A and a "
            "filter-life indicator.", SPECS_ALL, AIR_CLAIMS),
    },
    "VAR-02A": {
        "web_title": ("Orchard Valley Trail Mix Bar 40g — oats, honey and almonds",
                      ["food.net_weight_g", "food.ingredients"], []),
        "mkt_title": (
            "Orchard Valley Trail Mix Bar 40g — Oats, Honey & Almonds, High Fibre",
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
            "Orchard Valley Trail Mix Bar Multipack — 6 x 40g, oats, honey and almonds",
            ["food.net_weight_g", "food.ingredients"], []),
        "mkt_title": ("Orchard Valley Trail Mix Bar Multipack 6 x 40g — High Fibre",
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
            "Brightline BT-200 True Wireless Earbuds — 24 hours of playback", [], []),
        "mkt_title": ("Brightline BT-200 True Wireless Earbuds — 24h Battery, USB-C",
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
        "web_title": ("Cascade Rapid Kettle 1.7L — 3000W rapid boil, brushed steel",
                      ["specs.power_w"], []),
        "mkt_title": ("Cascade Rapid Kettle 1.7L — 3000W Rapid Boil, Brushed Steel",
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
    },
    "VAR-05A": {
        "web_title": ("Orchard Valley Granola Clusters 300g — honey and almond",
                      ["food.net_weight_g"], []),
        "mkt_title": (
            "Orchard Valley Granola Clusters 300g — Honey & Almond, High Fibre",
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
    },
    "VAR-06A": {
        "web_title": ("Voltaic Desk Fan V2 — 28W three-speed fan for desks and rooms",
                      ["specs.power_w"], []),
        "mkt_title": ("Voltaic Desk Fan V2 — 28W, 3 Speeds, Quiet Night Mode",
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

COMPARISON_TABLE = (
    "Model | Rated power | Coverage | Filter | Sound level\n"
    "AeroPure 300 | 45 W | 40 m² | HEPA H13 | 38 dB\n"
    "AeroPure 300 Max | 45 W | 65 m² | HEPA H13 | 38 dB"
)


# ---------------------------------------------------------------------------
# Supplier documents
#
# Extracted text, as the ingestion pipeline would hold it. DOC-01 v2 is the
# whole problem: it corrects the rated power of "the AeroPure 300" and admits
# that one model's measurement sheet was folded into v1, without ever saying
# which model the corrected figure belongs to. v3 is the answer.
# ---------------------------------------------------------------------------

DOC_BODIES = {
    "DOC-01-v1": """VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER RANGE

Document reference: DOC-01
Revision: v1
Issued: 12 August 2026
Prepared by: Specification Control, Voltaic Home

1. MODELS COVERED

  AeroPure 300       (VAR-01A)
  AeroPure 300 Max   (VAR-01B)

2. SUMMARY SPECIFICATION

  Rated power                 45 W
  Sound level, sleep setting  38 dB(A)
  Filter                      True HEPA H13
  Coverage, AeroPure 300      40 m²
  Coverage, AeroPure 300 Max  65 m²
  Energy class                A

3. NOTES

Rated power and sound level are stated for the range. Coverage differs by
model as tabulated above. Figures are taken from the test reports held by
Specification Control.
""",

    "DOC-01-v2": """VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER

Document reference: DOC-01
Revision: v2
Supersedes: v1 (issued 12 August 2026)
Issued: 29 September 2026
Prepared by: Specification Control, Voltaic Home

1. SCOPE

This revision corrects the rated power figure published for the AeroPure 300
air purifier. It supersedes revision v1 in full.

2. CORRECTION

  Rated power (mains, maximum fan setting)    65 W

The figure of 45 W given in revision v1 is withdrawn and must not be used in
customer-facing material issued after the date of this document.

3. REASON FOR CORRECTION

While revision v1 was being compiled, a measurement sheet belonging to one
model in the AeroPure 300 range was transcribed into the summary table for the
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

    "DOC-01-v3": """VOLTAIC HOME LIMITED
TECHNICAL SPECIFICATION - AEROPURE 300 AIR PURIFIER RANGE

Document reference: DOC-01
Revision: v3
Supersedes: v2 (issued 29 September 2026)
Issued: 3 October 2026
Prepared by: Specification Control, Voltaic Home

1. SCOPE

Revision v2 corrected the rated power published for the AeroPure 300 to 65 W
but did not identify the model to which the corrected figure applies. This
revision resolves that ambiguity and supersedes v2 in full.

2. RATED POWER BY MODEL

  AeroPure 300       (VAR-01A)    45 W
  AeroPure 300 Max   (VAR-01B)    65 W

The 65 W figure introduced in revision v2 applies to the AeroPure 300 Max
only. The rated power of the base AeroPure 300 is unchanged at 45 W, and the
figure published for it in revision v1 was correct.

3. MEASURED SOUND LEVEL - AEROPURE 300 MAX

  AeroPure 300 Max   (VAR-01B)    44 dB(A), maximum fan setting
  AeroPure 300       (VAR-01A)    38 dB(A), unchanged

The 44 dB(A) figure is issued for the first time in this revision. The
38 dB(A) published for the AeroPure 300 Max in revisions v1 and v2 was carried
across from the base model in error and is withdrawn.

4. UNCHANGED

Filter type, coverage area and energy class are unchanged for both models.
""",

    "DOC-03-v1": """ORCHARD VALLEY FOODS - PACK LABEL ARTWORK (EXTRACTED TEXT)

Document reference: DOC-03
Revision: v1
Issued: 16 August 2026
Product: Trail Mix Bar (PRD-02)

FRONT OF PACK
  Orchard Valley Trail Mix Bar
  Oats, honey and almonds
  NET WEIGHT 40 g

BACK OF PACK
  INGREDIENTS: oats, honey, sugar, almonds, sunflower oil.
  ALLERGY ADVICE: contains almonds.
  GTIN 05098765400011 (single bar)
  GTIN 05098765400028 (6 x 40 g multipack)
""",

    "DOC-03-v2": """ORCHARD VALLEY FOODS - PACK LABEL ARTWORK (EXTRACTED TEXT)

Document reference: DOC-03
Revision: v2
Supersedes: v1 (issued 16 August 2026)
Issued: 19 September 2026
Product: Trail Mix Bar (PRD-02)

CHANGE NOTE
  The declared net weight of the single bar is corrected from 40 g to 38 g
  following the recipe density review closed this month. Artwork has been
  re-originated and the plates are cut. The multipack declaration is
  unaffected pending its own artwork cycle.

FRONT OF PACK
  Orchard Valley Trail Mix Bar
  Oats, honey and almonds
  NET WEIGHT 38 g

BACK OF PACK
  INGREDIENTS: oats, honey, sugar, almonds, sunflower oil.
  ALLERGY ADVICE: contains almonds.
""",

    "DOC-04-v1": """ORCHARD VALLEY FOODS
ALLERGEN AND INGREDIENT NOTICE

Document reference: DOC-04
Revision: v1
Issued: 16 August 2026
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

    "DOC-04-v2": """ORCHARD VALLEY FOODS
ALLERGEN AND INGREDIENT NOTICE

Document reference: DOC-04
Revision: v2
Supersedes: v1 (issued 16 August 2026)
Issued: 1 October 2026
Product: Trail Mix Bar (PRD-02), all pack formats

1. CHANGE OF MANUFACTURING LINE

From the production week commencing 5 October 2026 the Trail Mix Bar is
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

    "DOC-06-v1": """CASCADE HOUSEWARES
DIMENSIONAL DRAWING - RAPID KETTLE 1.7L

Document reference: DOC-06
Revision: v1
Issued: 18 August 2026
Product: Cascade Rapid Kettle (PRD-04)

  Capacity          1.7 L
  Rated power       3000 W
  Height            255 mm
  Base diameter     160 mm
  Sound level       70 dB(A) at full boil
  Finish            brushed stainless steel
  Energy class      A
  GTIN              05044556600019
""",

    "DOC-06-v2": """CASCADE HOUSEWARES
DIMENSIONAL DRAWING - RAPID KETTLE 1.7L

Document reference: DOC-06
Revision: v2 - PROVISIONAL, NOT FOR PUBLICATION
Issued: 11 September 2026
Product: Cascade Rapid Kettle (PRD-04)

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

    "DOC-07-v2": """BRIGHTLINE ELECTRONICS
PORTAL ATTRIBUTE FEED - CHANGE REPORT

Document reference: DOC-07
Revision: v2
Issued: 23 September 2026
Supplier: Brightline Electronics (SUP-03)

Scheduled quarterly republication of the attribute feed for all Brightline
lines, including the BT-200 Earbuds (PRD-03).

CHANGES IN THIS REVISION

  None. Every attribute value in this revision is identical to v1. The
  revision number has advanced because the feed is republished on a fixed
  quarterly cycle, not because any value has moved.
""",

    "DOC-08-v1": """VOLTAIC HOME LIMITED
DECLARATION OF CONFORMITY

Document reference: DOC-08
Revision: v1
Issued: 20 August 2026
Manufacturer: Voltaic Home Limited (SUP-01)

Products covered:
  AeroPure 300       (VAR-01A)
  AeroPure 300 Max   (VAR-01B)
  Voltaic Desk Fan V2 (VAR-06A)

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


def docs_defining(variant_id: str) -> set[str]:
    return {doc for (eid, _), (doc, _) in ATTR_SOURCE.items() if eid == variant_id}


def build_nodes() -> list[dict]:
    """Four tiers with fixed coordinates - the UI draws this as hand-rolled SVG.

    ``single_source`` falls out of the data rather than being asserted: an
    entity defined by exactly one supplier document has nothing to corroborate
    it, which is what the badge is warning about.
    """
    nodes: list[dict] = []

    def place(index: int, total: int) -> float:
        # Margins at both ends so the outermost boxes are not on the edge.
        return round((index + 1) / (total + 1), 4)

    for i, (sid, name, family) in enumerate(SUPPLIERS):
        owned = [doc[0] for doc in SOURCE_DOCS if doc[1] == sid]
        nodes.append({
            "id": sid, "kind": "SUPPLIER", "name": name, "group": family,
            "x": 0.0, "y": place(i, len(SUPPLIERS)),
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
            "x": 0.33, "y": place(i, len(PRODUCTS)),
            "regulated": regulated, "single_source": len(docs) == 1,
        })

    for i, (vid, pid, name, _) in enumerate(VARIANTS):
        product = PRODUCT_BY_ID[pid]
        nodes.append({
            "id": vid, "kind": "VARIANT", "name": name,
            "group": product[2].split(".")[0],
            "x": 0.62, "y": place(i, len(VARIANTS)),
            "regulated": product[4], "single_source": len(docs_defining(vid)) == 1,
        })

    for i, (cid, name, kind, _, _, _, _) in enumerate(CHANNELS):
        nodes.append({
            "id": cid, "kind": "CHANNEL", "name": name, "group": kind,
            "x": 1.0, "y": place(i, len(CHANNELS)),
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
        if field is None:
            continue  # not part of this marketplace's schema
        fields[field] = view[field]
        paths.append(path)
    text = json.dumps(fields, sort_keys=True, ensure_ascii=False,
                      separators=(", ", ": "))
    return text, sorted(paths)


def facet_text(variant_id: str) -> tuple[str, list[str]]:
    attrs = attrs_for(variant_id)
    tokens = [f"allergen:{a}" for a in attrs.get("food.allergens.contains") or []]
    tokens += [f"may-contain:{a}" for a in attrs.get("food.allergens.may_contain") or []]
    tokens += [f"dietary:{c}" for c in attrs.get("claims") or []]
    tokens.append(f"weight:{attrs['food.net_weight_g']}g")
    tokens.append(f"format:{COPY[variant_id]['facet_format']}")
    paths = ["food.allergens.contains", "food.allergens.may_contain",
             "food.net_weight_g", "claims"]
    return " | ".join(sorted(tokens)), paths


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

    confirmable = sorted(
        (vid, path) for (vid, path) in ATTR_VALUES
        if (vid, path) not in FROZEN_BY_ARC and applies(path, category_of(vid))
    )
    variant_ids = [v[0] for v in VARIANTS]
    listing_ids = [l["id"] for l in listings]
    listing_by_id = {l["id"]: l for l in listings}

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

    email(16, 13, 40, "Autumn newsletter - what is landing in October",
          "marketing@internal",
          "Team,\n\nThe autumn newsletter goes out on Friday. The featured lines are "
          "the AeroPure 300 range and the Trail Mix Bar multipack. Copy is already "
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
    arc1 = email(10, 8, 45, "Cascade Rapid Kettle - dimensions under review",
                 "product@sup-04.example",
                 "Dear Content Team,\n\n"
                 "Please treat the dimensional figures for the Cascade Rapid Kettle "
                 "(PRD-04) as provisional for the next few days. Our tooling supplier "
                 "has flagged a possible discrepancy on the base diameter and we have "
                 "opened a tooling audit to settle it.\n\n"
                 "We are issuing revision v2 of the drawing today so that you have the "
                 "figures under review on file, but please do not publish against it "
                 "until the audit closes. We expect to conclude within three working "
                 "days.\n\n"
                 "Kind regards,\n"
                 "Priya Raman\n"
                 "Product Data Manager, Cascade Housewares (SUP-04)",
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

    email(13, 10, 5, "RE: Cascade Rapid Kettle - dimensions confirmed unchanged",
          "product@sup-04.example",
          "Dear Content Team,\n\n"
          "The tooling audit closed this morning. The base diameter measured within "
          "tolerance and no dimension on the Rapid Kettle changes.\n\n"
          "Revision v2 of the drawing is withdrawn. Please continue to work from v1 "
          "and disregard our notice of the 11th. Nothing needs to be republished.\n\n"
          "Apologies for the interruption.\n\n"
          "Kind regards,\n"
          "Priya Raman\n"
          "Product Data Manager, Cascade Housewares (SUP-04)",
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
          "National Account Manager, Orchard Valley Foods (SUP-02)",
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
          "AeroPure 300 - corrected rated power (DOC-01 rev v2)",
          "specs@sup-01.example",
          "Dear Content Team,\n\n"
          "Attached is revision v2 of the AeroPure 300 technical specification, "
          "issued this morning.\n\n"
          "The correction is to the rated power. The AeroPure 300 draws 65 W, not "
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
          "Quality Manager, Voltaic Home (SUP-01)",
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
        "supplier": "SUP-02", "effective_from": "2026-10-05", "material_hint": True,
    }

    add(SCENARIO2_DAY, 8, 10, "SPEC_DOC", "SUPPLIER_PORTAL",
        {**arc4_payload, "kind": "SPEC_SHEET", "precedence": 30},
        DOC_BODIES["DOC-04-v2"], ref="arc4-doc04-v2")

    email(SCENARIO2_DAY, 8, 30,
          "Trail Mix Bar - revised allergen declaration (DOC-04 rev v2)",
          "quality@sup-02.example",
          "Dear Content Team,\n\n"
          "We are moving the Trail Mix Bar onto line 4 at Ashford from the week "
          "commencing 5 October. Line 4 also runs a peanut recipe. Our changeover "
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
          "Supplier Quality Manager, Orchard Valley Foods (SUP-02)",
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
          "AeroPure 300 - rev v3, the 65 W applies to the Max only",
          "specs@sup-01.example",
          "Dear Content Team,\n\n"
          "Following your question on my note of 29 September: I am sorry, revision "
          "v2 was not clear and I should have said which model it referred to.\n\n"
          "The 65 W rating is the AeroPure 300 Max. The standard AeroPure 300 draws "
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
          "Quality Manager, Voltaic Home (SUP-01)",
          finale_payload)

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


def _golden_kind(payload: dict) -> str:
    """Which class of correction the document asserts.

    The same order of precedence the extractor is given: a withdrawal outranks
    what it withdraws, a contradiction outranks the value it contradicts, and
    an allergen outranks everything it arrives with.
    """
    if payload.get("withdraws") or payload.get("resolves_issue"):
        return "DOC_WITHDRAWN"
    if payload.get("conflicts_with"):
        return "SOURCE_CONFLICT"
    paths = [str(c["attribute_path"]) for c in _moved_by(payload)]
    kinds = [("ALLERGEN_CHANGE" if p.startswith("food.allergens")
              else "INGREDIENT_CHANGE" if p == "food.ingredients"
              else "SPEC_CORRECTION") for p in paths]
    if "ALLERGEN_CHANGE" in kinds:
        return "ALLERGEN_CHANGE"
    return kinds[0] if kinds else "SPEC_CORRECTION"


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


def build_golden(events: list[dict]) -> list[dict]:
    """The answer key, one row per document the extractor is asked to read."""
    rows = []
    for event in events:
        if event["type"] not in READ_BY_EXTRACT:
            continue
        payload = event["payload"]
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

    catalog = {
        "nodes": nodes,
        "products": [{"id": p, "name": n, "category": c, "supplier": s, "regulated": r}
                     for p, n, c, s, r in PRODUCTS],
        "variants": [{"id": v, "product_id": p, "name": n, "is_base": b}
                     for v, p, n, b in VARIANTS],
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

ID_PATTERN = re.compile(
    r"\b(?:PRD-\d{2}|VAR-\d{2}[A-Z]|LST-\d{2}|AST-\d{3}|DOC-\d{2}"
    r"|RUL-[A-Z]\d{2}|SUP-\d{2}|CH-[A-Z][A-Z-]*)\b"
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
    expected = [e["id"] for e in events if e["type"] in READ_BY_EXTRACT]
    if [g["event_id"] for g in golden] != expected:
        problems.append("the answer key does not cover exactly the documents "
                        "extract reads")
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


def check_tape(events: list[dict]) -> list[str]:
    problems = []
    if not 250 <= len(events) <= 320:
        problems.append(f"tape has {len(events)} events, wanted 250-320")
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
    for directory in (DOCS, COMMS, GOLDEN):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    for name in sorted(files):
        path = DATA / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding="utf-8", newline="\n")


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
    problems += check_tape(model["events"])
    problems += check_golden(model["events"], model["golden"])
    id_problems, notes = check_ids(model, files)
    problems += id_problems

    write_pack(files)

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
