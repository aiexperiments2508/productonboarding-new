"""Reporting the defects the estate introduces.

The estate can stamp seven kinds of defect on an arriving payload. That is only
worth doing if something downstream names them back. A generator that produces
a failure nothing detects has not made the demo harder, it has made the answer
key wrong - and an answer key that is wrong in the direction of flattery is the
worst artefact in a system like this.

So every member of ``defects.ALL`` has a detector here, and
``tests/test_estate.py::test_every_stamped_defect_is_detected`` walks the set
and fails if one does not. Adding a defect to the enum without adding a
detector breaks that test, which is the intended order of events.

Every detector is **deterministic**. Not because a model could not help - it
could, on the semantic ones - but because a defect is an assertion about what
arrived, and an assertion the system makes about its own inputs should not be
something a model can be persuaded out of. The model's turn comes later, on
questions the rules genuinely cannot answer.

Each detector returns a finding or ``None``. A finding names the defect, the
attribute path it concerns, and a sentence a reviewer can act on - never a
score, because nothing here is uncertain enough to need one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from sc.contracts import ChannelRuleKind
from sc.estate.defects import Defect, explain


@dataclass(frozen=True)
class Finding:
    defect: Defect
    path: str
    detail: str

    def as_dict(self) -> dict:
        return {"defect": str(self.defect), "path": self.path,
                "detail": self.detail}


def _rows(payload: dict) -> list[dict]:
    """The attribute rows a payload carries, whatever shape it arrived in."""
    rows = payload.get("rows") or payload.get("attributes") or []
    return [r for r in rows if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# The detectors
# ---------------------------------------------------------------------------


def missing_mandatory(payload: dict, base, entity_id: str = "") -> Finding | None:
    """A required attribute is absent.

    "Required" is per channel and per category, so this asks the same rule
    table the validator publishes against rather than a second list. A payload
    is not obliged to carry every attribute - only the ones a channel this
    entity lists on will refuse without.
    """
    supplied = {r.get("path") for r in _rows(payload)}
    declared = payload.get("declares") or []
    for path in declared:
        if path in supplied:
            continue
        required_by = [r.channel_id for r in base.rules
                       if r.kind == ChannelRuleKind.REQUIRED
                       and r.attribute_path == path]
        if required_by:
            return Finding(
                Defect.MISSING_MANDATORY, path,
                f"{explain(Defect.MISSING_MANDATORY)}; "
                f"{', '.join(sorted(required_by))} will refuse the listing")
    return None


def wrong_type(payload: dict, base, entity_id: str = "") -> Finding | None:
    """The value is present and is not the declared dtype.

    Kept apart from a missing value on purpose: the supplier *did* answer, so
    the remedy is a coercion or a mapping rather than a request for data.
    """
    for row in _rows(payload):
        path, value = row.get("path"), row.get("value")
        definition = base.attr_defs.get(path)
        if definition is None or value is None:
            continue
        if not _is_dtype(value, definition.dtype):
            return Finding(
                Defect.WRONG_TYPE, path,
                f"{explain(Defect.WRONG_TYPE)}: {value!r} is not "
                f"{definition.dtype}")
    return None


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


def foreign_vocabulary(payload: dict, base, entity_id: str = "") -> Finding | None:
    """A well-formed record in somebody else's field names.

    The data pool is not wrong to call net content ``netContent``. It is wrong
    for this catalog, and the distinction matters because the remedy is a
    mapping owned by the integration team rather than a correction owned by the
    supplier.
    """
    for row in _rows(payload):
        path = row.get("path")
        if path and path not in base.attr_defs:
            return Finding(
                Defect.FOREIGN_VOCABULARY, str(path),
                f"{explain(Defect.FOREIGN_VOCABULARY)}: "
                f"{path!r} is not an attribute this catalog defines")
    return None


def broken_format(payload: dict, base, entity_id: str = "") -> Finding | None:
    """The value says the right thing in the wrong shape.

    This is the defect a marketplace rejects a feed over while agreeing with
    its content, so the pattern comes from the channel rule rather than from a
    convention held here.
    """
    for row in _rows(payload):
        path, value = row.get("path"), row.get("value")
        if not isinstance(value, str):
            continue
        for rule in base.rules:
            if (rule.kind == ChannelRuleKind.FORMAT
                    and rule.attribute_path == path
                    and isinstance(rule.value, str)):
                if not re.search(rule.value, value):
                    return Finding(
                        Defect.BROKEN_FORMAT, str(path),
                        f"{explain(Defect.BROKEN_FORMAT)}; "
                        f"{rule.channel_id} requires {rule.value!r}")
    return None


def stale_version(payload: dict, base, entity_id: str = "") -> Finding | None:
    """Asserted against a document version that has been superseded.

    Dangerous precisely because the payload is internally consistent: it was
    true when it was written and nothing in it says it no longer is.
    """
    doc_id = payload.get("source_doc") or payload.get("doc_id")
    version = payload.get("source_version") or payload.get("doc_version")
    document = base.source_docs.get(doc_id) if doc_id else None
    if document and version and version != document.version:
        return Finding(
            Defect.STALE_VERSION, str(doc_id),
            f"{explain(Defect.STALE_VERSION)}: asserted against {version}, "
            f"current is {document.version}")
    return None


def contradicts_source(payload: dict, base, entity_id: str = "") -> Finding | None:
    """Disagrees with a value a higher-precedence source already asserted.

    Only detectable with the rest of the estate in view, which is the reason an
    estate of one system cannot produce this defect and an estate of ten can.
    Precedence comes from the source document ranking the policy already
    documents, not from a second ranking invented here.
    """
    for row in _rows(payload):
        path, value = row.get("path"), row.get("value")
        if path is None:
            continue
        entity = row.get("entity_id") or entity_id
        held = base.attr_values.get((entity, path))
        if held is None or value is None or held == value:
            continue
        source = base.attr_sources.get((entity, path))
        incoming_rank = int(payload.get("precedence") or 0)
        held_doc = base.source_docs.get(getattr(source, "doc_id", "") or "")
        held_rank = int(getattr(held_doc, "precedence", 0) or 0)
        if held_rank > incoming_rank:
            return Finding(
                Defect.CONTRADICTS_SOURCE, str(path),
                f"{explain(Defect.CONTRADICTS_SOURCE)}: says {value!r}, "
                f"{getattr(held_doc, 'id', 'a stronger source')} says {held!r}")
    return None


def missing_media(payload: dict, base, entity_id: str = "") -> Finding | None:
    """A record whose category requires imagery arrived without it.

    Counted apart from a missing attribute because media goes missing far more
    often, and because the team who fixes it is not the team who fixes a spec.
    """
    if not payload.get("requires_media"):
        return None
    supplied = payload.get("media") or []
    if not supplied:
        return Finding(
            Defect.MISSING_MEDIA, "media",
            f"{explain(Defect.MISSING_MEDIA)}")
    return None


#: Defect -> the deterministic check that reports it. The test walks this, so a
#: defect added to the enum without a detector fails before it can reach a
#: payload.
DETECTORS: dict[Defect, Callable[..., Finding | None]] = {
    Defect.MISSING_MANDATORY: missing_mandatory,
    Defect.WRONG_TYPE: wrong_type,
    Defect.FOREIGN_VOCABULARY: foreign_vocabulary,
    Defect.BROKEN_FORMAT: broken_format,
    Defect.STALE_VERSION: stale_version,
    Defect.CONTRADICTS_SOURCE: contradicts_source,
    Defect.MISSING_MEDIA: missing_media,
}


def detector_for(defect: Defect):
    """The check that reports this defect, or None if nothing does."""
    return DETECTORS.get(defect)


def inspect(payload: dict, base, entity_id: str = "") -> list[dict]:
    """Every defect this payload can be shown to carry.

    Walked in declaration order so a report reads the same way twice, and every
    detector is run rather than stopping at the first hit: a payload with a
    missing attribute *and* a stale version has two problems for two teams.
    """
    findings = []
    for defect in DETECTORS:
        finding = DETECTORS[defect](payload, base, entity_id)
        if finding is not None:
            findings.append(finding.as_dict())
    return findings
