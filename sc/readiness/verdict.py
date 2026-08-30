"""Counting findings into an outcome.

This module is deliberately dull, and its dullness is the point. It is the last
step before a product is either released downstream or sent back, and it is
arithmetic: count the findings by severity, apply two rules, return one of three
words.

Nothing here consults a model. A model may write the covering note a reviewer
reads - that is prose, and prose is what models are for - but the note is
produced *after* the verdict and cannot reach it. If a note could change an
outcome, the outcome would be the model's, and the whole argument this system
makes about bounded AI would be untrue at the one point it matters most.

There is no threshold, because there is no score. See ``checks.py``.
"""

from __future__ import annotations

from sc.readiness.checks import BLOCKING, Finding

#: The closed set. A fourth outcome is a fourth thing a downstream consumer has
#: to handle, and every candidate for one so far has been a shade of the second.
READY = "READY_TO_LAUNCH"
RETURN = "RETURN_TO_SOURCE"
BLOCKED = "BLOCKED"

#: Checks whose findings say a listing may not lawfully be sold, as opposed to
#: saying it would be a poor listing. Only these can block, and only ever
#: individually: blocking is a statement about legality, and reaching it by
#: accumulating quality findings would make it a judgement.
SALEABILITY_CHECKS = frozenset({"saleability", "forbidden_content"})


def decide(findings: list[Finding]) -> str:
    """The outcome, from the findings alone.

    Reproducible from its input and from nothing else - no clock, no
    confidence, no note. Two callers with the same findings get the same word.
    """
    if any(f.severity == BLOCKING or f.check in SALEABILITY_CHECKS
           for f in findings):
        return BLOCKED
    return RETURN if findings else READY


def summarise(entity_id: str, findings: list[Finding], *,
              model_read: bool = True) -> dict:
    """The verdict and everything a reviewer needs to act on it.

    Findings are returned sorted so that two assessments of one record read the
    same way, and grouped by the system that has to fix them - because a return
    that says "the data is incomplete" is not actionable and one that names the
    data pool is.

    ``model_read`` says whether the reading checks ran. An assessment that could
    not reach a model has found fewer things, and reporting that as a clean
    result would be the most dangerous lie this system could tell.
    """
    ordered = sorted(findings, key=lambda f: f.sort_key())
    outcome = decide(ordered)

    by_system: dict[str, list[dict]] = {}
    for finding in ordered:
        by_system.setdefault(finding.system or "unattributed", []).append(
            finding.as_dict())

    return {
        "entity_id": entity_id,
        "verdict": outcome,
        "ready": outcome == READY,
        "findings": [f.as_dict() for f in ordered],
        "blocking": [f.as_dict() for f in ordered if f.severity == BLOCKING
                     or f.check in SALEABILITY_CHECKS],
        # Who has to fix what. The estate's whole reason for existing is that
        # this question has an answer.
        "by_system": by_system,
        "checks_complete": model_read,
        "caveat": None if model_read else (
            "assessed without a model: the checks that read regulation, "
            "internal documentation and copy meaning did not run, so this is a "
            "narrower result rather than a clean one"),
    }
