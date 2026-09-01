"""The reference world: depots, markets, rules, audiences and campaign themes.

Declared here as frozen data, the way ``sc/estate/manifest.py`` declares the
estate, and for the same reason: these are things a retailer *has*, not things
a program computes, and scattering them through the generator would make
"which markets does Rotterdam serve" a question you answer by reading code.

Everything in this file is invented. The catalog has products, variants,
suppliers, categories, attributes, media, channels and listings; it has no
depot, no market, no price and no campaign. So these are written down once,
argued for once, and every node built from them is stamped ``synthetic``.

**The one place invention meets real data** is the certificate scheme. The
catalog already carries ``compliance.certificate_ref`` on seventy-four variants
with the scheme encoded in the prefix - ``UKCA-2411``, ``EN71-3-2676``,
``BS-EN-2781``, ``DOC-CE-1180``. ``SCHEME_OF_PREFIX`` reads that rather than
drawing one, which is what makes the compliance domain sit on the retailer's
own data instead of beside it.

**Why the geography is arranged the way it is.** A market that requires a
conformity regime, and a depot that serves that market while holding stock
certified under a different one, is a genuine and unglamorous failure: nobody
did anything wrong, no single system can see it, and it stops a shipment. The
arrangement below produces exactly that at Rotterdam, and produces it because
of what the depots and markets *are* rather than because a flag was set.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Warehouse:
    code: str
    name: str
    country: str
    region: str
    #: Which markets this depot ships to. The join that makes a compliance
    #: question answerable from a stock question.
    serves: tuple[str, ...]
    temperature_controlled: bool = False
    hazmat_licensed: bool = False


@dataclass(frozen=True)
class Market:
    code: str
    name: str
    country: str
    currency: str
    #: Regulations a product must satisfy to be sold here. Empty means this
    #: market enforces nothing *in this model* - not that it enforces nothing.
    requires: tuple[str, ...] = ()
    #: Category prefixes that may not be sold here at all, whatever the paper.
    restricted: tuple[str, ...] = ()
    min_age_enforced: bool = False


@dataclass(frozen=True)
class Regulation:
    code: str
    title: str
    authority: str
    #: Taxonomy prefixes this regulation reaches. A rule that applied to
    #: everything would make every uncertified product a finding, which is a
    #: report nobody reads rather than a finding anybody acts on.
    applies_to: tuple[str, ...]
    #: The certificate schemes that satisfy it. This is the whole of the
    #: compliance logic: a variant is covered when one of its certificates is
    #: of a scheme named here.
    accepted_schemes: tuple[str, ...]


@dataclass(frozen=True)
class Persona:
    code: str
    name: str
    description: str
    affinity_categories: tuple[str, ...]
    affinity_keywords: tuple[str, ...]


@dataclass(frozen=True)
class CampaignTheme:
    slug: str
    name: str
    objective: str
    #: Branches this theme draws members from. A theme naming more than one is
    #: an "occasion basket", and those are what make two products from
    #: different branches share a campaign - which is the entire basis of the
    #: cross-sell question.
    branches: tuple[str, ...]
    keywords: tuple[str, ...]


# ---------------------------------------------------------------------------
# Certificate schemes
#
# Read off the reference prefix, never drawn. The catalog encoded the scheme
# in the value and this is where that encoding is decoded, once.

SCHEME_OF_PREFIX: dict[str, str] = {
    "UKCA": "UKCA",
    "EN71-3": "EN71-3",
    "BS-EN": "BS-EN",
    "DOC-CE": "CE",
}

ISSUER_OF_SCHEME: dict[str, str] = {
    "UKCA": "Approved Body 0086",
    "CE": "Notified Body 1282",
    "EN71-3": "CEN/TC 52 assessment centre",
    "BS-EN": "BSI Assurance UK Ltd",
}


def scheme_of(reference: str) -> str | None:
    """The scheme a certificate reference belongs to, or None if unrecognised.

    Longest prefix first, because ``BS-EN`` and ``EN71-3`` both contain ``EN``
    and a shortest-match would file half the register under the wrong body.
    """
    for prefix in sorted(SCHEME_OF_PREFIX, key=len, reverse=True):
        if reference.startswith(prefix):
            return SCHEME_OF_PREFIX[prefix]
    return None


# ---------------------------------------------------------------------------
# Regulations

REGULATIONS: tuple[Regulation, ...] = (
    Regulation(
        code="REG-UKCA-2016",
        title="UK Conformity Assessed marking",
        authority="Office for Product Safety and Standards",
        applies_to=("electronics", "home", "hpc"),
        accepted_schemes=("UKCA",),
    ),
    Regulation(
        code="REG-CE-768-2008",
        title="CE marking under Decision 768/2008/EC",
        authority="European Commission",
        applies_to=("electronics", "home", "hpc"),
        # Note what is *not* here. UKCA does not satisfy CE, which is the
        # entire point of the pair and the reason a depot serving the EU can
        # hold stock it cannot ship.
        accepted_schemes=("CE",),
    ),
    Regulation(
        code="REG-EN71-2011",
        title="Toy safety: migration of certain elements",
        authority="CEN Technical Committee 52",
        applies_to=("baby",),
        accepted_schemes=("EN71-3", "CE"),
    ),
    Regulation(
        code="REG-BSEN-HARM",
        title="Harmonised British Standards for general merchandise",
        authority="British Standards Institution",
        applies_to=("general", "apparel"),
        accepted_schemes=("BS-EN",),
    ),
)


# ---------------------------------------------------------------------------
# Markets
#
# Only two markets require anything, and that restraint is deliberate. A model
# where every market enforces a regime would make almost every product a
# finding; the insight is worth reading precisely because the violation is
# narrow enough to be actionable.

MARKETS: tuple[Market, ...] = (
    Market(code="MK-GB", name="United Kingdom", country="GB", currency="GBP",
           requires=("REG-UKCA-2016",), min_age_enforced=True),
    Market(code="MK-IE", name="Ireland", country="IE", currency="EUR"),
    Market(code="MK-DE", name="Germany", country="DE", currency="EUR",
           requires=("REG-CE-768-2008",), min_age_enforced=True),
    Market(code="MK-FR", name="France", country="FR", currency="EUR",
           requires=("REG-CE-768-2008",)),
    Market(code="MK-US", name="United States", country="US", currency="USD",
           restricted=("health",)),
    Market(code="MK-AE", name="United Arab Emirates", country="AE",
           currency="AED", restricted=("health",), min_age_enforced=True),
)


# ---------------------------------------------------------------------------
# Warehouses
#
# WH-ROTTERDAM is the one that matters. It serves Germany and France, both of
# which require CE, and the generator deliberately stocks UKCA-certified lines
# there - which is how "stocked where it cannot lawfully ship" has something
# real to find. The other five are ordinary.

WAREHOUSES: tuple[Warehouse, ...] = (
    Warehouse(code="WH-LEEDS", name="Leeds RDC", country="GB",
              region="North England", serves=("MK-GB",)),
    Warehouse(code="WH-DAVENTRY", name="Daventry NDC", country="GB",
              region="Midlands", serves=("MK-GB",), temperature_controlled=True),
    Warehouse(code="WH-ROTTERDAM", name="Rotterdam EDC", country="NL",
              region="Benelux", serves=("MK-DE", "MK-FR", "MK-IE"),
              hazmat_licensed=True),
    Warehouse(code="WH-DUBLIN", name="Dublin DC", country="IE",
              region="Ireland", serves=("MK-IE",)),
    Warehouse(code="WH-NEWARK", name="Newark FC", country="US",
              region="US East", serves=("MK-US",)),
    Warehouse(code="WH-JEBELALI", name="Jebel Ali DC", country="AE",
              region="Gulf", serves=("MK-AE",), temperature_controlled=True),
)

#: Two storage locations per depot. Enough for the graph to have somewhere to
#: put the relationship; not so many that the picture becomes a floor plan.
LOCATION_KINDS: tuple[tuple[str, str], ...] = (
    ("BULK", "Bulk racking"),
    ("PICK", "Pick face"),
)


# ---------------------------------------------------------------------------
# Personas

PERSONAS: tuple[Persona, ...] = (
    Persona("PER-VALUE", "Value Seeker",
            "Shops the price, buys the own-label, reads the unit price.",
            ("food", "hpc", "general"), ("value", "multipack", "offer")),
    Persona("PER-FAMILY", "Family Shopper",
            "Weekly big shop, children in the house, buys for the household.",
            ("food", "baby", "home"), ("family", "school", "lunchbox")),
    Persona("PER-ECO", "Eco-conscious",
            "Reads the packaging claim and checks whether it is substantiated.",
            ("hpc", "home", "apparel"), ("recyclable", "refill", "organic")),
    Persona("PER-PREMIUM", "Premium Buyer",
            "Buys the top of the range and expects the photography to match.",
            ("electronics", "home"), ("premium", "professional")),
    Persona("PER-CONVENIENCE", "Convenience Led",
            "Small basket, high frequency, decides in front of the shelf.",
            ("food", "hpc"), ("quick", "single", "ready")),
    Persona("PER-HEALTH", "Health Focused",
            "Reads the ingredient panel before the front of pack.",
            ("health", "food"), ("free from", "low sugar", "supplement")),
)


# ---------------------------------------------------------------------------
# Campaign themes
#
# Ten themes for twenty-four campaigns. Four draw members from more than one
# branch - the occasion baskets - and they are the reason two products from
# different categories ever end up in the same campaign, which is the whole
# basis of the cross-sell question. A model where every campaign sat inside one
# branch would answer that question with an empty table, and the table would
# look like a correct answer.

CAMPAIGN_THEMES: tuple[CampaignTheme, ...] = (
    CampaignTheme("back-to-school", "Back to School Basket", "BASKET_BUILD",
                  ("food", "general", "apparel"),
                  ("school", "lunchbox", "uniform")),
    CampaignTheme("summer-home", "Summer at Home", "BASKET_BUILD",
                  ("home", "food", "general"),
                  ("garden", "outdoor", "entertaining")),
    CampaignTheme("new-baby", "Everything for a New Arrival", "BASKET_BUILD",
                  ("baby", "hpc", "home"),
                  ("newborn", "nursery", "gentle")),
    CampaignTheme("healthy-start", "Healthy Start", "BASKET_BUILD",
                  ("health", "food", "hpc"),
                  ("wellbeing", "free from", "supplement")),
    CampaignTheme("price-lock", "Price Lock", "ACQUISITION",
                  ("food",), ("value", "price lock", "everyday")),
    CampaignTheme("tech-upgrade", "Time to Upgrade", "ACQUISITION",
                  ("electronics",), ("upgrade", "latest", "trade in")),
    CampaignTheme("wardrobe-refresh", "Wardrobe Refresh", "SEASONAL",
                  ("apparel",), ("season", "new in", "layering")),
    CampaignTheme("spring-clean", "The Big Clean", "SEASONAL",
                  ("hpc",), ("cleaning", "fresh", "bulk")),
    CampaignTheme("end-of-line", "Last Chance", "CLEARANCE",
                  ("general", "home"), ("clearance", "last chance")),
    CampaignTheme("stock-up", "Stock Up and Save", "CLEARANCE",
                  ("food", "hpc"), ("multibuy", "bulk", "save")),
)

#: The themes whose members deliberately cross branches. Named rather than
#: derived so the intent survives somebody editing the tuple above.
BASKET_THEMES: frozenset[str] = frozenset({
    "back-to-school", "summer-home", "new-baby", "healthy-start",
})

PROMOTION_MECHANICS: tuple[str, ...] = (
    "PCT_OFF", "MULTIBUY", "BUNDLE", "PRICE_CUT",
)

#: Price bands per branch, in the retailer's own currency. Wide enough that a
#: histogram has a shape; narrow enough that a food line never costs more than
#: a television.
PRICE_BANDS: dict[str, tuple[float, float]] = {
    "food": (0.75, 9.0),
    "hpc": (1.20, 14.0),
    "health": (2.50, 28.0),
    "baby": (3.00, 45.0),
    "general": (2.00, 40.0),
    "apparel": (8.00, 120.0),
    "home": (6.00, 180.0),
    "electronics": (20.00, 420.0),
}

#: Roughly how many units a branch moves in a month, before per-variant and
#: per-market weighting. Food moves; electronics does not.
BRANCH_VELOCITY: dict[str, int] = {
    "food": 2400, "hpc": 1400, "health": 600, "baby": 400,
    "general": 500, "apparel": 300, "home": 220, "electronics": 90,
}

BY_MARKET: dict[str, Market] = {m.code: m for m in MARKETS}
BY_WAREHOUSE: dict[str, Warehouse] = {w.code: w for w in WAREHOUSES}
BY_REGULATION: dict[str, Regulation] = {r.code: r for r in REGULATIONS}


def regulations_for(category: str, market_code: str) -> tuple[Regulation, ...]:
    """Which regulations bite for this category in this market.

    Both halves are needed. A market requires a set of regimes; a regulation
    reaches a set of categories. A product is only in scope where the two
    overlap - which is what keeps "cannot lawfully ship" a narrow finding
    instead of a restatement of the whole catalog.
    """
    market = BY_MARKET.get(market_code)
    if market is None:
        return ()
    branch = category.split(".", 1)[0]
    return tuple(
        BY_REGULATION[code] for code in market.requires
        if code in BY_REGULATION
        and any(branch == prefix for prefix in BY_REGULATION[code].applies_to))
