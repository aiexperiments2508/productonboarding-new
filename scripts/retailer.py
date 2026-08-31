"""The retailer profile: everything category-shaped, in one file.

The seed pack used to hardcode one retailer's assortment across four files -
a taxonomy here, a required-media map there, a supplier list in a third, and
the category prefixes ``home.``/``food.``/``audio.`` written out by hand in
nine places under ``sc/``. Re-pointing the demo at a different retailer meant
finding all of them.

So the shape of a retailer is now data. ``data/profiles/<id>.json`` carries the
fascia, the branches and their taxonomy, the supplier roster, the catalogue as
*product lines* rather than a naming formula, and the per-branch facts the
running system needs - which imagery a category cannot launch without, which
attributes are worth previewing, which branches are regulated. A different
retailer is a different file and the same code.

``RETAILER_PROFILE`` selects it, the same way ``DATA_SEED`` selects the draw.

**The profile describes an assortment, not a rule.** Nothing here decides
whether a product may be published. Which imagery a category needs is a fact
about a retailer's own standard (INT-001) and belongs to the retailer; whether
a listing missing that imagery may go live is a rule, and rules stay in code
and in the corpus where a reviewer can read them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "profiles"

#: Which profile to build the pack from. One name, one file.
PROFILE_ID = os.environ.get("RETAILER_PROFILE", "ashcombe")


def load(profile_id: str = PROFILE_ID) -> dict:
    """Read one profile.

    Fails loudly. A missing profile would otherwise fall back to a default and
    produce a pack that looks right and is somebody else's assortment.
    """
    path = PROFILES / f"{profile_id}.json"
    if not path.exists():
        available = sorted(p.stem for p in PROFILES.glob("*.json"))
        raise SystemExit(
            f"no retailer profile {profile_id!r} at {path}. "
            f"Available: {', '.join(available) or '(none)'}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


PROFILE = load()


# ---------------------------------------------------------------------------
# Views onto the profile
# ---------------------------------------------------------------------------
# Each of these answers one question the generator or the running system asks.
# They are functions rather than module constants so that a caller loading a
# second profile - a test, or a future multi-retailer pack - gets that
# profile's answer rather than the one that happened to import first.


def branches(profile: dict = PROFILE) -> dict:
    return profile["branches"]


def taxonomy(profile: dict = PROFILE) -> dict:
    return profile["taxonomy"]


def suppliers(profile: dict = PROFILE) -> list[tuple[str, str, str]]:
    """``(id, name, branch)``, in declaration order so the draw is stable."""
    return [(s["id"], s["name"], s["branch"]) for s in profile["suppliers"]]


def required_media(profile: dict = PROFILE) -> dict[str, tuple[str, ...]]:
    """Prefix -> image roles the category cannot launch without.

    Keyed with the trailing dot the prefix matchers expect, so this drops
    straight into the shape ``sc.readiness.checks.REQUIRED_MEDIA`` already has.
    """
    return {f"{key}.": tuple(spec["required_media"])
            for key, spec in profile["branches"].items()}


def salient(profile: dict = PROFILE) -> dict[str, tuple[str, ...]]:
    """Prefix -> the attributes a channel preview leads with."""
    return {f"{key}.": tuple(spec["salient"])
            for key, spec in profile["branches"].items()}


def regulated_prefixes(profile: dict = PROFILE) -> tuple[str, ...]:
    """Branches whose products carry the regulated flag.

    ``regulated`` is one of the two switches every escalation path keys off, so
    which branches carry it is a decision about a retailer's risk appetite and
    belongs in the profile rather than in ``category.startswith("food.")``.
    """
    return tuple(f"{key}." for key, spec in profile["branches"].items()
                 if spec.get("regulated"))


def is_regulated(category: str, profile: dict = PROFILE) -> bool:
    return category.startswith(regulated_prefixes(profile))


def hues(profile: dict = PROFILE) -> dict[str, int]:
    """Branch -> the hue its generated imagery is drawn in."""
    return {key: spec["hue"] for key, spec in profile["branches"].items()}


def lines(profile: dict = PROFILE) -> list[tuple[str, str, bool]]:
    """The catalogue as ``(leaf, product line, is_own_brand)``.

    Ordered - the background draw walks it and a dict iteration that reordered
    would change every generated id.
    """
    out: list[tuple[str, str, bool]] = []
    for leaf, spec in profile["lines"].items():
        if leaf == "note":
            continue
        for name in spec.get("own", ()):
            out.append((leaf, name, True))
        for name in spec.get("brand", ()):
            out.append((leaf, name, False))
    return out


def own_brand(tier: str = "core", profile: dict = PROFILE) -> str:
    """The fascia prefix an own-brand line carries."""
    for entry in profile["fascia"]["own_brand_tiers"]:
        if entry["key"] == tier:
            return entry["prefix"]
    return profile["fascia"]["name"]


def minimum_age(leaf: str, profile: dict = PROFILE) -> int | None:
    """The age bar on this leaf, where the law sets one.

    Longest prefix wins, so ``food.alcohol.`` can cover three leaves without
    naming each and a leaf may still override its branch.
    """
    table = {k: v for k, v in profile.get("age_restricted", {}).items()
             if k != "note"}
    best: tuple[int, int] | None = None
    for prefix, age in table.items():
        if leaf == prefix or leaf.startswith(prefix):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), age)
    return best[1] if best else None


def export_controlled(profile: dict = PROFILE) -> tuple[str, ...]:
    return tuple(profile.get("export_controlled", {}).get("leaves", ()))


def allergen_codes(profile: dict = PROFILE) -> dict[str, str]:
    return dict(profile["allergen_codes"])


def as_catalog_block(profile: dict = PROFILE) -> dict:
    """What the running system needs, for ``catalog.json``.

    The generator writes this so that ``sc/`` reads the branch facts from the
    baseline rather than holding a second copy that drifts. Only the parts a
    running system actually consults - the assortment itself is already in the
    products it generated.
    """
    return {
        "id": profile["id"],
        "fascia": profile["fascia"]["name"],
        "market": profile["fascia"]["market"],
        "currency": profile["fascia"]["currency"],
        "branches": {
            key: {
                "label": spec["label"],
                "regulated": bool(spec.get("regulated")),
                "required_media": list(spec["required_media"]),
                "salient": list(spec["salient"]),
            }
            for key, spec in profile["branches"].items()
        },
        # The validator renders an allergen declaration into each channel's
        # own vocabulary, and the marketplace ENUM allowlist is built from the
        # same map. Both read it from here, so a declaration and the rule that
        # checks it cannot disagree about what "celery" codes as.
        "allergen_codes": dict(profile["allergen_codes"]),
    }
