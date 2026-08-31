"""Counting verdicts into the answer somebody came for.

``verdict`` decides one product. This tallies many, and the question it answers
is the one the Product 360 screen exists for: for this window, these suppliers
and this category, how much was fit to push downstream and how much had to go
back to the source to be corrected.

Deliberately separate from ``verdict``, and deliberately arithmetic. It reads
assessments that have already been made and adds nothing to them - no second
opinion, no weighting, no threshold. If this module could change what a product
counts as, there would be two answers to "is this ready" and the one on the
dashboard would be the one people quoted.

**The narrow-assessment rule survives aggregation, and that is the whole care
in this file.** ``checks_complete`` is false for the summary if it is false for
*any* product in it. Seventy-one products reported as clear, when they were
cleared by six checks of nine and the summary did not say so, is the same lie
as one product reported that way - and it is a more dangerous one, because a
number on a dashboard gets repeated by people who never saw the product.
"""

from __future__ import annotations

from sc.readiness.verdict import BLOCKED, READY, RETURN

#: The buckets, in the words the screen uses. "Cleared" is about what happens
#: next - it goes downstream - rather than about a score, because there is no
#: score.
BUCKETS = {READY: "cleared", RETURN: "returned", BLOCKED: "blocked"}


def _blank() -> dict:
    return {"assessed": 0, "cleared": 0, "returned": 0, "blocked": 0}


def _add(bucket: dict, verdict: str) -> None:
    bucket["assessed"] += 1
    name = BUCKETS.get(verdict)
    if name:
        bucket[name] += 1


def tally(assessments: list[tuple[dict, dict]], base) -> dict:
    """Count assessments into totals, and into who is responsible.

    ``assessments`` is a list of ``(row, summary)`` where ``row`` carries the
    product's supplier and category and ``summary`` is what ``assess``
    returned. Pure: no queries, no model, no clock.
    """
    totals = _blank()
    by_supplier: dict[str, dict] = {}
    by_category: dict[str, dict] = {}
    by_system: dict[str, dict] = {}
    by_check: dict[str, dict] = {}
    complete = True

    for row, summary in assessments:
        verdict = summary.get("verdict", "")
        _add(totals, verdict)
        complete = complete and bool(summary.get("checks_complete"))

        supplier = row.get("supplier") or "unattributed"
        _add(by_supplier.setdefault(supplier, _blank()), verdict)

        # Two levels of the taxonomy - the granularity a person filters at.
        branch = ".".join(str(row.get("category") or "").split(".")[:2])
        _add(by_category.setdefault(branch or "uncategorised", _blank()), verdict)

        # Who has to fix it. The estate's whole argument is that this question
        # has an answer, and this is where it pays off at population scale.
        seen_systems: set[str] = set()
        for finding in summary.get("findings") or []:
            system = finding.get("system") or "unattributed"
            entry = by_system.setdefault(
                system, {"system": system, "products": 0, "findings": 0})
            entry["findings"] += 1
            if system not in seen_systems:
                entry["products"] += 1
                seen_systems.add(system)

            check = finding.get("check") or "unknown"
            row_check = by_check.setdefault(
                check, {"check": check, "products": 0, "findings": 0})
            row_check["findings"] += 1
        for check in {f.get("check") for f in summary.get("findings") or []}:
            if check:
                by_check[check]["products"] += 1

    names = {n.id: n.name for n in base.catalog.nodes}
    owners = _owners()

    return {
        **totals,
        "checks_complete": complete,
        "caveat": None if complete else (
            "some products in this window were assessed without a model: the "
            "checks that read regulation, internal documentation and copy "
            "meaning did not run on them, so this is a narrower count rather "
            "than a cleaner one"),
        "by_supplier": [{"supplier": s, "name": names.get(s, s), **counts}
                        for s, counts in sorted(by_supplier.items())],
        "by_category": [{"prefix": c, "label": c.replace(".", " / "), **counts}
                        for c, counts in sorted(by_category.items())],
        "by_system": sorted(
            ({**entry, "owner": owners.get(entry["system"])}
             for entry in by_system.values()),
            key=lambda e: (-e["findings"], e["system"])),
        "by_check": sorted(by_check.values(),
                           key=lambda e: (-e["findings"], e["check"])),
    }


def _owners() -> dict[str, str]:
    """Which team owns each carrier, from the manifest and nowhere else."""
    from sc.estate.manifest import SYSTEMS

    return {system.id: system.owner for system in SYSTEMS}
