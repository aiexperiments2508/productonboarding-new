"""Is this product's information fit to publish?

    record    one product as the estate has left it, assembled once
    checks    the six decided by rules
    reading   the four that need prose read, where a model finds and cites
    verdict   counting findings into one of three words

The split between `checks` and `reading` is the whole architecture of this
surface, and it is the same split the rest of the system already makes: a model
interprets, deterministic code decides. Seven of the eleven questions have a
correct answer a rule can compute. Four require reading a regulation, the
retailer's own policy, a piece of internal documentation or a sentence, and on
those a model produces a *candidate with a citation* which a rule then admits or
drops.

Nothing here produces a score. See the note in `checks`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sc.readiness import checks as checks_mod
from sc.readiness import reading as reading_mod
from sc.readiness import record as record_mod
from sc.readiness import verdict as verdict_mod
from sc.readiness.checks import BLOCKING, Finding, Record  # noqa: F401
from sc.readiness.verdict import BLOCKED, READY, RETURN  # noqa: F401


def assess(entity_id: str, as_of: str | None = None, *,
           use_model: bool = True, run_id: str = "",
           include_record: bool = True, record=None, base=None) -> dict | None:
    """Assess one product. Returns None if the catalog has no such variant.

    The deterministic checks run first and always. The reading checks run after
    and may not run at all - which is reported rather than hidden, because an
    assessment that could not reach a model has found fewer things and calling
    that clean would be the most dangerous lie this surface could tell.

    ``use_model=False`` is not a degraded mode to apologise for. It is what the
    test suite exercises, what a venue with no network gets, and - since the
    product view started asking for it by default - what a reviewer sees first.

    ``include_record=False`` skips serialising the merged record. The product
    list keeps three scalars out of this and threw the rest away, which at four
    hundred variants was four hundred records built to be discarded.
    """
    from sc.state import baseline as baseline_mod

    base = base if base is not None else baseline_mod.get()
    if record is None:
        record = record_mod.build(entity_id, as_of, base=base)
    if record is None:
        return None

    findings: list[Finding] = []
    for check in checks_mod.DETERMINISTIC:
        findings.extend(check(record, base))

    complete = True
    if use_model:
        found, complete = _read(record, base, run_id)
        findings.extend(found)
    else:
        complete = False

    summary = verdict_mod.summarise(entity_id, findings, model_read=complete)
    # Which imagery this category needs, and which of it actually arrived.
    # Derived from the same table the required_media check binds on, so the
    # strip a reviewer looks at and the finding they act on cannot disagree.
    summary["media"] = checks_mod.media_status(record, base)
    if include_record:
        summary["record"] = record_mod.as_dict(record, base)
    return summary


def _read(record, base, run_id: str) -> tuple[list[Finding], bool]:
    """The four reading checks, run at the same time rather than in turn.

    They are independent: each retrieves its own passages and asks its own
    question. Run in series they were four network round trips a reviewer
    waited through one after another, for no reason other than a for loop.

    The fold is unchanged and is the point: one check failing to reach a model
    makes the *whole* assessment narrow. Reporting per-check would let a reader
    conclude the others were exhaustive, which they were not - they were merely
    reachable.

    Order comes from ``verdict.summarise``, which sorts, so which check happens
    to finish first cannot change what a reviewer reads.
    """
    checks = list(reading_mod.READING)
    if not checks:
        return [], True

    findings: list[Finding] = []
    complete = True
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = [pool.submit(check, record, base, run_id) for check in checks]
        for future in futures:
            try:
                found, ran = future.result()
            except Exception:  # noqa: BLE001 - a check that threw found nothing
                complete = False
                continue
            findings.extend(found)
            complete = complete and ran
    return findings, complete


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
