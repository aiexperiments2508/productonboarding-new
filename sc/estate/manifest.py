"""The external systems that feed the retailer.

The MVP had four suppliers and a tape, both written as literal tuples in the
generator, and no notion of a *system* at all. That collapsed two different
things into one: a supplier is who asserts a value, and a system is what
carried it. A retailer with one supplier still has eight systems, and the
question "why is this attribute wrong" is answered by the second one at least
as often as by the first.

So the estate is declared here, as data, and nothing else in the application
names one. Eleven systems, each standing for something a retailer genuinely
runs:

    supplier-portal        where a supplier types its own data
    supplier-pim           the supplier's master data, sent machine to machine
    label-artwork          the packaging artwork library - the legal source
    erp-master             finance and operations master data
    gdsn-pool              the industry data pool, in industry vocabulary
    regulatory-feed        notices from regulatory affairs
    marketplace-connector  what the channels say back
    translation-service    localised copy, always a little behind
    imaging-dam            photography and asset management
    market-signals         category management's view of what sells
    logistics-tms          how a thing ships, from transport operations

Two properties are deliberate and load-bearing.

**Conformance is per system, not per record.** A supplier portal where a human
types into a form omits things; an industry data pool does not omit things, it
uses its own field names for them. Those are different failures with different
remedies, and attaching them to the system rather than sprinkling them randomly
is what makes "which system should we fix" answerable.

**One system is clean and one is bad at several things.** An estate where
everything is equally suspect measures nothing - there is no contrast, so no
finding is informative. ``label-artwork`` is never wrong, because it is the
legal source and a retailer that cannot trust its own artwork has a different
problem. ``gdsn-pool`` is wrong in three ways at once, because a data pool
integration is where this genuinely hurts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sc.estate.defects import Defect


@dataclass(frozen=True)
class System:
    """One external system.

    ``index`` is not decoration. The tape is one globally ordered sequence and
    two systems can emit at the same simulated instant; the index breaks that
    tie, so the order is a property of the manifest rather than of whichever
    dictionary iterated first.
    """

    id: str
    title: str
    #: The real-world function this stands in for, in the retailer's own words.
    owner: str
    why: str
    #: Event types this system is the origin of.
    emits: tuple[str, ...]
    #: How this system misbehaves. Empty means it does not.
    defects: tuple[Defect, ...] = field(default=())
    #: Roughly what share of this system's payloads carry a defect, 0.0-1.0.
    #: Applied deterministically from the seed, never from live randomness.
    defect_rate: float = 0.0
    #: Typical batch size and the spread around it, in events.
    batch_size: tuple[int, int] = (2, 5)
    #: Seconds of simulated delay between this system's batches, min and max.
    #: Wide spreads are what make the arrivals visibly interleave.
    interval: tuple[float, float] = (0.6, 2.4)
    #: How far this system's assertions are trusted against another's. Mirrors
    #: the precedence already documented in POL-002 rather than inventing a
    #: second ranking - artwork outranks a portal feed, which outranks email.
    precedence: int = 20

    @property
    def well_behaved(self) -> bool:
        return not self.defects


SYSTEMS: tuple[System, ...] = (
    System(
        id="supplier-portal",
        title="Supplier Portal",
        owner="Supplier self-service",
        why="Where a supplier's own staff type specifications into a form. "
            "Everything a human fills in by hand is here, and so is every "
            "field they did not realise was required.",
        emits=("SUPPLIER_FEED", "SPEC_DOC"),
        defects=(Defect.MISSING_MANDATORY,),
        defect_rate=0.18,
        batch_size=(2, 6),
        interval=(0.5, 2.0),
        precedence=20,
    ),
    System(
        id="supplier-pim",
        title="Supplier PIM",
        owner="Supplier master data",
        why="The supplier's own product information system, sending machine to "
            "machine. Structurally sound and occasionally typed the way its "
            "database happens to store it rather than the way ours declares it.",
        emits=("SUPPLIER_FEED", "CATALOG_UPDATE"),
        defects=(Defect.WRONG_TYPE,),
        defect_rate=0.14,
        batch_size=(3, 8),
        interval=(0.8, 3.0),
        precedence=30,
    ),
    System(
        id="label-artwork",
        title="Label Artwork Library",
        owner="Packaging and artwork",
        why="The approved artwork, and therefore the legal declaration. This is "
            "the source every other system is checked against, which is exactly "
            "why it is the one system that introduces no defects: an estate "
            "where the arbiter is also unreliable cannot settle anything.",
        emits=("SPEC_DOC",),
        defects=(),
        defect_rate=0.0,
        batch_size=(1, 2),
        interval=(2.0, 5.0),
        precedence=40,
    ),
    System(
        id="erp-master",
        title="ERP Master Data",
        owner="Finance and operations",
        why="Identifiers, pack configuration and commercial data. Authoritative "
            "about what a thing is called and indifferent to how it is "
            "described, which is where its formats come apart.",
        emits=("CATALOG_UPDATE", "SUPPLIER_FEED"),
        defects=(Defect.BROKEN_FORMAT,),
        defect_rate=0.12,
        batch_size=(2, 5),
        interval=(1.0, 3.5),
        precedence=35,
    ),
    System(
        id="gdsn-pool",
        title="GDSN Data Pool",
        owner="Industry data pool",
        why="The industry-standard pool. It is not wrong to call net content "
            "`netContent` - it is wrong for this catalog, and the remedy is a "
            "mapping rather than a correction. The worst-behaved system here, "
            "deliberately: a data pool integration is where this genuinely hurts.",
        emits=("SUPPLIER_FEED",),
        defects=(Defect.FOREIGN_VOCABULARY, Defect.WRONG_TYPE,
                 Defect.CONTRADICTS_SOURCE),
        defect_rate=0.34,
        batch_size=(4, 10),
        interval=(0.4, 1.6),
        precedence=15,
    ),
    System(
        id="regulatory-feed",
        title="Regulatory Notices",
        owner="Regulatory affairs",
        why="Mandates, recalls and category restrictions. Rare, small, and the "
            "one feed where being late is worse than being wrong - so it "
            "delivers in ones and twos rather than waiting to fill a batch.",
        emits=("SPEC_DOC", "COMMS"),
        defects=(),
        defect_rate=0.0,
        batch_size=(1, 2),
        interval=(3.0, 7.0),
        precedence=45,
    ),
    System(
        id="marketplace-connector",
        title="Marketplace Connector",
        owner="Channel integration",
        why="What the channels say back - acknowledgements and rejections. A "
            "rejection is a fact about the connector's own schema rather than "
            "about the product, which is why it is a system and not a supplier.",
        emits=("CHANNEL_STATUS", "PUBLISH_TELEMETRY"),
        defects=(Defect.BROKEN_FORMAT,),
        defect_rate=0.16,
        batch_size=(2, 6),
        interval=(0.5, 2.2),
        precedence=25,
    ),
    System(
        id="translation-service",
        title="Translation Service",
        owner="Localisation",
        why="Localised copy, produced from whatever version was current when "
            "the job was queued. Structurally perfect and reliably a revision "
            "behind, which is the defect nobody notices until a recall.",
        emits=("CATALOG_UPDATE",),
        defects=(Defect.STALE_VERSION,),
        defect_rate=0.22,
        batch_size=(3, 7),
        interval=(1.5, 4.0),
        precedence=10,
    ),
    System(
        id="imaging-dam",
        title="Imaging and Asset Management",
        owner="Digital asset management",
        why="Photography and the records that point at it. Media goes missing "
            "far more often than attributes do, and the remedy is a different "
            "team, so it is worth counting separately.",
        emits=("CATALOG_UPDATE", "PUBLISH_TELEMETRY"),
        defects=(Defect.MISSING_MEDIA,),
        defect_rate=0.28,
        batch_size=(2, 5),
        interval=(1.0, 3.0),
        precedence=25,
    ),
    System(
        id="market-signals",
        title="Market Signals",
        owner="Category management",
        why="What is selling, where, and when - season, region and the "
            "festivities a category turns on. Advisory by construction: it "
            "informs how a product is presented and never what it is.",
        emits=("COMMS",),
        defects=(Defect.CONTRADICTS_SOURCE,),
        defect_rate=0.10,
        batch_size=(1, 4),
        interval=(2.0, 6.0),
        precedence=5,
    ),
    System(
        id="logistics-tms",
        title="Transport and Logistics",
        owner="Supply chain operations",
        why="Carrier bookings, pack configuration and dispatch confirmations. "
            "Authoritative about how a thing ships and indifferent to how it "
            "is described - so it sends a case dimension in whatever unit the "
            "carrier's booking screen wanted and rounds it on the way through.",
        emits=("CATALOG_UPDATE", "PUBLISH_TELEMETRY"),
        # Both reuse detectors that already exist. A defect kind with no
        # deterministic check behind it would be an assertion rather than a
        # finding, and `test_every_stamped_defect_is_detected` is there to stop
        # exactly that.
        defects=(Defect.WRONG_TYPE, Defect.BROKEN_FORMAT),
        defect_rate=0.15,
        batch_size=(2, 6),
        interval=(1.0, 3.5),
        precedence=18,
    ),
)

BY_ID: dict[str, System] = {s.id: s for s in SYSTEMS}

#: Position in the manifest, used to break ties when two systems emit at the
#: same simulated instant. Global order has to come from somewhere stated.
INDEX: dict[str, int] = {s.id: i for i, s in enumerate(SYSTEMS)}


def emitters_of(event_type: str) -> tuple[System, ...]:
    """Which systems are an origin for this kind of event."""
    return tuple(s for s in SYSTEMS if event_type in s.emits)


def describe() -> list[dict]:
    """The manifest as the API and the console render it."""
    return [
        {
            "id": s.id,
            "title": s.title,
            "owner": s.owner,
            "why": s.why,
            "emits": list(s.emits),
            "defects": [str(d) for d in s.defects],
            "defect_rate": s.defect_rate,
            "precedence": s.precedence,
            "well_behaved": s.well_behaved,
            "index": INDEX[s.id],
        }
        for s in SYSTEMS
    ]
