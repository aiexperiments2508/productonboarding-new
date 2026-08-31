"""Which gaps a model could fill, decided without asking one.

The report has to answer "how many of these can be fixed automatically", and
the honest answer has two parts that must not be run together.

**What can be decided deterministically.** ``enrich`` fills a gap only from a
passage it was supplied, and ``sc.graph.nodes._validated_fill`` drops any fill
whose ``chunk_id`` is not in that supplied set. So the negative is *sound*: if
retrieval finds no passage for a gap, ``enrich`` provably cannot fill it, and
no model has to be asked to know that. That is a real answer, it costs no
gateway traffic, and it is what the report loads with.

**What cannot.** Whether a passage that exists actually *states* the value is a
reading question, and only a model can answer it. So a candidate is reported as
**a source passage is on file**, never as "the AI can fill this". Running the
model turns each candidate into a proposed fill with its citation, or into a
supplier request - and the two counts will differ. That difference is the
truthful and interesting number, and hiding it would be the same lie
``checks_complete`` exists to prevent.

**Safety-class attributes are never candidates.** Not "candidates that need
approval" - not candidates. ``enrich``'s own docstring says why: a plausible
allergen list is not an allergen list, and it gets printed on a label and read
by somebody who needs it to be right. They are counted separately so the
exclusion is visible rather than silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Which readiness checks describe a gap a value could close. A finding from
#: any other check is a different kind of problem: a forbidden phrase is not
#: fixed by supplying a value, and a withdrawal notice is not fixed at all.
GAP_CHECKS = frozenset({"applicable_attributes", "mandatory_information"})

#: What a candidate is retrieved against. The same three document classes
#: ``enrich`` searches, because a candidate found in a corpus ``enrich`` does
#: not read is a candidate it cannot use.
DOC_TYPES = ["STANDARD", "CHANNEL", "POLICY"]

CANDIDATE = "CANDIDATE"
NO_SOURCE = "NO_SOURCE"
SAFETY_HELD = "SAFETY_HELD"


@dataclass
class Gap:
    """One missing value, and whether anything could close it."""

    entity_id: str
    attribute_path: str
    label: str
    dtype: str
    unit: str | None
    safety_class: bool
    state: str
    why: str = ""
    citation: dict | None = None
    #: Set only after the reading pass has run.
    proposed: object = None
    confidence: float | None = None

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "attribute_path": self.attribute_path,
            "label": self.label,
            "dtype": self.dtype,
            "unit": self.unit,
            "safety_class": self.safety_class,
            "state": self.state,
            "why": self.why,
            "citation": self.citation,
            "proposed": self.proposed,
            "confidence": self.confidence,
        }


@dataclass
class Assessment:
    """The gaps for one batch, bucketed."""

    gaps: list[Gap] = field(default_factory=list)

    @property
    def candidates(self) -> list[Gap]:
        return [g for g in self.gaps if g.state == CANDIDATE]

    def counts(self) -> dict:
        held = [g for g in self.gaps if g.state == SAFETY_HELD]
        none = [g for g in self.gaps if g.state == NO_SOURCE]
        return {
            "gaps": len(self.gaps),
            "candidates": len(self.candidates),
            "products": len({g.entity_id for g in self.candidates}),
            "held_safety": len(held),
            "no_source": len(none),
            "read": False,
            "label": ("gaps with a source passage on file. Whether the passage "
                      "states the value is a reading question, and until the "
                      "sources are read this is what could be filled rather "
                      "than what will be"),
        }


def gaps_for(entity_id: str, findings: list[dict], base) -> list[dict]:
    """The missing values a product's findings name.

    Read off the findings the checks already produced rather than recomputed,
    so the report cannot disagree with the verdict beside it about what is
    missing.
    """
    out = []
    seen: set[str] = set()
    for finding in findings:
        if finding.get("check") not in GAP_CHECKS:
            continue
        path = str(finding.get("subject") or "")
        definition = base.attr_defs.get(path)
        if definition is None or path in seen:
            continue
        seen.add(path)
        out.append({
            "entity_id": entity_id,
            "attribute_path": path,
            "label": definition.label,
            "dtype": definition.dtype,
            "unit": definition.unit,
            "safety_class": definition.safety_class,
        })
    return out


def assess(gap_rows: list[dict], base, *, top_k: int = 4) -> Assessment:
    """Bucket every gap, using retrieval and no model.

    One search per distinct attribute rather than per gap: forty products short
    of the same ingredient declaration is one question about the corpus asked
    forty times, and the corpus does not change between them.
    """
    from sc.rag import retrieve

    assessment = Assessment()
    by_path: dict[str, list[dict]] = {}
    for row in gap_rows:
        if row["safety_class"]:
            assessment.gaps.append(Gap(
                **_gap_fields(row), state=SAFETY_HELD,
                why=("safety class: a value a model inferred rather than read "
                     "blocks publication instead of degrading it, so this one "
                     "is for the supplier to send")))
            continue
        by_path.setdefault(row["attribute_path"], []).append(row)

    for path, rows in sorted(by_path.items()):
        entities = sorted({r["entity_id"] for r in rows})
        try:
            found = retrieve.search(path, top_k=top_k, doc_types=DOC_TYPES,
                                    entities=entities)
        except Exception:  # noqa: BLE001 - no index is not a fixable gap
            found = []
        citations = retrieve.cite(found) if found else []
        for row in rows:
            if citations:
                assessment.gaps.append(Gap(
                    **_gap_fields(row), state=CANDIDATE,
                    citation=citations[0],
                    why=(f"{len(citations)} supplied passage"
                         f"{'' if len(citations) == 1 else 's'} could carry "
                         f"this value")))
            else:
                assessment.gaps.append(Gap(
                    **_gap_fields(row), state=NO_SOURCE,
                    why=("nothing retrievable mentions this attribute for this "
                         "product, so there is no sentence to read it out of "
                         "and the supplier has to send it")))
    return assessment


def _gap_fields(row: dict) -> dict:
    return {
        "entity_id": row["entity_id"],
        "attribute_path": row["attribute_path"],
        "label": row["label"],
        "dtype": row["dtype"],
        "unit": row["unit"],
        "safety_class": row["safety_class"],
    }
