"""The check that runs before onboarding, and stops it.

A product arriving from a supplier raises two questions, and running them
together was the mistake this module exists to correct. *May we sell this at
all?* is a question about regulation and about the retailer's own policy, and
if the answer is no then nothing downstream matters - the record's wattage is
not interesting, filling its gaps is work thrown away, and proposing values for
a product that is going back to its supplier is worse than useless because
somebody has to read the proposals. *Is the record complete?* is the question
onboarding is actually about, and it only becomes worth asking once the first
one is settled.

``readiness`` already asks both. It runs eleven checks in one pass and counts
the findings, which is right for "is this fit to launch" and wrong for "should
this be onboarded at all", because the count treats a withdrawal notice and a
missing net-content the same way: as findings.

**So this is a partition, not a second implementation.** It reads one summary
``readiness.assess`` already produced and splits its findings in two by the
check that raised each one. There is no query here, no model, no clock and no
rule of its own - the same discipline ``mandatory_information`` follows against
the publish-time validator, for the same reason. A gate that re-derived
"unsaleable" would be a second answer to a question that already has one, and
the reviewer would be shown whichever ran.

**Why the gate is a set of check names and not a severity.** Three of the four
gate checks produce ``BLOCKING`` findings, and it would be tempting to make the
gate *be* ``severity == BLOCKING``. It must not be. ``checks.py`` reserves
BLOCKING for a regulation saying a thing may not be sold, and
``policy_conformance`` is deliberately ``OPEN`` - an organisational policy
breach stops onboarding without being a statement about legality. Reading the
severity would either drop the policy check from the gate or force it to claim
an authority it does not have. Naming the checks keeps both true at once.
"""

from __future__ import annotations

from sc.readiness.verdict import SALEABILITY_CHECKS

#: The retailer's own policy, read by ``reading.policy_conformance``. Named
#: apart from the saleability set because the two carry different authority and
#: the reason a product was stopped has to say which.
POLICY_CHECK = "policy_conformance"

#: Every check whose finding stops onboarding. ``sale_permitted`` (a withdrawal
#: notice on file), ``forbidden_content`` (a claim that may never appear),
#: ``saleability`` (a mandate the record breaches) and ``policy_conformance``.
GATE_CHECKS = frozenset(SALEABILITY_CHECKS | {POLICY_CHECK})

PASSED = "PASSED"
STOPPED = "STOPPED"

#: Who said so, worst first. A product stopped by both a regulation and a
#: policy is stopped by the regulation - that is the sentence the supplier gets
#: and the one that decides whether the answer can be argued with.
REGULATION = "REGULATION"
POLICY = "POLICY"

_AUTHORITY = {
    "sale_permitted": REGULATION,
    "saleability": REGULATION,
    "forbidden_content": REGULATION,
    POLICY_CHECK: POLICY,
}


def evaluate(summary: dict) -> dict:
    """Split one assessment into what stops onboarding and what it is about.

    ``summary`` is what ``readiness.assess`` returned. Pure: the same summary
    always gives the same verdict, and nothing here reads the database.

    ``checks_complete`` travels through unchanged and is the honest half of the
    answer. A gate that could not reach a model has run its two deterministic
    checks and neither of its reading ones, so a pass is *narrower* rather than
    cleaner - and a screen that showed an unqualified "compliant" off the back
    of it would be making exactly the claim this codebase spends its design
    avoiding.
    """
    findings = summary.get("findings") or []
    stopped = [f for f in findings if f.get("check") in GATE_CHECKS]
    data = [f for f in findings if f.get("check") not in GATE_CHECKS]

    # Worst first: a regulation outranks a policy, and the first line is what a
    # supplier reads.
    authorities = {_AUTHORITY.get(str(f.get("check"))) for f in stopped}
    authority = (REGULATION if REGULATION in authorities
                 else POLICY if POLICY in authorities
                 else None)

    return {
        "passed": not stopped,
        "outcome": STOPPED if stopped else PASSED,
        "authority": authority,
        "findings": stopped,
        "data_findings": data,
        "checks_complete": bool(summary.get("checks_complete")),
        "why": _sentence(stopped, authority),
    }


def _sentence(stopped: list[dict], authority: str | None) -> str:
    """Why this product is going back, in one line a supplier can act on.

    Names the document rather than the check. "It failed policy_conformance" is
    not something anybody outside this repository can do anything with; "POL-001
    says an allergen declaration is required before listing" is.
    """
    if not stopped:
        return ""
    lead = stopped[0]
    basis = str(lead.get("basis") or "").strip()
    detail = str(lead.get("detail") or "").strip()
    source = (f"{basis} " if basis else "")
    head = ("a regulation" if authority == REGULATION
            else "this organisation's own policy")
    rest = (f" and {len(stopped) - 1} other" +
            ("" if len(stopped) == 2 else "s") if len(stopped) > 1 else "")
    return (f"stopped by {head}: {source}{detail}{rest}".strip()
            if detail else f"stopped by {head}{rest}".strip())
