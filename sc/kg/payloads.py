"""What the four back-office systems put on the wire.

Nine payload shapes, one per reference event type. They are models rather than
loose dicts for the ordinary reason - the generator and the projection have to
agree about a field name - and they are *checked* for one much less ordinary
reason, which is the whole of this docstring.

**A reference payload travels through code that was not written for it.**

The estate predates these systems. Three modules read the ``events`` table with
no lane predicate at all, and they read payloads by looking for keys they
recognise:

* ``sc/readiness/window.py`` asks which products anything arrived for between
  two dates, and reference events sit squarely inside the horizon.
* ``sc/lifecycle/timeline.py`` joins arrivals to events to build one product's
  journey.
* ``sc/estate/topology.py`` derives the map's system-to-supplier edges.

All three go through ``sc/estate/reach.py``, which reads exactly seven
top-level keys: ``entity_id``, ``product_id``, ``variant_id``, ``product`` and
``listing_id`` as scalars, ``entities`` and ``applies_to`` as lists. And four
more modules read their own particular key: ``ingest._raw_rows`` wants ``rows``
or a top-level ``path``, ``detection._rows`` wants ``rows``, ``ingest._media_row``
wants ``media``, and ``intake._last_sent`` filters on ``supplier``.

So the rule is: **a reference payload names a variant only where nothing is
looking.** Inside ``lines[]``, inside ``members[]``, inside ``scope[]`` - all
nested or unlisted, all invisible to ``refs_of``. Never at the top level.

The consequence is the correct answer rather than a dodge. Six weekly stock
snapshots are not "six things arrived for this product", and reporting them on
the product screen as though they were would be exactly the class of false
statement ``readiness/window.py`` exists to avoid making. A product's timeline
stays the supplier-and-decision story. The four new systems draw on the estate
map as boxes with no supplier edges, which is honest: a depot does not feed a
supplier's data.

``assert_safe`` below enforces this rather than trusting it, because the failure
it prevents is silent. A payload that grew an ``entity_id`` would not raise
anywhere - it would quietly inflate a count on a screen three modules away, and
the number would look plausible.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

#: Top-level keys a reference payload may never carry, and who reads each.
#:
#: Kept as data next to the check so the reason survives: somebody adding a
#: tenth payload shape should be able to see what they would break, not just
#: that something breaks.
FORBIDDEN_TOP_LEVEL: dict[str, str] = {
    # sc/estate/reach.py - SCALAR_KEYS
    "entity_id": "reach.refs_of - would count this as a product arrival",
    "product_id": "reach.refs_of - would count this as a product arrival",
    "variant_id": "reach.refs_of - would count this as a product arrival",
    "product": "reach.refs_of - would count this as a product arrival",
    "listing_id": "reach.refs_of - would count this as a product arrival",
    # sc/estate/reach.py - LIST_KEYS
    "entities": "reach.refs_of - would put this on a product's timeline",
    "applies_to": "reach.refs_of - would put this on a product's timeline",
    # the modules that read one key of their own
    "rows": "ingest._raw_rows and detection._rows - would read it as attributes",
    "path": "ingest._raw_rows - would read the payload as a single attribute row",
    "media": "ingest._media_row - would write a media fact",
    "supplier": "intake._last_sent - would file this against a supplier",
}


class _Payload(BaseModel):
    """Frozen, and extras refused.

    ``extra="forbid"`` is doing real work here. A typo that added an unexpected
    key would otherwise be accepted and then be invisible until whichever of
    the seven readers above happened to recognise it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def assert_safe(payload: dict) -> None:
    """Raise if a payload names a product where an existing reader would see it.

    Called by the generator for every event it writes, and by the tests for
    every event in the pack. Cheap, and it is the only thing standing between a
    renamed field and a wrong number on the product screen.
    """
    for key, reader in FORBIDDEN_TOP_LEVEL.items():
        if key in payload:
            raise ValueError(
                f"reference payload carries a top-level {key!r}: {reader}")


# ---------------------------------------------------------------------------
# Warehouse - wms-inventory


class StockLine(_Payload):
    variant_id: str
    sku: str
    on_hand: int
    allocated: int
    reorder_point: int
    first_stocked: date


class StockSnapshotPayload(_Payload):
    """One depot's count for one week.

    Weekly rather than daily because nine snapshots per depot is a series a
    reader can see the shape of, and sixty-two is a wall of numbers. The week
    is part of the stock level's key downstream: nine counts of the same pallet
    are nine facts, not one fact restated.
    """

    warehouse_id: str
    warehouse_name: str
    country: str
    serves_markets: list[str]
    week_start: date
    lines: list[StockLine]


# ---------------------------------------------------------------------------
# Sales - trading-epos


class PriceLine(_Payload):
    variant_id: str
    sku: str
    list_price: float
    currency: str
    effective_from: date
    price_band: Literal["ENTRY", "MID", "PREMIUM"]


class PriceListPayload(_Payload):
    market_id: str
    market_name: str
    currency: str
    issued_on: date
    lines: list[PriceLine]


class SalesLine(_Payload):
    variant_id: str
    sku: str
    units: int
    revenue: float
    #: Rank within the variant's depth-2 category subtree, 1 being the best
    #: seller. Carried rather than derived because "the best seller in this
    #: category" is what the insight asks, and computing it from a single
    #: market's rows would give a different answer per market.
    rank_in_category: int
    category: str


class SalesPeriodPayload(_Payload):
    market_id: str
    period_start: date
    period_end: date
    currency: str
    lines: list[SalesLine]


# ---------------------------------------------------------------------------
# Marketing - campaign-manager


class CampaignPayload(_Payload):
    """A campaign, and what is in it.

    ``members`` is the only place in this file that a list of variant ids sits
    at the top level, and it is safe because ``reach.LIST_KEYS`` is
    ``("entities", "applies_to")`` and this is neither. That is a thin margin,
    which is why ``assert_safe`` checks it on every event rather than leaving
    it to whoever next renames a field.
    """

    campaign_id: str
    name: str
    market_id: str
    channels: list[str]
    starts_on: date
    ends_on: date
    audience_id: str
    keywords: list[str]
    members: list[str]
    objective: Literal["ACQUISITION", "BASKET_BUILD", "CLEARANCE", "SEASONAL"]


class PromotionPayload(_Payload):
    promotion_id: str
    campaign_id: str | None = None
    mechanic: Literal["PCT_OFF", "MULTIBUY", "BUNDLE", "PRICE_CUT"]
    depth_pct: float
    starts_on: date
    ends_on: date
    market_id: str
    members: list[str]


class AudiencePayload(_Payload):
    audience_id: str
    name: str
    description: str
    affinity_categories: list[str]
    affinity_keywords: list[str]


# ---------------------------------------------------------------------------
# Compliance - cert-registry


class CertificatePayload(_Payload):
    """One entry in the register.

    ``certificate_ref`` is the retailer's own value, read straight off
    ``compliance.certificate_ref`` in the catalog - seventy-four variants carry
    one and two of them share ``UKCA-2411``. That reuse is the point: it is
    what makes "everything sharing a certificate that lapses in ninety days" a
    question about the real catalog rather than about invented data sitting
    beside it.

    The scheme is parsed out of the reference's prefix rather than drawn,
    because the catalog already encoded it there.
    """

    certificate_ref: str
    scheme: Literal["UKCA", "CE", "EN71-3", "BS-EN"]
    issuer: str
    issued_on: date
    expires_on: date
    status: Literal["VALID", "EXPIRED", "WITHDRAWN"]
    satisfies: list[str]
    #: The variants citing this reference. Named ``scope`` and not
    #: ``applies_to`` deliberately - see the module docstring.
    scope: list[str]


class RegulationPayload(_Payload):
    regulation_id: str
    title: str
    authority: str
    applies_to_categories: list[str]
    accepted_schemes: list[str]


class MarketRulePayload(_Payload):
    market_id: str
    market_name: str
    country: str
    requires_regulations: list[str]
    restricted_categories: list[str]
    min_age_enforced: bool
