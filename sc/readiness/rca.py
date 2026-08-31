"""Why is this finding here, and who has to fix it.

A readiness finding says what is wrong. It already names the system that
carried the value, because "the data is incomplete" is not something anybody
can act on and "the data pool sent net content in its own vocabulary" is. What
it does not say is *why that system does this* and *what the owning team has to
do about it*, and a reviewer looking at eleven findings is otherwise being
asked to know the estate by heart.

So this joins three things the system already holds, and adds no fourth:

1.  **The finding** - its check, its subject, the system it names, the rule or
    document it rests on.
2.  **That system's declared behaviour.** ``sc.estate.manifest`` says what each
    system is for, who owns it and how it misbehaves; ``sc.estate.defects``
    says what each defect kind means. This leg alone answers the question with
    no model involved, which is why the surface still works with the gateway
    off.
3.  **A passage from the corpus**, retrieved for this product.

The bound is the one the rest of this package works under, and it is not
relaxed here just because the output is prose: **a model produces a candidate
with a citation; a rule decides.** The gate is ``reading._cited`` - imported,
not reimplemented, because two copies of the rule that decides what counts as
evidence is two answers to the only question that matters. A candidate citing
nothing retrievable is dropped and the deterministic account is used instead.

**This runs after the verdict and cannot reach it.** ``verdict.decide`` counts
findings; nothing here is a finding. If an explanation could change an outcome
the outcome would be the model's, and the argument this system makes about
bounded AI would be untrue at the one point somebody acts on it.
"""

from __future__ import annotations

from sc.estate import defects as defects_mod
from sc.estate.manifest import BY_ID
from sc.llm import gateway
from sc.llm.gateway import GatewayError
from sc.rag import retrieve
from sc.readiness import reading as reading_mod

#: How many findings get an explanation. `explain` puts whatever blocks the
#: product first, so this is the top of the list rather than an arbitrary slice
#: - and a model call per finding on a twelve-finding product is twelve calls
#: to fill a panel nobody scrolls to the bottom of.
DEFAULT_LIMIT = 3

SYSTEM_PROMPT = (
    "You explain why a data-quality finding happened, for a reviewer deciding "
    "whether to send a product back to its supplier.\n"
    "You are given one finding, the declared behaviour of the system that "
    "carried the value, and passages from internal documentation.\n"
    "Use ONLY those. Do not introduce a cause, a number, a system or a remedy "
    "that is not in one of them.\n"
    "Say what most likely happened upstream, then what the named team has to "
    "do. Two sentences each at most. No speculation about intent.\n"
    "Cite the passage id you used.\n"
    'Reply as JSON: {"narrative": str, "remedy": str, "citation": str}'
)

#: Which declared defect each deterministic check tends to be the symptom of.
#: A mapping between two closed sets, so it can be wrong about which of a
#: system's known failure modes fired and cannot invent a new one.
DEFECT_BY_CHECK: dict[str, str] = {
    "applicable_attributes": "MISSING_MANDATORY",
    "mandatory_information": "MISSING_MANDATORY",
    "declared_types": "WRONG_TYPE",
    "required_media": "MISSING_MEDIA",
    "contradicting_sources": "CONTRADICTS_SOURCE",
}


def _likely_defect(finding: dict, system) -> str:
    """Which of this system's declared defects the finding looks like.

    Constrained to the system's *own* declared set. Returns "" when it declares
    none, and that is a real answer rather than a gap: ``label-artwork``
    introduces no defects, so a finding against it is a finding about the
    record and not about the carrier.
    """
    if system is None or not system.defects:
        return ""
    declared = {str(d) for d in system.defects}
    wanted = DEFECT_BY_CHECK.get(finding.get("check", ""), "")
    if wanted in declared:
        return wanted
    # No match. Name one this system actually declares rather than none - but
    # only ever one it declares.
    return sorted(declared)[0]


def _template(finding: dict, system, defect: str, passage) -> dict:
    """The explanation without a model.

    Assembled from the manifest's own words, so what degrades is the prose and
    never the grounding: the account a reviewer reads offline rests on exactly
    the same legs as the one they read online.
    """
    owner = getattr(system, "owner", None)
    carrier = getattr(system, "title", None) or finding.get("system") or "A system"
    explanation = defects_mod.explain(defect) if defect else ""
    narrative = (
        f"{carrier} carried this value. {explanation}" if explanation else
        f"{carrier} carried this value and declares no failure mode of its "
        f"own, so the gap is in the record rather than in the delivery."
    )
    subject = finding.get("subject") or "the value"
    return {
        "narrative": narrative.strip(),
        "remedy": (f"{owner or 'The team that owns the carrier'} has to resend "
                   f"{subject} for this product. Until it arrives the record "
                   f"stays as it is."),
        "citation": passage.chunk.id if passage else finding.get("citation", ""),
        "source": passage.chunk.doc_id if passage else "",
        "written_by_model": False,
        "note": "explained without a model, from the same declared behaviour "
                "and the same passage",
    }


def _explain_one(finding: dict, record, *, use_model: bool,
                 run_id: str = "") -> dict:
    system = BY_ID.get(finding.get("system") or "")
    defect = _likely_defect(finding, system)

    passages = retrieve.for_product(
        f"{finding.get('check', '')} {finding.get('subject', '')} "
        f"{finding.get('detail', '')}",
        record.entity_id, top_k=3, related=[record.product_id])
    passage = passages[0] if passages else None

    facts = {
        "check": finding.get("check", ""),
        "subject": finding.get("subject", ""),
        "severity": finding.get("severity", ""),
        "detail": finding.get("detail", ""),
        "system": finding.get("system"),
        "owner": getattr(system, "owner", None),
        "likely_defect": defect or None,
        "defect_explanation": defects_mod.explain(defect) if defect else "",
        "defect_rate": getattr(system, "defect_rate", None),
        "basis": finding.get("basis", ""),
    }

    if not use_model or not passages:
        return {**facts, **_template(finding, system, defect, passage)}

    behaviour = (
        f"System: {getattr(system, 'title', None) or finding.get('system') or 'unknown'}\n"
        f"Owned by: {getattr(system, 'owner', None) or 'unknown'}\n"
        f"What it is for: {getattr(system, 'why', '')}\n"
        f"Declared failure modes: "
        f"{', '.join(sorted(str(d) for d in getattr(system, 'defects', ()))) or 'none'}"
    )
    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user",
              "content": (f"Finding: {finding.get('check')} on "
                          f"{finding.get('subject')}\n"
                          f"Detail: {finding.get('detail')}\n\n"
                          f"{behaviour}\n\n"
                          f"Documentation:\n{reading_mod._render(passages)}")}],
            model=reading_mod._model(), agent="readiness.rca", run_id=run_id)
    except GatewayError:
        return {**facts, **_template(finding, system, defect, passage)}

    if not isinstance(reply, dict):
        return {**facts, **_template(finding, system, defect, passage)}

    # The same gate the reading checks use. An explanation citing a passage
    # nobody retrieved is the failure mode that looks most like success.
    kept = reading_mod._cited([reply], passages)
    narrative = str(reply.get("narrative") or "").strip()
    remedy = str(reply.get("remedy") or "").strip()
    if not kept or not narrative or not remedy:
        return {**facts, **_template(finding, system, defect, passage)}

    _, chunk = kept[0]
    return {**facts,
            "narrative": narrative[:400],
            "remedy": remedy[:400],
            "citation": chunk.id,
            "source": chunk.doc_id,
            "written_by_model": True,
            "note": ""}


def explain(entity_id: str, summary: dict, record, *, use_model: bool = True,
            limit: int = DEFAULT_LIMIT, run_id: str = "") -> dict:
    """Root causes for the worst findings on one product.

    Returns no causes for a product with nothing open. A page offering to
    explain a clean record would be offering to explain nothing.
    """
    findings = summary.get("findings") or []
    # Blocking first, and taken from `summary["blocking"]` rather than from the
    # sort order. `Finding.sort_key` promotes severity BLOCKING, but a
    # saleability finding blocks the product at severity OPEN - so a blocked
    # record whose other finding happens to sort earlier alphabetically would
    # have had the cosmetic one explained and the disqualifying one cut off by
    # the limit. The verdict already knows which findings block; this asks it
    # rather than re-deriving it.
    blocking = summary.get("blocking") or []
    keyed = {(f.get("check"), f.get("subject")) for f in blocking}
    ordered = blocking + [f for f in findings
                          if (f.get("check"), f.get("subject")) not in keyed]
    wanted = ordered[:max(0, limit)]
    return {
        "entity_id": entity_id,
        "verdict": summary.get("verdict"),
        "checks_complete": summary.get("checks_complete", False),
        "causes": [_explain_one(f, record, use_model=use_model, run_id=run_id)
                   for f in wanted],
        # What was left unexplained, said out loud. A panel showing three of
        # eleven without saying so reads as a product with three problems.
        "not_explained": max(0, len(findings) - len(wanted)),
        "unattributed": sum(1 for f in findings if not f.get("system")),
    }
