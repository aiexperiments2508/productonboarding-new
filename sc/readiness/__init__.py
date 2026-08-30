"""Is this product's information fit to publish?

    record    one product as the estate has left it, assembled once
    checks    the six decided by rules
    reading   the three that need prose read, where a model finds and cites
    verdict   counting findings into one of three words

The split between `checks` and `reading` is the whole architecture of this
surface, and it is the same split the rest of the system already makes: a model
interprets, deterministic code decides. Six of the nine questions have a correct
answer a rule can compute. Three require reading a regulation, a piece of
internal documentation or a sentence, and on those a model produces a *candidate
with a citation* which a rule then admits or drops.

Nothing here produces a score. See the note in `checks`.
"""

from __future__ import annotations

from sc.readiness import checks as checks_mod
from sc.readiness import reading as reading_mod
from sc.readiness import record as record_mod
from sc.readiness import verdict as verdict_mod
from sc.readiness.checks import BLOCKING, Finding, Record  # noqa: F401
from sc.readiness.verdict import BLOCKED, READY, RETURN  # noqa: F401


def assess(entity_id: str, as_of: str | None = None, *,
           use_model: bool = True, run_id: str = "") -> dict | None:
    """Assess one product. Returns None if the catalog has no such variant.

    The deterministic checks run first and always. The reading checks run after
    and may not run at all - which is reported rather than hidden, because an
    assessment that could not reach a model has found fewer things and calling
    that clean would be the most dangerous lie this surface could tell.

    ``use_model=False`` is not a degraded mode to apologise for. It is what the
    test suite exercises, and it is what a venue with no network gets.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    record = record_mod.build(entity_id, as_of)
    if record is None:
        return None

    findings: list[Finding] = []
    for check in checks_mod.DETERMINISTIC:
        findings.extend(check(record, base))

    complete = True
    if use_model:
        for check in reading_mod.READING:
            found, ran = check(record, base, run_id)
            findings.extend(found)
            # One check failing to reach a model makes the whole assessment
            # narrow. Reporting per-check would let a reader conclude the other
            # two were exhaustive, which they were not - they were merely
            # reachable.
            complete = complete and ran
    else:
        complete = False

    summary = verdict_mod.summarise(entity_id, findings, model_read=complete)
    summary["record"] = record_mod.as_dict(record, base)
    return summary


def assess_all(as_of: str | None = None, *, use_model: bool = False) -> list[dict]:
    """Every variant, assessed. What the Product 360 list renders.

    Defaults to skipping the reading checks: a list view assessing twenty
    products would make twenty model calls to render a page nobody has clicked
    into yet. The detail view asks for the full assessment.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    results = []
    for entity_id in sorted(base.variants):
        summary = assess(entity_id, as_of, use_model=use_model)
        if summary is not None:
            results.append(summary)
    return results
