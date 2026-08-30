"""Project bitemporal facts into the validator's ``Overlay``.

This is the join between what the system *knows* and what the validator
*computes*. Corrections are stored as ordinary facts; this module reads them at
a chosen point on both time axes and assembles the values in force.

The mapping is deliberately direct: **a correction's effective window is the
fact's own validity interval**. A supplier restating a rating from the 29th is
a fact with ``valid_from`` on the 29th, so the validator's window and the
store's validity window are the same thing rather than two representations that
can drift apart.

Because ``as_of_recorded`` is a parameter, a resolution can be validated
against what was known when the decision was taken rather than against
corrections that landed afterwards - which is what lets the republish gate
notice that an approval has been overtaken.

Fact conventions this module reads, and the event reducer writes:

* ``variant`` / ``product`` facts whose ``attr`` is an attribute path carry
  attribute values; ``provenance.source_id`` names the source document, either
  as ``"DOC-01"`` or as ``"DOC-01:v2"`` when the fact pins its own version.
* the reserved ``decision_version.<path>`` attr records the version a standing
  decision on that attribute was validated against.
* ``source_doc`` facts carry ``version`` and ``status``; ``channel`` facts
  carry ``status``, the feed acknowledgement from the channel gateway.
* ``listing`` facts carry ``status`` and ``published_version`` - the source
  version the listing last went out on, written by ``tools.planning`` when a
  publish commits and read by the validator's freeze-window rule.
"""

from __future__ import annotations

from datetime import datetime

from sc.sim.engine import AttrState, Overlay
from sc.state import baseline, store

ATTR_DECISION = "decision_version."
ATTR_PUBLISHED_VERSION = "published_version"
ATTR_STATUS = "status"
ATTR_VERSION = "version"


def _version_of(provenance, doc_versions: dict[str, str]) -> str:
    """The source-document version a fact's value came from.

    A fact may pin its own version (``DOC-01:v2``); otherwise it inherits
    whatever version of its document is in force, which is what makes a later
    document revision propagate to every value it asserted.
    """
    source_id = provenance.source_id or ""
    doc, _, pinned = source_id.partition(":")
    return pinned or doc_versions.get(doc, "")


def build(as_of_valid: datetime, as_of_recorded: datetime | None = None) -> Overlay:
    """Assemble every corrected value in force at the given instants.

    ``as_of_recorded`` defaults to ``as_of_valid``: "as of this moment, using
    everything known by this moment". Both axes run on the replay clock, so
    defaulting the recorded axis to wall-clock time would put every read
    outside the horizon and hide every fact the replay has produced.
    """
    as_of_recorded = as_of_recorded or as_of_valid
    overlay = Overlay(as_of=as_of_valid)

    # Documents first: an attribute fact's version is looked up here.
    for fact in store.get_many("source_doc", as_of_valid, as_of_recorded):
        if fact.attr == ATTR_VERSION:
            overlay.doc_versions[fact.entity_id] = str(fact.value)
        elif fact.attr == ATTR_STATUS:
            overlay.doc_status[fact.entity_id] = str(fact.value)

    for fact in store.get_many("channel", as_of_valid, as_of_recorded,
                               attr=ATTR_STATUS):
        overlay.channel_status[fact.entity_id] = str(fact.value)

    for entity_type in ("product", "variant"):
        for fact in store.get_many(entity_type, as_of_valid, as_of_recorded):
            if fact.attr.startswith(ATTR_DECISION):
                path = fact.attr[len(ATTR_DECISION):]
                overlay.decision_version[f"{fact.entity_id}:{path}"] = str(fact.value)
                continue
            overlay.attr_values[(fact.entity_id, fact.attr)] = AttrState(
                value=fact.value,
                version=_version_of(fact.provenance, overlay.doc_versions),
                fact_id=fact.id,
                recorded_at=fact.recorded_at,
                provenance_kind=str(fact.provenance.kind),
                confidence=fact.provenance.confidence,
            )

    # Listings carry publication state rather than attribute values; a listing
    # withheld or rejected on a channel is a fact about that channel's feed,
    # and the version it last published on is what the freeze-window rule
    # compares the values in force against.
    for fact in store.get_many("listing", as_of_valid, as_of_recorded,
                               attr=ATTR_STATUS):
        overlay.channel_status.setdefault(fact.entity_id, str(fact.value))

    for fact in store.get_many("listing", as_of_valid, as_of_recorded,
                               attr=ATTR_PUBLISHED_VERSION):
        overlay.published_version[fact.entity_id] = str(fact.value)

    return overlay


def is_quiet(overlay: Overlay) -> bool:
    """True when nothing has been corrected - used to decide whether a
    correction run has anything to investigate."""
    return not (overlay.attr_values or overlay.doc_versions or overlay.doc_status
                or overlay.channel_status or overlay.decision_version)


def summarise(overlay: Overlay) -> list[str]:
    """The lines the Factory Floor and the audit ledger show.

    Each reads ``document version supersedes version: entity path old -> new``,
    because that is the sentence the brief asks every change to be able to
    produce about itself.
    """
    base = baseline.get()
    lines: list[str] = []

    for (entity_id, path), state in sorted(overlay.attr_values.items()):
        unit = base.attr_defs[path].unit if path in base.attr_defs else None
        chain = store.lineage(state.fact_id) if state.fact_id else []
        doc = (chain[0].provenance.source_id or "").partition(":")[0] if chain else ""

        # What this value replaced: the fact it superseded if there is one,
        # otherwise the value the prepared content was written against.
        if chain[1:]:
            was_value = chain[1].value
            was_version = _version_of(chain[1].provenance, overlay.doc_versions)
        else:
            key = (entity_id, path)
            source = base.attr_sources.get(key)
            was_value = base.attr_values.get(key)
            was_version = source.version if source else ""

        moved = was_value is not None and was_value != state.value
        lead = f"{doc} {state.version} supersedes {was_version}: " if moved else ""
        shown = f"{was_value} -> {state.value}" if moved else str(state.value)
        tail = f" ({state.provenance_kind}"
        tail += f" {state.confidence:.2f})" if state.confidence is not None else ")"
        lines.append(f"{lead}{entity_id} {path} {shown}"
                     + (f" {unit}" if unit else "") + tail)

    for doc_id, status in sorted(overlay.doc_status.items()):
        if status == "ACTIVE":
            continue
        version = overlay.doc_versions.get(doc_id)
        lines.append(f"{doc_id} {version} is {status}" if version
                     else f"{doc_id} is {status}")
    for channel_id, status in sorted(overlay.channel_status.items()):
        lines.append(f"{channel_id} feed {status}")
    for ref, version in sorted(overlay.decision_version.items()):
        lines.append(f"{ref} last validated against {version}")

    return lines
