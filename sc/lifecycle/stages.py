"""Where a product is in its journey.

The system already knows a great deal about a product: whether its information
is fit to launch, which listings exist and what state each one is in, what has
been committed, whether a correction case is open. What it has never had is the
join - the one sentence a category manager actually asks for, which is "where
has this got to".

**Stage is derived and never stored.** The publication estate is derived from
the channels for exactly this reason, and says so: an estate that could
disagree with the channel list is a second account of where content goes, and
the first thing it would disagree about is the channel somebody just added. A
stored lifecycle column would be a second account of a product's state, and the
first thing it would disagree about is the product somebody just corrected.

So this module is a pure function of things that already exist, and the closed
set below is small on purpose. A stage a downstream reader has to special-case
is a stage that will be got wrong somewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sc.readiness.verdict import BLOCKED, READY, RETURN

#: The lanes, in the order work moves through them.
DRAFT = "DRAFT"
WITH_SUPPLIER = "WITH_SUPPLIER"
CLEARED = "CLEARED"
PUSHED_DOWNSTREAM = "PUSHED_DOWNSTREAM"
LIVE = "LIVE"
LATE_CHANGE = "LATE_CHANGE"

STAGES: tuple[str, ...] = (DRAFT, WITH_SUPPLIER, CLEARED, PUSHED_DOWNSTREAM,
                           LIVE, LATE_CHANGE)

#: What each lane is for, in the words the screen uses. Held beside the names
#: so the UI cannot describe a lane differently from the rule that fills it.
DESCRIPTIONS: dict[str, str] = {
    DRAFT: "A supplier has proposed a line the catalog does not have yet. "
           "Nothing enters the catalog until a reviewer accepts it.",
    WITH_SUPPLIER: "Sent back. Something is missing or contradicted, and the "
                   "system that has to fix it is named on every finding.",
    CLEARED: "Fit to launch, and not yet pushed anywhere.",
    PUSHED_DOWNSTREAM: "Cleared and dispatched. The listings are prepared and "
                       "waiting on their launch date.",
    LIVE: "On sale. What a shopper sees is what the record says.",
    LATE_CHANGE: "A correction has landed against something already prepared "
                 "or already live. The old value is still out there.",
}


@dataclass
class Placement:
    """One product's position, and why it is there."""

    product_id: str
    stage: str
    verdict: str
    #: The variants this product has, with their SKUs and their own verdicts.
    variants: list[dict] = field(default_factory=list)
    #: Listing counts by status, which is what separates prepared from live.
    listings: dict[str, int] = field(default_factory=dict)
    #: What is holding it, in the words the checks used.
    findings: list[dict] = field(default_factory=list)
    #: Which systems have to fix those findings.
    systems: list[str] = field(default_factory=list)
    #: Set when a correction has landed against it since it was cleared.
    correction: dict | None = None
    #: Set when something about it is currently hidden downstream.
    redactions: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "stage": self.stage,
            "verdict": self.verdict,
            "variants": self.variants,
            "listings": self.listings,
            "findings": self.findings,
            "systems": self.systems,
            "correction": self.correction,
            "redactions": self.redactions,
        }


def stage_of(*, verdict: str, listings: dict[str, int], dispatched: bool,
             corrected: bool, redacted: bool) -> str:
    """The lane, from state that already exists. Pure arithmetic, no clock.

    Order matters and is argued rather than arbitrary:

    * A late change outranks everything below it. A product that is live and
      also carrying a correction is not simply live - the whole point of the
      lane is that something wrong is currently in front of a shopper, and a
      board that filed it under "on sale" would be hiding the one row anybody
      needs to look at.
    * Being sent back outranks being live, for a product that is both. The
      finding is the actionable half.
    """
    if corrected or redacted:
        return LATE_CHANGE
    if verdict in (RETURN, BLOCKED):
        return WITH_SUPPLIER
    if listings.get("LIVE"):
        return LIVE
    if dispatched or listings.get("PREPARED") and verdict == READY:
        return PUSHED_DOWNSTREAM if dispatched else CLEARED
    return CLEARED
