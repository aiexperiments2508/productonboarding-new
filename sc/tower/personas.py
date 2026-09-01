"""Who is looking, and what they came for.

Six roles, each with a tab it opens on and the handful of figures it actually
uses. Declared as data so the API and the UI read one list; a second copy in
the frontend is where "Compliance" and "Compliance Officer" start appearing on
two screens for the same person.

**This is a lens and not a permission boundary, and every surface that renders
it says so.** There is no identity provider anywhere in this system, no session
and no password - ``sc/main.py`` states that position about its own routes, and
``apps/vendor/server.py`` states it about supplier identity. Nothing here
changes that. Picking a persona changes which numbers are put in front of you;
it does not change which numbers you may ask the API for, and pretending
otherwise would be worse than not offering the picker at all, because a control
that looks like access control and is not is the kind of thing somebody builds
a process on top of.

What *is* enforced is unchanged and lives where it always did: a decision, a
fill, a threshold move and a spend cap each demand a named actor and write it
to the audit ledger. That name is taken at its word. It is attribution, which
is a real property, rather than authentication, which this system does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The tabs a persona can open on. Matched to the four the UI renders, and
#: named here because a persona pointing at a tab that does not exist is a
#: blank screen rather than an error.
TABS: tuple[str, ...] = ("flow", "feeds", "kpis", "cost")

#: The sentence every persona-aware surface carries. Held once so six screens
#: cannot phrase the disclaimer six ways, and one of them weakly.
LENS_NOTE = (
    "A persona chooses what you are shown, not what you are allowed to see. "
    "There is no login in this system: every route stays open to anyone who "
    "can reach it, and what an action records is the name whoever took it "
    "typed. That is attribution, not access control, and it is deliberate - "
    "an approval gate is worth more than a password box in front of a "
    "dashboard."
)


@dataclass(frozen=True)
class Persona:
    """One role's default view. Frozen: it is a declaration, not state."""

    id: str
    label: str
    #: What this person is trying to find out, in their words.
    question: str
    default_tab: str
    #: The KPI keys this persona opens on, in the order they read them. Keys
    #: are the ones `sc.tower.kpis.summary` returns; a key that stops existing
    #: is a test failure rather than a blank tile - see `tests/test_tower.py`.
    tiles: tuple[str, ...]
    #: Which register columns this persona filters by first.
    scope: tuple[str, ...] = field(default_factory=tuple)


PERSONAS: tuple[Persona, ...] = (
    Persona(
        id="supplier-ops",
        label="Supplier Ops",
        question="Whose feeds are failing, and what do I tell them?",
        default_tab="feeds",
        tiles=("feeds_received", "rows_received", "feed_success_rate",
               "feeds_with_defects", "blocked_rate"),
        scope=("supplier", "system"),
    ),
    Persona(
        id="catalog-manager",
        label="Catalog Manager",
        question="How much of this week's intake is fit to sell?",
        default_tab="flow",
        tiles=("rows_assessed", "all_clear_rate", "blocked_rate",
               "awaiting_decision", "median_hours_to_downstream"),
        scope=("supplier", "category"),
    ),
    Persona(
        id="compliance",
        label="Compliance",
        question="What did the gate stop, on whose authority, and what got "
                 "through that should not have?",
        default_tab="flow",
        tiles=("compliance_pass_rate", "blocked_rate", "residual_errors",
               "residual_error_rate", "checks_complete"),
        scope=("supplier", "system"),
    ),
    Persona(
        id="ai-ops",
        label="AI Ops",
        question="What is the system writing unattended, and how much of it "
                 "is a person still having to answer?",
        default_tab="kpis",
        tiles=("proposals", "autonomous_fills", "autonomous_fill_rate",
               "decisions_by_person", "awaiting_decision"),
        scope=("supplier",),
    ),
    Persona(
        id="finops",
        label="FinOps",
        question="What are the models costing, where is it going, and what is "
                 "the cache saving?",
        default_tab="cost",
        tiles=("cost_usd", "cost_avoided_usd", "tokens", "tokens_avoided",
               "cost_per_row_cleared_usd"),
        scope=("system",),
    ),
    Persona(
        id="executive",
        label="Executive",
        question="Is this working, and can I say so out loud?",
        default_tab="kpis",
        tiles=("feeds_received", "all_clear_rate", "autonomous_fill_rate",
               "median_hours_to_downstream", "cost_per_row_cleared_usd"),
        scope=(),
    ),
)

BY_ID = {persona.id: persona for persona in PERSONAS}

#: The one offered when nobody has chosen. Catalog Manager rather than
#: Executive on purpose: the first screen should be the one somebody can act
#: on, and a summary nobody can act on is what a control tower is usually
#: accused of being.
DEFAULT = "catalog-manager"


def describe() -> dict:
    """The declarations, as the API and the UI read them."""
    return {
        "personas": [
            {"id": p.id, "label": p.label, "question": p.question,
             "default_tab": p.default_tab, "tiles": list(p.tiles),
             "scope": list(p.scope)}
            for p in PERSONAS
        ],
        "default": DEFAULT,
        "tabs": list(TABS),
        "enforced": False,
        "note": LENS_NOTE,
    }


def get(persona_id: str | None) -> Persona:
    """One persona, falling back to the default rather than raising.

    A stale id in somebody's localStorage should open the tower on a sensible
    screen, not a 400. Nothing is gated on this value, so an unrecognised one
    cannot widen anything either.
    """
    return BY_ID.get(persona_id or "", BY_ID[DEFAULT])
