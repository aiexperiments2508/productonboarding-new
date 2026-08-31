"""The systems a correction goes *out* to.

The estate so far is about what arrives. This is the other end: the systems that
own a live listing, and the only ones that can change what a shopper sees.

Two properties separate this from the ingest estate, and neither is negotiable.

**Every tool here mutates.** A supplier system that could write to the retailer's
catalog is a compromise waiting to happen; a publication system that could not
write would be pointless. So the safeguards do not travel with the caller, they
travel with the tool: `commit_plan` refuses without a recorded approval whichever
server it is reached through, and that refusal is enforced at the planning
boundary rather than in the graph, so no future graph edit can route around it.

**A publication system is not load-bearing for the decision.** A channel that
has stopped answering must not be able to hold up a correction to the five that
are answering. Dispatch is therefore per system and reports per system: a
correction is "published to four of five, one deferred", never "failed".

The blast radius already answers which listings a correction reaches. What it
could not do was say which *systems* have to be told, which is the question
somebody has to answer before anything gets fixed.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What a publication system can be asked to do. A closed vocabulary and not a
#: general write surface: a connector that accepts arbitrary mutations is one
#: nobody can reason about.
#:
#: It was three, and the three were the whole vocabulary of "the shopper-facing
#: value is wrong". A fourth and fifth were added when it turned out that is
#: two questions rather than one. Replacing a wrong value needs a validated
#: replacement to exist; taking it down does not, and waiting for one means
#: leaving a wrong allergen declaration on sale in the meantime. So `redact`
#: hides, `push_update` replaces, and they are gated separately.
#:
#: `discharge` is the fifth because some channels cannot do either. A printed
#: run cannot be recalled, so what is owed is an erratum, and an obligation
#: nobody can close is not an obligation.
VERBS: tuple[str, ...] = ("push_update", "redact", "withdraw_listing",
                          "restore_listing", "discharge")


@dataclass(frozen=True)
class PublicationSystem:
    """One system that owns live listings.

    Derived from the channels the catalog already declares rather than
    configured separately. A publication estate that could disagree with the
    channel list is a second account of where content goes, and the first thing
    it would disagree about is the channel somebody just added.
    """

    id: str
    channel_id: str
    title: str
    owner: str
    #: Whether what this channel published can be recalled. A print run cannot,
    #: which is why a correction reaching it is a different conversation from
    #: one reaching a web page.
    recallable: bool
    freeze_days: int

    @property
    def endpoint(self) -> str:
        return f"/mcp/publish/{self.id}"


def systems(base) -> list[PublicationSystem]:
    """The publication estate, derived from the channels in the catalog."""
    out: list[PublicationSystem] = []
    for channel_id in sorted(base.channels):
        channel = base.channels[channel_id]
        out.append(PublicationSystem(
            id=f"pub-{channel_id.lower()}",
            channel_id=channel_id,
            title=f"{channel.name} publisher",
            owner="Channel integration",
            # A freeze window exists because the artefact cannot be pulled
            # back; the two facts are the same fact and are not stored twice.
            recallable=channel.freeze_days == 0,
            freeze_days=channel.freeze_days,
        ))
    return out


def by_channel(base) -> dict[str, PublicationSystem]:
    return {s.channel_id: s for s in systems(base)}


def blast_to_systems(trace: dict, base) -> list[dict]:
    """Which publication systems a blast radius reaches, and with what.

    The trace already names the listings. This groups them by the system that
    owns each one and carries the SKUs along, because "eleven listings" is a
    number and "these four SKUs on these three systems" is a work list.

    Ordered by system so two reads of one trace agree.
    """
    affected = (trace or {}).get("affected") or {}
    listings = affected.get("listings") or []
    lookup = by_channel(base)

    grouped: dict[str, dict] = {}
    for listing_id in sorted(listings):
        listing = base.listings.get(listing_id)
        if listing is None:
            continue
        system = lookup.get(listing.channel_id)
        if system is None:
            continue
        entry = grouped.setdefault(system.id, {
            "system": system.id,
            "channel_id": system.channel_id,
            "title": system.title,
            "recallable": system.recallable,
            "freeze_days": system.freeze_days,
            "listings": [],
            "skus": [],
        })
        entry["listings"].append(listing_id)
        variant = base.variants.get(listing.variant_id)
        sku = getattr(variant, "sku", "") or listing.variant_id
        if sku not in entry["skus"]:
            entry["skus"].append(sku)

    for entry in grouped.values():
        entry["skus"].sort()
        entry["listings"].sort()
    return [grouped[k] for k in sorted(grouped)]


def affected_skus(trace: dict, base) -> list[dict]:
    """The SKUs a correction reaches, with where each one is live.

    A blast radius expressed in internal identifiers is a blast radius only this
    system can read. Everybody who has to *act* on one - a buyer, a supplier, a
    marketplace account manager - works in SKUs.
    """
    affected = (trace or {}).get("affected") or {}
    rows: list[dict] = []
    for variant_id in sorted(affected.get("variants") or []):
        variant = base.variants.get(variant_id)
        if variant is None:
            continue
        listings = [l for l in (affected.get("listings") or [])
                    if l in base.listings
                    and base.listings[l].variant_id == variant_id]
        rows.append({
            "sku": variant.sku or variant_id,
            "entity_id": variant_id,
            "name": variant.name,
            "product_id": variant.product_id,
            "listings": sorted(listings),
            "channels": sorted({base.listings[l].channel_id for l in listings}),
        })
    return rows
