"""Is this product's information fit to publish?

The validator already answers a different question well: is this *change*
publishable on this channel. That question presumes a product that is already
live and asks what one correction does to it. Nothing asked whether a record was
complete enough to go live in the first place, which is the question a category
manager actually has.

Nine checks. Six are decided here, by rules, over the same tables the
publish-time validator reads - a product that passed readiness and then failed
publication on the same fact would mean two implementations of one rule, and the
rules-as-data design exists to prevent exactly that.

Three need reading and live in ``reading.py``: whether a mandate covers this
product, whether a sentence has become semantically wrong, and whether the
record contradicts internal documentation. On those a model finds and cites; a
rule decides, and a candidate with no citation is dropped.

**There is no score.** A product with three open findings is not seventy per
cent ready. It is not ready, and the three findings are the thing somebody acts
on. A number would invite a threshold and a threshold would invite publishing at
ninety, which is how a missing allergen declaration reaches a shelf.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sc.contracts import ChannelRuleKind, MediaRole

#: Which image roles a category cannot launch without. Mirrors INT-001 rather
#: than inventing a second rule - the document is what a reviewer is shown when
#: they ask why a product was held.
#:
#: The catalog carries the answer for the retailer it describes, and
#: ``required_media_for`` reads it from there. This table is the fallback for a
#: pack generated before profiles existed, which is why it still names three
#: branches that a current pack has eight of.
REQUIRED_MEDIA: dict[str, tuple[MediaRole, ...]] = {
    "home.": (MediaRole.HERO, MediaRole.IN_SITU),
    "food.": (MediaRole.PACK_FRONT, MediaRole.INGREDIENT_PANEL),
    "audio.": (MediaRole.HERO,),
}


def required_media_for(base) -> dict[str, tuple[MediaRole, ...]]:
    """The category-to-imagery table this catalog declares.

    A retailer that sells clothing needs a detail shot on a garment and a
    retailer that does not has no opinion about one, so the table belongs to
    the assortment. Falls back to the module constant when the catalog carries
    no profile - an older pack is still a valid catalog.
    """
    branches = (getattr(base.catalog, "profile", None) or {}).get("branches")
    if not branches:
        return REQUIRED_MEDIA
    return {f"{key}.": tuple(MediaRole(r) for r in spec.get("required_media", ()))
            for key, spec in branches.items()}

#: Content that may never appear, whatever a supplier sends. From INT-002. These
#: are not weighed against completeness and they are not gradeable; the phrase
#: is either there or it is not.
#:
#: Matched on whole words, because "cures" must not fire on "manicures" and a
#: substring check here would produce a finding nobody can act on.
FORBIDDEN_PHRASES: tuple[tuple[str, str], ...] = (
    ("cures", "a medical claim on a product that is not a medicine"),
    ("treats", "a medical claim on a product that is not a medicine"),
    ("prevents", "a medical claim on a product that is not a medicine"),
    ("clinically proven", "a medical claim requiring evidence held on file"),
    ("completely safe", "an absolute safety claim"),
    ("harmless", "an absolute safety claim"),
    ("guaranteed to", "a guaranteed outcome"),
    ("100% effective", "a guaranteed outcome"),
)

#: Severity. BLOCKING is reserved for saleability - a regulation saying this may
#: not be sold - and is never reached by accumulating other findings. Blocking
#: is a statement about legality, and arriving at it by weight of evidence would
#: make it a judgement.
BLOCKING = "BLOCKING"
OPEN = "OPEN"

#: The attribute a withdrawal notice moves. Mirrors ``sim.engine.SALE_PERMITTED``
#: - the same fact bars a launch here and refuses a publish there, and the two
#: surfaces must not disagree about which attribute says so.
SALE_PERMITTED = "compliance.sale_permitted"


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a record.

    ``system`` is the point of the whole estate. "The data is incomplete" is not
    something anybody can act on; "the data pool sent net content in its own
    vocabulary and the field is still empty" is, because it names who has to fix
    it. A finding that cannot name a system says so rather than blaming one.
    """

    check: str
    subject: str          # the attribute path, media role or asset it concerns
    detail: str
    severity: str = OPEN
    system: str | None = None
    #: The rule id, document id or chunk id this rests on. A finding with no
    #: basis is an opinion.
    basis: str = ""
    citation: str = ""

    def sort_key(self) -> tuple:
        return (self.severity != BLOCKING, self.check, self.subject, self.detail)

    def as_dict(self) -> dict:
        return {"check": self.check, "subject": self.subject,
                "detail": self.detail, "severity": self.severity,
                "system": self.system, "basis": self.basis,
                "citation": self.citation}


@dataclass
class Record:
    """One product, as the estate has left it.

    Assembled once and handed to every check, so nine checks do not make nine
    passes over the fact store and cannot disagree about what is in force.
    """

    entity_id: str
    product_id: str
    category: str
    regulated: bool
    values: dict[str, object] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    systems: dict[str, str | None] = field(default_factory=dict)
    defects: dict[str, tuple[str, ...]] = field(default_factory=dict)
    media: list = field(default_factory=list)
    listings: list[str] = field(default_factory=list)
    #: Values that lost a precedence contest, kept because a settled
    #: disagreement is settled rather than absent.
    superseded: dict[str, list[dict]] = field(default_factory=dict)

    def system_for(self, path: str) -> str | None:
        return self.systems.get(path)


# ---------------------------------------------------------------------------
# The six that need no model
# ---------------------------------------------------------------------------


def applicable_attributes(record: Record, base) -> list[Finding]:
    """Every attribute the category defines has a value.

    "Applicable" comes from the attribute's own ``applies_to`` prefixes, so a
    snack is never held for missing a wattage. An attribute that applies and is
    absent is a gap; one that does not apply is not a gap and must not be
    reported as one, or the finding list becomes noise a reviewer learns to
    scroll past.
    """
    findings = []
    for path, definition in sorted(base.attr_defs.items()):
        applies = (not definition.applies_to
                   or any(record.category.startswith(prefix)
                          for prefix in definition.applies_to))
        if not applies or path in record.values:
            continue
        # Silent unless a channel wants it: `mandatory_information` is the check
        # that speaks for channel requirements, and reporting the same absence
        # twice would double every finding list.
        if definition.required_for:
            continue
        findings.append(Finding(
            check="applicable_attributes", subject=path,
            detail=f"{definition.label} applies to {record.category} and has "
                   f"no value",
            system=record.system_for(path), basis="category attribute schema"))
    return findings


def declared_types(record: Record, base) -> list[Finding]:
    """Every value parses as the type the attribute declares."""
    findings = []
    for path, value in sorted(record.values.items()):
        definition = base.attr_defs.get(path)
        if definition is None or value is None:
            continue
        if not _is_dtype(value, definition.dtype):
            findings.append(Finding(
                check="declared_types", subject=path,
                detail=f"{value!r} is not {definition.dtype}",
                system=record.system_for(path),
                basis="attribute schema"))
    return findings


def _is_dtype(value: object, dtype: str) -> bool:
    if dtype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if dtype == "str":
        return isinstance(value, str)
    if dtype.startswith("list["):
        return isinstance(value, list)
    return True


def mandatory_information(record: Record, base) -> list[Finding]:
    """Everything a channel this product lists on refuses without.

    Reads the same rule rows the publish-time validator reads. Two readings of
    one table is one table; two tables would be two answers to "why was this
    held", and the reviewer would be shown whichever one ran.
    """
    channels = {base.listings[l].channel_id for l in record.listings
                if l in base.listings}
    findings = []
    for rule in sorted(base.rules, key=lambda r: r.id):
        if rule.kind != ChannelRuleKind.REQUIRED or rule.channel_id not in channels:
            continue
        path = rule.attribute_path
        if not path:
            continue
        definition = base.attr_defs.get(path)
        # A rule requiring a wattage binds on a marketplace, and a snack bar
        # lists on that marketplace. Without this the snack is held for missing
        # a rated power it could never have - a finding nobody can act on, in a
        # list a reviewer then learns to scroll past.
        if definition is not None and definition.applies_to and not any(
                record.category.startswith(prefix)
                for prefix in definition.applies_to):
            continue
        value = record.values.get(path)
        if value is None or value == "" or value == []:
            definition = base.attr_defs.get(path)
            findings.append(Finding(
                check="mandatory_information", subject=path,
                detail=f"{(definition.label if definition else path)} is "
                       f"required by {rule.channel_id} and is not held",
                system=record.system_for(path), basis=rule.id))
    return findings


def required_media(record: Record, base) -> list[Finding]:
    """The imagery the category cannot launch without.

    By role, not by count. Three hero shots and no ingredient panel is a food
    product nobody with an allergy can check, and a count would call it complete.
    """
    wanted: tuple[MediaRole, ...] = ()
    for prefix, roles in required_media_for(base).items():
        if record.category.startswith(prefix):
            wanted = roles
            break

    held = {str(asset.role) for asset in record.media}
    findings = []
    for role in wanted:
        if str(role) in held:
            continue
        words = str(role).lower().replace("_", " ")
        article = "an" if words[0] in "aeiou" else "a"
        findings.append(Finding(
            check="required_media", subject=str(role),
            detail=f"{record.category} requires {article} {words} image and "
                   f"none is held",
            # Media has an owner, and it is not the supplier who sent the specs.
            system=next((a.system for a in record.media if a.system), None),
            basis="INT-001"))
    return findings


def media_status(record: Record, base) -> list[dict]:
    """Every image slot this category has, and whether it arrived.

    The same question ``required_media`` answers, in the shape a page renders
    rather than the shape a finding takes. Deliberately derived from the same
    catalog table: a strip that could disagree with the finding
    beside it would be a second opinion about what this product needs.

    A detail shot is listed and never required, so that "has imagery" and "has
    the imagery it needs" stay visibly different questions on the page as well
    as in the rules.

    ``held`` is a fact about the catalog, not about the disk. A record pointing
    at an asset the imaging system never delivered is exactly the state this is
    for, and the page reports it as missing whichever way it is missing.
    """
    required: tuple[MediaRole, ...] = ()
    for prefix, roles in required_media_for(base).items():
        if record.category.startswith(prefix):
            required = roles
            break

    by_role = {str(asset.role): asset for asset in record.media}
    slots: list[str] = [str(role) for role in required]
    for role in sorted(by_role):
        if role not in slots:
            slots.append(role)
    if str(MediaRole.DETAIL) not in slots:
        slots.append(str(MediaRole.DETAIL))

    # Who to chase when a slot is empty. Taken from whatever this product's
    # other imagery came through rather than guessed, and left null when the
    # record holds no imagery at all - "we do not know who owes this" is a
    # true answer and a made-up owner is not.
    carrier = next((a.system for a in record.media if a.system), None)

    rows = []
    for role in slots:
        asset = by_role.get(role)
        rows.append({
            "role": role,
            "required": role in {str(r) for r in required},
            "held": asset is not None,
            "id": getattr(asset, "id", None),
            "uri": getattr(asset, "uri", None),
            "alt_text": getattr(asset, "alt_text", None),
            "system": getattr(asset, "system", None) or carrier,
        })
    return rows


def contradicting_sources(record: Record, base) -> list[Finding]:
    """Two systems that both sent data and do not agree.

    Only detectable with the whole estate in view, which is why an estate of one
    could never produce it. A disagreement that precedence has already settled
    is reported as settled rather than as open: the record knows which value won
    and why, and re-raising it would ask a reviewer to re-decide something the
    policy decided.
    """
    findings = []
    for path, losers in sorted(record.superseded.items()):
        held = record.values.get(path)
        for loser in losers:
            if loser.get("value") == held:
                continue
            findings.append(Finding(
                check="contradicting_sources", subject=path,
                detail=f"{loser.get('system') or 'an unnamed system'} says "
                       f"{loser.get('value')!r}; the record holds {held!r} "
                       f"from {record.sources.get(path, 'an unnamed document')}",
                system=loser.get("system"), basis="POL-002"))
    return findings


def forbidden_content(record: Record, base) -> list[Finding]:
    """Content that may never appear, whatever a supplier sent.

    Deterministic and deliberately so. No wattage makes "cures asthma"
    publishable, so this cannot be a judgement about the product - it is a
    judgement about the sentence, and the sentence is either there or it is not.
    """
    findings = []
    for listing_id in sorted(record.listings):
        for asset_id in sorted(base.assets_by_listing.get(listing_id, [])):
            asset = base.assets.get(asset_id)
            if asset is None or not asset.text:
                continue
            haystack = f" {asset.text.lower()} "
            for phrase, why in FORBIDDEN_PHRASES:
                if f" {phrase} " in haystack or f" {phrase}." in haystack:
                    findings.append(Finding(
                        check="forbidden_content", subject=asset_id,
                        detail=f"{asset.field} contains {phrase!r} - {why}",
                        basis="INT-002"))
    return findings


def sale_permitted(record: Record, base) -> list[Finding]:
    """Has an authority ordered this product down?

    The one blocking finding that needs no reading. ``saleability`` in
    ``reading.py`` asks a model whether a mandate *covers* this product, which
    is a question about a regulation's scope and genuinely needs judgement.
    This asks whether a withdrawal notice has already been served on it, which
    is a fact in the record, and putting it behind a gateway would mean a
    withdrawn product read as merely incomplete whenever the gateway was down.

    Only an explicit denial blocks. A missing value is a gap
    ``applicable_attributes`` already reports; reading "we were never told" as
    "not permitted" would hold the whole catalogue the first time a supplier
    left the field empty.
    """
    if record.values.get(SALE_PERMITTED) is not False:
        return []
    return [Finding(
        check="sale_permitted", subject=SALE_PERMITTED,
        detail="a withdrawal notice is in force against this product; it may "
               "not be offered for sale on any channel, and no correction to "
               "its content changes that",
        severity=BLOCKING,
        system=record.system_for(SALE_PERMITTED),
        basis="REG-003")]


#: The seven, in the order a reviewer reads them: what is missing, then what is
#: wrong, then what may not be there at all - and, before any of it, whether
#: this may be sold.
DETERMINISTIC = (
    sale_permitted,
    applicable_attributes,
    mandatory_information,
    declared_types,
    required_media,
    contradicting_sources,
    forbidden_content,
)
