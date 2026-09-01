"""The three checks that need somebody to read something.

Seven of the eleven checks are rules over the record. These four are not, and
it is
worth being precise about why, because "we used AI here" is the kind of claim
that gets waved at problems it does not fit.

*   **Saleability.** A regulation is prose. Whether `REG-001`'s mandatory
    particulars are met by a snack bar is a reading question; no table encodes
    it, and writing one would be transcribing the regulation into code where it
    would immediately start drifting from the document.
*   **Semantic staleness.** A sentence can become untrue without any rule
    noticing - the copy calls a product economical in a paragraph that names no
    figure, so no literal check fires and no claim predicate binds.
*   **Internal contradiction.** Our own documentation says things about
    categories that no attribute captures.
*   **Policy conformance.** The retailer's own handling policy is prose too,
    and it binds differently from a regulation: it says what this organisation
    will not put on a shelf, not what the law forbids. Which is why a finding
    here is ``OPEN`` and never ``BLOCKING`` - see the note on the function.

The bounds are the same in all four, and they are what make this safe:

**A model produces a candidate finding with a citation. A rule decides.** A
candidate that cites nothing retrievable is dropped - not softened, not flagged
low-confidence, dropped - because a finding a reviewer cannot open is a finding
they cannot check, and an unopenable finding against a product is worse than a
missed one.

**Confidence is never a gate.** Nothing here admits a finding because a model
said 0.9. The gate is the citation, which is checkable.

**Every one degrades.** With no gateway they return nothing and say so, and the
assessment reports that it ran narrow. Reporting a narrower result as a clean
one is the single most dangerous thing this surface could do.
"""

from __future__ import annotations

import json

from sc.llm import gateway
from sc.llm.gateway import GatewayError
from sc.rag import retrieve
from sc.readiness.checks import BLOCKING, Finding, Record

#: How many passages each reading check is given. Small on purpose: a check
#: reading twenty passages produces findings a reviewer cannot trace back, and
#: the retrieval is already scoped to the product.
PASSAGES = 4

SALEABILITY_SYSTEM = (
    "You are checking whether a market authority's requirements are met by a "
    "product record.\n"
    "You are given the requirement passages and the record. Report only "
    "requirements the record VIOLATES.\n"
    "Every finding must quote the passage id it rests on. A finding you cannot "
    "cite must be omitted - it is better to miss one than to report one nobody "
    "can check.\n"
    "Do not judge quality, wording or completeness. Only whether a stated "
    "requirement is unmet.\n"
    'Reply as JSON: {"findings": [{"requirement": str, "why": str, '
    '"citation": str}]}'
)

CONTRADICTION_SYSTEM = (
    "You are checking a product record against the retailer's own internal "
    "documentation.\n"
    "Report only places where the record CONTRADICTS the documentation. "
    "Silence is the correct answer for a record that merely says less than the "
    "documentation covers.\n"
    "Every finding must quote the passage id it rests on and name the "
    "attribute or asset it concerns.\n"
    'Reply as JSON: {"findings": [{"subject": str, "why": str, '
    '"citation": str}]}'
)

POLICY_SYSTEM = (
    "You are checking a product record against the retailer's own published "
    "policy.\n"
    "Report only policies the record BREACHES. A policy the record simply says "
    "nothing about is not a breach, and reporting it as one would hold every "
    "product the policy has an opinion on.\n"
    "Every finding must quote the passage id it rests on and name the "
    "attribute, asset or product property it concerns. A finding you cannot "
    "cite must be omitted.\n"
    'Reply as JSON: {"findings": [{"subject": str, "why": str, '
    '"citation": str}]}'
)

SEMANTIC_SYSTEM = (
    "You are checking whether prepared marketing copy has become untrue for a "
    "product, given the values the record now holds.\n"
    "Report only sentences whose MEANING is now wrong. A sentence quoting a "
    "superseded number is already caught by a rule and is not your job; yours "
    "is the sentence that is wrong without naming a figure at all.\n"
    "Every finding must name the asset id it concerns.\n"
    'Reply as JSON: {"findings": [{"asset_id": str, "why": str}]}'
)


def _record_lines(record: Record, base) -> str:
    lines = [f"Product {record.product_id} variant {record.entity_id}, "
             f"category {record.category}"
             + (" (regulated)" if record.regulated else "")]
    for path, value in sorted(record.values.items()):
        definition = base.attr_defs.get(path)
        label = definition.label if definition else path
        lines.append(f"- {label} ({path}) = {value!r}")
    roles = sorted(str(a.role) for a in record.media)
    lines.append(f"- imagery held: {', '.join(roles) if roles else 'none'}")
    return "\n".join(lines)


def _passages(query: str, record: Record, doc_types: list[str]) -> list:
    return retrieve.for_product(query, record.entity_id, top_k=PASSAGES,
                                doc_types=doc_types,
                                related=[record.product_id])


def _render(passages: list) -> str:
    return "\n\n".join(f"[{p.chunk.id}] {p.chunk.text}" for p in passages)


def _cited(candidates: list[dict], passages: list) -> list[tuple]:
    """Keep only candidates that cite a passage we actually retrieved.

    The gate, and the whole reason this is safe to hand to a model. A citation
    naming something that was never in front of it is a fabrication, and it is
    the failure mode that looks most like success: a specific, confident,
    checkable-sounding finding pointing at nothing.
    """
    by_chunk = {p.chunk.id: p.chunk for p in passages}
    by_doc = {p.chunk.doc_id: p.chunk for p in passages}
    kept: list[tuple] = []
    for candidate in candidates:
        cite = str(candidate.get("citation") or "").strip()
        chunk = by_chunk.get(cite) or by_doc.get(cite)
        if chunk is None:
            # A citation naming a retrieved document inside a longer string,
            # which is how a model usually writes one.
            chunk = next((c for doc_id, c in by_doc.items()
                          if doc_id and doc_id in cite), None)
        if chunk is None:
            continue
        kept.append((candidate, chunk))
    return kept


def _findings_of(reply: object) -> list[dict]:
    """Whatever the model returned, as a list of dicts.

    Defensive because the evaluation harness measured this exact failure on
    this exact gateway: a third of replies came back as a bare array where an
    object was required. A reply shaped differently is not a reason to lose a
    check.
    """
    if isinstance(reply, dict):
        items = reply.get("findings")
    elif isinstance(reply, list):
        items = reply
    elif isinstance(reply, str):
        try:
            return _findings_of(json.loads(reply))
        except Exception:  # noqa: BLE001 - an unparseable reply is no findings
            return []
    else:
        items = None
    return [i for i in (items or []) if isinstance(i, dict)]


def _model() -> str:
    from sc.graph.nodes import fast_model

    return fast_model()


def saleability(record: Record, base,
                run_id: str = "") -> tuple[list[Finding], bool]:
    """Does a mandate forbid selling this?

    The only check that can block. A finding here says the listing may not
    lawfully be sold, which is categorically different from saying it would be
    a poor listing - and it is why blocking is never reached by accumulating
    quality findings.
    """
    passages = _passages(
        f"mandatory requirements for {record.category} saleability",
        record, ["REGULATION"])
    if not passages:
        return [], True

    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": SALEABILITY_SYSTEM},
             {"role": "user",
              "content": ("Requirements:\n" + _render(passages)
                          + "\n\nRecord:\n" + _record_lines(record, base))}],
            model=_model(), agent="readiness.saleability", run_id=run_id)
    except GatewayError:
        return [], False

    findings = []
    for candidate, chunk in _cited(_findings_of(reply), passages):
        findings.append(Finding(
            check="saleability",
            subject=str(candidate.get("requirement") or chunk.doc_id)[:120],
            detail=str(candidate.get("why") or "")[:300],
            # Set here rather than by the model. The model found the passage;
            # the rule that a regulation outranks a preference is ours.
            severity=BLOCKING,
            basis=chunk.doc_id, citation=chunk.id))
    return findings, True


def internal_contradiction(record: Record, base,
                           run_id: str = "") -> tuple[list[Finding], bool]:
    """Does the record contradict the retailer's own documentation?"""
    passages = _passages(
        f"internal requirements for onboarding {record.category}",
        record, ["INTERNAL"])
    if not passages:
        return [], True

    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": CONTRADICTION_SYSTEM},
             {"role": "user",
              "content": ("Documentation:\n" + _render(passages)
                          + "\n\nRecord:\n" + _record_lines(record, base))}],
            model=_model(), agent="readiness.internal", run_id=run_id)
    except GatewayError:
        return [], False

    findings = []
    for candidate, chunk in _cited(_findings_of(reply), passages):
        subject = str(candidate.get("subject") or chunk.doc_id)[:120]
        findings.append(Finding(
            check="internal_contradiction",
            subject=subject,
            detail=str(candidate.get("why") or "")[:300],
            system=record.system_for(subject),
            basis=chunk.doc_id, citation=chunk.id))
    return findings, True


def policy_conformance(record: Record, base,
                       run_id: str = "") -> tuple[list[Finding], bool]:
    """Does the record breach the retailer's own policy?

    The fourth reading check, and the one that made the onboarding gate
    possible. ``saleability`` asks whether a market authority forbids selling
    this; this asks whether *we* have said we will not sell it like this -
    allergen handling, how a correction must be treated, when something is
    escalated, what a withdrawal notice obliges. Both are prose, both need
    reading, and they are not the same question.

    **A finding here is ``OPEN`` and never ``BLOCKING``, deliberately.**
    ``checks.py`` reserves BLOCKING for a regulation saying a thing may not be
    sold, and quietly widening it to cover internal policy would make every
    statement of preference a statement about legality. The onboarding gate in
    ``sc.onboarding.gate`` stops a product on a policy breach anyway - stopping
    onboarding and declaring something unlawful are different acts, and keeping
    them different is the whole reason the gate reads a set of check names
    rather than a severity.
    """
    passages = _passages(
        f"policy for handling {record.category} product information",
        record, ["POLICY"])
    if not passages:
        return [], True

    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": POLICY_SYSTEM},
             {"role": "user",
              "content": ("Policy:\n" + _render(passages)
                          + "\n\nRecord:\n" + _record_lines(record, base))}],
            model=_model(), agent="readiness.policy", run_id=run_id)
    except GatewayError:
        return [], False

    findings = []
    for candidate, chunk in _cited(_findings_of(reply), passages):
        subject = str(candidate.get("subject") or chunk.doc_id)[:120]
        findings.append(Finding(
            check="policy_conformance",
            subject=subject,
            detail=str(candidate.get("why") or "")[:300],
            system=record.system_for(subject),
            basis=chunk.doc_id, citation=chunk.id))
    return findings, True


def semantic_copy(record: Record, base,
                  run_id: str = "") -> tuple[list[Finding], bool]:
    """Has a sentence become untrue without any rule noticing?

    The narrow case a model is genuinely needed for: copy saying a product is
    quiet, economical or suitable for a use, in a paragraph naming no number -
    so no literal check fires and no claim predicate binds, and the sentence is
    still wrong.

    Confirmed against the record rather than trusted. A flag naming an asset
    this product does not have is dropped, which is the same gate the cited
    checks use for the same reason.
    """
    assets = []
    for listing_id in sorted(record.listings):
        for asset_id in sorted(base.assets_by_listing.get(listing_id, [])):
            asset = base.assets.get(asset_id)
            if asset is not None and asset.text:
                assets.append(asset)
    if not assets:
        return [], True

    copy = "\n".join(f"[{a.id}] ({a.field}) {a.text}" for a in assets)
    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": SEMANTIC_SYSTEM},
             {"role": "user",
              "content": ("Record:\n" + _record_lines(record, base)
                          + "\n\nCopy:\n" + copy)}],
            model=_model(), agent="readiness.semantic", run_id=run_id)
    except GatewayError:
        return [], False

    held = {a.id: a for a in assets}
    findings = []
    for candidate in _findings_of(reply):
        asset = held.get(str(candidate.get("asset_id") or ""))
        if asset is None:
            # An asset this product does not have. Same gate as a missing
            # citation, same reasoning.
            continue
        findings.append(Finding(
            check="semantic_copy", subject=asset.id,
            detail=str(candidate.get("why") or "")[:300],
            basis=f"{asset.listing_id}:{asset.field}", citation=asset.id))
    return findings, True


#: The four, each returning its findings and whether it actually ran. The flag
#: is not decoration: an assessment that could not reach a model has found fewer
#: things, and the caller has to be able to say so rather than report a narrower
#: result as a clean one.
READING = (saleability, internal_contradiction, policy_conformance,
           semantic_copy)
