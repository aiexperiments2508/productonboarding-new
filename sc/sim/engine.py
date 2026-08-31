"""Deterministic validation and propagation engine.

**No LLM touches this file.** Agents propose candidate ``ChangeSet``s; this
module decides what they cost and whether the result is publishable. Every
number a reviewer, a judge or the UI ever shows originates here, which is what
makes the recommendation defensible: the same change set against the same
catalog always produces the same KPIs and the same ``trace_hash``.

The pass is a propagation over the product record, not a simulation of anything
uncertain:

1.  Build the effective attribute table - baseline values, overlaid with the
    facts in force, overlaid with the change set's own SET_ATTRIBUTE actions.
2.  Follow ``derived_from`` to every content asset built on a value that has
    since moved, and to every listing those assets sit on.
3.  Evaluate the channel rules, the claim substantiation table, the allergen
    declaration rules, the freeze-window rule on channels that publish
    something irreversible, the fail-closed safety gate and the republish gate
    against that scope.
4.  Score the outcome and name every rule that bound.

Staleness propagates rather than being clamped: a corrected attribute makes an
asset stale, which makes a listing unpublishable, which blocks a channel. That
chain is what the Investigation tab renders as the causal explanation.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from sc import db
from sc.contracts import (
    ActionKind,
    ChangeSet,
    ChannelRuleKind,
    ContentAsset,
    KPIs,
    Listing,
    ProvenanceKind,
    SimResult,
    Violation,
    ViolationSeverity,
)
from sc.state.baseline import Baseline

# An inferred value on a safety attribute below this blocks publication rather
# than degrading it. Fail closed: an allergen the model is 70% sure about is
# not a fact, and no amount of downstream polish makes it one.
SAFETY_CONFIDENCE = 0.9

# The constraints that fail a publish closed rather than degrading it, and the
# only ones the ``safety_flags`` KPI counts on their own. ``tools.planning``
# imports this as its publish gate, so the number a reviewer reads and the rule
# that refuses the commit cannot drift apart.
SAFETY_CONSTRAINTS = ("allergen_declaration", "safety_confidence",
                      "sale_prohibited")

#: The attribute that says whether the product may be sold at all.
#:
#: Everything else this validator checks asks whether a *listing* is fit to
#: publish. This one asks whether the product is lawful to sell, which is a
#: different question with a different answer when the record is perfect and an
#: authority has ordered it down anyway. Correcting copy cannot clear it and
#: nothing a supplier sends can either.
SALE_PERMITTED = "compliance.sale_permitted"

HARD = ViolationSeverity.HARD
SOFT = ViolationSeverity.SOFT

# Channels where quoting a superseded number is a blocking error rather than a
# blemish: a marketplace rejects the feed, and print cannot be recalled.
LITERAL_HARD_CHANNELS = ("CH-MKT-A", "CH-PRINT")

# Fields whose MAX_LEN budget counts entries rather than characters. A PDP is
# allowed five bullets, not five letters.
COUNTED_FIELDS = ("bullets", "facets")


# ---------------------------------------------------------------------------
# Claim substantiation - the table STD-001 documents verbatim
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimRule:
    """One substantiation rule.

    ``holds`` reads nothing but effective attribute values, so a claim is
    substantiated by the record rather than by anybody's opinion of it.
    """

    claim: str
    paths: tuple[str, ...]
    statement: str
    holds: Callable[[dict[str, object]], bool]


def _free_of(values: dict[str, object], *needles: str) -> bool:
    declared = list(values.get("food.allergens.contains") or []) + list(
        values.get("food.allergens.may_contain") or [])
    return not any(n in str(item).lower() for item in declared for n in needles)


CLAIM_RULES: dict[str, ClaimRule] = {
    "gluten-free": ClaimRule(
        "gluten-free",
        ("food.allergens.contains", "food.allergens.may_contain"),
        "no gluten or wheat in contains or may_contain",
        lambda v: _free_of(v, "gluten", "wheat"),
    ),
    "high-fibre": ClaimRule(
        "high-fibre", ("food.fibre_g",), "food.fibre_g >= 6 g",
        lambda v: float(v["food.fibre_g"]) >= 6.0,
    ),
    "low-energy": ClaimRule(
        "low-energy", ("specs.power_w",), "specs.power_w <= 50 W",
        lambda v: float(v["specs.power_w"]) <= 50.0,
    ),
    "peanut-free": ClaimRule(
        "peanut-free",
        ("food.allergens.contains", "food.allergens.may_contain"),
        "no peanut in contains or may_contain",
        lambda v: _free_of(v, "peanut"),
    ),
    "ultra-quiet": ClaimRule(
        "ultra-quiet", ("specs.noise_db",), "specs.noise_db <= 40 dB",
        lambda v: float(v["specs.noise_db"]) <= 40.0,
    ),
}

# Allergen names as the channels' controlled vocabularies code them. Keyed by
# substring so "roasted almonds" and "almond" both land on AL-NUT.
#
# The catalog carries the map for the assortment it describes, and
# ``allergen_codes_for`` reads it from there - an assortment that sells fish
# and shellfish has to be able to code them, and the marketplace's own ENUM
# allowlist is built from the same map, so the two cannot disagree about what
# a declaration renders as. This table is the fallback for a pack generated
# before the profile existed.
ALLERGEN_CODES: dict[str, str] = {
    "almond": "AL-NUT",
    "egg": "AL-EGG",
    "gluten": "AL-GLUTEN",
    "hazelnut": "AL-NUT",
    "milk": "AL-MILK",
    "nut": "AL-NUT",
    "peanut": "AL-PEANUT",
    "soy": "AL-SOY",
    "walnut": "AL-NUT",
    "wheat": "AL-GLUTEN",
}


def allergen_codes_for(base) -> dict[str, str]:
    """The word-to-code map this catalog declares."""
    codes = (getattr(getattr(base, "catalog", None), "profile", None)
             or {}).get("allergen_codes")
    return dict(codes) if codes else ALLERGEN_CODES


# ---------------------------------------------------------------------------
# Overlay - what the store knows, projected into what the validator reads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttrState:
    """One attribute value and everything needed to defend it.

    The provenance travels with the value rather than beside it, because every
    gate downstream - the safety gate, the republish gate, the diff the
    reviewer approves - is a question about where the number came from.
    """

    value: object
    version: str                  # source doc version this value came from
    fact_id: str | None
    recorded_at: datetime | None
    provenance_kind: str          # ProvenanceKind value
    confidence: float | None


@dataclass
class Overlay:
    """Corrections in force, resolved from the bitemporal store.

    Built by the caller at a chosen ``as_of_recorded`` instant, so a resolution
    can deliberately be validated against what was known at decision time
    rather than against later-arriving corrections - which is exactly what the
    republish gate needs in order to catch a decision that has gone stale.
    """

    attr_values: dict[tuple[str, str], AttrState] = field(default_factory=dict)
    doc_versions: dict[str, str] = field(default_factory=dict)
    doc_status: dict[str, str] = field(default_factory=dict)   # ACTIVE|SUPERSEDED|WITHDRAWN
    channel_status: dict[str, str] = field(default_factory=dict)
    # "entity:path" -> the version a standing decision was validated against.
    decision_version: dict[str, str] = field(default_factory=dict)
    # listing id -> the source version its last publish went out on, which
    # moves the seed pack's ``Listing.published_version`` forward.
    published_version: dict[str, str] = field(default_factory=dict)
    as_of: datetime | None = None

    def digest(self) -> str:
        return db.dumps({
            "attrs": {
                f"{e}|{p}": [s.value, s.version, s.provenance_kind, s.confidence]
                for (e, p), s in sorted(self.attr_values.items())
            },
            "doc_versions": dict(sorted(self.doc_versions.items())),
            "doc_status": dict(sorted(self.doc_status.items())),
            "channel_status": dict(sorted(self.channel_status.items())),
            "decision_version": dict(sorted(self.decision_version.items())),
            "published_version": dict(sorted(self.published_version.items())),
            "as_of": self.as_of,
        })


@dataclass
class _Trace:
    """Accumulates the full internal state for hashing and explanation."""

    steps: list[tuple] = field(default_factory=list)

    def add(self, *parts) -> None:
        self.steps.append(parts)

    def digest(self) -> str:
        h = hashlib.sha256()
        for step in self.steps:
            h.update("|".join(str(p) for p in step).encode())
            h.update(b"\n")
        return h.hexdigest()[:32]


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


_VERSION = re.compile(r"^v(\d+)$")


def _rank(version: str) -> int:
    """Order two source-document versions. Anything unparseable sorts first."""
    m = _VERSION.match(version or "")
    return int(m.group(1)) if m else 0


def _empty(value: object) -> bool:
    return value is None or value == "" or value == []


def _on_file(state: object) -> bool:
    """Whether a mandatory field has been answered.

    Deliberately looser than ``_empty``: an empty ``may_contain`` is a declared
    absence of allergens, which is a complete answer. Counting it as a gap
    reports a clean catalog as incomplete, and the reviewer stops believing
    the number.
    """
    return state is not None and state.value is not None and state.value != ""


def _is_dtype(value: object, dtype: object) -> bool:
    if dtype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if dtype == "str":
        return isinstance(value, str)
    if dtype == "bool":
        return isinstance(value, bool)
    if dtype == "list[str]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    return True


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _quantity(value: object, unit: str | None) -> str:
    return f"{value} {unit}" if unit else str(value)


def _allergen_statement(contains: list, may_contain: list, base=None) -> str:
    parts = []
    if contains:
        parts.append("Contains: " + ", ".join(str(a) for a in contains) + ".")
    if may_contain:
        parts.append("May contain: " + ", ".join(str(a) for a in may_contain) + ".")
    return " ".join(parts)


def _allergen_code_list(contains: list, may_contain: list,
                        base=None) -> list[str]:
    table = ALLERGEN_CODES if base is None else allergen_codes_for(base)
    codes = set()
    for item in list(contains) + list(may_contain):
        text = str(item).lower()
        for needle, code in table.items():
            if needle in text:
                codes.add(code)
    return sorted(codes)


# The channel field name is what says which rendering a channel wants; the
# mapping lives in the channel's own attribute_map, so a new channel needs no
# code here beyond the format it names.
# Both take the baseline as an optional third argument so a caller with one
# can be rendered against this catalog's own code map, and a caller without
# one still gets the regulated default.
ALLERGEN_FORMATS: dict[str, Callable[..., object]] = {
    "allergen_statement": _allergen_statement,
    "allergenCodes": _allergen_code_list,
}
INGREDIENT_FORMATS: dict[str, Callable[[list], object]] = {
    "ingredients": lambda v: ", ".join(str(x) for x in v),
}

_INGREDIENT_PROSE = re.compile(r"Ingredients:\s*([^.]*)")


def _literal_pattern(value: object, unit: str | None) -> re.Pattern:
    """Find a superseded number quoted in prose.

    The lookarounds are the whole point: ``45`` must not match inside ``145``
    or ``45.5``, or every price and dimension on the page becomes a false
    positive.
    """
    body = rf"(?<![\d.]){re.escape(str(value))}(?![\d.])"
    if unit:
        body += rf"\s?{re.escape(unit)}"
        if unit[-1].isascii() and unit[-1].isalpha():
            body += r"\b"
    else:
        body += r"\b"
    return re.compile(body)


def _feed_fields(text: str) -> dict[str, object]:
    """A marketplace feed row as the channel will receive it.

    Regenerated rows come from a change set and may therefore be malformed;
    an unparseable row contributes no fields rather than taking the validator
    down with it, and the REQUIRED rules then report what is missing.
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Effective state
# ---------------------------------------------------------------------------


def _effective(base: Baseline, actions: list, overlay: Overlay):
    """Baseline values, then facts in force, then the change set itself.

    Returns the table, the keys the run touched, the keys whose value actually
    moved, and the keys a human has settled.
    """
    table: dict[tuple[str, str], AttrState] = {}
    for key in sorted(base.attr_values):
        source = base.attr_sources.get(key)
        table[key] = AttrState(
            value=base.attr_values[key],
            version=source.version if source else "",
            fact_id=None,
            recorded_at=None,
            provenance_kind=ProvenanceKind.RECORDED,
            confidence=None,
        )

    touched: set[tuple[str, str]] = set()
    decided: set[tuple[str, str]] = set()

    for key in sorted(overlay.attr_values):
        state = overlay.attr_values[key]
        table[key] = state
        touched.add(key)
        if state.provenance_kind == ProvenanceKind.DECIDED:
            decided.add(key)

    for action in actions:
        if action.kind != ActionKind.SET_ATTRIBUTE:
            continue
        key = (action.entity_id, action.attribute_path)
        prior = table.get(key)
        # A proposed change is INFERRED whatever confidence it claims for
        # itself. Only a human decision recorded in the store clears the
        # safety gate - otherwise an agent could unblock itself by asserting
        # certainty, which is the one thing fail-closed has to prevent.
        table[key] = AttrState(
            value=action.new_value,
            version=(action.source.version if action.source and action.source.version
                     else (prior.version if prior else "")),
            fact_id=None,
            recorded_at=None,
            provenance_kind=ProvenanceKind.INFERRED,
            confidence=action.confidence,
        )
        touched.add(key)

    changed = {k for k in sorted(touched)
               if table[k].value != base.attr_values.get(k)}
    return table, touched, changed, decided


def _values_of(table: dict, entity_id: str) -> dict[str, object]:
    return {path: state.value for (eid, path), state in table.items()
            if eid == entity_id}


def _listings_for(base: Baseline, entity_id: str) -> list[str]:
    """Every listing an entity id reaches, at whatever level it names.

    ``base.listings_of`` is keyed by variant, but a fact is recorded against
    whichever entity the evidence named: ``replay.ingest.record_attribute`` and
    the extraction node both write product ids, and a supplier document saying
    "the Northaven AP300" names a product. Resolving through this rather than
    through ``listings_of`` directly is what stops a rule going quiet on the
    level it was not written for - the fail-closed safety gate above all.
    """
    if entity_id in base.listings:
        return [entity_id]
    if entity_id in base.variants:
        return list(base.listings_of.get(entity_id, []))
    if entity_id in base.products:
        return sorted(listing_id
                      for variant_id in base.variants_of.get(entity_id, [])
                      for listing_id in base.listings_of.get(variant_id, []))
    return []


def _scope(base: Baseline, actions: list, touched: set) -> list[str]:
    """The listings this run has to look at.

    Candidate resolutions fan out concurrently, so a change set touching one
    variant must not walk the whole catalog. The one deliberate widening is
    ``assets_derived_from``: the comparison table on the base variant's page
    quotes the Max's wattage, so a correction scoped to the Max still lands
    there. An empty scope means nothing was touched at all, which is the
    whole-catalog readiness pass.
    """
    listings: set[str] = set()

    for entity_id, path in sorted(touched):
        listings.update(_listings_for(base, entity_id))
        for asset_id in base.assets_derived_from.get(f"{entity_id}:{path}", []):
            listings.add(base.assets[asset_id].listing_id)

    for action in actions:
        if action.kind in (ActionKind.REGENERATE_COPY, ActionKind.REMAP_TAXONOMY,
                           ActionKind.WITHHOLD_CHANNEL):
            listings.add(action.listing_id)
        elif action.kind == ActionKind.SET_FACET:
            listings.update(base.listings_by_channel.get(action.channel_id, []))

    return sorted(listings) if listings else sorted(base.listings)


def _texts(base: Baseline, actions: list, listing_ids: list[str]) -> dict[str, str]:
    """Asset text as it would be published, after any regeneration."""
    texts = {asset_id: base.assets[asset_id].text
             for listing_id in listing_ids
             for asset_id in base.assets_by_listing.get(listing_id, [])}
    for action in actions:
        if action.kind == ActionKind.REGENERATE_COPY and action.proposed_text:
            texts[action.asset_id] = action.proposed_text
    return texts


def _published(base: Baseline, listing_id: str,
               texts: dict[str, str]) -> dict[str, object]:
    """The channel-side record this listing would send.

    A marketplace feed row contributes every machine field it carries under the
    channel's own names; copy assets then contribute their own field, and win
    where the two name the same thing. Copy is the canonical text - a feed row
    that still holds the old title is stale, not authoritative, and saying so
    is ``stale_asset``'s job rather than this function's.
    """
    record: dict[str, object] = {}
    assets = [base.assets[a] for a in base.assets_by_listing.get(listing_id, [])]
    for asset in assets:
        if asset.field == "feed_row":
            record.update(_feed_fields(texts.get(asset.id, asset.text)))
    for asset in assets:
        if asset.field != "feed_row":
            record[asset.field] = texts.get(asset.id, asset.text)
    return record


def _applies(base: Baseline, variant_id: str, path: str) -> bool:
    """Whether a category is expected to carry this attribute at all.

    Marketplace A requires a wattage, but not on a snack bar - without this
    gate every food listing fails the appliance rules and the baseline is
    never clean.
    """
    definition = base.attr_defs.get(path)
    if definition is None:
        return False
    if not definition.applies_to:
        return True
    category = base.products[base.product_of_variant[variant_id]].category
    return any(category.startswith(prefix) for prefix in definition.applies_to)


# ---------------------------------------------------------------------------
# Validation passes
# ---------------------------------------------------------------------------


def _check_staleness(base: Baseline, listing: Listing, asset: ContentAsset,
                     table: dict, changed: set, texts: dict[str, str],
                     regenerated: set[str], out: list[Violation]) -> None:
    """Copy still standing on a value that has moved underneath it."""
    channel = listing.channel_id
    built = _rank(asset.built_at_version)

    for ref in sorted(asset.derived_from):
        entity_id, _, path = ref.partition(":")
        key = (entity_id, path)
        state = table.get(key)
        if state is None:
            continue

        if _rank(state.version) > built and asset.id not in regenerated:
            out.append(Violation(
                constraint="stale_asset", severity=SOFT,
                entity_id=asset.id, channel_id=channel,
                required=float(_rank(state.version)), available=float(built),
                detail=(f"{asset.id} ({listing.id} {asset.field}) was built "
                        f"against {ref} {asset.built_at_version}; "
                        f"{state.version} is now in force"),
            ))

        if key not in changed:
            continue
        old = base.attr_values.get(key)
        if isinstance(old, bool) or not isinstance(old, (int, float)):
            continue
        unit = base.attr_defs[path].unit if path in base.attr_defs else None
        if not _literal_pattern(old, unit).search(texts.get(asset.id, asset.text)):
            continue
        # The deterministic half of contradiction detection. Whether the
        # surviving sentence is *wrong* or merely happens to repeat the number
        # is a semantic question, and a later advisory LLM node's job.
        out.append(Violation(
            constraint="stale_literal",
            severity=HARD if channel in LITERAL_HARD_CHANNELS else SOFT,
            entity_id=asset.id, channel_id=channel,
            required=float(_rank(state.version)), available=float(built),
            detail=(f"{asset.id} ({listing.id} {asset.field}) still quotes "
                    f"{_quantity(old, unit)} for {ref}, superseded by "
                    f"{_quantity(state.value, unit)}"),
        ))


def _published_version(overlay: Overlay, listing: Listing) -> str:
    """The source version this listing last went out on."""
    return overlay.published_version.get(listing.id, listing.published_version)


def _check_frozen_version(base: Baseline, listing: Listing, table: dict,
                          at_press: str, out: list[Violation]) -> None:
    """A published artefact standing on a value that has moved under it.

    Only on channels declaring a freeze window, because only those publish
    something that cannot be recalled: once the catalogue file has left
    prepress, regenerating the copy changes nothing a shopper is holding. A
    reversible channel answers a moved value by republishing, and raising this
    there would block every correction with the correction's own arrival.

    Deliberately blind to whether the copy was regenerated. That is the whole
    finding of INC-2026-002: rebuilding ``catalogue_copy`` cleared the only
    signal there was, and 214,000 catalogues printed the superseded figure. It
    is cleared by publishing the listing again - a press decision - and by
    withholding it, and by nothing else.
    """
    channel = base.channels[listing.channel_id]
    if channel.freeze_days <= 0 or not at_press:
        return

    printed = _rank(at_press)
    for asset_id in base.assets_by_listing.get(listing.id, []):
        for ref in sorted(base.assets[asset_id].derived_from):
            entity_id, _, path = ref.partition(":")
            state = table.get((entity_id, path))
            if state is None or _rank(state.version) <= printed:
                continue
            out.append(Violation(
                constraint="stale_version", severity=HARD,
                entity_id=listing.id, channel_id=channel.id,
                required=float(_rank(state.version)), available=float(printed),
                detail=(f"{listing.id} went to press at {at_press}; {ref} is "
                        f"now {state.version}. {channel.id} freezes content for "
                        f"{channel.freeze_days} days before a press date, so "
                        f"this needs a reprint decision rather than regenerated "
                        f"copy"),
            ))


def _check_rules(base: Baseline, listing: Listing, table: dict,
                 published: dict, out: list[Violation]) -> None:
    """Every ChannelRule the listing's channel declares, in rule-id order."""
    variant_id = listing.variant_id
    channel = base.channels[listing.channel_id]

    for rule in base.rules_by_channel.get(listing.channel_id, []):
        path = rule.attribute_path
        if path and not _applies(base, variant_id, path):
            continue

        entity_id = f"{listing.id}:{rule.field}"
        effective = table.get((variant_id, path)) if path else None
        value = effective.value if effective else None
        shown = published.get(rule.field)
        head = f"{rule.id} on {channel.id}"

        if rule.kind == ChannelRuleKind.REQUIRED:
            if _empty(value):
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    required=1.0, available=0.0,
                    detail=(f"{head} requires {rule.field}: no value on file "
                            f"for {variant_id} {path}"),
                ))

        elif rule.kind == ChannelRuleKind.DTYPE:
            if not _empty(value) and not _is_dtype(value, rule.value):
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    detail=(f"{head} requires {rule.field} to be {rule.value}; "
                            f"{variant_id} {path} is "
                            f"{type(value).__name__} {value!r}"),
                ))

        elif rule.kind == ChannelRuleKind.MAX_LEN:
            if shown is None:
                continue
            budget = float(rule.value)
            used = float(len(str(shown).splitlines()) if rule.field in COUNTED_FIELDS
                         else len(str(shown)))
            if used > budget:
                unit = "entries" if rule.field in COUNTED_FIELDS else "characters"
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    required=budget, available=used,
                    detail=(f"{head} allows {budget:.0f} {unit} in {rule.field}; "
                            f"{used:.0f} written"),
                ))

        elif rule.kind == ChannelRuleKind.FORMAT:
            if shown is None:
                continue
            if not re.search(str(rule.value), str(shown)):
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    detail=(f"{head} requires {rule.field} to match "
                            f"{rule.value}; got {str(shown)[:60]!r}"),
                ))

        elif rule.kind == ChannelRuleKind.ENUM:
            if shown is None:
                continue
            allowed = set(rule.value or [])
            rejected = sorted(str(m) for m in _as_list(shown)
                              if str(m) not in allowed)
            if rejected:
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    detail=(f"{head} rejects {', '.join(rejected)} in "
                            f"{rule.field}; permitted values are "
                            f"{', '.join(sorted(allowed))}"),
                ))

        elif rule.kind == ChannelRuleKind.ORDERED_MATCH:
            source = table.get((variant_id, str(rule.value)))
            if shown is None or source is None:
                continue
            want = _as_list(source.value)
            got = _as_list(shown)
            if got != want:
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    detail=(f"{head} requires {rule.field} to match "
                            f"{rule.value} in order; declared "
                            f"{', '.join(got)} against {', '.join(want)}"),
                ))

        elif rule.kind == ChannelRuleKind.CATEGORY_MAPPED:
            category = base.products[base.product_of_variant[variant_id]].category
            if category not in channel.category_map:
                out.append(Violation(
                    constraint="channel_schema", severity=rule.severity,
                    entity_id=entity_id, channel_id=channel.id,
                    detail=(f"{head} has no {channel.taxonomy} node for "
                            f"internal category {category}"),
                ))


def _check_claims(base: Baseline, listing: Listing, table: dict,
                  out: list[Violation]) -> None:
    """Every claim the variant asserts and every claim the copy leans on."""
    variant_id = listing.variant_id
    values = _values_of(table, variant_id)

    claimed = set(str(c) for c in (values.get("claims") or []))
    for asset_id in base.assets_by_listing.get(listing.id, []):
        claimed.update(str(c) for c in base.assets[asset_id].claims_used)

    for claim in sorted(claimed):
        rule = CLAIM_RULES.get(claim)
        if rule is None:
            continue
        # A value of the wrong type is as unusable as a missing one: the claim
        # cannot be substantiated either way, and the DTYPE rule is already
        # reporting the type problem in its own words.
        unusable = [p for p in rule.paths
                    if values.get(p) is None
                    or (p in base.attr_defs
                        and not _is_dtype(values[p], base.attr_defs[p].dtype))]
        if unusable:
            out.append(Violation(
                constraint="claim_consistency", severity=HARD,
                entity_id=f"{variant_id}:claims", channel_id=listing.channel_id,
                detail=(f"claim '{claim}' needs {rule.statement}; "
                        f"{variant_id} has no usable value for "
                        f"{', '.join(unusable)}"),
            ))
        elif not rule.holds(values):
            out.append(Violation(
                constraint="claim_consistency", severity=HARD,
                entity_id=f"{variant_id}:claims", channel_id=listing.channel_id,
                detail=(f"claim '{claim}' holds only if {rule.statement}; "
                        + ", ".join(f"{p}={values[p]}" for p in rule.paths)),
            ))


def _check_allergens(base: Baseline, listing: Listing, table: dict,
                     published: dict, texts: dict[str, str],
                     out: list[Violation]) -> None:
    """Declarations must be complete, in the channel's format, and in order."""
    variant_id = listing.variant_id
    if not _applies(base, variant_id, "food.allergens.contains"):
        return

    contains = list(table.get((variant_id, "food.allergens.contains"),
                              AttrState([], "", None, None, "", None)).value or [])
    may = list(table.get((variant_id, "food.allergens.may_contain"),
                         AttrState([], "", None, None, "", None)).value or [])

    # 1. The channel's own field, rendered the way that channel demands it.
    field_name = base.channel_field(listing.channel_id, "food.allergens.contains")
    formatter = ALLERGEN_FORMATS.get(field_name)
    if formatter is not None:
        want = formatter(contains, may, base)
        got = published.get(field_name)
        if got != want:
            out.append(Violation(
                constraint="allergen_declaration", severity=HARD,
                entity_id=f"{listing.id}:{field_name}", channel_id=listing.channel_id,
                detail=(f"{listing.channel_id} requires {field_name} to read "
                        f"{want!r}; prepared content has {got!r}"),
            ))

    # 2. Whatever the format, every declared allergen has to be somewhere a
    # shopper can read it. A missing allergen is never a soft failure.
    copy = "\n".join(texts.get(asset_id, base.assets[asset_id].text)
                     for asset_id in base.assets_by_listing.get(listing.id, []))
    lowered = copy.lower()
    absent = sorted(str(a) for a in contains + may if str(a).lower() not in lowered)
    if absent:
        out.append(Violation(
            constraint="allergen_declaration", severity=HARD,
            entity_id=f"{listing.id}:food.allergens", channel_id=listing.channel_id,
            required=float(len(contains) + len(may)),
            available=float(len(contains) + len(may) - len(absent)),
            detail=(f"{listing.id} content does not declare "
                    f"{', '.join(absent)} anywhere"),
        ))

    # 3. Ingredient order carries meaning, so a reordered declaration is a
    # different declaration - which is what MKB-2208 rejects a feed for.
    source = table.get((variant_id, "food.ingredients"))
    if source is None:
        return
    want_order = _as_list(source.value)
    declared: list[tuple[str, list[str]]] = []
    ingredient_field = base.channel_field(listing.channel_id, "food.ingredients")
    if ingredient_field in published:
        declared.append((ingredient_field, _as_list(published[ingredient_field])))
    for asset_id in base.assets_by_listing.get(listing.id, []):
        text = texts.get(asset_id, base.assets[asset_id].text)
        found = _INGREDIENT_PROSE.search(text)
        if found:
            declared.append((asset_id, _as_list(found.group(1))))

    for where, order in declared:
        if order != want_order:
            out.append(Violation(
                constraint="allergen_declaration", severity=HARD,
                entity_id=f"{listing.id}:food.ingredients",
                channel_id=listing.channel_id,
                detail=(f"{where} declares {', '.join(order)}; "
                        f"{variant_id} food.ingredients is "
                        f"{', '.join(want_order)}"),
            ))
            return


def _check_safety(base: Baseline, table: dict, decided: set,
                  listings: list[str], out: list[Violation]) -> None:
    """Fail closed on a low-confidence inference about a safety attribute."""
    in_scope = set(listings)
    for key in sorted(table):
        entity_id, path = key
        definition = base.attr_defs.get(path)
        if definition is None or not definition.safety_class:
            continue
        state = table[key]
        if state.provenance_kind != ProvenanceKind.INFERRED or key in decided:
            continue
        confidence = state.confidence
        if confidence is not None and confidence >= SAFETY_CONFIDENCE:
            continue

        for listing_id in _listings_for(base, entity_id):
            if listing_id not in in_scope:
                continue
            out.append(Violation(
                constraint="safety_confidence", severity=HARD,
                entity_id=f"{entity_id}:{path}",
                channel_id=base.listings[listing_id].channel_id,
                required=SAFETY_CONFIDENCE, available=float(confidence or 0.0),
                detail=(f"{path} on {entity_id} is INFERRED at "
                        f"{confidence if confidence is not None else 0.0:.2f}, "
                        f"below the {SAFETY_CONFIDENCE:.2f} safety threshold, "
                        f"with no human decision on file; {listing_id} withheld"),
            ))


def _check_sale_permitted(base: Baseline, table: dict,
                          listings: list[str], out: list[Violation]) -> None:
    """A product an authority has ordered down may not be published.

    Kept apart from ``_check_safety`` on purpose, though both fail closed. That
    one is about *confidence* - a value the model is not sure enough about -
    and it only ever fires on an inference. This one fires on a fact, recorded
    with certainty by somebody with the power to stop a sale, and the remedy is
    not a better reading.

    Named as its own constraint rather than folded into the safety gate so the
    reason survives to the reviewer. "Withheld: safety confidence" and
    "withheld: a withdrawal notice" are the same outcome and different
    sentences, and the second is the one somebody has to act on.
    """
    in_scope = set(listings)
    for key in sorted(table):
        entity_id, path = key
        if path != SALE_PERMITTED:
            continue
        state = table[key]
        # Only an explicit denial blocks. A missing value is a gap the
        # readiness checks report; treating "we were never told" as "not
        # permitted" would hold the whole catalog the first time a supplier
        # left the field empty.
        if state.value is not False:
            continue

        for listing_id in _listings_for(base, entity_id):
            if listing_id not in in_scope:
                continue
            out.append(Violation(
                constraint="sale_prohibited", severity=HARD,
                entity_id=f"{entity_id}:{path}",
                channel_id=base.listings[listing_id].channel_id,
                required=1.0, available=0.0,
                detail=(f"{entity_id} is not permitted for sale; "
                        f"{listing_id} may not be published, and no correction "
                        f"to its content changes that"),
            ))


def _check_version_currency(base: Baseline, table: dict, overlay: Overlay,
                            out: list[Violation]) -> None:
    """The republish gate.

    A resolution validated against v1 cannot be published once v2 is in force,
    however good it looked at the time. This is what stops the finale's "Max
    only" clarification being overtaken by an approval taken before it landed.
    """
    for ref in sorted(overlay.decision_version):
        entity_id, _, path = ref.partition(":")
        state = table.get((entity_id, path))
        if state is None:
            continue
        decided_at = overlay.decision_version[ref]
        if _rank(decided_at) >= _rank(state.version):
            continue
        out.append(Violation(
            constraint="stale_version", severity=HARD,
            entity_id=ref,
            required=float(_rank(state.version)), available=float(_rank(decided_at)),
            detail=(f"{ref} was validated against {decided_at}; "
                    f"{state.version} is now in force and must be revalidated "
                    f"before republishing"),
        ))


def _check_citations(actions: list, out: list[Violation]) -> None:
    """An uncited change is not publishable.

    The brief requires every generated change to cite the evidence it rests
    on, so this is a rule breach rather than a stylistic lapse.
    """
    for action in actions:
        if action.source is not None:
            continue
        if action.kind == ActionKind.SET_ATTRIBUTE:
            entity_id = f"{action.entity_id}:{action.attribute_path}"
        elif action.kind == ActionKind.REGENERATE_COPY:
            entity_id = action.asset_id
        else:
            continue
        out.append(Violation(
            constraint="citation_missing", severity=HARD, entity_id=entity_id,
            detail=(f"action {action.id} ({action.kind}) changes published "
                    f"content without citing a source document"),
        ))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _listings_hit(base: Baseline, violation: Violation) -> list[str]:
    """Which listings a violation actually stops from publishing.

    Violations name whatever entity the rule is about - an asset, a listing
    field, a variant attribute - so readiness has to resolve each one back to
    the listings it blocks rather than assuming a single shape.
    """
    head = violation.entity_id.split(":", 1)[0]
    if head in base.listings:
        return [head]
    if head in base.assets:
        return [base.assets[head].listing_id]
    candidates = _listings_for(base, head)
    if violation.channel_id:
        return [l for l in candidates
                if base.listings[l].channel_id == violation.channel_id]
    return list(candidates)


def _safety_flag(base: Baseline, violation: Violation) -> bool:
    """Whether a binding violation is a *safety* problem rather than a wrong page.

    Two grounds, both about the declaration itself: one of the constraints that
    fails the publish closed, or a breach on a safety-class attribute - an
    allergen list quoting a superseded value is a safety flag wherever it
    appears. Membership of a regulated product is not a third ground. Counting
    it as one is what reported a wattage correction, on a purifier with no
    safety-class attribute, as carrying three safety flags: the flags belonged
    to a regulated product elsewhere in the blast radius, and a reviewer reading
    "3" against an air purifier has been told something untrue.
    """
    if violation.constraint in SAFETY_CONSTRAINTS:
        return True
    definition = base.attr_defs.get(violation.entity_id.partition(":")[2])
    return bool(definition and definition.safety_class)


def _kpis(base: Baseline, table: dict, changed: set, listings: list[str],
          withheld: set[str], actions: list, raw: list[Violation],
          violations: list[Violation]) -> KPIs:
    """What this resolution costs, in the units a reviewer counts in."""
    live = [lid for lid in listings if lid not in withheld]

    stale = {v.entity_id for v in raw
             if v.constraint in ("stale_asset", "stale_literal")}
    blocked = {v.channel_id for v in violations
               if v.severity == HARD and v.channel_id}
    blocked.update(base.listings[lid].channel_id for lid in sorted(withheld))

    unready = {lid for v in violations if v.severity == HARD
               for lid in _listings_hit(base, v)}
    ready = [lid for lid in live if lid not in unready]

    required = filled = 0
    for listing_id in live:
        listing = base.listings[listing_id]
        for definition in base.applicable_attrs(listing.variant_id):
            if listing.channel_id not in definition.required_for:
                continue
            required += 1
            if _on_file(table.get((listing.variant_id, definition.path))):
                filled += 1

    republish = sum(1 for a in actions if a.kind in (
        ActionKind.REGENERATE_COPY, ActionKind.REMAP_TAXONOMY,
        ActionKind.SET_FACET, ActionKind.WITHHOLD_CHANNEL))
    touched_listings = {base.assets[a].listing_id for a in sorted(stale)
                        if a in base.assets}
    touched_listings.update(
        listing_id for key in sorted(changed)
        for listing_id in _listings_for(base, key[0]))
    republish += len(touched_listings)

    return KPIs(
        fields_affected=len(changed),
        assets_stale=len(stale),
        channels_blocked=len(blocked),
        listings_ready_pct=round(100.0 * len(ready) / len(live), 2) if live else 100.0,
        completeness_pct=round(100.0 * filled / required, 2) if required else 100.0,
        safety_flags=sum(1 for v in violations
                         if v.severity == HARD and _safety_flag(base, v)),
        republish_steps=republish,
    )


def _dedupe(violations: list[Violation]) -> list[Violation]:
    """Collapse repeats of the same binding rule.

    One rule can bind on every asset of a listing; the reviewer needs the rule
    and its worst instance, not twelve rows of it. HARD always survives SOFT,
    then the largest gap wins.
    """
    worst: dict[tuple, Violation] = {}
    for v in violations:
        key = (v.constraint, v.entity_id, v.channel_id or "")
        rank = (v.severity == HARD, v.required - v.available)
        if key not in worst:
            worst[key] = v
            continue
        held = worst[key]
        if rank > (held.severity == HARD, held.required - held.available):
            worst[key] = v
    return sorted(worst.values(),
                  key=lambda v: (v.constraint, v.entity_id, v.channel_id or ""))


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def simulate(base: Baseline, delta: ChangeSet,
             overlay: Overlay | None = None) -> SimResult:
    """Validate one candidate resolution and score it."""
    started = time.perf_counter()
    overlay = overlay or Overlay()
    trace = _Trace()
    trace.add("seed", delta.id, overlay.digest())

    # Sorted by id so two equivalent change sets built in a different order
    # produce an identical trace.
    actions = sorted(delta.actions, key=lambda a: a.id)
    table, touched, changed, decided = _effective(base, actions, overlay)

    listings = _scope(base, actions, touched)
    withheld = {a.listing_id for a in actions
                if a.kind == ActionKind.WITHHOLD_CHANNEL}
    regenerated = {a.asset_id for a in actions
                   if a.kind == ActionKind.REGENERATE_COPY}
    texts = _texts(base, actions, listings)

    for listing_id in listings:
        for path in sorted(base.attr_defs):
            state = table.get((base.listings[listing_id].variant_id, path))
            if state is not None:
                trace.add("attr", listing_id, path, db.dumps(state.value),
                          state.version, state.provenance_kind, state.confidence)

    raw: list[Violation] = []
    for listing_id in listings:
        listing = base.listings[listing_id]
        # A withheld listing is not being published, so its channel rules have
        # nothing to bind on. The block itself is the cost, and it is counted
        # in channels_blocked rather than hidden.
        if listing_id in withheld:
            trace.add("withheld", listing_id, listing.channel_id)
            continue
        published = _published(base, listing_id, texts)
        for asset_id in base.assets_by_listing.get(listing_id, []):
            _check_staleness(base, listing, base.assets[asset_id], table, changed,
                             texts, regenerated, raw)
        _check_frozen_version(base, listing, table,
                              _published_version(overlay, listing), raw)
        _check_rules(base, listing, table, published, raw)
        _check_claims(base, listing, table, raw)
        _check_allergens(base, listing, table, published, texts, raw)

    _check_safety(base, table, decided, listings, raw)
    _check_sale_permitted(base, table, listings, raw)
    _check_version_currency(base, table, overlay, raw)
    _check_citations(actions, raw)

    violations = _dedupe(raw)
    for v in violations:
        trace.add("violation", v.constraint, v.severity, v.entity_id,
                  v.channel_id, v.required, v.available)

    kpis = _kpis(base, table, changed, listings, withheld, actions, raw, violations)
    for name, value in sorted(kpis.model_dump().items()):
        trace.add("kpi", name, value)

    return SimResult(
        delta_id=delta.id,
        feasible=not any(v.severity == HARD for v in violations),
        violations=violations,
        kpis=kpis,
        trace_hash=trace.digest(),
        runtime_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def baseline_readiness(base: Baseline, overlay: Overlay | None = None) -> SimResult:
    """Validate the catalog as it stands, changing nothing.

    With a quiet overlay nothing is touched, so the scope is the whole catalog
    and the answer is "is the prepared content publishable right now?". The
    seed generator asserts this comes back clean; every violation a run reports
    afterwards is therefore attributable to the correction under investigation.
    """
    return simulate(base, ChangeSet(id="BASELINE"), overlay)
