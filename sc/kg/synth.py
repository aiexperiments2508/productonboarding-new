"""Generating the back-office reference pack.

Four systems' worth of events, derived from the seed and from the retailer's
own catalog. Same seed, same bytes, on any machine and any Python - the rule
``sc/estate/emitter.py`` states and the reason ``sc/rng.py`` exists. Nothing
here calls ``random`` and nothing reads a clock.

**Derived, not drawn, wherever the catalog already knows.** A certificate's
scheme is parsed out of the reference the catalog already carries; a price band
follows the branch; sales velocity follows the branch and the number of
listings a variant actually has, because a variant on five channels genuinely
moves more than one on a single channel. Free invention is confined to the
things that have no counterpart at all - which depot, which month, which
campaign.

**Why some conditions are planted.** Uniformly random data answers every
interesting question with an empty table, and an empty table reads as a correct
answer rather than as a missing one. ``scripts/generate_data.py`` solved this
the same way and says so: the catalog is shaped around its inject rather than
being uniformly random. So four conditions below are placed deliberately, each
one named in ``PLANTED``, and each has a test asserting it is still there. The
other two insights need no help - fifty-three variants are genuinely missing a
role their branch requires, and several categories genuinely depend on one
supplier.

The planting never invents the *evidence*, only the *arrangement*. The variants
that turn up as "stocked where it cannot lawfully ship" hold real UKCA
references from the real catalog; what is arranged is that a depot serving
Germany is the one holding them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sc import rng as rng_mod
from sc.kg import domains as dom
from sc.kg import payloads as pay

#: Matches ``emitter.seed()`` and ``generate_data.SEED``. One seed for the
#: whole pack, split into named streams per domain and per entity.
DEFAULT_SEED = 20802

#: Which coarse origin each event type carries. ``Event.source`` is the system
#: as the tape knows it; the carrying system comes from the manifest.
SOURCE_OF: dict[str, str] = {
    "STOCK_SNAPSHOT": "WMS",
    "PRICE_LIST": "EPOS",
    "SALES_PERIOD": "EPOS",
    "CAMPAIGN": "CAMPAIGN_MANAGER",
    "PROMOTION": "CAMPAIGN_MANAGER",
    "AUDIENCE": "CAMPAIGN_MANAGER",
    "CERTIFICATE": "CERT_REGISTRY",
    "REGULATION": "CERT_REGISTRY",
    "MARKET_RULE": "CERT_REGISTRY",
}

#: Each planted condition, the insight it feeds, and how many rows it
#: guarantees. Read by ``tests/test_kg_data.py``, which asserts each is still
#: present - a plant that quietly stops planting is a demo that quietly stops
#: demonstrating.
PLANTED: dict[str, str] = {
    "certificates-expiring": "12 certificates lapse within 90 days of the "
                             "horizon start, and 8 have already lapsed",
    "bestsellers-without-media": "6 variants that genuinely lack a required "
                                 "media role are ranked first in their subtree",
    "stock-it-cannot-ship": "every UKCA-certified variant in CE scope is "
                            "stocked at the depot that serves Germany",
    "cross-sell-pairs": "6 variant pairs from different products share at "
                        "least two occasion-basket campaigns",
}

#: How many certificates fall in each expiry bucket. See ``_expiry`` for why
#: the windows are anchored to the horizon rather than to today.
EXPIRING_SOON = 12
ALREADY_EXPIRED = 8

#: How many real media-gap carriers get pushed to the top of their subtree.
BESTSELLERS_WITHOUT_MEDIA = 6

#: How many cross-branch pairs are placed in two basket campaigns each.
CROSS_SELL_PAIRS = 6

CAMPAIGN_COUNT = 24
PROMOTION_COUNT = 30


# ---------------------------------------------------------------------------
# Reading the catalog


@dataclass(frozen=True)
class _Pack:
    """What the generator needs out of the seed pack, indexed once."""

    variants: dict[str, dict]
    products: dict[str, dict]
    branch_of: dict[str, str]
    subtree_of: dict[str, str]
    listings_of: dict[str, int]
    held_roles: dict[str, set[str]]
    required_roles: dict[str, set[str]]
    cert_ref: dict[str, str]
    channels: list[str]
    horizon_start: date
    horizon_days: int


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))


def _load(data_dir: Path | None = None) -> _Pack:
    """Index the seed pack.

    Reads ``catalog.json`` and ``attributes.jsonl`` directly rather than going
    through ``sc.state.baseline``. The baseline merges ``catalog.live.json`` -
    lines a reviewer accepted at runtime - and a reference pack whose bytes
    depended on what somebody clicked during the last demo would not be
    reproducible, which is the one property this file exists to have.
    """
    root = data_dir or _data_dir()
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))

    products = {p["id"]: p for p in catalog["products"]}
    variants = {v["id"]: v for v in catalog["variants"]}

    branch_of, subtree_of = {}, {}
    for vid, variant in variants.items():
        product = products.get(variant["product_id"])
        if product is None:
            continue
        parts = product["category"].split(".")
        branch_of[vid] = parts[0]
        subtree_of[vid] = ".".join(parts[:2])

    listings_of: dict[str, int] = {}
    for listing in catalog["listings"]:
        listings_of[listing["variant_id"]] = \
            listings_of.get(listing["variant_id"], 0) + 1

    held_roles: dict[str, set[str]] = {}
    for asset in catalog["media"]:
        held_roles.setdefault(asset["entity_id"], set()).add(asset["role"])

    required_roles = {
        branch: set(spec.get("required_media", []))
        for branch, spec in catalog["profile"]["branches"].items()}

    cert_ref: dict[str, str] = {}
    attributes = root / "attributes.jsonl"
    if attributes.exists():
        with attributes.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("path") == "compliance.certificate_ref":
                    cert_ref[row["entity_id"]] = str(row["value"])

    return _Pack(
        variants=variants, products=products, branch_of=branch_of,
        subtree_of=subtree_of, listings_of=listings_of,
        held_roles=held_roles, required_roles=required_roles,
        cert_ref=cert_ref,
        channels=[c["id"] for c in catalog["channels"]],
        horizon_start=date.fromisoformat(catalog["horizon_start"]),
        horizon_days=int(catalog["horizon_days"]))


# ---------------------------------------------------------------------------
# The calendar


def _weeks(pack: _Pack) -> list[date]:
    """Nine Monday week-starts covering the horizon.

    Weekly rather than daily: nine counts per depot is a series whose shape a
    reader can see, and sixty-two is a wall of numbers with the same
    information in it.
    """
    first = pack.horizon_start - timedelta(days=pack.horizon_start.weekday())
    end = pack.horizon_start + timedelta(days=pack.horizon_days)
    weeks, cursor = [], first
    while cursor < end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks


def _months(pack: _Pack) -> list[tuple[date, date]]:
    """Whole calendar months that start inside the horizon."""
    end = pack.horizon_start + timedelta(days=pack.horizon_days)
    out, year, month = [], pack.horizon_start.year, pack.horizon_start.month
    while date(year, month, 1) < end:
        start = date(year, month, 1)
        nxt = date(year + (month == 12), (month % 12) + 1, 1)
        if start >= pack.horizon_start:
            out.append((start, nxt - timedelta(days=1)))
        year, month = nxt.year, nxt.month
    return out


def _gaps(pack: _Pack) -> list[str]:
    """Variants missing a media role their branch requires.

    Real, and computed the same way ``sc/readiness/checks.py`` computes it -
    branch requirement against held assets. The bestseller plant picks from
    this list rather than inventing a gap, so the finding it produces is one
    the record view would also report.
    """
    out = []
    for vid in sorted(pack.variants):
        branch = pack.branch_of.get(vid)
        if branch is None:
            continue
        if pack.required_roles.get(branch, set()) - pack.held_roles.get(vid, set()):
            out.append(vid)
    return out


# ---------------------------------------------------------------------------
# Placement


def _depots_for(pack: _Pack, seed: int) -> dict[str, list[str]]:
    """Which depots hold which variants.

    Two to three depots each, drawn per variant so adding a variant does not
    reshuffle the others. Then the plant: every UKCA-certified variant that
    falls in CE scope is also placed at the depot serving Germany and France.

    That placement is the whole of "stocked where it cannot lawfully ship". It
    invents no evidence - the UKCA references are the catalog's own - it only
    arranges for the stock to sit where the mismatch bites, which is precisely
    the situation the insight exists to surface and which no single system in
    this estate can see.
    """
    codes = [w.code for w in dom.WAREHOUSES]
    placement: dict[str, list[str]] = {code: [] for code in codes}

    for vid in sorted(pack.variants):
        draw = rng_mod.stream(seed, "kg", "depot", vid)
        held = set()
        for _ in range(draw.randint(2, 3)):
            held.add(draw.pick(codes))
        for code in sorted(held):
            placement[code].append(vid)

    for vid in ce_scope_ukca(pack):
        if vid not in placement["WH-ROTTERDAM"]:
            placement["WH-ROTTERDAM"].append(vid)

    return {code: sorted(vids) for code, vids in placement.items()}


def ce_scope_ukca(pack: _Pack) -> list[str]:
    """UKCA-certified variants whose category is in scope of the CE regime.

    Public because the test that pins the plant asks the same question, and a
    test that recomputed it would be testing its own copy of the rule.
    """
    out = []
    for vid in sorted(pack.cert_ref):
        if dom.scheme_of(pack.cert_ref[vid]) != "UKCA":
            continue
        branch = pack.branch_of.get(vid, "")
        if any(branch == prefix
               for prefix in dom.BY_REGULATION["REG-CE-768-2008"].applies_to):
            out.append(vid)
    return out


def _markets_for(pack: _Pack, seed: int) -> dict[str, list[str]]:
    """Which markets sell which variants. Home market always; two to three more."""
    placement: dict[str, list[str]] = {m.code: [] for m in dom.MARKETS}
    others = [m.code for m in dom.MARKETS if m.code != "MK-GB"]

    for vid in sorted(pack.variants):
        draw = rng_mod.stream(seed, "kg", "market", vid)
        sold = {"MK-GB"}
        for _ in range(draw.randint(1, 3)):
            sold.add(draw.pick(others))
        # A market that restricts the branch does not sell it at all - which is
        # what makes RESTRICTED_IN an edge rather than a property.
        branch = pack.branch_of.get(vid, "")
        sold = {code for code in sold
                if not any(branch == p for p in dom.BY_MARKET[code].restricted)}
        for code in sorted(sold):
            placement[code].append(vid)

    return {code: sorted(vids) for code, vids in placement.items()}


def _expiry(pack: _Pack, reference: str, bucket: str) -> tuple[date, date, str]:
    """When a certificate was issued and when it lapses.

    The windows are anchored to the **horizon**, never to today. Every as-of
    read in this system runs on the replay clock, and a ninety-day window
    measured against real time would work by coincidence on the day it was
    written and stop working silently afterwards.

    The soon bucket sits between the horizon's end and ninety days after its
    start, which is a narrow window on purpose: it means those certificates are
    unexpired at every point in the replay *and* inside the ninety-day question
    at every point in the replay. The far bucket starts past that window, so
    the count at the horizon start is exactly ``EXPIRING_SOON``.
    """
    draw = rng_mod.stream(pack.horizon_days, "kg", "cert", reference)
    start = pack.horizon_start
    if bucket == "soon":
        expires = start + timedelta(days=draw.randint(63, 89))
    elif bucket == "expired":
        expires = start - timedelta(days=draw.randint(20, 300))
    else:
        expires = start + timedelta(days=draw.randint(100, 900))
    issued = expires - timedelta(days=draw.randint(365, 1460))
    status = "EXPIRED" if expires < start else "VALID"
    return issued, expires, status


# ---------------------------------------------------------------------------
# Building the events


def _event(index: int, event_type: str, when: datetime, payload: dict) -> dict:
    """One event, with the payload checked before it is written.

    ``assert_safe`` runs here rather than in a test so a bad shape cannot reach
    a file at all. The failure it guards is silent: a payload that grew a
    top-level ``entity_id`` would be accepted everywhere and then quietly
    inflate an arrival count on the product screen.
    """
    pay.assert_safe(payload)
    from sc.replay.tape import REF_BASE

    return {
        "id": f"EVT-R{index:06d}",
        "seq": REF_BASE + index,
        "ts": when.isoformat(),
        "type": event_type,
        "source": SOURCE_OF[event_type],
        "payload": payload,
    }


def build(seed: int | None = None, data_dir: Path | None = None) -> list[dict]:
    """The whole reference pack, in sequence order.

    Ordered by type rather than interleaved by time. The tape's ordering is
    part of its meaning - it is a recording of a race - and this is not: it is
    a set of registers delivered once. Grouping them keeps the sequence stable
    when one domain grows, so adding a warehouse does not renumber every
    certificate.
    """
    seed = DEFAULT_SEED if seed is None else seed
    pack = _load(data_dir)
    events: list[dict] = []
    start = datetime.combine(pack.horizon_start, datetime.min.time())

    def emit(event_type: str, when: datetime, payload: dict) -> None:
        events.append(_event(len(events), event_type, when, payload))

    # --- markets and the rules they enforce --------------------------------
    for offset, market in enumerate(dom.MARKETS):
        emit("MARKET_RULE", start + timedelta(hours=offset),
             pay.MarketRulePayload(
                 market_id=market.code, market_name=market.name,
                 country=market.country,
                 requires_regulations=list(market.requires),
                 restricted_categories=list(market.restricted),
                 min_age_enforced=market.min_age_enforced,
             ).model_dump(mode="json"))

    for offset, regulation in enumerate(dom.REGULATIONS):
        emit("REGULATION", start + timedelta(hours=6 + offset),
             pay.RegulationPayload(
                 regulation_id=regulation.code, title=regulation.title,
                 authority=regulation.authority,
                 applies_to_categories=list(regulation.applies_to),
                 accepted_schemes=list(regulation.accepted_schemes),
             ).model_dump(mode="json"))

    # --- the certificate register ------------------------------------------
    # Grouped by reference, because two variants share UKCA-2411 in the real
    # catalog and one certificate covering two products is exactly what the
    # "shared certification" question needs to find.
    scope_of: dict[str, list[str]] = {}
    for vid in sorted(pack.cert_ref):
        scope_of.setdefault(pack.cert_ref[vid], []).append(vid)

    references = sorted(scope_of)
    # Certificates covering more than one variant go into the lapsing cohort
    # first. The insight is "products *sharing* a certification that expires
    # soon", and a cohort of twelve single-product certificates would answer it
    # truthfully and demonstrate nothing - the shared ones are the whole reason
    # the question is asked of a graph rather than of a spreadsheet.
    by_reach = sorted(references, key=lambda r: (-len(scope_of[r]), r))
    buckets = {}
    for position, reference in enumerate(by_reach):
        if position < EXPIRING_SOON:
            buckets[reference] = "soon"
        elif position < EXPIRING_SOON + ALREADY_EXPIRED:
            buckets[reference] = "expired"
        else:
            buckets[reference] = "far"

    for offset, reference in enumerate(references):
        scheme = dom.scheme_of(reference)
        if scheme is None:
            continue
        issued, expires, status = _expiry(pack, reference, buckets[reference])
        satisfies = [r.code for r in dom.REGULATIONS
                     if scheme in r.accepted_schemes]
        emit("CERTIFICATE", start + timedelta(hours=12, minutes=offset),
             pay.CertificatePayload(
                 certificate_ref=reference, scheme=scheme,
                 issuer=dom.ISSUER_OF_SCHEME[scheme],
                 issued_on=issued, expires_on=expires, status=status,
                 satisfies=satisfies, scope=sorted(scope_of[reference]),
             ).model_dump(mode="json"))

    # --- audiences ----------------------------------------------------------
    for offset, persona in enumerate(dom.PERSONAS):
        emit("AUDIENCE", start + timedelta(days=1, hours=offset),
             pay.AudiencePayload(
                 audience_id=persona.code, name=persona.name,
                 description=persona.description,
                 affinity_categories=list(persona.affinity_categories),
                 affinity_keywords=list(persona.affinity_keywords),
             ).model_dump(mode="json"))

    # --- campaigns ----------------------------------------------------------
    by_branch: dict[str, list[str]] = {}
    for vid in sorted(pack.variants):
        by_branch.setdefault(pack.branch_of.get(vid, "general"), []).append(vid)

    pairs = _cross_sell_pairs(pack, seed)
    basket_slots = [i for i in range(CAMPAIGN_COUNT)
                    if dom.CAMPAIGN_THEMES[i % len(dom.CAMPAIGN_THEMES)].slug
                    in dom.BASKET_THEMES]

    campaigns: list[dict] = []
    for index in range(CAMPAIGN_COUNT):
        theme = dom.CAMPAIGN_THEMES[index % len(dom.CAMPAIGN_THEMES)]
        draw = rng_mod.stream(seed, "kg", "campaign", index)
        starts = pack.horizon_start + timedelta(days=draw.randint(0, 40))
        ends = starts + timedelta(days=draw.randint(7, 21))

        members: set[str] = set()
        for branch in theme.branches:
            pool = by_branch.get(branch, [])
            for _ in range(draw.randint(2, 5)):
                if pool:
                    members.add(draw.pick(pool))

        # The plant: each pair goes into two basket campaigns, so a pair shares
        # more than one and the cross-sell question has something to join on.
        for pair_index, pair in enumerate(pairs):
            slots = _slots_for_pair(basket_slots, pair_index)
            if index in slots:
                members.update(pair)

        campaign = pay.CampaignPayload(
            campaign_id=f"CMP-{index + 1:03d}",
            name=f"{theme.name} {starts.strftime('%b')}",
            market_id=draw.pick([m.code for m in dom.MARKETS]),
            channels=sorted({draw.pick(pack.channels)
                             for _ in range(draw.randint(1, 3))}),
            starts_on=starts, ends_on=ends,
            audience_id=draw.pick([p.code for p in dom.PERSONAS]),
            keywords=list(theme.keywords),
            members=sorted(members),
            objective=theme.objective,
        )
        campaigns.append(campaign.model_dump(mode="json"))
        emit("CAMPAIGN",
             datetime.combine(starts, datetime.min.time()) + timedelta(hours=9),
             campaigns[-1])

    # --- promotions ---------------------------------------------------------
    for index in range(PROMOTION_COUNT):
        draw = rng_mod.stream(seed, "kg", "promotion", index)
        parent = campaigns[draw.randint(0, len(campaigns) - 1)]
        starts = date.fromisoformat(parent["starts_on"])
        ends = date.fromisoformat(parent["ends_on"])
        members = parent["members"][:draw.randint(1, 4)] or parent["members"]
        emit("PROMOTION",
             datetime.combine(starts, datetime.min.time()) + timedelta(hours=10),
             pay.PromotionPayload(
                 promotion_id=f"PRM-{index + 1:03d}",
                 campaign_id=parent["campaign_id"],
                 mechanic=draw.pick(list(dom.PROMOTION_MECHANICS)),
                 depth_pct=round(draw.uniform(5.0, 40.0), 1),
                 starts_on=starts, ends_on=ends,
                 market_id=parent["market_id"], members=members,
             ).model_dump(mode="json"))

    # --- prices -------------------------------------------------------------
    markets = _markets_for(pack, seed)
    prices: dict[str, float] = {}
    for vid in sorted(pack.variants):
        branch = pack.branch_of.get(vid, "general")
        low, high = dom.PRICE_BANDS.get(branch, (2.0, 40.0))
        draw = rng_mod.stream(seed, "kg", "price", vid)
        prices[vid] = round(draw.uniform(low, high), 2)

    for offset, market in enumerate(dom.MARKETS):
        lines = []
        for vid in markets[market.code]:
            branch = pack.branch_of.get(vid, "general")
            low, high = dom.PRICE_BANDS.get(branch, (2.0, 40.0))
            price = prices[vid]
            position = (price - low) / (high - low) if high > low else 0.5
            lines.append(pay.PriceLine(
                variant_id=vid, sku=pack.variants[vid].get("sku", ""),
                list_price=price, currency=market.currency,
                effective_from=pack.horizon_start,
                price_band=("ENTRY" if position < 0.33
                            else "MID" if position < 0.72 else "PREMIUM"),
            ))
        emit("PRICE_LIST", start + timedelta(days=2, hours=offset),
             pay.PriceListPayload(
                 market_id=market.code, market_name=market.name,
                 currency=market.currency, issued_on=pack.horizon_start,
                 lines=lines,
             ).model_dump(mode="json"))

    # --- stock --------------------------------------------------------------
    depots = _depots_for(pack, seed)
    for week_index, week_start in enumerate(_weeks(pack)):
        for offset, warehouse in enumerate(dom.WAREHOUSES):
            lines = []
            for vid in depots[warehouse.code]:
                draw = rng_mod.stream(seed, "kg", "stock", warehouse.code,
                                      vid, week_index)
                branch = pack.branch_of.get(vid, "general")
                weekly = max(dom.BRANCH_VELOCITY.get(branch, 300) // 4, 8)
                on_hand = draw.randint(0, weekly * 3)
                lines.append(pay.StockLine(
                    variant_id=vid, sku=pack.variants[vid].get("sku", ""),
                    on_hand=on_hand,
                    allocated=int(on_hand * draw.uniform(0.05, 0.35)),
                    # A quarter of a month's movement. Derived, so "below the
                    # reorder point" is a condition about velocity rather than
                    # a coin toss.
                    reorder_point=max(int(weekly * 0.28), 4),
                    first_stocked=pack.horizon_start,
                ))
            emit("STOCK_SNAPSHOT",
                 datetime.combine(week_start, datetime.min.time())
                 + timedelta(hours=6 + offset),
                 pay.StockSnapshotPayload(
                     warehouse_id=warehouse.code,
                     warehouse_name=warehouse.name,
                     country=warehouse.country,
                     serves_markets=list(warehouse.serves),
                     week_start=week_start, lines=lines,
                 ).model_dump(mode="json"))

    # --- sales --------------------------------------------------------------
    boosted = _bestsellers_without_media(pack, seed)
    for month_index, (period_start, period_end) in enumerate(_months(pack)):
        for offset, market in enumerate(dom.MARKETS):
            units_of: dict[str, int] = {}
            for vid in markets[market.code]:
                draw = rng_mod.stream(seed, "kg", "sales", market.code,
                                      vid, month_index)
                branch = pack.branch_of.get(vid, "general")
                base = dom.BRANCH_VELOCITY.get(branch, 300)
                # A variant on five channels genuinely moves more than one on
                # a single channel, so reach scales the draw rather than the
                # draw standing alone.
                reach = 0.6 + 0.18 * pack.listings_of.get(vid, 1)
                units_of[vid] = max(int(base * reach * draw.uniform(0.2, 1.4)), 1)

            # The plant: six variants that really are missing a required media
            # role are pushed to the top of their own subtree, so "best sellers
            # with no primary image" has something true to report. The gap is
            # real; only the ranking is arranged.
            for vid in boosted:
                if vid in units_of:
                    subtree = pack.subtree_of.get(vid)
                    peers = [u for other, u in units_of.items()
                             if pack.subtree_of.get(other) == subtree]
                    units_of[vid] = max(peers or [0]) + 250

            ranks = _rank_within_subtree(pack, units_of)
            lines = [
                pay.SalesLine(
                    variant_id=vid, sku=pack.variants[vid].get("sku", ""),
                    units=units, revenue=round(units * prices[vid], 2),
                    rank_in_category=ranks[vid],
                    category=pack.subtree_of.get(vid, ""),
                )
                for vid, units in sorted(units_of.items())]

            emit("SALES_PERIOD",
                 datetime.combine(period_end, datetime.min.time())
                 + timedelta(days=1, hours=2 + offset),
                 pay.SalesPeriodPayload(
                     market_id=market.code, period_start=period_start,
                     period_end=period_end, currency=market.currency,
                     lines=lines,
                 ).model_dump(mode="json"))

    return events


def _rank_within_subtree(pack: _Pack, units: dict[str, int]) -> dict[str, int]:
    """Rank each variant within its depth-2 category, best seller first.

    Ties break on the variant id so two runs of the same seed rank them the
    same way. An unstable tie-break would make the pack irreproducible in the
    one field the bestseller insight reads.
    """
    grouped: dict[str, list[str]] = {}
    for vid in units:
        grouped.setdefault(pack.subtree_of.get(vid, ""), []).append(vid)

    ranks: dict[str, int] = {}
    for members in grouped.values():
        for position, vid in enumerate(
                sorted(members, key=lambda v: (-units[v], v)), start=1):
            ranks[vid] = position
    return ranks


def _bestsellers_without_media(pack: _Pack, seed: int) -> list[str]:
    """The real media-gap carriers chosen to be ranked first.

    Drawn from ``_gaps`` rather than invented, so every row the insight returns
    is a variant the record view would also flag. Spread across subtrees so the
    six do not all land in one category and read as one problem.
    """
    draw = rng_mod.stream(seed, "kg", "bestseller")
    seen_subtrees: set[str] = set()
    chosen: list[str] = []
    candidates = _gaps(pack)

    for _ in range(len(candidates) * 3):
        if len(chosen) >= BESTSELLERS_WITHOUT_MEDIA or not candidates:
            break
        vid = draw.pick(candidates)
        subtree = pack.subtree_of.get(vid, "")
        if vid in chosen or subtree in seen_subtrees:
            continue
        chosen.append(vid)
        seen_subtrees.add(subtree)
    return sorted(chosen)


def _cross_sell_pairs(pack: _Pack, seed: int) -> list[tuple[str, str]]:
    """Six pairs of variants from different products, in different branches.

    Different products because two variants of one product are the same thing
    in two sizes, and calling that a cross-sell candidate would be a finding
    nobody can act on.
    """
    draw = rng_mod.stream(seed, "kg", "crosssell")
    branches = sorted({b for b in pack.branch_of.values()})
    pairs: list[tuple[str, str]] = []
    used: set[str] = set()

    for index in range(CROSS_SELL_PAIRS):
        left_branch = branches[index % len(branches)]
        right_branch = branches[(index + 3) % len(branches)]
        left_pool = sorted(v for v in pack.variants
                           if pack.branch_of.get(v) == left_branch
                           and v not in used)
        right_pool = sorted(v for v in pack.variants
                            if pack.branch_of.get(v) == right_branch
                            and v not in used)
        if not left_pool or not right_pool:
            continue
        left = draw.pick(left_pool)
        right = next((v for v in right_pool
                      if pack.variants[v]["product_id"]
                      != pack.variants[left]["product_id"]), None)
        if right is None:
            continue
        used.update({left, right})
        pairs.append((left, right))
    return pairs


def _slots_for_pair(basket_slots: list[int], pair_index: int) -> set[int]:
    """The two basket campaigns a planted pair appears in.

    Two, not one: "share a campaign" is satisfied by coincidence and "share two"
    is not, so the insight asks for the stronger signal and the plant supplies
    it.
    """
    if len(basket_slots) < 2:
        return set()
    first = basket_slots[(pair_index * 2) % len(basket_slots)]
    second = basket_slots[(pair_index * 2 + 1) % len(basket_slots)]
    return {first, second}


def write(path: Path | None = None, seed: int | None = None,
          data_dir: Path | None = None) -> dict:
    """Write the pack as JSON lines and report what went into it."""
    target = path or (_data_dir() / "backoffice.jsonl")
    events = build(seed, data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        for event in events:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    tally: dict[str, int] = {}
    for event in events:
        tally[event["type"]] = tally.get(event["type"], 0) + 1
    return {"path": str(target), "events": len(events), "by_type": tally}
