"""The named ways an arriving payload can be wrong.

"Some of the data is incomplete or erroneous" is the kind of claim that is easy
to demonstrate and hard to measure. A payload that is simply mangled proves
nothing: no rule names it, no reviewer can act on it, and a validator that
misses it looks the same as one that catches it.

So a defect here is a *named* thing, drawn from a closed set, stamped on the
arrival that carries it. That turns three separate questions into one answer:

*   what did the estate do to this payload,
*   what should the validator have said about it,
*   and did it.

The set is closed on purpose. A generator that could invent new failure modes
would keep producing defects nothing downstream knows how to report, and the
answer key would drift from the thing it grades. ``tests/test_estate.py``
asserts that every member of this set is detected by something, which is the
check that keeps this file honest.

Each defect names the *class* of problem, not the fix. `WRONG_TYPE` says a
value arrived as the wrong dtype; whether the right response is to coerce it,
reject it or ask the supplier is a decision for the rules, not for the feed.
"""

from __future__ import annotations

from enum import StrEnum


class Defect(StrEnum):
    """What is wrong with an arriving payload.

    Ordered roughly by how early it is caught: the first three are visible
    from the payload alone, the next two need the catalog, and the last two
    need the rest of the estate.
    """

    #: A required attribute is absent. The commonest real-world defect and the
    #: least dramatic: a supplier fills in what its own system asks for, which
    #: is not the same list the retailer publishes against.
    MISSING_MANDATORY = "MISSING_MANDATORY"

    #: The value is present and is not the declared dtype - a wattage as the
    #: string "65 W", a weight as "40g". Cheap to detect and worth keeping
    #: apart from a missing value, because the supplier *did* answer.
    WRONG_TYPE = "WRONG_TYPE"

    #: A well-formed record in somebody else's vocabulary. The GDSN pool is not
    #: wrong to call it `netContent`; it is wrong for *this* catalog, and the
    #: distinction matters because the fix is a mapping rather than a
    #: correction.
    FOREIGN_VOCABULARY = "FOREIGN_VOCABULARY"

    #: The value is right and its shape is not - an allergen statement that
    #: says the correct thing in the wrong format. This is the defect a
    #: marketplace rejects a feed over while agreeing with its content.
    BROKEN_FORMAT = "BROKEN_FORMAT"

    #: Asserted against a document version that has since been superseded.
    #: Dangerous precisely because the payload is internally consistent: it was
    #: true, and nothing about it says it no longer is.
    STALE_VERSION = "STALE_VERSION"

    #: Disagrees with a value already asserted by a higher-precedence source.
    #: Only detectable with the rest of the estate in view, which is why an
    #: estate of one system cannot produce it.
    CONTRADICTS_SOURCE = "CONTRADICTS_SOURCE"

    #: A record whose category requires imagery arrived without it. Kept
    #: separate from MISSING_MANDATORY because media is missing far more often
    #: than attributes are, and because the remedy is a different team.
    MISSING_MEDIA = "MISSING_MEDIA"


#: Every defect, in declaration order. The tests walk this rather than the enum
#: directly so the order a report renders in is stable.
ALL: tuple[Defect, ...] = tuple(Defect)


#: What a reviewer is told, per defect. Held here rather than in the UI because
#: the same sentence has to appear in an API response, a console line and a
#: readiness finding, and three copies would disagree within a week.
EXPLANATION: dict[Defect, str] = {
    Defect.MISSING_MANDATORY:
        "a required attribute was not supplied",
    Defect.WRONG_TYPE:
        "the value is not the type the attribute declares",
    Defect.FOREIGN_VOCABULARY:
        "the record uses the sending system's own field names",
    Defect.BROKEN_FORMAT:
        "the value is correct but not in the format the channel requires",
    Defect.STALE_VERSION:
        "asserted against a document version that has been superseded",
    Defect.CONTRADICTS_SOURCE:
        "disagrees with a source that outranks this one",
    Defect.MISSING_MEDIA:
        "the category requires imagery and none was supplied",
}


def explain(defect: str) -> str:
    """One sentence for a defect, or the raw name if it is not one of ours.

    Never raises. A defect that reached a display surface is already past the
    point where refusing to render it helps anybody.
    """
    try:
        return EXPLANATION[Defect(defect)]
    except (ValueError, KeyError):
        return str(defect)
