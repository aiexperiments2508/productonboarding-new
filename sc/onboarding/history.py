"""What the retailer already knows about a value nobody sent.

A supplier leaves a field empty. Before anybody asks a model to read a document
for it, there are three cheaper questions with answers already on file:

*   **Does another variant of this product hold it?** A 45 W kettle and a 65 W
    kettle differ in wattage and agree about their plug type, their material
    and their warranty. A sibling is the strongest prior there is, because it is
    the same product.
*   **Does the rest of the category hold it?** Two hundred snack bars mostly
    agree about their unit of measure. One product disagreeing with two hundred
    is worth proposing; two products splitting fifty-fifty is not, and the
    support count is what says which of those it is.
*   **Has a person already settled this field?** Every decision a category
    manager makes is kept, and a value they approved for this attribute before
    is evidence about this attribute now. This is the loop closing: the queue
    feeds itself, and a reviewer who answers the same question twice sees their
    first answer offered back on the second.

**None of this needs a gateway**, which is the property that makes the whole
suggestion pass survive a venue with no network - and it is what the test suite
exercises, since the gateway is pinned to a closed port throughout.

**A prior is evidence and never an answer.** Nothing here writes, nothing here
decides, and a prior does not become a value on its own: ``suggest`` weighs it
against the passage a model actually read, and the score it produces is what
routes the proposal. The category holding a value is a reason to *ask*, not a
reason to assert - which is why every prior carries its support count and the
row it came from, and why the manager is shown both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Where a prior came from, strongest first. The order is the one
#: ``suggest._score`` weights them in and the one a reviewer reads them in.
SIBLING = "SIBLING"
APPROVAL = "APPROVAL"
CATEGORY = "CATEGORY"

SOURCE_ORDER = (SIBLING, APPROVAL, CATEGORY)

#: How much of the taxonomy makes a "category" for this purpose. Two levels -
#: ``food.snacks`` rather than ``food`` or ``food.snacks.bars`` - which is the
#: granularity the rollup already groups by, so a reviewer comparing the two
#: sees the same populations.
CATEGORY_DEPTH = 2

#: A category prior nothing much agrees with is noise. Below this many holders
#: the value is reported with its count and weighted at nothing, because "one
#: other product in this category says 12" is not a fact about the category.
MIN_CATEGORY_SUPPORT = 3


@dataclass(frozen=True)
class Prior:
    """One thing already on file that bears on a missing value."""

    source: str
    value: object
    #: How many rows say it. One sibling, forty category members, three past
    #: decisions - the number is what separates a convention from a coincidence.
    support: int
    detail: str
    #: The row this can be traced to: a variant id, or a decision id.
    reference: str = ""

    def as_dict(self) -> dict:
        return {"source": self.source, "value": self.value,
                "support": self.support, "detail": self.detail,
                "reference": self.reference}


def priors_for(entity_id: str, attribute_path: str, base,
               overlay=None) -> list[Prior]:
    """Everything already on file about this one missing value.

    ``overlay`` is the corrected-values overlay at the instant being assessed.
    Passed in rather than built, because a batch of forty products asks this
    question a hundred times and the overlay for one instant is one overlay -
    the same reason ``assess._walk`` builds it once for the whole pass.
    """
    found: list[Prior] = []
    found.extend(_siblings(entity_id, attribute_path, base, overlay))
    found.extend(_decisions(attribute_path))
    found.extend(_category(entity_id, attribute_path, base, overlay))
    return found


def _held(base, overlay, entity_id: str, path: str) -> object:
    """The value in force for one variant, corrections included.

    The overlay wins over the seeded pack, which is the same precedence
    ``readiness.record`` applies - a prior read from the pack when a correction
    has since moved the value would be evidence for a value nobody holds.
    """
    key = (entity_id, path)
    if overlay is not None:
        state = overlay.attr_values.get(key)
        if state is not None:
            return state.value
    return base.attr_values.get(key)


def _siblings(entity_id: str, path: str, base, overlay) -> list[Prior]:
    """What the other variants of this same product hold."""
    product_id = base.product_of_variant.get(entity_id, "")
    if not product_id:
        return []
    by_value: dict[str, list[str]] = {}
    for sibling in base.variants_of.get(product_id, []):
        if sibling == entity_id:
            continue
        value = _held(base, overlay, sibling, path)
        if value is None or value == "" or value == []:
            continue
        by_value.setdefault(_key(value), []).append(sibling)

    out = []
    for key, holders in sorted(by_value.items(), key=lambda kv: -len(kv[1])):
        value = json.loads(key)
        held = ", ".join(sorted(holders)[:3])
        out.append(Prior(
            source=SIBLING, value=value, support=len(holders),
            reference=sorted(holders)[0],
            detail=(f"{len(holders)} other variant"
                    f"{'' if len(holders) == 1 else 's'} of this product "
                    f"hold{'s' if len(holders) == 1 else ''} "
                    f"{_say(value)} ({held})")))
    return out


def _category(entity_id: str, path: str, base, overlay) -> list[Prior]:
    """What the rest of this product's category holds.

    Only the modal value is returned. A list of every distinct reading of an
    attribute across two hundred products is not evidence, it is a histogram,
    and a reviewer given one has been handed the analysis rather than the
    answer.
    """
    product_id = base.product_of_variant.get(entity_id, "")
    product = base.products.get(product_id)
    if product is None:
        return []
    branch = _branch(product.category)
    if not branch:
        return []

    by_value: dict[str, int] = {}
    for variant_id, variant in base.variants.items():
        if variant.product_id == product_id:
            continue
        other = base.products.get(variant.product_id)
        if other is None or _branch(other.category) != branch:
            continue
        value = _held(base, overlay, variant_id, path)
        if value is None or value == "" or value == []:
            continue
        by_value[_key(value)] = by_value.get(_key(value), 0) + 1

    if not by_value:
        return []
    key, support = max(by_value.items(), key=lambda kv: (kv[1], kv[0]))
    agreement = support / sum(by_value.values())
    value = json.loads(key)
    return [Prior(
        source=CATEGORY, value=value, support=support, reference=branch,
        detail=(f"{support} of {sum(by_value.values())} products in {branch} "
                f"hold {_say(value)} ({agreement:.0%} of those that hold a "
                f"value at all)"
                + ("" if support >= MIN_CATEGORY_SUPPORT
                   else f" - fewer than {MIN_CATEGORY_SUPPORT} is not a "
                        f"convention, so it is shown and weighed at nothing "
                        f"either way")))]


def _decisions(path: str) -> list[Prior]:
    """Values a person has already settled on for this attribute.

    Read from the decided suggestions rather than from the audit ledger, and
    the difference matters: the ledger records that a decision happened, and
    this needs the *value* that was decided. A REJECT contributes nothing - it
    is a statement that a particular proposal was wrong, not evidence for any
    other value.
    """
    from sc import db

    rows = db.query(
        "SELECT id, decision, proposed, decided_value FROM"
        " onboarding_suggestions WHERE attribute_path = ?"
        " AND decision IN ('APPROVE', 'RECTIFY')"
        " ORDER BY decided_at DESC LIMIT 200", (path,))

    by_value: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        # RECTIFY is the interesting one: a manager who corrected a proposal
        # told us what the value should have been, which is a stronger signal
        # than agreeing with one.
        raw = (row["decided_value"] if row["decision"] == "RECTIFY"
               else row["proposed"])
        try:
            value = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            continue
        if value is None:
            continue
        by_value.setdefault(_key(value), []).append((row["id"], row["decision"]))

    out = []
    for key, decisions in sorted(by_value.items(), key=lambda kv: -len(kv[1])):
        rectified = sum(1 for _, d in decisions if d == "RECTIFY")
        settled = json.loads(key)
        out.append(Prior(
            source=APPROVAL, value=settled, support=len(decisions),
            reference=decisions[0][0],
            detail=(f"a reviewer has settled this field on {_say(settled)} "
                    f"{len(decisions)} time"
                    f"{'' if len(decisions) == 1 else 's'}"
                    + (f", {rectified} by correcting a proposal"
                       if rectified else ""))))
    return out


def _say(value: object) -> str:
    """A value as it reads mid-sentence.

    Named in every prior's own words rather than left to the row beside it. A
    reviewer reading "the category holds this value" under a proposal that
    disagrees with the category has been told the opposite of what happened.
    """
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "nothing"
    return str(value)


def _branch(category: str) -> str:
    return ".".join(str(category or "").split(".")[:CATEGORY_DEPTH])


def _key(value: object) -> str:
    """A stable grouping key for a value of any declared type.

    JSON rather than ``str``: an attribute can be a list, and ``str`` would put
    ``["milk", "soy"]`` and ``["soy", "milk"]`` in different buckets while
    making ``1`` and ``"1"`` the same one. Both of those would be wrong in the
    direction that matters - the first splits agreement, the second invents it.
    """
    return json.dumps(value, sort_keys=True, default=str)
