"""Proposing a value for a field nobody sent, and scoring the proposal.

Read-only. Nothing here writes a fact, a decision or a row; ``fix`` is still the
only writer, and it asks this module what to write.

Three sources feed one proposal:

*   a passage a model actually read, gated by ``_validated_fill`` exactly as
    ``enrich`` gates it - a fill naming a chunk that was not supplied is
    refused, so the corpus half cannot invent;
*   what the rest of the product and the rest of the category already hold;
*   what a person has decided about this field before.

``history`` gathers the second and third and needs no gateway, which is what
lets this produce a proposal at a venue with no network - and it is the path
the test suite exercises, since the gateway is pinned to a closed port
throughout.

**The confidence is computed here and is not the model's own number.**

That is the single most important line in this module, because the score is
what decides whether a value is written without a person looking at it. A
model's self-reported confidence is a fluent guess about its own fluency: it
moves with phrasing, it is uncalibrated between prompts, and it is exactly the
quantity a model is worst at. Handing it the autonomy gate would make the gate
the model's. So the self-report is *one input, discounted*, and everything else
in the score is a count of things already on file - which is checkable, is
stable between runs, and is what the reviewer is shown.

Two consequences follow and both are deliberate:

*   **A single source can never reach autonomy.** Not because the weights
    happen to fall short of the default threshold - a threshold is a knob, and
    a safety property that holds only while nobody turns it is not a safety
    property. ``supporters`` is counted here and ``decide.route`` refuses
    anything under ``MIN_SOURCES`` before it looks at the number at all.
*   **Disagreement costs more than agreement pays.** A sibling holding a
    different value is stronger evidence that the proposal is wrong than a
    category convention is that it is right.

**A safety-class attribute scores zero and is never proposed autonomously.**
Not "scores low" - zero, and routed to a person whatever else agrees. That rule
already holds in ``fixable`` (never a candidate) and in ``sim.engine``
(fail-closed under 0.9 at publish); this is the third place it has to hold, and
a plausible allergen list is still not an allergen list however many siblings
agree with it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sc.onboarding import fixable as fixable_mod
from sc.onboarding import history as history_mod

#: How much of a model's self-reported confidence survives. It is evidence that
#: a sentence was read and understood, and it is not a measurement - so it can
#: carry a proposal most of the way and never the whole way on its own.
CITED_TRUST = 0.72

#: What each corroborating prior adds. A sibling is the same product; a past
#: decision is a person who has answered this before; a category is a
#: convention, and conventions have exceptions.
AGREEMENT = {
    history_mod.SIBLING: 0.30,
    history_mod.APPROVAL: 0.26,
    history_mod.CATEGORY: 0.12,
}

#: What a prior holding a *different* value takes away. Larger than what the
#: same prior adds, because evidence that a proposal is wrong is worth more
#: than evidence that it is unremarkable.
DISAGREEMENT = {
    history_mod.SIBLING: 0.45,
    history_mod.APPROVAL: 0.35,
    history_mod.CATEGORY: 0.18,
}

#: What a prior alone is worth as a starting point, before corroboration. A
#: value read off the catalog with no document behind it is a good guess and is
#: not a reading, and it starts below the passage-backed path for that reason.
PRIOR_BASE = {
    history_mod.SIBLING: 0.55,
    history_mod.APPROVAL: 0.52,
    history_mod.CATEGORY: 0.30,
}

#: Where the proposed value itself came from.
FROM_PASSAGE = "PASSAGE"
FROM_PRIOR = "PRIOR"


@dataclass
class Suggestion:
    """One proposed value for one missing field, and why."""

    entity_id: str
    attribute_path: str
    label: str
    dtype: str
    unit: str | None
    safety_class: bool
    value: object
    confidence: float
    #: How many distinct sources support this value. Counted rather than
    #: derived from the score, because ``decide.route`` refuses an
    #: uncorroborated proposal before it looks at the number - and a rule that
    #: reads a confidence to find out how many things agreed would stop holding
    #: the day somebody changes a weight.
    supporters: int = 0
    #: The evidence the score was composed from, in the order it was weighed.
    #: This is what the category manager reads.
    reasons: list[dict] = field(default_factory=list)
    citation: dict | None = None
    source: str = FROM_PRIOR

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "attribute_path": self.attribute_path,
            "label": self.label,
            "dtype": self.dtype,
            "unit": self.unit,
            "safety_class": self.safety_class,
            "value": self.value,
            "confidence": round(self.confidence, 4),
            "supporters": self.supporters,
            "reasons": self.reasons,
            "citation": self.citation,
            "source": self.source,
        }


def for_gaps(gaps: list[dict], base, *, run_id: str = "",
             use_model: bool = True, overlay=None,
             include_safety_class: bool = False) -> list[Suggestion]:
    """A proposal per gap that anything at all can be said about.

    ``gaps`` are ``fixable.Gap`` dictionaries as the batch report carries them.
    A gap nothing supports produces no ``Suggestion`` at all rather than a
    zero-confidence one - the caller turns those into requests to the supplier,
    and a row saying "we propose nothing, at 0% confidence" is a queue item
    somebody has to read to learn nothing.
    """
    if not gaps:
        return []

    reads = _read_sources(gaps, base, run_id=run_id) if use_model else {}

    out: list[Suggestion] = []
    for gap in gaps:
        safety = bool(gap.get("safety_class"))
        if safety and not include_safety_class:
            # Held before anything is spent on it. `fixable` already refuses
            # these as candidates; this is the same rule at the next stage.
            continue
        found = _one(gap, base, reads.get(_key(gap)), overlay)
        if found is not None:
            out.append(found)
    return out


def _one(gap: dict, base, read: dict | None, overlay) -> Suggestion | None:
    """Compose one proposal from whatever the three sources produced."""
    entity_id = str(gap.get("entity_id") or "")
    path = str(gap.get("attribute_path") or "")
    priors = history_mod.priors_for(entity_id, path, base, overlay)

    if read is not None:
        value, source = read["value"], FROM_PASSAGE
    else:
        best = _strongest(priors)
        if best is None:
            return None
        value, source = best.value, FROM_PRIOR

    confidence, supporters, reasons = _score(value, read, priors)
    safety = bool(gap.get("safety_class"))
    if safety:
        # Zero rather than low. See the module docstring: the number is what
        # routes the proposal, and a safety-class value must never be routed
        # anywhere but at a person.
        confidence = 0.0
        reasons.append({
            "kind": "SAFETY", "agrees": False, "weight": 0.0, "support": 0,
            "detail": ("safety class: a value a model inferred rather than "
                       "read blocks publication instead of degrading it, so "
                       "this one is decided by a person whatever agrees with "
                       "it"),
        })

    return Suggestion(
        entity_id=entity_id, attribute_path=path,
        label=str(gap.get("label") or path), dtype=str(gap.get("dtype") or ""),
        unit=gap.get("unit"), safety_class=safety,
        value=value, confidence=confidence, supporters=supporters,
        reasons=reasons,
        citation=(read or {}).get("citation") or gap.get("citation"),
        source=source)


def _strongest(priors: list[history_mod.Prior]) -> history_mod.Prior | None:
    """The prior a proposal is built on when no passage was read.

    Ordered by what the source is worth rather than by how many rows it has: a
    single sibling of the same product beats forty members of a category, which
    is the whole reason the sources are named rather than pooled.
    """
    usable = [p for p in priors if _weighable(p)]
    if not usable:
        return None
    return max(usable, key=lambda p: (PRIOR_BASE.get(p.source, 0.0), p.support))


def _weighable(prior: history_mod.Prior) -> bool:
    """A category convention two products agree on is not a convention."""
    return not (prior.source == history_mod.CATEGORY
                and prior.support < history_mod.MIN_CATEGORY_SUPPORT)


def _score(value: object, read: dict | None,
           priors: list[history_mod.Prior]) -> tuple[float, int, list[dict]]:
    """The confidence, how many sources support it, and the parts it is made of.

    Deterministic given its inputs. Two callers with the same passage and the
    same catalog get the same number, which is what makes a threshold on it
    mean anything.

    The supporter count is returned rather than inferred, because it decides
    something the number does not: ``decide.route`` refuses an uncorroborated
    proposal whatever it scores.
    """
    reasons: list[dict] = []
    supporters = 0

    if read is not None:
        # Discounted, never taken at face value. See the module docstring.
        raw = float(read.get("confidence") or 0.0)
        score = max(0.0, min(1.0, raw)) * CITED_TRUST
        supporters += 1
        citation = read.get("citation") or {}
        reasons.append({
            "kind": FROM_PASSAGE, "agrees": True, "support": 1,
            "weight": round(score, 4), "value": value,
            "reference": citation.get("doc_id", ""),
            "detail": (f"read from {citation.get('doc_id') or 'a supplied passage'}"
                       + (f" — {citation.get('heading')}" if citation.get("heading") else "")
                       + f'; the model quoted "{_clip(read.get("quote"))}" and '
                       + f"rated itself {raw:.0%}, which counts for "
                       + f"{CITED_TRUST:.0%} of that here"),
        })
    else:
        base_prior = next((p for p in priors
                           if _weighable(p) and _same(p.value, value)), None)
        score = PRIOR_BASE.get(base_prior.source, 0.0) if base_prior else 0.0
        if base_prior is not None:
            supporters += 1
            reasons.append({
                "kind": base_prior.source, "agrees": True,
                "support": base_prior.support, "weight": round(score, 4),
                "value": base_prior.value, "reference": base_prior.reference,
                "detail": base_prior.detail + " — no document was read for this "
                          "field, so the proposal is what the catalog already "
                          "says rather than what a source states",
            })

    seen_base = {r.get("kind") for r in reasons}
    for prior in priors:
        if prior.source in seen_base and _same(prior.value, value):
            continue
        agrees = _same(prior.value, value)
        if not _weighable(prior):
            # Reported so the reviewer sees it, weighted at nothing - and in
            # *both* directions, which is the whole point. Two products out of
            # fifteen are not a category convention, so they are not evidence
            # that a value is right; letting the same two subtract when they
            # happen to disagree would be treating one body of evidence as too
            # thin to support a proposal and thick enough to sink it.
            reasons.append({
                "kind": prior.source, "agrees": agrees,
                "support": prior.support, "weight": 0.0,
                "value": prior.value, "reference": prior.reference,
                "detail": prior.detail,
            })
            continue
        table = AGREEMENT if agrees else DISAGREEMENT
        weight = table.get(prior.source, 0.0)
        if agrees:
            score += weight
            supporters += 1
        else:
            score -= weight
        reasons.append({
            "kind": prior.source, "agrees": agrees, "support": prior.support,
            "weight": round(weight if agrees else -weight, 4),
            "value": prior.value, "reference": prior.reference,
            "detail": prior.detail if agrees else (
                prior.detail + " — which is not the value proposed here"),
        })

    return max(0.0, min(1.0, score)), supporters, reasons


# ---------------------------------------------------------------------------
# The reading pass
# ---------------------------------------------------------------------------


def _read_sources(gaps: list[dict], base, *, run_id: str) -> dict:
    """Ask a model to read the retrieved passages, and keep only cited fills.

    Lifted out of ``fix.apply`` unchanged rather than reimplemented, and it has
    to stay that way: ``_validated_fill`` is the gate that refuses a value whose
    chunk was never supplied, and a second reader with its own idea of what
    counts as cited would be a second set of rules about what a model may
    assert. The first thing the two would disagree about is an allergen.

    With no gateway this returns nothing, and every proposal falls back to the
    priors. That is a narrower answer, not a guess.
    """
    from sc.graph import prompts
    from sc.graph.nodes import _validated_fill, fast_model
    from sc.llm.gateway import GatewayError, complete_json
    from sc.rag import retrieve

    entities = sorted({g["entity_id"] for g in gaps})
    paths = sorted({g["attribute_path"] for g in gaps})
    chunks = retrieve.search(" ".join(paths)[:200] or "attribute", top_k=6,
                             doc_types=fixable_mod.DOC_TYPES, entities=entities)
    supplied = retrieve.cite(chunks)
    known_chunks = {c["chunk_id"] for c in supplied}
    definitions = [{"path": g["attribute_path"], "dtype": g["dtype"],
                    "unit": g["unit"], "ordered": False} for g in gaps]

    try:
        reply, _usage = complete_json(
            [{"role": "system", "content": prompts.ENRICH_SYSTEM},
             {"role": "user", "content": prompts.enrich_user(
                 gaps, supplied, definitions)}],
            model=fast_model(), agent="enrich", run_id=run_id)
        proposed = reply.get("fills") or []
    except GatewayError:
        return {}

    wanted = {_key(g) for g in gaps}
    reads: dict[tuple[str, str], dict] = {}
    for fill in proposed:
        if not isinstance(fill, dict):
            continue
        row, _why = _validated_fill(base, fill, known_chunks)
        if row is None:
            continue
        key = (row["entity_id"], row["attribute_path"])
        if key in reads or key not in wanted:
            # A fill for something nobody asked about is not an answer to the
            # question, whatever else it is.
            continue
        reads[key] = {
            **row,
            "citation": next((c for c in supplied
                              if c["chunk_id"] == row["chunk_id"]), {}),
        }
    return reads


def _key(gap: dict) -> tuple[str, str]:
    return (str(gap.get("entity_id") or ""),
            str(gap.get("attribute_path") or ""))


def _same(a: object, b: object) -> bool:
    """Value equality that survives JSON round trips and list order."""
    return (json.dumps(a, sort_keys=True, default=str)
            == json.dumps(b, sort_keys=True, default=str))


def _clip(text: object, limit: int = 90) -> str:
    words = str(text or "").strip()
    return words if len(words) <= limit else words[:limit - 1] + "…"
