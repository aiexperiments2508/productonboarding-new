"""Graph nodes.

The division of labour is the same in every node: **tools establish what is
true, the model interprets it, and code decides what happens next.** Every node
that calls a model validates the reply against tool output before it is allowed
to affect state, and every node degrades to a deterministic fallback when the
gateway is unreachable - a dead network must slow the demo down, not stop it.

The whole test suite runs with the gateway pointed at a closed port, so the
fallback path is the one that actually executes in CI. A node that cannot reach
a recommendation without a model is a bug rather than a limitation.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from langgraph.types import Command, Send, interrupt
from pydantic import ValidationError

from sc import db
from sc.contracts import (
    ActionKind,
    ApprovalDecision,
    ChangeScope,
    ChangeSet,
    ChangeSummaryLine,
    CorrectionKind,
    EventType,
    IncidentStatus,
    LlmUsage,
    Provenance,
    ProvenanceKind,
    RegenerateCopyAction,
    RemapTaxonomyAction,
    RequestSupplierInputAction,
    ScopeLevel,
    SetAttributeAction,
    SetFacetAction,
    SourceRef,
    WithholdChannelAction,
)
from sc.a2a import client as a2a_client
from sc.graph import evidence, prompts
from sc.graph.state import RESET, FactoryState, ScenarioTask, _detected_at, step
from sc.llm import gateway
from sc.llm import models as model_registry
from sc.llm.gateway import GatewayError
from sc.rag import retrieve
from sc.replay import ingest, tape
from sc.sim import engine
# The validator's own resolution of an entity id into the listings it reaches.
# Shared rather than restated: a violation the engine raised against a product
# has to name the same listings here as it did there, and a fact is recorded
# against whichever level the evidence named.
from sc.sim.engine import _listings_for as listings_for
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod
from sc.state import store
from sc.state.baseline import precedence
from sc.tools import planning


# Model tiers, resolved from what the gateway actually serves rather than
# pinned to an alias. Extraction and classification are high volume and
# mechanical; the scope argument, the rewritten copy and the recommendation are
# what a reviewer reads, so they get the strongest model available - which may
# be a flash-class model if the gateway serves nothing larger.
def fast_model() -> str:
    return model_registry.resolve_tier("fast")


def reasoning_model() -> str:
    return model_registry.resolve_tier("reasoning")


# How many readings of a correction are validated. Three is the honest number:
# the narrowest the evidence supports, the widest, and at most one in between.
# A fourth is a variation on one of those and costs a validation pass to say so.
MAX_CANDIDATES = 3

# How many content assets one run will ask a model to rewrite. Past this the
# skipped ones are reported rather than silently dropped - a reviewer told
# "twelve of nineteen fields were rewritten" can act; one shown twelve and no
# count cannot.
MAX_REGENERATIONS = 12

# How many of those rewrites are in flight at once. The fields are independent -
# twelve bullets on five listings have nothing to say to each other - so the
# loop was serial only because it was written in the order it was thought of.
#
# Six rather than twelve: the gateway is a single upstream with its own rate
# limits, and asking it for twelve simultaneous reasoning completions produces a
# 429 storm that the retry path turns back into serial latency. Six also keeps
# the number of threads writing to the response cache inside what one SQLite
# writer absorbs comfortably.
#
# Settable to 1, which restores exactly the serial path. That is what makes
# "the concurrent result equals the serial result" a test rather than a claim.
MAX_REGEN_WORKERS = max(1, int(os.environ.get("REGEN_WORKERS", "6")))

# The same, for reading supplier documents. Extraction's *writes* stay strictly
# sequential - see the note in `extract` - and only the readings are fanned out.
MAX_EXTRACT_WORKERS = max(1, int(os.environ.get("EXTRACT_WORKERS", "6")))

# One retry after a publish conflict. A second is a queue rather than a
# recovery, and a reviewer should be told rather than watched over by a
# spinning graph.
MAX_PUBLISH_RETRIES = 1

# Confidence carried by a value taken from the structured hint that accompanies
# a supplier document, when no model is available to read the prose. It sits
# deliberately below ``engine.SAFETY_CONFIDENCE``: the hint is still a claim
# about what a document says, and an allergen the system merely believes is
# exactly what the fail-closed gate exists to stop reaching a label.
FALLBACK_CONFIDENCE = 0.8

# The one failure regeneration cannot clear. A low-confidence inference about a
# safety attribute is wrong in the record, not in the sentence, so the listing
# is withheld rather than rewritten. Everything else in the safety gate -
# a missing allergen declaration above all - is a defect in the copy, which the
# copywriter can fix and ``validate_final`` re-checks.
# `sale_prohibited` joins it for the same reason and a stronger one: no
# sentence a copywriter can write makes a withdrawn product sellable, and a
# leg that tried would be spending a model call on rewording a listing that is
# coming down.
UNFIXABLE_BY_COPY = ("safety_confidence", "sale_prohibited")

# Fields that are prose rather than machine data. These are the ones worth a
# model call when the deterministic rewrite cannot settle them.
NL_FIELDS = ("title", "bullets", "description", "catalogue_copy", "shelf_text",
             "comparison_table", "facets")

# Listing states that mean content is not reaching the channel.
BLOCKED_STATUSES = ("REJECTED", "WITHHELD")

# Where a correction goes when no product can be named for it. It is a case
# rather than a discard: a correction the system could not attribute is exactly
# the kind of thing that must stay on a reviewer's list.
UNSCOPED_CASE = "UNSCOPED"


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _iso(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else tape.sim_now()


def _render(results) -> str:
    return "\n\n".join(
        f"[{r.chunk.doc_id} | {r.chunk.metadata.get('heading','')}]\n{r.chunk.text[:900]}"
        for r in results) or "(nothing retrieved)"


def _policy_extract(query: str) -> str:
    return _render(retrieve.search(query, top_k=2, doc_types=["POLICY"]))


def _dedupe_citations(citations: list[dict]) -> list[dict]:
    """Keep first appearance. The opening retrieval and an evidence-desk policy
    lookup routinely land on the same chunk, and a doubled citation list reads
    as two sources agreeing when it is one source cited twice."""
    seen: set[str] = set()
    unique: list[dict] = []
    for c in citations or []:
        key = c.get("chunk_id") or f"{c.get('doc_id')}:{c.get('heading')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def _spend(node: str, *usage: LlmUsage | None) -> dict:
    """What one node spent on models, for ``state["usage"]``.

    Keyed by node name because the state reducer merges dicts by overwriting
    keys rather than summing them: a flat accumulator would keep only the last
    node to write, and per-node totals are what "which step costs the money"
    needs anyway. A node whose calls all failed reaches its fallback and
    records nothing, which is why CI - where the gateway is a closed port -
    leaves the field empty rather than filling it with zeroes.
    """
    used = [u for u in usage if u is not None]
    if not used:
        return {}
    return {node: {
        "calls": len(used),
        "prompt_tokens": sum(int(u.prompt_tokens) for u in used),
        "completion_tokens": sum(int(u.completion_tokens) for u in used),
        "total_tokens": sum(int(u.total_tokens) for u in used),
        "cost_usd": round(sum(float(u.cost_usd) for u in used), 6),
        # Count rather than flag: a node can make several calls, and how many
        # of them the record/replay cache served is the interesting half.
        "cache_hits": sum(1 for u in used if u.cached),
    }}


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------


def monitor(state: FactoryState) -> dict:
    """Establish what is currently uncorrected, and pin the run's clock.

    Signals are derived from the *facts in force* rather than from whatever
    this call happens to drain off the event tape. The API's replay clock also
    ingests events, so a run that relied on draining would find the queue empty
    and conclude nothing was wrong. Reading the state of the record instead
    makes the node idempotent and re-runnable, which is also what lets a
    resumed thread and a revision reach the same conclusion.

    Both time axes are pinned once, here. A recommendation has to be
    reproducible against the evidence it actually had rather than against
    corrections that landed while it was still being written.

    The signals this node derives are the *whole* record, not one case's share
    of it. Narrowing the run to a case is ``scope_case``'s job, on the far side
    of ``extract``, because a case can only be resolved once every unread
    document has been read - see that node. What is settled here is which case
    the run *asks* for: the caller's, or the worst one the record already held.
    """
    ingest.drain()  # pick up anything not yet processed; safe if already done
    now = tape.sim_now()
    base = baseline_mod.get()

    signals = _signals_in_force(now)
    examined = _examined_events()
    unread = sorted(
        (e for e in tape.released(limit=400)
         if e.type in (EventType.SPEC_DOC, EventType.COMMS)
         and e.id not in examined),
        key=lambda e: e.seq,
    )

    # A revision re-enters this node on the same thread. Everything that
    # accumulates has to be cleared here, at the single point where a revision
    # begins - scattering the resets across the nodes that write those fields
    # would mean every future node has to remember it is on a revision.
    revising = bool(state.get("replan_reason")) and not state.get("revision_started")
    prefix = [RESET] if revising else []

    cases = open_cases(signals, base)
    # A revision never re-picks: re-planning on the same thread is the whole
    # point of staying on one case, and the second pass sees a record the first
    # pass wrote to, so a fresh pick could walk the incident onto a different
    # product between revisions.
    case_id = str(state.get("case_id") or "")
    if not case_id and not revising and cases:
        case_id = cases[0]["case_id"]
    asked = next((c for c in cases if c["case_id"] == case_id), None)

    carried: dict = {}
    if revising:
        carried = {
            "revision": int(state.get("revision") or 0) + 1,
            "revision_started": True,
            "previous_recommendation": state.get("recommendation") or {},
            "previous_ranked": state.get("ranked") or [],
            # The superseded decision is cleared: leaving it in place would let
            # the UI show a stale approval beside a plan it never approved.
            "recommendation": {},
            "approval": {},
            "commit_result": {},
            "ranked": [],
            "scenarios": [],
            "rejected_actions": [],
            "scope_candidates": [],
            "chosen_scope": {},
            "claim_flags": [],
            "regenerated": [],
            "enrichments": [],
            "final_validation": {},
            "plan_diff": {},
        }

    return {
        "run_id": state.get("run_id") or _uid("RUN"),
        "as_of": now.isoformat(),
        "as_of_recorded": now.isoformat(),
        "signals": prefix + signals,
        "citations": prefix,
        "sim_results": prefix,
        "event_ids": [e.id for e in unread],
        "case_id": case_id,
        "status": "MONITORING",
        **carried,
        "trace": [
            step("monitor",
                 (f"revision {carried['revision']}: " if revising else "")
                 + f"{len(signals)} corrections in force, "
                 f"{len(unread)} documents to read",
                 sim_clock=now.isoformat(),
                 revision=carried.get("revision", state.get("revision", 0))),
            step("monitor",
                 (f"case {case_id}: {asked['title']}" if asked
                  else f"case {case_id}: nothing open on the record yet"
                  if case_id else "no open case to scope to")
                 + ", confirmed once the documents are read",
                 case_id=case_id,
                 other_cases=[c["case_id"] for c in cases
                              if c["case_id"] != case_id],
                 severity_hint=asked["severity_hint"] if asked else None),
        ],
    }


def _examined_events() -> set[str]:
    """Events a previous pass already read. One query, not one per event."""
    rows = db.query("SELECT DISTINCT entity_id FROM audit WHERE action = 'EXAMINE'")
    return {r["entity_id"] for r in rows}


#: Attribute path prefix to correction kind, most consequential first. The
#: order is the precedence: a document that moves two of these is named by the
#: first one it matches, because that is the half a reviewer has to act on.
#:
#: Mirrored by ``_golden_kind`` in ``scripts/generate_data.py``, and
#: ``tests/test_golden.py`` asserts the two agree - the answer key grading
#: extraction has to classify a document the same way the fallback does, or the
#: evaluation measures the disagreement instead of the model.
KIND_BY_PATH: tuple[tuple[str, str], ...] = (
    ("compliance.sale_permitted", str(CorrectionKind.REGULATORY_ORDER)),
    ("compliance.export_control", str(CorrectionKind.EXPORT_RESTRICTION)),
    ("food.allergens", str(CorrectionKind.ALLERGEN_CHANGE)),
    ("food.ingredients", str(CorrectionKind.INGREDIENT_CHANGE)),
    ("cosmetic.inci", str(CorrectionKind.COMPOSITION_CHANGE)),
    ("health.active_ingredient", str(CorrectionKind.COMPOSITION_CHANGE)),
    ("textile.fibre_composition", str(CorrectionKind.COMPOSITION_CHANGE)),
    ("compliance.certificate_ref", str(CorrectionKind.CERTIFICATION_LAPSE)),
    ("compliance.min_age", str(CorrectionKind.LEGAL_REQUIREMENT_CHANGE)),
    ("pack.net_quantity", str(CorrectionKind.NET_QUANTITY_CHANGE)),
    ("food.net_weight_g", str(CorrectionKind.NET_QUANTITY_CHANGE)),
    ("origin.country", str(CorrectionKind.ORIGIN_CHANGE)),
)


def _kind_for_path(path: str) -> str:
    """Which class of correction a change to this attribute is.

    Allergens outrank everything a supplier can say: a document that reorders
    an ingredient list *and* adds a possible allergen is an allergen change,
    because that is the half with the consequence. Above them sit the two
    things that are not corrections at all - an order that the product may not
    be sold, and a restriction on where it may go.
    """
    for prefix, kind in KIND_BY_PATH:
        if path == prefix or path.startswith(f"{prefix}."):
            return kind
    return str(CorrectionKind.SPEC_CORRECTION)


def _fact_head(state):
    """The assertion at the top of a value's correction chain."""
    chain = store.lineage(state.fact_id) if state.fact_id else []
    return chain[0] if chain else None


def _signals_in_force(now: datetime) -> list[dict]:
    """Reconstruct correction signals from the bitemporal facts in force.

    Values here are plain JSON types, never enum members: the checkpointer
    serialises state with msgpack, and an unregistered enum round-trips with a
    deprecation warning today and will fail outright later.

    Facts are the durable record; a signal is a view over them. Deriving one
    from the other means the graph sees the same correction whether it was
    extracted a second ago or a week ago, by this run or another - and it means
    a revision that cannot re-read an already-examined document still sees what
    that document said.

    Two reads, not one. A correction announced ahead of its effective date is
    not in force today and is still an open correction: content has to be
    prepared before the change takes effect, which is the whole reason a
    supplier sends the notice early. So the valid-time read is taken both at
    the replay clock and at the end of the horizon, and anything visible only
    in the second is reported with the date it becomes true.

    **Five kinds of open thing, not two.** This used to report a moved value
    and a refused feed, and nothing else - which meant the queue a reviewer
    picks from, and the case ``monitor`` takes when the caller names none, were
    blind to three sorts of correction the estate detects perfectly well:

      DATA_GAP        a document asserted a required value and left it empty.
                      Classified here rather than by path, using ingestion's
                      own ``is_gap`` so the queue cannot disagree with the
                      record that filled it.
      DOC_WITHDRAWN   a document is no longer in force and values are still
                      standing on it. ``overlay.doc_status`` has carried this
                      the whole time and only ``summarise`` was reading it.
      SOURCE_CONFLICT a feed row lost a precedence contest. ``ingest`` refuses
                      to record the loser - correctly - so the disagreement
                      leaves no fact behind, and it is recomputed here from the
                      event that carried it against the value in force now.

    All three are *derived*, like everything else here. Nothing is stored, so
    nothing has to be retired: a conflict whose value later converges, a gap
    later filled and a document later reinstated stop being reported because
    the record stopped saying them, which is the only resolution rule that
    cannot drift out of step with the facts.
    """
    base = baseline_mod.get()
    horizon_end = datetime.combine(
        base.horizon_start + timedelta(days=base.horizon_days), datetime.min.time())

    in_force = overlay_mod.build(now, now)
    announced = overlay_mod.build(horizon_end, now)

    signals: list[dict] = []
    seen: set[tuple[str, str]] = set()
    # Which entities are standing on which document *version*, for the
    # withdrawal pass below. Built here rather than in a second scan because
    # the document a value came from is already being resolved on this line,
    # and resolving it twice means two lineage walks over the same facts.
    #
    # Keyed by the pinned ``doc:version``, never by the document alone. A
    # withdrawal retracts one revision, and ``_doc_ref`` is explicit that an
    # unpinned fact merely *inherits* whatever version is in force - so keying
    # by document would report every value the document ever asserted as
    # unsupported the moment a later revision was retracted, which is the
    # opposite of what a retraction means.
    standing: dict[str, dict[str, set[str]]] = {}

    # What every attribute holds now and who said so, assembled once. The
    # conflict pass below asks this of every row on the tape.
    held = _held_values(base, in_force)

    for ov in (in_force, announced):
        for key in sorted(ov.attr_values):
            entity_id, path = key
            if key in seen:
                continue
            attr_state = ov.attr_values[key]
            was = base.attr_values.get(key)

            head = _fact_head(attr_state)
            source_id = (head.provenance.source_id or "") if head else ""
            doc, _, pinned = source_id.partition(":")
            if doc and pinned:
                standing.setdefault(f"{doc}:{pinned}", {}) \
                        .setdefault(entity_id, set()).add(path)

            # A feed that restates a value it already agrees with is not news.
            # Checked after the document is resolved: an unchanged value is
            # still standing on whatever asserted it, and the withdrawal of
            # that document is news about the value even so.
            if attr_state.value == was:
                continue
            seen.add(key)

            definition = base.attr_defs.get(path)
            effective = head.valid_from.date() if head else None
            future = bool(effective and effective > now.date())

            # A required value a document asserted as empty is a gap, not a
            # correction to whatever it used to say. ``ingest.is_gap`` decides,
            # so this and the ingestion that recorded the row cannot disagree
            # about what counts as missing.
            gap = ingest.is_gap(definition, attr_state.value)
            unit = f" {definition.unit}" if definition and definition.unit else ""
            summary = (
                f"{doc} {attr_state.version} sent {entity_id} {path} empty; "
                f"it is required on "
                f"{', '.join(sorted(definition.required_for))}"
                if gap else
                f"{doc} {attr_state.version} corrects {entity_id} "
                f"{path}: {was} -> {attr_state.value}{unit}"
                + (f", effective {effective}" if future else ""))

            signals.append({
                "id": f"SIG-{entity_id}-{path}",
                "kind": (str(CorrectionKind.DATA_GAP) if gap
                         else _kind_for_path(path)),
                "detected_at": (head.recorded_at if head else now).isoformat(),
                "entities": [entity_id],
                "attribute_paths": [path],
                "old_value": was,
                "new_value": attr_state.value,
                "unit": definition.unit if definition else None,
                "window_start": effective.isoformat() if effective else None,
                "summary": summary,
                "source": {"doc_id": doc, "version": attr_state.version},
                "provisional": False,
                "resolves_issue": False,
                "provenance": {
                    "kind": attr_state.provenance_kind,
                    "source_id": f"{doc}:{attr_state.version}" if doc else None,
                    "confidence": attr_state.confidence,
                },
            })

    # A channel that refused the feed is a correction signal of its own: the
    # content is not reaching shoppers and the reason is a fact about the
    # channel, not about the supplier.
    for listing_id in sorted(in_force.channel_status):
        status = in_force.channel_status[listing_id]
        listing = base.listings.get(listing_id)
        if listing is None or status not in BLOCKED_STATUSES:
            continue
        signals.append({
            "id": f"SIG-{listing_id}-{status}",
            "kind": str(CorrectionKind.CHANNEL_REJECTION),
            "detected_at": now.isoformat(),
            "entities": [listing_id, listing.channel_id, listing.variant_id],
            "attribute_paths": [],
            "summary": (f"{listing.channel_id} has {listing_id} "
                        f"({listing.variant_id}) as {status}"),
            "provisional": False,
            "resolves_issue": False,
            "provenance": {"kind": str(ProvenanceKind.RECORDED)},
        })

    signals += _withdrawn_doc_signals(now, in_force, base, standing)
    signals += _conflict_signals(now, base, held)

    return signals


def _held_values(base, in_force) -> dict[tuple[str, str], tuple[object, str]]:
    """What every attribute holds now, and which document said so.

    The same answer ``ingest._in_force`` gives, assembled once for the whole
    record instead of one fact-store query per row. The conflict pass below
    asks this question of every attribute row on the tape, and asking it a
    query at a time turned a page load into several hundred round trips.

    The overlay is a diff - only corrected values are in it - so the lineage
    walk this needs runs over a handful of facts rather than over the estate.
    """
    values: dict[tuple[str, str], tuple[object, str]] = {}
    for key, value in base.attr_values.items():
        source = base.attr_sources.get(key)
        values[key] = (value, source.doc_id if source else "")
    for key, attr_state in in_force.attr_values.items():
        head = _fact_head(attr_state)
        doc, _, _ = ((head.provenance.source_id or "") if head else "").partition(":")
        values[key] = (attr_state.value, doc)
    return values


def _withdrawn_doc_signals(now: datetime, in_force, base,
                           standing: dict[str, dict[str, set[str]]]
                           ) -> list[dict]:
    """Retracted document revisions that values are still standing on.

    A withdrawal changes no value - every number in the record is exactly what
    it was a moment ago - which is precisely why it needs saying: the evidence
    under those numbers has gone, and no amount of reading the values
    themselves would ever reveal it.

    **Scoped to the retracted revision, and that is the whole of the rule.**
    Withdrawing a revision is usually the opposite of bad news: the tape's own
    withdrawal retracts a provisional dimensional drawing after the tooling
    audit closed, and what it means is that the *earlier* version stands and
    nothing is wrong. ``state.merge_signals`` already treats that as a
    resolver. So a case opens only where a fact in force pins the withdrawn
    ``doc:version`` - a value that revision asserted and nothing has since
    replaced. A fact that merely inherits the version, or one recorded from an
    earlier revision, is still supported and is not reported.

    One signal per entity, not per path: a revision withdrawn under six of a
    variant's attributes is one piece of news about that variant, and six rows
    would be six cases' worth of noise about one event.
    """
    out: list[dict] = []
    for doc_id in sorted(in_force.doc_status):
        status = str(in_force.doc_status[doc_id])
        if status == "ACTIVE":
            continue
        version = in_force.doc_versions.get(doc_id, "")
        if not version:
            continue
        ref = f"{doc_id}:{version}"
        entities = standing.get(ref, {})

        for entity_id in sorted(entities):
            paths = sorted(entities[entity_id])
            out.append({
                "id": f"SIG-{entity_id}-{doc_id}-{status}",
                "kind": str(CorrectionKind.DOC_WITHDRAWN),
                "detected_at": now.isoformat(),
                # The subject before the document, which is the order
                # ``case_of`` reads entities in and the order every other
                # signal here uses.
                "entities": [entity_id, doc_id],
                "attribute_paths": paths,
                "old_value": None,
                "new_value": None,
                "summary": (f"{doc_id} {version} is {status}, and {entity_id} "
                            f"is still standing on it for "
                            f"{', '.join(paths)} - the values are unchanged "
                            f"and the evidence under them has gone"),
                "source": {"doc_id": doc_id, "version": version},
                "provisional": False,
                # Deliberately not a resolver. A retraction that *clears* an
                # earlier notice is read out of the event by ``extract``, which
                # sets this; a retraction that leaves values unsupported is the
                # opposite, and must not retire the signals it stands beside.
                "resolves_issue": False,
                "provenance": {"kind": str(ProvenanceKind.RECORDED),
                               "source_id": ref},
            })
    return out


#: How far back the conflict pass reads the tape. A contest is settled at the
#: instant the row arrives and stays settled, so what this bounds is how long a
#: losing row keeps asking to be looked at - not whether it was refused.
CONFLICT_SCAN = 400


def _conflict_signals(now: datetime, base,
                      held: dict[tuple[str, str], tuple[object, str]]
                      ) -> list[dict]:
    """Feed rows a precedence contest refused, recomputed from the tape.

    ``ingest`` returns before ``store.record`` when an incoming row ranks below
    the document in force, and it is right to: recording the loser would let a
    portal spreadsheet quietly beat a pack label. But it also means the
    disagreement leaves no fact behind, and a view derived from facts alone
    cannot see it - which is why a source conflict has never opened a case,
    though the graph has a whole leg, ``supplier_clarification``, for one.

    Both halves survive even so. The losing value is in the event payload,
    which is durable; the winning value is the fact in force. So the contest is
    recomputed rather than remembered, and against what is in force *now*
    rather than at the instant it arrived - which is what gives resolution for
    free. A row the record later adopted, or whose document later outranked the
    one that beat it, simply stops being reported.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in tape.released(limit=CONFLICT_SCAN,
                               event_type=str(EventType.SUPPLIER_FEED)):
        for raw in ingest._raw_rows(event.payload or {}):
            row = ingest._row(base, raw)
            if row is None or not row.doc_id:
                continue
            key = (row.entity_id, row.path)
            if key in seen:
                continue
            standing_value, standing_doc = held.get(key, (None, ""))
            # The record came round to it: there is nothing left in dispute.
            if standing_value == row.value:
                continue
            # This row won, or was never ranked below the value that stands.
            if precedence(base, row.doc_id) >= precedence(base, standing_doc):
                continue
            if not ingest._material(base, row.path, standing_value, row.value):
                continue
            seen.add(key)

            incoming = base.source_docs.get(row.doc_id)
            standing_of = base.source_docs.get(standing_doc)
            out.append({
                "id": f"SIG-{row.entity_id}-{row.path}-CONFLICT",
                "kind": str(CorrectionKind.SOURCE_CONFLICT),
                "detected_at": event.ts.isoformat(),
                # Entity first, then both documents. The pair is the whole
                # point: a case naming one of them would hide the argument.
                "entities": [row.entity_id, standing_doc, row.doc_id],
                "attribute_paths": [row.path],
                "old_value": standing_value,
                "new_value": row.value,
                "unit": row.unit,
                "summary": (
                    f"{row.ref} ({incoming.kind if incoming else 'unknown'}, "
                    f"precedence {precedence(base, row.doc_id)}) says "
                    f"{row.entity_id} {row.path} is {row.value}; "
                    f"{standing_doc} "
                    f"({standing_of.kind if standing_of else 'unknown'}, "
                    f"precedence {precedence(base, standing_doc)}) has "
                    f"{standing_value} - {ingest.PRECEDENCE_POLICY} keeps "
                    f"{standing_doc}, so the feed value is not in force"),
                "source": {"doc_id": row.doc_id, "version": row.version},
                "provisional": False,
                "resolves_issue": False,
                "provenance": {"kind": str(ProvenanceKind.RECORDED),
                               "source_id": row.ref},
            })
    return out


def case_of(signal: dict, base) -> str | None:
    """The product a correction concerns - the unit a reviewer decides about.

    Keyed by product rather than by source document for two reasons. The publish
    lock is ``channel_id:product_id``, so the product is what a reviewer
    actually commits; and the day-18 disagreement spans two documents about one
    product, so grouping by document would split a single conflict in half -
    precisely the wrong seam.

    Entities are read in the order the signal lists them, which is the order
    that puts the subject first: a channel rejection names its listing before
    the channel, and a source conflict names the entity before the two documents
    arguing about it. A channel or a document alone identifies no case.
    """
    for entity_id in signal.get("entities") or []:
        if entity_id in base.products:
            return entity_id
        if entity_id in base.product_of_variant:
            return base.product_of_variant[entity_id]
        listing = base.listings.get(entity_id)
        if listing is not None and listing.variant_id in base.product_of_variant:
            return base.product_of_variant[listing.variant_id]
    return None


def open_cases(signals: list[dict], base) -> list[dict]:
    """Group open signals into per-product cases, worst first.

    An unresolved correction on a product is therefore visible to anyone
    deciding anything else about that product, which is the safety property the
    grouping exists for.
    """
    grouped: dict[str, list[dict]] = {}
    for signal in signals or []:
        grouped.setdefault(case_of(signal, base) or UNSCOPED_CASE,
                           []).append(signal)

    cases: list[dict] = []
    for case_id in sorted(grouped):
        members = grouped[case_id]
        product = base.products.get(case_id)
        paths = sorted({str(p) for s in members
                        for p in s.get("attribute_paths") or [] if p})
        # The source doc of each signal, plus any document named as an entity -
        # a source conflict cites the two documents that disagree that way, and
        # a case that listed only one of them would hide the disagreement.
        documents = {str((s.get("source") or {}).get("doc_id") or "")
                     for s in members}
        documents |= {str(e) for s in members for e in s.get("entities") or []
                      if e in base.source_docs}
        earliest = min(members,
                       key=lambda s: (_detected_at(s), str(s.get("id") or "")))
        safety = any(base.attr_defs[p].safety_class
                     for p in paths if p in base.attr_defs)
        regulated = bool(product and product.regulated)

        cases.append({
            "case_id": case_id,
            "product": case_id if product else "",
            "title": (f"{case_id} {product.name}" if product
                      else "corrections not attributed to a product"),
            "signal_ids": sorted(str(s.get("id") or "") for s in members),
            "signals": members,
            "documents": sorted(documents - {""}),
            "attribute_paths": paths,
            "safety": safety,
            "regulated": regulated,
            "first_detected": str(earliest.get("detected_at") or ""),
            "severity_hint": _severity_hint(members, safety, regulated),
        })

    # Safety, then regulated, then oldest, then id. The first two mirror the
    # escalation triage cannot argue down, so the list a reviewer picks from is
    # ordered by the same thing that will drive the run.
    return sorted(cases, key=lambda c: (
        not c["safety"], not c["regulated"],
        _detected_at({"detected_at": c["first_detected"]}), c["case_id"]))


#: Kinds that are grave whatever they touch. An order to stop selling and a
#: recall are not corrections whose severity depends on their blast radius -
#: they are the severity. Kept separate from the safety-class attribute test
#: because a takedown can name a product whose every attribute is ordinary.
GRAVE_KINDS = frozenset({
    str(CorrectionKind.REGULATORY_ORDER),
    str(CorrectionKind.SAFETY_RECALL),
    str(CorrectionKind.EXPORT_RESTRICTION),
})


def _severity_hint(signals: list[dict], safety: bool, regulated: bool) -> str:
    """How bad a case looks before triage measures it. A hint, never a verdict."""
    if safety or regulated:
        return "CRITICAL"
    if any(s.get("kind") in GRAVE_KINDS for s in signals):
        return "CRITICAL"
    if any(s.get("kind") == str(CorrectionKind.CHANNEL_REJECTION) for s in signals):
        return "HIGH"
    return "MEDIUM"


def _case_view(case: dict) -> dict:
    """A case without its signal bodies - what goes into checkpointed state."""
    return {key: value for key, value in case.items() if key != "signals"}


# ---------------------------------------------------------------------------
# extract - what a supplier document actually says
# ---------------------------------------------------------------------------


def extract(state: FactoryState) -> dict:
    """Read the correction out of a specification document or a covering email.

    This is the only place a model creates a fact, and everything it creates is
    written INFERRED with a confidence, so the UI can badge which half of the
    picture was observed and which was concluded - and so the fail-closed
    safety gate applies to the right half.

    Three checks stand between the reply and the store: the attribute path must
    exist in ``attr_defs``, the entity must exist in the catalog, and the value
    must parse as the declared dtype. A path a model invents is a change the
    catalog cannot apply, so it is dropped with the reason recorded rather than
    written and discovered later.
    """
    base = baseline_mod.get()
    run_id = state["run_id"]
    recorded = _iso(state.get("as_of_recorded"))
    hint = _catalog_hint(base)

    new_signals: list[dict] = []
    traces: list[dict] = []
    errors: list[str] = []
    spent: list[LlmUsage] = []
    latest = recorded

    documents: list[tuple[str, object]] = []
    for event_id in state.get("event_ids", []):
        row = db.one("SELECT * FROM events WHERE id = ?", (event_id,))
        if row is None:
            continue
        documents.append((event_id, tape._row_to_event(row)))

    def read_one(item: tuple) -> tuple:
        """One document, read by the model or from its structured hint.

        A reading depends on the catalog and the document alone - never on what
        a previous document wrote - which is precisely why this half may be done
        concurrently and the persistence below may not.

        Nothing here writes: the audit line, the facts and the watermark all
        belong to the sequential pass, so a reading that is later skipped as
        immaterial has cost a call and changed nothing.
        """
        event_id, event = item
        try:
            extracted, usage = gateway.complete_json(
                extract_messages(base, event, hint),
                model=fast_model(), agent="extract", run_id=run_id)
            return event_id, event, extracted, usage, fast_model(), None
        except GatewayError as exc:
            # The structured hint every tape event carries. It is the
            # machine-readable form of the same notice rather than a reading of
            # it, which is why it can stand in for the model without pretending
            # to be an observation.
            return (event_id, event, _extraction_from_payload(event), None,
                    None, exc)

    if len(documents) > 1 and MAX_EXTRACT_WORKERS > 1:
        with ThreadPoolExecutor(
                max_workers=min(MAX_EXTRACT_WORKERS, len(documents)),
                thread_name_prefix="extract") as pool:
            readings = list(pool.map(read_one, documents))
    else:
        readings = [read_one(item) for item in documents]

    # The writes stay in tape order, and that is not a stylistic preference.
    # `latest` is a watermark that advances as each document is persisted, and
    # the next document is read against it, so that a covering email restating
    # its own specification sees what the specification already wrote. Persist
    # these concurrently and the same correction is asserted twice.
    for event_id, event, extracted, usage, model_name, outage in readings:
        payload = event.payload or {}
        if usage is not None:
            spent.append(usage)
        if outage is not None:
            # One line, not one per document: the gateway being down is a
            # single fact about the run, and repeating it fourteen times buries
            # the extraction errors that are worth reading.
            #
            # Deduplicated on the *fact* rather than on the sentence. The
            # gateway phrases the same outage two ways - the first document
            # meets a refused connection, and every document after it meets the
            # circuit breaker refusing to try again - so a membership test
            # against the text let one outage through twice, and would let it
            # through a third time the next time the wording changed.
            message = f"extract: {outage}"
            if not any(_same_outage(message, e) for e in errors):
                errors.append(message)
            traces.append(step("extract", f"{event_id} read from its structured "
                                          f"hint - no model available",
                               error=str(outage)[:160]))

        planning.audit("extract", "EXAMINE", "event", event_id,
                       {"material": extracted.get("material"),
                        "kind": extracted.get("kind")},
                       Provenance(kind=ProvenanceKind.INFERRED, agent="extract",
                                  model=model_name, run_id=run_id,
                                  confidence=extracted.get("confidence")))

        if not extracted.get("material"):
            traces.append(step("extract", f"{event_id} reads as immaterial",
                               subject=payload.get("subject")))
            continue

        rows, dropped, considered = _extraction_rows(base, event, extracted, latest)
        for reason in dropped:
            errors.append(f"extract({event_id}): {reason}")

        if considered and not rows:
            # The document named attributes and every one of them is already on
            # file - a covering email restating its own specification. Emitting
            # a signal here would put an empty notice on top of the correction
            # it accompanies and retire it.
            traces.append(step("extract",
                               f"{event_id} restates values already on file",
                               rejected=dropped))
            continue

        signals, wrote_at = _persist_extraction(event, extracted, rows, recorded,
                                                run_id, model_name)
        # The watermark the next document is read against. A covering email
        # restating the specification it accompanies has to see what the
        # specification already wrote, or the same correction is asserted twice.
        latest = max(latest, wrote_at)
        new_signals.extend(signals)
        written = sum(1 for s in signals if s.get("attribute_paths")
                      and s["kind"] != str(CorrectionKind.SOURCE_CONFLICT))
        traces.append(step(
            "extract",
            f"{event_id}: {signals[0]['kind'] if signals else 'nothing'} - "
            f"{len(rows)} value(s) read, {written} recorded",
            confidence=extracted.get("confidence"),
            applies_to=extracted.get("applies_to"),
            correction=bool(extracted.get("is_correction")),
            conflicts=[s["id"] for s in signals
                       if s["kind"] == str(CorrectionKind.SOURCE_CONFLICT)],
            rejected=dropped))

    if not traces:
        # A node that ran must say so. The graph view infers which nodes
        # executed from the trace, and a silent node renders as "not taken",
        # which reads as a branch that was skipped rather than one with nothing
        # to do.
        traces.append(step("extract", "no unread supplier documents"))

    update: dict = {"signals": new_signals, "trace": traces, "errors": errors,
                    "usage": _spend("extract", *spent), "status": "EXTRACTING"}
    if latest > recorded:
        # A correction is recorded strictly after the fact it supersedes, so
        # writing one can push past the instant the run pinned. The run has to
        # be able to see what it just learned, so the recorded axis advances to
        # cover its own writes and no further.
        update["as_of_recorded"] = latest.isoformat()
    return update


def extract_messages(base, event, hint: dict | None = None) -> list[dict]:
    """The exact prompt this node puts in front of a model, for one document.

    Public because ``scripts/evaluate.py`` grades the extractor against the
    answer key and has to grade the prompt that ships. A scorer that rebuilt
    the messages itself would go on reporting yesterday's accuracy the first
    time this prompt was revised, which is the failure an eval exists to catch.
    """
    payload = event.payload or {}
    return [
        {"role": "system", "content": prompts.EXTRACT_SYSTEM},
        {"role": "user", "content": prompts.extract_user(
            str(payload.get("doc_id", "")),
            str(payload.get("doc_version", "")),
            str(payload.get("kind", "") or event.type),
            str(payload.get("from", "") or payload.get("supplier", "")),
            str(payload.get("subject", "") or payload.get("summary", "")),
            _document_text(base, event), event.ts.isoformat(),
            _catalog_hint(base) if hint is None else hint)},
    ]


def _catalog_hint(base) -> dict:
    """The paths and ids an extraction is allowed to name.

    Spliced into the prompt from the catalog itself, so "anything not here does
    not exist" is true rather than aspirational.
    """
    return {
        "attribute_paths": [
            f"{path} ({d.dtype}{', ' + d.unit if d.unit else ''}"
            f"{', safety-class' if d.safety_class else ''})"
            for path, d in sorted(base.attr_defs.items())
        ],
        "products": [f"{p.id} {p.name} [{p.category}]"
                     for p in sorted(base.catalog.products, key=lambda p: p.id)],
        "variants": [f"{v.id} {v.name} ({v.product_id}"
                     f"{', base model' if v.is_base else ''})"
                     for v in sorted(base.catalog.variants, key=lambda v: v.id)],
    }


def _document_text(base, event) -> str:
    """The document to read: the event's own body, or the text on disk.

    ``SourceDoc.body_path`` is where the seed pack keeps a document's extracted
    text, and it is the seam a real parser plugs into later - so a notice that
    arrives as a reference rather than as a body is still read rather than
    silently reduced to its structured hint.

    Two guards. The version has to match: the file named by ``body_path`` is
    one revision of the document, and feeding v1's text to a v2 notice would
    have the run extract superseded values as if they were the correction.
    And an unreadable file degrades to the empty body the caller already
    handles - a document that cannot be opened must not end a run mid-flight.
    """
    if event.body:
        return event.body

    payload = event.payload or {}
    doc = base.source_docs.get(str(payload.get("doc_id") or ""))
    named = str(payload.get("doc_version") or "")
    if doc is None or not doc.body_path or (named and named != doc.version):
        return ""
    try:
        return (baseline_mod.data_dir() / doc.body_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _extraction_from_payload(event) -> dict:
    """The deterministic reading: the structured hint the event carries.

    Shaped exactly like the model's reply so one persistence path serves both,
    which is what keeps the fallback honest - it writes the same kind of fact,
    through the same validation, with its own confidence.
    """
    payload = event.payload or {}
    paths = [str(payload.get("attribute_path") or "")]
    paths += [str(c.get("attribute_path") or "")
              for c in payload.get("changes") or [] if isinstance(c, dict)]

    kind = None
    if payload.get("withdraws") or payload.get("resolves_issue"):
        kind = str(CorrectionKind.DOC_WITHDRAWN)
    elif payload.get("conflicts_with"):
        kind = str(CorrectionKind.SOURCE_CONFLICT)
    # Flags a supplier cannot set. These arrive on the regulatory feed, they
    # say the sale itself is in question rather than any value in the record,
    # and they are read before the paths because a takedown that also revised
    # a weight is a takedown.
    elif payload.get("takedown"):
        kind = str(CorrectionKind.REGULATORY_ORDER)
    elif payload.get("recall"):
        kind = str(CorrectionKind.SAFETY_RECALL)
    elif payload.get("export_restricted"):
        kind = str(CorrectionKind.EXPORT_RESTRICTION)
    elif payload.get("rule_change"):
        kind = str(CorrectionKind.LEGAL_REQUIREMENT_CHANGE)
    else:
        # Most consequential path wins, and `KIND_BY_PATH` is in that order,
        # so the earliest entry any path matches is the answer.
        best = len(KIND_BY_PATH)
        for path in paths:
            if not path:
                continue
            named = _kind_for_path(path)
            rank = next((i for i, (_p, k) in enumerate(KIND_BY_PATH)
                         if k == named), len(KIND_BY_PATH))
            if rank < best:
                best, kind = rank, named
            elif kind is None:
                kind = named
    entities = [str(e) for e in payload.get("entities") or [] if e]

    return {
        "material": bool(payload.get("material_hint", True)),
        "kind": kind or str(CorrectionKind.SPEC_CORRECTION),
        "entity_guess": entities[0] if entities else None,
        "product_guess": payload.get("product"),
        "attribute_path": payload.get("attribute_path"),
        "old_value": payload.get("old_value"),
        "new_value": payload.get("new_value"),
        "unit": payload.get("unit"),
        "effective": payload.get("effective_from"),
        "applies_to": str(payload.get("applies_to") or "UNCLEAR").upper(),
        "is_correction": bool(payload.get("is_correction")),
        "resolves_issue": bool(payload.get("resolves_issue")),
        "provisional": bool(payload.get("provisional")),
        "confidence": FALLBACK_CONFIDENCE,
        "quote": str(payload.get("summary") or payload.get("subject") or ""),
        "changes": payload.get("changes"),
    }


def _resolve_entity(base, named) -> str:
    """Map what a document called something onto a catalog id, or give up.

    A model asked for an id routinely answers with the label it read - "PRD-01
    Northaven AP300 Air Purifier [home.air-treatment.purifiers]" - and passing that
    through as an id refuses an extraction that was right about the value and
    only wrong about the name. Nothing here guesses: resolution is by identity
    alone - an exact id, the id the label leads with, an exact product or
    variant name, or an id spelled out inside the label. A variant wins over the
    product it belongs to, because it is the more specific claim. Anything else
    still comes back empty and is still refused, with the text on the record.
    """
    text = str(named or "").strip()
    if not text:
        return ""
    if text in base.variants or text in base.products:
        return text

    head = text.split()[0].strip("[](),.:;")
    if head in base.variants or head in base.products:
        return head

    lowered = text.casefold()
    for holder in (base.variants, base.products):
        for entity_id in sorted(holder):
            if holder[entity_id].name.casefold() == lowered:
                return entity_id

    for entity_id in sorted(base.variants) + sorted(base.products):
        if re.search(rf"\b{re.escape(entity_id)}\b", text):
            return entity_id
    return ""


def _coerce(value, dtype: str):
    """Parse an extracted value as its declared type, or refuse.

    Repair is limited to shape - ``"65"`` for an int, a comma-joined string for
    a list. A value that cannot be read as its type is not a value; guessing
    one would put a number on a page that nobody asserted.
    """
    if value is None:
        return None, "no value"
    try:
        if dtype == "int":
            if isinstance(value, bool):
                return None, "expected int, got bool"
            return int(str(value).strip()), ""
        if dtype == "float":
            if isinstance(value, bool):
                return None, "expected float, got bool"
            return float(str(value).strip()), ""
        if dtype == "bool":
            if isinstance(value, bool):
                return value, ""
            return None, f"expected bool, got {value!r}"
        if dtype == "list[str]":
            if isinstance(value, list):
                return [str(x).strip() for x in value], ""
            parts = [p.strip() for p in str(value).split(",") if p.strip()]
            return parts, ""
        return str(value), ""
    except (TypeError, ValueError):
        return None, f"{value!r} does not parse as {dtype}"


def _same_outage(message: str, existing: str) -> bool:
    """Are these two lines the same outage, reported twice?

    Same stage, and both of them the gateway being unreachable. That is the
    whole test: an outage is a fact about the run, and the run has either met
    one or it has not - which of the gateway client's two phrasings the first
    worker happened to get is not something a reviewer should have to reason
    about.
    """
    if message.split(":", 1)[0] != existing.split(":", 1)[0]:
        return False
    unreachable = ("cannot reach", "unreachable")
    return (any(w in message for w in unreachable)
            and any(w in existing for w in unreachable))


def _extraction_rows(base, event, extracted: dict,
                     read_at: datetime) -> tuple[list[dict], list[str]]:
    """Validate an extraction into attribute rows the catalog can apply.

    The reply template carries one attribute path, and a supplier document
    routinely corrects several - the finale revises a wattage and a measured
    noise level in the same revision. So rows the structured hint declares for
    a (entity, path) the model did not name are folded in and put through the
    identical validation, rather than being lost to the shape of the template.

    Read at the end of the horizon rather than at the document's own date: a
    change announced ahead of its effective date has still been asserted, and
    asserting it a second time when the covering email repeats it would
    manufacture a correction history out of one notice.
    """
    horizon_end = datetime.combine(
        base.horizon_start + timedelta(days=base.horizon_days), datetime.min.time())
    ov = overlay_mod.build(horizon_end, read_at)
    effective = dict(base.attr_values)
    for key, attr_state in ov.attr_values.items():
        effective[key] = attr_state.value

    named = [extracted.get("entity_guess"), extracted.get("product_guess"),
             *(event.payload.get("entities") or [])]
    entity_hint = next((resolved for resolved in
                        (_resolve_entity(base, n) for n in named) if resolved), "")
    # What the document called it, kept for the refusal message: "no such
    # product or variant ''" tells a reviewer nothing about what was rejected.
    hint_label = next((str(n) for n in named if n), "")

    candidates: list[dict] = [{
        "entity_id": entity_hint,
        "attribute_path": extracted.get("attribute_path"),
        "new_value": extracted.get("new_value"),
        "old_value": extracted.get("old_value"),
        "unit": extracted.get("unit"),
    }]
    for raw in (extracted.get("changes") or event.payload.get("changes") or []):
        if isinstance(raw, dict):
            candidates.append(raw)

    rows: list[dict] = []
    dropped: list[str] = []
    seen: set[tuple[str, str]] = set()
    considered = 0

    for raw in candidates:
        entity_id = _resolve_entity(base, raw.get("entity_id")) or entity_hint
        path = str(raw.get("attribute_path") or "")
        if not path:
            continue  # a notice with nothing the catalog can hold; still a signal
        considered += 1
        if path not in base.attr_defs:
            dropped.append(f"no such attribute {path!r}")
            continue
        if not entity_id:
            dropped.append(f"no such product or variant "
                           f"{str(raw.get('entity_id') or hint_label)!r}")
            continue
        if (entity_id, path) in seen:
            continue
        seen.add((entity_id, path))

        definition = base.attr_defs[path]
        value, why = _coerce(raw.get("new_value"), definition.dtype)
        if why:
            dropped.append(f"{entity_id} {path}: {why}")
            continue
        was = effective.get((entity_id, path))
        if value == was:
            # A restatement of a value already in force is a confirmation, not
            # a correction. Recording it would put a no-op action on the
            # reviewer's diff and inflate every count under it.
            continue

        rows.append({
            "entity_id": entity_id,
            "attribute_path": path,
            "value": value,
            "old_value": was if raw.get("old_value") is None else raw.get("old_value"),
            "unit": definition.unit or raw.get("unit"),
            "safety": definition.safety_class,
            # Which document the value being replaced is standing on. POL-002
            # is settled against this rather than against arrival order.
            "held_doc": _standing_doc(base, ov, (entity_id, path)),
        })

    return rows, dropped, considered


def _standing_doc(base, ov, key: tuple[str, str]) -> str:
    """The document behind the value in force, or behind the prepared content."""
    attr_state = ov.attr_values.get(key)
    if attr_state is not None:
        head = _fact_head(attr_state)
        if head is not None:
            return (head.provenance.source_id or "").partition(":")[0]
    source = base.attr_sources.get(key)
    return source.doc_id if source else ""


def _valid_from(effective, fallback: datetime) -> datetime:
    """When the corrected value becomes true in the world.

    Not the day the document arrived: a shared-line allergen change announced
    three weeks ahead is true from the date the supplier names, and content has
    to be prepared against that date rather than against today.
    """
    try:
        return (datetime.combine(date.fromisoformat(str(effective)),
                                 datetime.min.time())
                if effective else fallback)
    except (TypeError, ValueError):
        return fallback


def _persist_extraction(event, extracted: dict, rows: list[dict],
                        recorded: datetime, run_id: str,
                        model: str | None) -> tuple[list[dict], datetime]:
    """Write extracted values into the bitemporal store, one signal per row.

    ``supersedes_id`` is passed **only** when the document says it is revising
    a value, and only when there is a fact about the same entity and attribute
    to revise. Chaining two independent notices would fabricate a correction
    history, and superseding a fact about a different entity is not possible at
    all - a fact about the product is not a fact about the variant, which is
    the distinction the whole scenario turns on.
    """
    base = baseline_mod.get()
    payload = event.payload or {}
    doc_id = str(payload.get("doc_id", ""))
    version = str(payload.get("doc_version", ""))
    confidence = _confidence(extracted)
    valid_from = _valid_from(extracted.get("effective"), event.ts)
    is_correction = bool(extracted.get("is_correction"))
    source = {"doc_id": doc_id, "version": version,
              "excerpt": str(extracted.get("quote") or "")[:300]}
    provenance = {"kind": str(ProvenanceKind.INFERRED), "source_id": event.id,
                  "confidence": confidence, "agent": "extract", "model": model,
                  "run_id": run_id}

    signals: list[dict] = []
    latest = recorded

    if not rows:
        # A notice the catalog cannot hold a value for is still a notice - the
        # kettle dimensions "under review pending a tooling audit" has no path
        # in attr_defs and is exactly the signal a withdrawal has to clear.
        signals.append({
            "id": f"SIG-{event.id}",
            "kind": _extracted_kind(extracted, []),
            "detected_at": event.ts.isoformat(),
            "entities": sorted({resolved for resolved in (
                _resolve_entity(base, extracted.get("entity_guess")),
                _resolve_entity(base, extracted.get("product_guess"))) if resolved}),
            "attribute_paths": [],
            "summary": str(extracted.get("quote") or payload.get("subject") or "")[:300],
            "source_event_id": event.id,
            "source": source,
            "resolves_issue": bool(extracted.get("resolves_issue")),
            "provisional": bool(extracted.get("provisional")),
            "provenance": provenance,
        })
        return signals, latest

    for index, row in enumerate(rows, start=1):
        entity_id, path = row["entity_id"], row["attribute_path"]
        entity_type = "variant" if entity_id in base.variants else "product"
        signal_id = (f"SIG-{event.id}" if len(rows) == 1
                     else f"SIG-{event.id}-{index}")
        unit = f" {row['unit']}" if row.get("unit") else ""
        held_doc = row.get("held_doc") or ""

        if (held_doc and held_doc != doc_id
                and precedence(base, doc_id) < precedence(base, held_doc)):
            # POL-002 settles this, not arrival order. Recording the value
            # would let a sales email quietly beat the pack label, so the
            # disagreement is raised and the higher-ranked value stays in force.
            signals.append({
                "id": signal_id,
                "kind": str(CorrectionKind.SOURCE_CONFLICT),
                "detected_at": event.ts.isoformat(),
                "entities": [entity_id, held_doc, doc_id],
                "attribute_paths": [path],
                "old_value": row.get("old_value"),
                "new_value": row["value"],
                "unit": row.get("unit"),
                "summary": (f"{doc_id} {version} (precedence "
                            f"{precedence(base, doc_id)}) says {entity_id} "
                            f"{path} is {row['value']}{unit}; {held_doc} "
                            f"(precedence {precedence(base, held_doc)}) has "
                            f"{row.get('old_value')} - POL-002 keeps "
                            f"{held_doc}, so this value is not recorded"),
                "source_event_id": event.id,
                "source": source,
                "resolves_issue": False,
                "provisional": bool(extracted.get("provisional")),
                "provenance": provenance,
            })
            continue

        prior = (store.get(entity_type, entity_id, path, as_of_valid=valid_from,
                           as_of_recorded=recorded) if is_correction else None)

        ingest.record_attribute(
            entity_id=entity_id, attribute_path=path, value=row["value"],
            valid_from=valid_from, source_event_id=event.id, source_doc=doc_id,
            source_version=version, confidence=confidence, agent="extract",
            model=model, run_id=run_id, recorded_at=recorded,
            supersedes_id=prior.id if prior else None)
        if prior is not None:
            # record_attribute pushes a correction one tick past what it
            # supersedes so the two do not tie on the recorded axis; the run
            # has to know it did, or it cannot read its own writes back.
            latest = max(latest, prior.recorded_at + timedelta(microseconds=1))

        signals.append({
            "id": signal_id,
            "kind": _extracted_kind(extracted, [path]),
            "detected_at": event.ts.isoformat(),
            "entities": [entity_id],
            "attribute_paths": [path],
            "old_value": row.get("old_value"),
            "new_value": row["value"],
            "unit": row.get("unit"),
            "window_start": valid_from.date().isoformat(),
            "summary": (f"{doc_id} {version} corrects {entity_id} {path}: "
                        f"{row.get('old_value')} -> {row['value']}{unit}"),
            "source_event_id": event.id,
            "source": source,
            "resolves_issue": bool(extracted.get("resolves_issue")),
            "provisional": bool(extracted.get("provisional")),
            "provenance": provenance,
        })

    return signals, latest


def _confidence(extracted: dict) -> float:
    try:
        return max(0.0, min(1.0, float(extracted.get("confidence"))))
    except (TypeError, ValueError):
        return FALLBACK_CONFIDENCE


def _extracted_kind(extracted: dict, paths: list[str]) -> str:
    """The model's classification, checked against the paths it named."""
    named = str(extracted.get("kind") or "").upper()
    try:
        kind = str(CorrectionKind(named))
    except ValueError:
        kind = ""
    for path in paths:
        derived = _kind_for_path(path)
        # Allergens are not a judgement call: a path in the allergen family is
        # an allergen change whatever the document was mostly about.
        if derived == str(CorrectionKind.ALLERGEN_CHANGE):
            return derived
    return kind or (_kind_for_path(paths[0]) if paths
                    else str(CorrectionKind.SPEC_CORRECTION))


# ---------------------------------------------------------------------------
# scope_case - extraction is global, action is case-scoped
# ---------------------------------------------------------------------------


def scope_case(state: FactoryState) -> dict:
    """Narrow the run to one product's correction, now that every document is read.

    The filter has to sit *after* extraction, and that is the whole reason this
    is a node rather than three lines in ``monitor``. ``monitor`` derives signals
    from the facts in force, and a correction sitting in an unread supplier
    document is not yet a fact - so a case filter applied there sees an empty
    record, and ``extract`` then appends every correction it reads behind it,
    unfiltered. That is how a snack bar's allergen reached the triage of an
    air-purifier case and put another product's id in the escalation sentence
    rendered on two screens.

    Extraction stays global and action is case-scoped: ``extract`` still reads
    every unexamined document and records every fact, because facts are facts,
    a document is read once, and skipping one would mean the run that eventually
    decides *that* case never sees it. This is where the two part company, so
    everything downstream - triage, the blast radius, the scope resolver, the
    recommendation and the approval gate - sees one case's signals only.

    Its own step rather than a filter at the head of ``triage``, because which
    corrections a run is allowed to act on is a decision in its own right: it is
    what the reviewer is being asked to approve the boundary of, and it belongs
    in the trace where they can read it.
    """
    base = baseline_mod.get()
    signals = state.get("signals") or []
    cases = open_cases(signals, base)

    case_id = str(state.get("case_id") or "")
    chosen = next((c for c in cases if c["case_id"] == case_id), None)
    others = [_case_view(c) for c in cases if c["case_id"] != case_id]

    if case_id:
        # A named case with nothing open carries nothing. Falling back to every
        # signal would turn a scoped run into an unscoped one without saying so.
        kept = chosen["signals"] if chosen else []
        summary = (f"case {case_id}: {chosen['title']}" if chosen
                   else f"case {case_id}: nothing open")
    else:
        # Nothing was open when the run began, so there was no list to pick
        # from - this is the pass that reads the documents and opens the cases.
        # Choosing one here would decide a case the caller never saw, so the run
        # stays unscoped and reports every case it opened for a later, scoped run
        # to be started against.
        kept = signals
        summary = f"no case was open to scope to - {len(cases)} opened by this run"

    return {
        "case_id": case_id,
        "case": _case_view(chosen) if chosen else {},
        "other_open_cases": others,
        # RESET replaces the accumulated list rather than adding to it: the
        # merge reducer appends, so returning the in-case signals alone would
        # leave the out-of-case ones exactly where they already are.
        "signals": [RESET, *kept],
        "status": "CASE_SCOPED",
        "trace": [step("scope_case",
                       f"{summary}, {len(kept)} of {len(signals)} correction(s) "
                       f"in scope, {len(others)} other case(s) open",
                       case_id=case_id,
                       other_cases=[c["case_id"] for c in others],
                       out_of_case=sorted(
                           {str(s.get("id") or "") for s in signals}
                           - {str(s.get("id") or "") for s in kept}),
                       severity_hint=chosen["severity_hint"] if chosen else None)],
    }


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------


def triage(state: FactoryState) -> dict:
    """Classify severity on the combined reach of everything in play.

    The model applies a retrieved policy to a blast radius it did not compute.
    Two things are then taken out of its hands, deterministically and whatever
    it said: a correction touching a safety-class attribute, or any variant of
    a regulated product, is CRITICAL and material. That is not a tie-break, it
    is a rule - an allergen is not a matter of classification judgement, and a
    model that could argue one down would be a model that could publish one.
    """
    signals = state.get("signals", [])
    if not signals:
        return {"material": False, "severity": "LOW",
                "triage_reason": "no corrections detected",
                "status": "QUIET",
                "trace": [step("triage", "nothing to investigate")]}

    blast = _blast_radius(signals, state.get("as_of"))
    policy = _policy_extract("correction severity classification material change")
    escalation = _forced_escalation(signals, blast, str(state.get("case_id") or ""))

    spent: list[LlmUsage] = []
    try:
        verdict, usage = gateway.complete_json(
            [{"role": "system", "content": prompts.TRIAGE_SYSTEM},
             {"role": "user", "content": prompts.triage_user(
                 signals, blast, policy)}],
            model=fast_model(), agent="triage", run_id=state["run_id"])
        spent.append(usage)
        severity = str(verdict.get("severity", "MEDIUM")).upper()
        material = bool(verdict.get("material", True))
        reason = str(verdict.get("reason", ""))
        errors: list[str] = []
    except GatewayError as exc:
        severity, material, reason = _triage_fallback(blast)
        errors = [f"triage: {exc}"]

    if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        severity = "MEDIUM"

    if escalation:
        severity, material = "CRITICAL", True
        reason = f"escalated by policy: {escalation}. " + reason

    return {"severity": severity, "material": material, "triage_reason": reason,
            "affected": blast, "status": "TRIAGED", "errors": errors,
            "usage": _spend("triage", *spent),
            "trace": [step("triage", f"{severity}, material={material}"
                           + (" (measured, no model)" if errors else ""),
                           reason=reason, escalated=escalation,
                           totals=blast["totals"])]}


def _case_products(base, signals: list[dict], case_id: str) -> set[str]:
    """The products a run is deciding about.

    A case is one product, so a named case answers this by itself. Without one
    it is whatever the signals name directly - never what tracing them reaches.
    """
    if case_id and case_id in base.products:
        return {case_id}
    return set(_products_of(base, signals))


def _forced_escalation(signals: list[dict], blast: dict, case_id: str = "") -> str:
    """The measured grounds for overriding a soft classification, if any.

    Measured within the case, as a second line of defence behind the case
    filter. A blast radius unions the derivation trace of every signal, so it
    legitimately reaches products this run is not deciding about: tracing a
    document a correction cites arrives at everything else that document
    describes. Escalating an air-purifier case because a snack sharing a sales
    channel is regulated is wrong reasoning even where the signal set is right,
    so the regulated test is taken over the products the case is about rather
    than over everything the trace touched.
    """
    base = baseline_mod.get()
    in_case = _case_products(base, signals, case_id)
    scoped = [s for s in signals if case_of(s, base) in in_case] if in_case else signals
    safety = sorted({path for s in scoped for path in s.get("attribute_paths") or []
                     if path in base.attr_defs and base.attr_defs[path].safety_class})
    regulated = sorted({p for p in blast["affected"].get("products", [])
                        if p in base.products and base.products[p].regulated
                        and (not in_case or p in in_case)})
    # An order from an authority is a ground on its own. The two tests above
    # both read the *record* - which attributes are safety-class, which
    # products are regulated - and a withdrawal notice can name a product where
    # neither is true. The gravity is in the notice, not in the catalog.
    ordered = sorted({str(s.get("kind")) for s in scoped
                      if str(s.get("kind")) in GRAVE_KINDS})
    parts = []
    if safety:
        parts.append(f"{', '.join(safety)} is safety-class")
    if regulated:
        parts.append(f"{', '.join(regulated)} is regulated")
    if ordered:
        parts.append(f"{', '.join(ordered).lower().replace('_', ' ')} in scope")
    return "; ".join(parts)


def _triage_fallback(blast: dict) -> tuple[str, bool, str]:
    """Deterministic severity when no model is available. Thresholds only.

    Reach is counted in published surfaces rather than in fields, and a channel
    with a freeze window counts for more: a printed catalogue cannot be
    corrected after it goes to press, so one attribute reaching it outranks
    five reaching a web page.
    """
    base = baseline_mod.get()
    totals = blast["totals"]
    channels = blast["affected"].get("channels", [])
    frozen = sorted(c for c in channels
                    if c in base.channels and base.channels[c].freeze_days > 0)

    if totals["safety_flags"] or totals["regulated"]:
        return "CRITICAL", True, ("safety-class or regulated content exposed "
                                  "(measured)")
    if frozen:
        return "HIGH", True, (f"{', '.join(frozen)} has a freeze window and "
                              f"{totals['listings']} listings are exposed (measured)")
    if totals["listings"] > 8:
        return "HIGH", True, f"{totals['listings']} listings exposed (measured)"
    if totals["listings"] > 0:
        return "MEDIUM", True, f"{totals['listings']} listings exposed (measured)"
    return "LOW", False, "no prepared content reached"


def _blast_radius(signals: list[dict], as_of: str | None = None) -> dict:
    """Union the derivation traces of every signal.

    Delegated to the lineage-analyst peer, which unions
    ``network.trace_dependencies`` per entity. Computed from the lineage the
    content was actually built with and never from a model - this is the figure
    the triage prompt is told to treat as authoritative, and a blast radius a
    model could influence would be a blast radius nobody could check.
    """
    entities = sorted({str(e) for s in signals or []
                       for e in s.get("entities") or [] if e})
    if not entities:
        empty = {"products": [], "variants": [], "attributes": [], "assets": [],
                 "listings": [], "channels": []}
        return {"roots": [], "affected": empty, "chain": [],
                "totals": {"fields": 0, "assets": 0, "listings": 0, "channels": 0,
                           "safety_flags": 0, "regulated": 0},
                "summary": "no catalog entity named"}

    return a2a_client.call("lineage-analyst",
                           {"entities": entities, "depth": 3, "as_of": as_of})


# The explanation each relation carries into the reviewer's causal chain. The
# walk is structural, so the words are fixed rather than written per run.
_RELATION_WORDS = {
    "supersedes": "replaces the version the prepared content was written against",
    "defines": "is the document that asserts this value",
    "derives": "was written from this value",
    "contains": "is a sellable form of this product",
    "lists_on": "is published through this listing",
    "feeds": "sends this listing to the channel",
}

MAX_CHAIN_LINKS = 24


def _causal_chain(blast: dict) -> list[dict]:
    """The lineage walk, phrased as the chain a reviewer reads.

    Structural, not narrated: every link is an edge the catalog already holds,
    so the explanation is a label rather than an argument.
    """
    chain = []
    for link in (blast.get("chain") or [])[:MAX_CHAIN_LINKS]:
        relation = str(link.get("relation", ""))
        chain.append({
            "from_ref": link.get("from", ""),
            "to_ref": link.get("to", ""),
            "relation": relation,
            "explanation": (f"{link.get('from', '')} "
                            f"{_RELATION_WORDS.get(relation, relation)} "
                            f"{link.get('to', '')}"),
            "evidence": [],
        })
    return chain


# ---------------------------------------------------------------------------
# resolve_scope - the bounded exception step
# ---------------------------------------------------------------------------


def resolve_scope(state: FactoryState) -> dict:
    """Work out which variants each correction applies to.

    This is the one judgement in the system that no rule settles, and the one
    node where a model chooses an action rather than describing one. It is
    given a closed, read-only tool desk (``sc.graph.evidence``) and may ask for
    specific lookups before concluding, up to ``MAX_PASSES`` extra rounds -
    that is what the brief means by an investigation whose path depends on what
    the correction touches.

    Three things keep it honest. The readings themselves are enumerated from
    the catalog by the resolution-planner peer, so the model argues among
    answers the record supports rather than inventing one. The mandatory
    evidence is resolved *before* the model is asked anything, because "does
    this apply to the base or the variant" is a question about the current
    catalog and a retrieved postmortem will happily assert an answer that the
    model then believes. And every request, refusal and answer lands in the run
    trace, so "the agent decided what to look at next" is visible rather than
    asserted.

    With the gateway down the enumeration still stands and the widest reading
    is taken, with low confidence and a rationale that says why. Fail safe, not
    fail silent: a correction applied too widely republishes a number on a page
    it does not belong on, which a reviewer can see and reject; one applied too
    narrowly leaves a wrong number live, which nobody sees at all.
    """
    base = baseline_mod.get()
    signals = [s for s in state.get("signals", [])
               if s.get("attribute_paths") and s.get("new_value") is not None]
    blast = state.get("affected") or _blast_radius(signals, state.get("as_of"))

    tables, readings = _enumerate_scopes(base, signals, state.get("as_of"))
    deterministic = _product_readings(base, signals, readings)

    query = " ".join(s.get("summary", "") for s in signals)[:400]
    guidance = retrieve.search(query or "which variant does a correction apply to",
                               top_k=5, doc_types=["POLICY", "STANDARD", "CHANNEL"])
    priors = retrieve.search(query or "variant correction scope", top_k=4,
                             doc_types=["POSTMORTEM"])
    citations = retrieve.cite(guidance) + retrieve.cite(priors)
    prior_ids = sorted({c["doc_id"] for c in retrieve.cite(priors)})

    traces: list[dict] = []
    spent: list[LlmUsage] = []
    # Resolved before the investigator is asked anything - the reasoning is in
    # evidence.mandatory_requests and still holds.
    gathered = evidence.run_requests(evidence.mandatory_requests(signals, blast))
    citations.extend(evidence.citations_from(gathered))
    if gathered:
        traces.append(step("resolve_scope",
                           "resolved before concluding: " + ", ".join(
                               f"{r['tool']}({r['argument']})" for r in gathered),
                           pass_number=0, requests=_request_trace(gathered)))

    versions = {r["argument"]: r["result"] for r in gathered
                if r["tool"] == "source_versions"}
    rendered = "\n\n".join(prompts.variant_rows(t) for t in tables) or "(none)"

    def finish(candidates: list[dict], rejected: list[dict], errors: list[str],
               note: str, **detail) -> dict:
        traces.append(step("resolve_scope", note,
                           candidates=[f"{c['level']}:{','.join(c['entities'])}"
                                       for c in candidates],
                           rejected=[r["why"] for r in rejected][:4],
                           evidence_requests=len(gathered),
                           agent_requests=sum(1 for r in gathered
                                              if r.get("origin") == "AGENT"),
                           **detail))
        return {
            "scope_candidates": candidates,
            "rejected_actions": rejected,
            "causal_chain": _causal_chain(blast),
            "root_causes": [s["id"] for s in signals],
            "symptoms": [s["id"] for s in state.get("signals", [])
                         if s.get("kind") == str(CorrectionKind.CHANNEL_REJECTION)],
            "prior_incidents": prior_ids,
            "citations": _dedupe_citations(citations),
            "evidence_log": gathered,
            "affected": blast,
            "status": "SCOPED",
            "errors": errors,
            # One entry however many passes the investigation took: the node is
            # the unit a reviewer asks the cost of, not the round trip.
            "usage": _spend("resolve_scope", *spent),
            "trace": traces,
        }

    system = prompts.scope_system(evidence.catalogue())
    argued: dict = {}
    for attempt in range(evidence.MAX_PASSES + 1):
        final_pass = attempt == evidence.MAX_PASSES
        try:
            argued, usage = gateway.complete_json(
                [{"role": "system", "content": system},
                 {"role": "user", "content": prompts.scope_user(
                     signals, rendered, versions, _render(guidance),
                     _render(priors),
                     gathered=evidence.render(gathered) if gathered else "",
                     final_pass=final_pass)}],
                model=reasoning_model(), agent="resolve_scope",
                run_id=state["run_id"])
            spent.append(usage)
        except GatewayError as exc:
            widest = []
            for reading in _widest_readings(base, deterministic):
                widest.append({**reading, "confidence": 0.3, "rationale": (
                    "no model was available to argue a narrower reading, so the "
                    "correction is applied to every variant the record puts in "
                    "scope. " + reading.get("rationale", ""))[:400]})
            candidates, rejected = _merge_candidates(base, widest, [], readings)
            return finish(candidates, rejected, [f"resolve_scope: {exc}"],
                          "widest reading of each product - no model available "
                          "to narrow it", error=str(exc)[:160])

        requests = argued.get("requests") or []
        if not requests or final_pass:
            break

        records = evidence.run_requests(requests)
        gathered.extend(records)
        citations.extend(evidence.citations_from(records))
        versions.update({r["argument"]: r["result"] for r in records
                         if r["tool"] == "source_versions"})
        traces.append(step("resolve_scope",
                           "investigator asked for " + ", ".join(
                               f"{r['tool']}({r['argument']})" for r in records),
                           pass_number=attempt + 1,
                           requests=_request_trace(records)))

    candidates, rejected = _merge_candidates(base, deterministic,
                                             argued.get("candidates") or [],
                                             readings)
    return finish(candidates, rejected, [],
                  f"{len(candidates)} readings of the correction to validate, "
                  f"{len(rejected)} refused")


def _request_trace(records: list[dict]) -> list[dict]:
    return [{"tool": r["tool"], "argument": r["argument"], "why": r["why"],
             "status": r["status"], "origin": r["origin"]} for r in records]


def _products_of(base, signals: list[dict]) -> list[str]:
    """Every product a set of signals reaches, whatever kind of id they name."""
    products: set[str] = set()
    for signal in signals:
        for entity_id in signal.get("entities") or []:
            if entity_id in base.products:
                products.add(entity_id)
            elif entity_id in base.product_of_variant:
                products.add(base.product_of_variant[entity_id])
    return sorted(products)


def _named_variants(base, signals: list[dict], product_id: str) -> set[str]:
    return {e for s in signals for e in s.get("entities") or []
            if e in base.variants
            and base.product_of_variant[e] == product_id}


def _enumerate_scopes(base, signals: list[dict],
                      as_of: str | None) -> tuple[list[dict], dict[str, dict]]:
    """Ask the resolution-planner peer which readings the record supports.

    The peer enumerates - base only, one named variant, every variant - and
    attaches the documents behind each. It does not choose, and neither does
    this: choosing is the validator's job, and the reason that can be done by
    measurement is that every reading here becomes a change set the validator
    can price.
    """
    tables: list[dict] = []
    readings: dict[str, dict] = {}

    for product_id in _products_of(base, signals):
        relevant = [s for s in signals
                    if any(e == product_id
                           or base.product_of_variant.get(e) == product_id
                           for e in s.get("entities") or [])]
        answer = a2a_client.call("resolution-planner", {
            "product": product_id,
            "entities": sorted({e for s in relevant
                                for e in s.get("entities") or []}),
            "attribute_paths": sorted({p for s in relevant
                                       for p in s.get("attribute_paths") or []}),
            # The hint stays UNCLEAR on purpose: the peer scores it as one of
            # three checks, and a hint taken from the document being resolved
            # would let the document settle the question it raised.
            "applies_to": "UNCLEAR",
            "as_of": as_of,
        })
        if not answer.get("candidates"):
            continue
        readings[product_id] = answer
        tables.append({
            "product": base.products[product_id].model_dump(mode="json"),
            "variants": answer.get("variants", []),
            "attributes": answer.get("attributes", []),
        })

    return tables, readings


def _product_readings(base, signals: list[dict],
                      readings: dict[str, dict]) -> list[dict]:
    """Three readings of each product in play, and never a reading of two.

    A correction to the air purifier has nothing to say about the snack bar, so
    a candidate never spans products. Combining them - one pick per product,
    unioned - produced a scope holding another product's variants, a confidence
    that was the lowest of two unrelated arguments, and a rationale that was two
    level descriptions stapled together. None of the three is a reading of
    anything a reviewer can argue about.

    Per product these are the three worth validating: the narrowest the record
    supports, the variants the correction names, and every variant of the
    product.
    """
    out: list[dict] = []
    for product_id in sorted(readings):
        candidates = readings[product_id].get("candidates") or []
        if not candidates:
            continue
        named_ids = _named_variants(base, signals, product_id)
        widest = max(candidates, key=lambda c: len(c["entities"]))
        narrowest = sorted(candidates,
                           key=lambda c: (-c.get("confidence", 0.0),
                                          len(c["entities"]), c["entities"]))[0]
        named = next((c for c in candidates
                      if named_ids and set(c["entities"]) == named_ids), narrowest)

        seen: set[tuple[str, ...]] = set()
        for chosen in (narrowest, named, widest):
            entities = sorted(chosen["entities"])
            key = tuple(entities)
            if not entities or key in seen:
                continue
            seen.add(key)
            out.append({
                "level": _level_for(base, entities),
                "entities": entities,
                "confidence": round(float(chosen.get("confidence", 0.0)), 2),
                "rationale": str(chosen.get("rationale", ""))[:400],
                "evidence": sorted(chosen.get("evidence") or []),
            })

    return sorted(out, key=lambda c: (_scope_product(base, c),
                                      len(c["entities"]), c["entities"]))


def _scope_product(base, scope: dict) -> str:
    """The product a reading is about. Empty when it does not name one."""
    products = {base.product_of_variant[e] for e in scope.get("entities") or []
                if e in base.variants}
    return sorted(products)[0] if len(products) == 1 else ""


def _scope_problem(base, scope: dict) -> str:
    """Why the catalog cannot hold this reading, if it cannot.

    The same contract ``_validate_actions`` applies to actions: a candidate the
    planner cannot price is refused with its reason on the record rather than
    dropped, because "this reading was proposed and refused, because" is the
    useful answer to a reviewer.
    """
    entities = scope.get("entities") or []
    if not entities:
        return "a reading naming no variant is not a reading"

    unknown = sorted(e for e in entities if e not in base.variants)
    if unknown:
        return f"no such variant: {', '.join(unknown)}"

    products = sorted({base.product_of_variant[e] for e in entities})
    if len(products) > 1:
        return (f"a reading spans {', '.join(products)}; a correction to one "
                f"product cannot put another product's variants in scope")

    if scope.get("level") == str(ScopeLevel.VARIANT) and len(entities) > 1:
        return (f"VARIANT is one named variant, not {len(entities)}: "
                f"{', '.join(entities)}")
    return ""


def _level_for(base, entities: list[str]) -> str:
    """Name a reading from the variants it actually covers.

    Derived rather than taken on trust: a model that answers "BASE" while
    naming both variants has described the widest reading and labelled it the
    narrowest, and the label is what the reviewer reads.
    """
    products = {base.product_of_variant[e] for e in entities if e in base.variants}
    family = {v for p in products for v in base.variants_of.get(p, [])}
    if family and set(entities) == family:
        return str(ScopeLevel.ALL)
    if entities and all(e in base.variants and base.variants[e].is_base
                        for e in entities):
        return str(ScopeLevel.BASE)
    return str(ScopeLevel.VARIANT)


def _widest_readings(base, candidates: list[dict]) -> list[dict]:
    """The widest reading of each product that the record still supports.

    One per product rather than one overall: a single widest taken across a run
    carrying two corrections would leave the other product's correction
    unapplied and unmentioned.

    Widest among the best-evidenced readings, not widest outright. Fail-safe
    means applying the correction everywhere the record puts it in scope, and
    once a clarification names one variant while the others stand on a
    different document, the record stops putting them in scope - the
    enumeration says so, by scoring that reading at zero. Taking the widest
    reading regardless would republish the corrected figure onto a model the
    supplier has just said it does not apply to, which is the one error a
    reviewer is least likely to catch: the recommendation reads as though the
    ambiguity had been resolved. Where nothing separates the readings this
    still returns the widest, so an ambiguous notice with no model available is
    applied as broadly as before.
    """
    grouped: dict[str, list[dict]] = {}
    for candidate in candidates:
        grouped.setdefault(_scope_product(base, candidate), []).append(candidate)

    out: list[dict] = []
    for product_id in sorted(grouped):
        rows = grouped[product_id]
        best = max(float(c.get("confidence") or 0.0) for c in rows)
        supported = [c for c in rows if float(c.get("confidence") or 0.0) >= best]
        # Ties broken by the entity list, so a re-run picks the same reading.
        out.append(max(supported, key=lambda c: (len(c["entities"]), c["entities"])))
    return out


def _merge_candidates(base, deterministic: list[dict], argued: list[dict],
                      readings: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Fold the model's readings into the enumerated ones, and validate all of them.

    The model may only argue over variants the catalog holds, and its level is
    recomputed from the entity set it named rather than taken from the label it
    chose. Where it argues for a reading the peer already enumerated, its
    rationale and confidence replace the generated ones - that argument is what
    it is for.

    Every surviving reading then goes through ``_scope_problem``, which refuses
    a scope that names an unknown variant, spans two products, or labels several
    variants VARIANT. Refusals are returned rather than dropped, on the same
    contract ``_validate_actions`` uses.

    The enumerated readings are never discarded, so the narrowest and the
    widest of each product are both on the table however few the model argued.
    """
    known = {v for product_id in readings
             for v in base.variants_of.get(product_id, [])}
    merged = {tuple(c["entities"]): dict(c) for c in deterministic}
    rejected: list[dict] = []

    for raw in argued:
        if not isinstance(raw, dict):
            continue
        named = sorted({str(e) for e in raw.get("entities") or []})
        entities = [e for e in named if e in known]
        if not entities:
            if named:
                rejected.append({
                    "action": {"scope": raw},
                    "why": (f"argued reading names {', '.join(named)}, which no "
                            f"product in this correction holds")})
            continue
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        key = tuple(entities)
        held = merged.get(key, {})
        merged[key] = {
            "level": _level_for(base, entities),
            "entities": entities,
            "confidence": confidence,
            "rationale": str(raw.get("rationale") or held.get("rationale", ""))[:400],
            "evidence": sorted({str(e) for e in (raw.get("evidence") or [])}
                               | set(held.get("evidence") or [])),
        }

    ordered = sorted(merged.values(),
                     key=lambda c: (_scope_product(base, c),
                                    len(c["entities"]), c["entities"]))
    # Validated against the contract before it reaches state: a ChangeScope the
    # planner cannot build a ChangeSet from is not a candidate.
    out: list[dict] = []
    for candidate in ordered:
        why = _scope_problem(base, candidate)
        if why:
            rejected.append({"action": {"scope": candidate}, "why": why})
            continue
        out.append(ChangeScope.model_validate(candidate).model_dump(mode="json"))
    return out, rejected


# ---------------------------------------------------------------------------
# plan_candidates
# ---------------------------------------------------------------------------


def plan_candidates(state: FactoryState) -> dict:
    """Turn each reading of the correction into a change set the validator can price.

    Entirely deterministic. A scope says which variants are in play; the
    corrections say which attributes moved and on whose word; the cross of the
    two is the change set. No model is involved, because there is nothing here
    to judge - the judgement was made upstream and is about to be measured.

    Actions naming an attribute, entity or listing the catalog does not hold
    are rejected with the reason recorded rather than dropped. The rejected
    list is shown in the UI: "this was proposed and refused, because" is a more
    useful answer to a reviewer than a shorter list of options.
    """
    base = baseline_mod.get()
    values = _effective_values(state)
    rows = _correction_rows(base, state, values)
    scopes = _pick_scopes(base, state.get("scope_candidates") or [])

    scenarios: list[dict] = []
    # The readings ``resolve_scope`` already refused travel with the actions
    # refused here: both answer the reviewer's "what else was proposed".
    rejected: list[dict] = list(state.get("rejected_actions") or [])

    for scope in scopes:
        actions, dropped = _validate_actions(_actions_for(base, scope, rows), base)
        rejected.extend(dropped)
        if not actions:
            continue
        try:
            delta = ChangeSet.model_validate(
                {"id": _uid("D"), "scope": scope, "actions": actions}
            ).model_dump(mode="json")
        except ValidationError as exc:
            rejected.append({"action": {"scope": scope},
                             "why": f"scope is not a valid change set: "
                                    f"{exc.errors()[0]['msg']}"})
            continue
        scenarios.append({
            "id": _uid("SC"),
            "name": _scope_name(base, scope),
            "summary": _scope_summary(base, scope, actions),
            "delta": delta,
        })

    return {
        "scenarios": scenarios,
        "rejected_actions": rejected,
        "corrections": rows,
        "status": "PLANNED",
        "trace": [step("plan_candidates",
                       f"{len(scenarios)} candidate resolutions from "
                       f"{len(rows)} corrected value(s), "
                       f"{len(rejected)} proposal(s) refused",
                       candidates=[s["name"] for s in scenarios],
                       rejected=[r["why"] for r in rejected][:4])],
    }


def _pick_scopes(base, candidates: list[dict]) -> list[dict]:
    """At most MAX_CANDIDATES readings per product, always the two that bracket them.

    The narrowest and the widest are the pair the reviewer's question is
    actually about - "why not the other variant too" - so they are never the
    ones dropped to fit the cap. What goes in between is whatever the evidence
    rates highest.

    The cap is per product because the readings are: applying it across the run
    dropped a well-evidenced reading of one correction to make room for the
    bracket of another.
    """
    grouped: dict[str, list[dict]] = {}
    for candidate in candidates:
        grouped.setdefault(_scope_product(base, candidate), []).append(candidate)

    out: list[dict] = []
    for product_id in sorted(grouped):
        rows = sorted(grouped[product_id],
                      key=lambda c: (len(c["entities"]), c["entities"]))
        if len(rows) > MAX_CANDIDATES:
            middle = sorted(rows[1:-1],
                            key=lambda c: (-c.get("confidence", 0.0),
                                           len(c["entities"])))[:MAX_CANDIDATES - 2]
            rows = sorted([rows[0], *middle, rows[-1]],
                          key=lambda c: (len(c["entities"]), c["entities"]))
        out.extend(rows)
    return out


def _effective_values(state: FactoryState,
                      actions: list[dict] | None = None) -> dict:
    """Baseline values, then the facts in force, then a change set's own edits.

    The same composition the validator makes, so a node deciding whether a
    value has moved is asking the question the engine will answer.
    """
    base = baseline_mod.get()
    ov = overlay_mod.build(_iso(state.get("as_of")),
                           _iso(state.get("as_of_recorded")))
    values = dict(base.attr_values)
    for key, attr_state in ov.attr_values.items():
        values[key] = attr_state.value
    for action in actions or []:
        if action.get("kind") == str(ActionKind.SET_ATTRIBUTE):
            values[(action["entity_id"], action["attribute_path"])] = \
                action.get("new_value")
    return values


def _correction_rows(base, state: FactoryState, values: dict) -> list[dict]:
    """The corrected values in play, one row per (entity, attribute).

    Derived from the signals rather than from the store, because a correction
    announced ahead of its effective date is in play for planning and not yet
    in force for reading - and the plan is what has to be prepared early.

    ``old_value`` is the value the prepared content was written against, not
    whatever the store now believes. The reviewer's question is "what does the
    page say today and what will it say tomorrow", and answering it with the
    inference the extractor already recorded would show every row as unchanged.
    """
    rows: dict[tuple[str, str], dict] = {}
    for signal in state.get("signals", []):
        if signal.get("new_value") is None:
            continue
        for path in signal.get("attribute_paths") or []:
            definition = base.attr_defs.get(path)
            if definition is None:
                continue
            for entity_id in signal.get("entities") or []:
                if entity_id not in base.variants and entity_id not in base.products:
                    continue
                product = (entity_id if entity_id in base.products
                           else base.product_of_variant[entity_id])
                rows[(entity_id, path)] = {
                    "entity_id": entity_id,
                    "product": product,
                    "attribute_path": path,
                    "old_value": base.attr_values.get((entity_id, path)),
                    "in_force": values.get((entity_id, path)),
                    "new_value": signal["new_value"],
                    "unit": definition.unit,
                    "safety": definition.safety_class,
                    "confidence": float(
                        (signal.get("provenance") or {}).get("confidence")
                        or FALLBACK_CONFIDENCE),
                    "source": signal.get("source") or {},
                    "signal_id": signal.get("id"),
                }
    return [rows[key] for key in sorted(rows)]


def _actions_for(base, scope: dict, rows: list[dict]) -> list[dict]:
    """One SET_ATTRIBUTE per (variant, attribute) the reading puts in scope.

    A correction only reaches the variants of the product it was about, and
    only the attributes that product's category is expected to carry - a
    wattage correction has nothing to say about a snack bar, whatever the scope
    happens to name.

    The comparison is against the *published* value rather than against what
    the store now believes. The extractor has already recorded what the
    document asserts, so measuring against that would make every reading
    produce an empty change set and drop the narrow candidate entirely. A
    change set is what gets published, not what gets believed, and a value
    already on the page is the only kind there is nothing to do about.

    Two corrections can reach the same field - the ambiguous notice that named
    the product and the clarification that named the variant. The later
    document version wins, and a notice naming the variant outranks one naming
    the product at the same version. Publishing under the older citation is
    what the republish gate exists to refuse, so it is settled here rather than
    discovered at the gate.
    """
    try:
        in_scope = base.variants_in_scope(ChangeScope.model_validate(scope))
    except ValidationError:
        return []

    def standing(row: dict) -> tuple:
        return (engine._rank((row.get("source") or {}).get("version", "")),
                row["entity_id"] in base.variants)

    chosen: dict[tuple[str, str], dict] = {}
    for row in rows:
        applicable = {d.path for variant_id in in_scope
                      for d in base.applicable_attrs(variant_id)}
        if row["attribute_path"] not in applicable:
            continue
        for variant_id in in_scope:
            if base.product_of_variant.get(variant_id) != row["product"]:
                continue
            if row["attribute_path"] not in {
                    d.path for d in base.applicable_attrs(variant_id)}:
                continue
            key = (variant_id, row["attribute_path"])
            if base.attr_values.get(key) == row["new_value"]:
                continue
            held = chosen.get(key)
            if held is not None and standing(held["_row"]) >= standing(row):
                continue
            chosen[key] = {
                "_row": row,
                "id": f"SA-{variant_id}-{row['attribute_path']}",
                "kind": str(ActionKind.SET_ATTRIBUTE),
                "entity_id": variant_id,
                "attribute_path": row["attribute_path"],
                "old_value": base.attr_values.get(key),
                "new_value": row["new_value"],
                "unit": row["unit"],
                "confidence": row["confidence"],
                "source": row["source"] or None,
                "rationale": (f"{row['signal_id']}: applied under the "
                              f"{scope.get('level')} reading of the correction"),
            }
    return [{k: v for k, v in chosen[key].items() if k != "_row"}
            for key in sorted(chosen)]


def _scope_name(base, scope: dict) -> str:
    entities = scope.get("entities") or []
    if scope.get("level") == str(ScopeLevel.ALL):
        products = sorted({base.product_of_variant[e] for e in entities
                           if e in base.variants})
        return f"Apply to every variant of {', '.join(products) or 'the product'}"
    names = [base.variants[e].name for e in entities if e in base.variants]
    return f"Apply to {', '.join(names) or 'the named variants'}"


def _scope_summary(base, scope: dict, actions: list[dict]) -> str:
    paths = sorted({a["attribute_path"] for a in actions
                    if a.get("attribute_path")})
    return (f"{scope.get('level')} reading: {len(actions)} attribute value(s) "
            f"across {len(scope.get('entities') or [])} variant(s) - "
            f"{', '.join(paths)}. {scope.get('rationale', '')}")[:400]


# The action classes, keyed by the kind they declare. Validation goes through
# the contract itself rather than a parallel list of required fields, so an
# action the change set cannot hold is rejected here rather than at the
# validator, with a message naming the field.
_ACTION_MODELS = {
    str(ActionKind.SET_ATTRIBUTE): SetAttributeAction,
    str(ActionKind.REGENERATE_COPY): RegenerateCopyAction,
    str(ActionKind.REMAP_TAXONOMY): RemapTaxonomyAction,
    str(ActionKind.SET_FACET): SetFacetAction,
    str(ActionKind.WITHHOLD_CHANNEL): WithholdChannelAction,
    str(ActionKind.REQUEST_SUPPLIER_INPUT): RequestSupplierInputAction,
}


def _unknown_reference(base, kind: str, action: dict) -> str:
    """Whether an action names something the catalog does not hold."""
    if kind == str(ActionKind.SET_ATTRIBUTE):
        entity_id = action.get("entity_id")
        if entity_id not in base.variants and entity_id not in base.products:
            return f"no such product or variant: {entity_id!r}"
        if action.get("attribute_path") not in base.attr_defs:
            return f"no such attribute: {action.get('attribute_path')!r}"

    elif kind in (str(ActionKind.REGENERATE_COPY), str(ActionKind.REMAP_TAXONOMY),
                  str(ActionKind.WITHHOLD_CHANNEL)):
        listing_id = action.get("listing_id")
        if listing_id not in base.listings:
            return f"no such listing: {listing_id!r}"
        if kind == str(ActionKind.WITHHOLD_CHANNEL):
            channel_id = action.get("channel_id")
            if base.listings[listing_id].channel_id != channel_id:
                return f"{listing_id} does not publish to {channel_id!r}"
        if kind == str(ActionKind.REGENERATE_COPY):
            asset = base.assets.get(action.get("asset_id"))
            if asset is None:
                return f"no such content asset: {action.get('asset_id')!r}"
            if asset.listing_id != listing_id:
                return f"{asset.id} is not on {listing_id}"

    elif kind == str(ActionKind.SET_FACET):
        if action.get("channel_id") not in base.channels:
            return f"no such channel: {action.get('channel_id')!r}"

    elif kind == str(ActionKind.REQUEST_SUPPLIER_INPUT):
        if action.get("supplier") not in base.docs_by_supplier:
            return f"no such supplier: {action.get('supplier')!r}"

    return ""


def _validate_actions(actions: list[dict], base) -> tuple[list[dict], list[dict]]:
    """Reject actions the catalog cannot execute, each with its reason.

    Nothing is dropped silently. A proposal that names an attribute nobody
    holds is a fact about the proposal, and the reviewer is shown it - a
    shorter option list with no explanation is the same information with the
    interesting half removed.
    """
    valid: list[dict] = []
    rejected: list[dict] = []

    for raw in actions or []:
        action = dict(raw)
        action.setdefault("id", _uid("a"))
        kind = str(action.get("kind") or "")

        model = _ACTION_MODELS.get(kind)
        if model is None:
            rejected.append({"action": raw, "why": f"unknown action kind {kind!r}"})
            continue

        why = _unknown_reference(base, kind, action)
        if why:
            rejected.append({"action": raw, "why": why})
            continue

        try:
            valid.append(model.model_validate(action).model_dump(mode="json"))
        except ValidationError as exc:
            first = exc.errors()[0]
            rejected.append({"action": raw,
                             "why": f"{kind} is malformed: "
                                    f"{'.'.join(str(p) for p in first['loc'])} "
                                    f"{first['msg']}"})
    return valid, rejected


# ---------------------------------------------------------------------------
# validate - fanned out with Send
# ---------------------------------------------------------------------------


def fan_out_validations(state: FactoryState) -> list[Send]:
    """One validation per candidate, run concurrently."""
    return [
        Send("validate_one", ScenarioTask(
            run_id=state["run_id"], as_of=state["as_of"],
            as_of_recorded=state["as_of_recorded"], scenario=scenario))
        for scenario in state.get("scenarios", [])
    ]


def validate_one(task: ScenarioTask) -> dict:
    """Validate one candidate. Deterministic, no model involvement."""
    scenario = task["scenario"]
    # Delegated to the validator peer. With USE_A2A=1 this is a JSON-RPC call
    # over the protocol; otherwise the same handler runs in-process. The
    # trace_hash is identical either way, which is the only acceptable outcome
    # for a step whose entire job is reproducibility.
    result = a2a_client.call("validator", {
        "delta": scenario["delta"],
        "as_of": task["as_of"],
        "as_of_recorded": task["as_of_recorded"],
    })
    kpis = result.get("kpis", {})
    return {
        "sim_results": [{
            "scenario_id": scenario["id"], "name": scenario["name"],
            "summary": scenario["summary"], "delta": scenario["delta"],
            **result,
        }],
        "trace": [step("validate", f"{scenario['name']}: "
                                   f"{kpis.get('listings_ready_pct', 0)}% of "
                                   f"affected listings publishable, "
                                   f"{kpis.get('fields_affected', 0)} fields moved",
                       scenario_id=scenario["id"],
                       feasible=result.get("feasible"),
                       trace_hash=result.get("trace_hash"))],
    }


# ---------------------------------------------------------------------------
# rank
# ---------------------------------------------------------------------------


def rank(state: FactoryState) -> dict:
    """Score and order the validated resolutions. Arithmetic only.

    Safety is a pre-sort rather than a weight. ``planning._score`` already
    keeps any resolution carrying a safety flag behind every resolution
    carrying none; this refines that boolean into a count, so that between two
    blocked options the one blocking less wins. The sort is stable, so the
    deterministic score still orders everything inside a tie.
    """
    results = list(state.get("sim_results", []))
    carried = _carry_forward(state.get("previous_ranked"), results)

    for scenario in carried:
        # Re-validated against the world as it stands now. Carrying the old
        # numbers forward would put a resolution scored against superseded
        # evidence on the same table as one scored against current evidence,
        # which is the exact failure the revision exists to avoid.
        result = a2a_client.call("validator", {
            "delta": scenario["delta"], "as_of": state.get("as_of"),
            "as_of_recorded": state.get("as_of_recorded")})
        results.append({"scenario_id": scenario["id"], "name": scenario["name"],
                        "summary": scenario["summary"],
                        "delta": scenario["delta"],
                        "carried_from": scenario.get("carried_from"), **result})

    scored = planning._score(results, state.get("weights") or {})
    ranked = sorted(scored, key=lambda r: r.get("kpis", {}).get("safety_flags", 0))

    diff = _plan_diff(state, ranked)
    chosen_scope = (ranked[0].get("delta", {}).get("scope") or {}) if ranked else {}

    note = ""
    if len(ranked) > 1:
        widest = max(ranked, key=lambda r: len(
            (r.get("delta", {}).get("scope") or {}).get("entities") or []))
        if widest["scenario_id"] != ranked[0]["scenario_id"]:
            note = (f"the widest reading ({widest['name']}) is not the "
                    f"top-ranked one - it moves "
                    f"{widest['kpis']['fields_affected']} fields against "
                    f"{ranked[0]['kpis']['fields_affected']}")

    return {"ranked": ranked, "chosen_scope": chosen_scope, "plan_diff": diff,
            "status": "RANKED",
            "trace": [step("rank", f"{len(ranked)} resolutions scored"
                           + (f"; {note}" if note else "")
                           + (f"; {diff['headline']}" if diff else ""),
                           order=[r["name"] for r in ranked],
                           carried_forward=[c["name"] for c in carried],
                           pareto=[r["name"] for r in ranked
                                   if r.get("pareto_optimal")])]}


def _signature(delta: dict) -> str:
    """What a resolution *does*, independent of what it is called."""
    return "|".join(sorted(
        json.dumps(a, sort_keys=True, default=str)
        for a in (delta.get("actions") or [])))


def _carry_forward(previous_ranked: list[dict] | None,
                   fresh: list[dict]) -> list[dict]:
    """Previous options worth re-validating under the new evidence.

    This is what makes a re-plan targeted rather than a restart: the reviewer
    gets to see the option they nearly approved re-scored against what has
    arrived since, instead of a fresh list that may not contain it at all.

    Deduplicated against this revision's candidates by action signature, not by
    name. The same reading is routinely re-proposed under a different label,
    and validating it twice would put two identical rows on the comparison
    table and make the Pareto front look denser than it is.
    """
    seen = {_signature(s.get("delta") or {}) for s in fresh}
    out: list[dict] = []
    for prior in previous_ranked or []:
        delta = prior.get("delta") or {}
        if not delta.get("actions"):
            continue
        signature = _signature(delta)
        if signature in seen:
            continue
        seen.add(signature)
        out.append({
            "id": _uid("SC"),
            "name": f"{prior.get('name', 'previous reading')} (previous plan)",
            "summary": prior.get("summary", ""),
            # A fresh delta id: the validator keys its idempotency on it, and
            # reusing the old one would return the old verdict against the new
            # world - the exact failure this feature exists to avoid.
            "delta": {**delta, "id": _uid("D")},
            "carried_from": prior.get("scenario_id"),
        })
    return out


# The figures a revision is compared on. Every one comes from the validator.
_DIFF_KPIS = ("listings_ready_pct", "fields_affected", "assets_stale",
              "channels_blocked", "completeness_pct", "safety_flags",
              "republish_steps")


def _plan_diff(state: FactoryState, ranked: list[dict]) -> dict:
    """What changed between the superseded plan and this one. Arithmetic only.

    The brief asks the UI to show exactly why the recommendation changes when
    new evidence arrives. *Exactly* is the operative word, so this is computed
    from the two option sets rather than asked of a model: which reading led
    before, which leads now, what that costs, and which corrections are new
    since the plan being replaced. The narrative explains this diff; it does
    not produce it.
    """
    previous = state.get("previous_recommendation") or {}
    if not previous or not ranked:
        return {}

    prior_by_id = {r.get("scenario_id"): r
                   for r in state.get("previous_ranked") or []}
    was = prior_by_id.get(previous.get("scenario_id")) or {}
    now = ranked[0]

    # The previously chosen actions may reappear under a new scenario id, so
    # match on what the option does rather than on what it is called.
    was_signature = _signature(was.get("delta") or previous.get("delta") or {})
    still_available = next(
        (r for r in ranked if _signature(r.get("delta") or {}) == was_signature),
        None)
    held = bool(still_available) and (
        still_available["scenario_id"] == now["scenario_id"])

    before, after = was.get("kpis") or {}, now.get("kpis") or {}
    moved = {key: round(float(after.get(key, 0)) - float(before.get(key, 0)), 2)
             for key in _DIFF_KPIS if before or after}

    known = {s.get("id") for s in (previous.get("signals_seen") or [])}
    fresh = [s for s in state.get("signals", [])
             if s.get("id") not in known] if known else state.get("signals", [])

    return {
        "revision": int(state.get("revision") or 0),
        "held": held,
        "headline": (f"recommendation holds ({now['name']})" if held else
                     f"recommendation moves from "
                     f"{was.get('name') or previous.get('scenario_name')} to "
                     f"{now['name']}"),
        "previous": {"scenario_id": previous.get("scenario_id"),
                     "name": was.get("name") or previous.get("scenario_name"),
                     "scope": (was.get("delta") or {}).get("scope") or {},
                     "kpis": before},
        "current": {"scenario_id": now.get("scenario_id"), "name": now.get("name"),
                    "scope": (now.get("delta") or {}).get("scope") or {},
                    "kpis": after},
        "previous_now_ranked": (ranked.index(still_available) + 1
                                if still_available else None),
        "previous_still_feasible": (still_available.get("feasible")
                                    if still_available else None),
        "moved": moved,
        "new_signals": [{"id": s.get("id"), "kind": s.get("kind"),
                         "summary": s.get("summary")} for s in fresh][:6],
        "reason": state.get("replan_reason", ""),
    }


def _ranked_for_prompt(ranked: list[dict]) -> list[dict]:
    """The ranked resolutions trimmed to the figures a reader needs.

    Shared with the recommendation prompt rather than re-implemented, so the
    approval gate shows the reviewer exactly the rows the writer was given.
    """
    return prompts._ranked_for_prompt(ranked)


def _chosen(state: FactoryState) -> dict:
    """The resolution the downstream leg is working on: the top-ranked one."""
    ranked = state.get("ranked") or []
    return ranked[0] if ranked else {}


def _append_actions(state: FactoryState, extra: list[dict]) -> list[dict]:
    """Add actions to the change set the downstream leg is working on.

    Propagation, regeneration and enrichment each add to one resolution rather
    than proposing new ones, so the working change set lives at the head of
    ``ranked`` and every node returns the whole list back. Keeping it there
    means the reviewer approves the same object the validator priced.
    """
    ranked = [dict(r) for r in state.get("ranked") or []]
    if not ranked or not extra:
        return ranked
    head = dict(ranked[0])
    delta = dict(head.get("delta") or {})
    actions = list(delta.get("actions") or [])
    held = {a.get("id") for a in actions}
    delta["actions"] = actions + [a for a in extra if a.get("id") not in held]
    head["delta"] = delta
    ranked[0] = head
    return ranked


# ---------------------------------------------------------------------------
# propagate - the blast radius made executable
# ---------------------------------------------------------------------------


def propagate(state: FactoryState) -> dict:
    """Turn the lineage walk into the actions that follow from it.

    Wholly deterministic, and that is the point: which copy quotes a corrected
    value, which taxonomy node a channel cannot map, which facet leans on a
    claim that no longer holds - all of it is in ``derived_from`` and the rule
    table, and none of it is a matter of opinion. The model's turn comes after,
    on the sentences the record cannot settle.

    The mechanical half of regeneration happens here, through the copywriter
    peer: a superseded figure quoted in prose is swapped for the corrected one
    with the same matcher the validator uses to find it, and a marketplace feed
    row is rebuilt under the channel's own field names. Only assets it actually
    rewrote get a REGENERATE_COPY action. Emitting one with no replacement text
    would clear the staleness flag without fixing anything, which is worse than
    leaving the flag standing.

    A listing is withheld only where the failure is in the record rather than
    in the copy. Rewriting a sentence does not make a low-confidence allergen
    inference certain, so that listing comes off the channel; a badly formatted
    declaration is a defect in the copy and goes to ``regenerate`` instead.
    """
    base = baseline_mod.get()
    chosen = _chosen(state)
    if not chosen:
        return {"status": "NOTHING_TO_PROPAGATE",
                "trace": [step("propagate", "no validated resolution to propagate")]}

    actions = (chosen.get("delta") or {}).get("actions") or []
    values = _effective_values(state, actions)
    corrected = {f"{a['entity_id']}:{a['attribute_path']}": a["new_value"]
                 for a in actions if a.get("kind") == str(ActionKind.SET_ATTRIBUTE)}
    source = next((a.get("source") for a in actions if a.get("source")), None)

    rewritten = a2a_client.call("copywriter",
                                {"values": corrected, "source": source})
    copy_rows = rewritten.get("copy", [])

    proposed: list[dict] = [dict(row["action"]) for row in copy_rows
                            if row.get("changed") and row.get("action")]
    for action in proposed:
        # An uncited change to published content is a HARD violation by design,
        # so the correction's own source travels with every rewrite.
        action.setdefault("source", source)

    listings = _propagation_listings(base, corrected, chosen)
    proposed.extend(_taxonomy_actions(base, listings, source))
    proposed.extend(_facet_actions(base, listings, values, source))
    withheld = _withhold_actions(base, chosen, source)
    proposed.extend(withheld)

    valid, dropped = _validate_actions(proposed, base)
    unresolved = sorted({row["asset_id"] for row in copy_rows
                         if row.get("unresolved")})

    return {
        "ranked": _append_actions(state, valid),
        "rejected_actions": (state.get("rejected_actions") or []) + dropped,
        "status": "PROPAGATED",
        "trace": [step("propagate",
                       f"{len(valid)} follow-on action(s): "
                       f"{sum(1 for a in valid if a['kind'] == str(ActionKind.REGENERATE_COPY))}"
                       f" fields rewritten deterministically, "
                       f"{len(withheld)} listing(s) withheld, "
                       f"{len(unresolved)} field(s) the record cannot settle",
                       withheld=[a["listing_id"] for a in withheld],
                       unresolved=unresolved,
                       kinds=sorted({a["kind"] for a in valid}))],
    }


def _propagation_listings(base, corrected: dict, chosen: dict) -> list[str]:
    """Every listing a corrected value reaches, through copy or through scope.

    The cross-variant edge is why this is not simply "the listings of the
    variants in scope": the comparison table on the base model's page is built
    from the Max's wattage, so a correction scoped to the Max lands there too.
    """
    listings: set[str] = set()
    for ref in sorted(corrected):
        entity_id, _, _ = ref.partition(":")
        for variant_id in ([entity_id] if entity_id in base.variants
                           else base.variants_of.get(entity_id, [])):
            listings.update(base.listings_of.get(variant_id, []))
        for asset_id in base.assets_derived_from.get(ref, []):
            listings.add(base.assets[asset_id].listing_id)
    return sorted(listings)


def _taxonomy_actions(base, listings: list[str], source) -> list[dict]:
    """Listings whose channel has no node for the product's internal category.

    A marketplace that enforces CATEGORY_MAPPED will refuse the feed outright,
    and the fix is a mapping decision rather than a content edit - so the
    action names the gap and leaves the destination for a human to choose.
    """
    out = []
    for listing_id in listings:
        listing = base.listings[listing_id]
        channel = base.channels[listing.channel_id]
        demands_mapping = any(
            r.kind == "CATEGORY_MAPPED"
            for r in base.rules_by_channel.get(listing.channel_id, []))
        category = base.products[base.product_of_variant[listing.variant_id]].category
        if not demands_mapping or category in channel.category_map:
            continue
        out.append({
            "id": f"RT-{listing_id}",
            "kind": str(ActionKind.REMAP_TAXONOMY),
            "listing_id": listing_id,
            "from_node": category,
            "to_node": "",
            "source": source,
            "rationale": (f"{channel.id} speaks {channel.taxonomy} and has no "
                          f"node for internal category {category}; the feed is "
                          f"refused until one is chosen"),
        })
    return out


def _facet_actions(base, listings: list[str], values: dict, source) -> list[dict]:
    """Search facets a correction has made wrong.

    Facets are filters rather than sentences: a shopper who filters on
    peanut-free and is shown a bar that may contain peanuts has been failed by
    the index, not by the copy. So a claim facet the substantiation table no
    longer supports is removed, and a newly declared allergen gains one.
    """
    out: list[dict] = []
    for listing_id in listings:
        listing = base.listings[listing_id]
        if str(base.channels[listing.channel_id].kind) != "SEARCH":
            continue
        merged = {path: values.get((listing.variant_id, path))
                  for (entity_id, path) in values if entity_id == listing.variant_id}

        for asset_id in base.assets_by_listing.get(listing_id, []):
            asset = base.assets[asset_id]
            if asset.field != "facets":
                continue
            present = {line.strip() for line in asset.text.splitlines() if line.strip()}

            for facet in sorted(present):
                claim = facet.partition(":")[2]
                rule = engine.CLAIM_RULES.get(claim)
                if rule is None or any(merged.get(p) is None for p in rule.paths):
                    continue
                try:
                    holds = rule.holds(merged)
                except (TypeError, ValueError):
                    holds = False
                if holds:
                    continue
                out.append({
                    "id": f"SF-{listing.channel_id}-{facet}",
                    "kind": str(ActionKind.SET_FACET),
                    "channel_id": listing.channel_id,
                    "facet": facet, "op": "REMOVE", "source": source,
                    "reason": (f"'{claim}' holds only if {rule.statement}, which "
                               f"the corrected values no longer support"),
                })

            declared = (list(merged.get("food.allergens.contains") or [])
                        + list(merged.get("food.allergens.may_contain") or []))
            for allergen in sorted({str(a) for a in declared}):
                facet = f"allergen:{allergen}"
                if facet in present:
                    continue
                out.append({
                    "id": f"SF-{listing.channel_id}-{facet}",
                    "kind": str(ActionKind.SET_FACET),
                    "channel_id": listing.channel_id,
                    "facet": facet, "op": "ADD", "source": source,
                    "reason": (f"{allergen} is now declared on "
                               f"{listing.variant_id} and has to be filterable"),
                })
    return out


def _listings_for_violation(base, violation: dict) -> list[str]:
    """Which listings a violation actually stops from publishing."""
    head = str(violation.get("entity_id", "")).split(":", 1)[0]
    if head in base.listings:
        return [head]
    if head in base.assets:
        return [base.assets[head].listing_id]
    candidates = listings_for(base, head)
    channel_id = violation.get("channel_id")
    if channel_id:
        return [l for l in candidates
                if base.listings[l].channel_id == channel_id]
    return list(candidates)


def _withhold_actions(base, chosen: dict, source) -> list[dict]:
    """Fail closed, as an explicit act rather than an absence of one.

    Withholding has consequences, so it appears in the diff, needs approval
    like anything else, and lands in the audit trail - which is why it is an
    action and not a quietly skipped listing.
    """
    out: dict[str, dict] = {}
    for violation in chosen.get("violations") or []:
        if violation.get("severity") != "HARD":
            continue
        if violation.get("constraint") not in UNFIXABLE_BY_COPY:
            continue
        for listing_id in _listings_for_violation(base, violation):
            listing = base.listings[listing_id]
            out[listing_id] = {
                "id": f"WC-{listing_id}",
                "kind": str(ActionKind.WITHHOLD_CHANNEL),
                "listing_id": listing_id,
                "channel_id": listing.channel_id,
                "source": source,
                "reason": violation.get("detail", ""),
                "rationale": ("held back until a human decides the value: "
                              + str(violation.get("detail", ""))[:200]),
            }
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------------------
# scan_claims - the advisory semantic pass
# ---------------------------------------------------------------------------


def scan_claims(state: FactoryState) -> dict:
    """Look for sentences the corrected values have quietly made untrue.

    Two mechanical checks have already run: the substantiation table, which
    catches a tagged claim whose supporting value moved, and the literal scan,
    which catches copy still quoting a superseded figure. Neither catches
    meaning - "whisper-quiet enough for a bedroom" quotes nothing, is tagged
    with nothing, and is equally untrue once the measured level moves from
    38 dB to 44 dB.

    So the model reads for meaning, and its flags are **advisory**. A flag is
    promoted to a finding only where the deterministic rule table agrees or the
    literal scan already caught the same asset; everything else is shown to the
    reviewer as a suggestion. That asymmetry is deliberate: a missed sentence
    costs a reviewer a read, and a promoted hallucination costs a republish.
    """
    base = baseline_mod.get()
    chosen = _chosen(state)
    rows, assets, confirmed = scan_claims_inputs(state)
    if not rows:
        return {"claim_flags": [],
                "trace": [step("scan_claims", "no corrected values to scan")]}

    caught = {v.get("entity_id") for v in chosen.get("violations") or []
              if v.get("constraint") in ("stale_literal", "claim_consistency")}

    spent: list[LlmUsage] = []
    try:
        found, usage = gateway.complete_json(
            [{"role": "system", "content": prompts.SCAN_CLAIMS_SYSTEM},
             {"role": "user", "content": prompts.scan_claims_user(
                 rows, assets, engine.CLAIM_RULES)}],
            model=fast_model(), agent="scan_claims", run_id=state["run_id"])
        spent.append(usage)
        flags = found.get("flags") or []
        errors: list[str] = []
    except GatewayError as exc:
        # The tags the copy already carries. Not a substitute for reading, but
        # it is what the record can say on its own.
        flags = [{"asset_id": asset_id, "excerpt": "",
                  "why": f"'{claim}' is tagged on this copy and no longer holds",
                  "claim": claim, "severity": "HARD", "confidence": 1.0}
                 for asset_id, claims in sorted(confirmed.items())
                 for claim in sorted(claims)]
        errors = [f"scan_claims: {exc}"]

    known = {a["id"] for a in assets}
    out: list[dict] = []
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        asset_id = str(flag.get("asset_id") or "")
        if asset_id not in known:
            continue  # a flag on copy that is not in scope is not a finding
        claim = str(flag.get("claim") or "")
        supported = claim in confirmed.get(asset_id, set()) or asset_id in caught
        out.append({
            "asset_id": asset_id,
            "listing_id": base.assets[asset_id].listing_id,
            "excerpt": str(flag.get("excerpt") or "")[:300],
            "why": str(flag.get("why") or "")[:300],
            "claim": claim,
            "severity": "HARD" if supported else "SOFT",
            "status": "CONFIRMED" if supported else "ADVISORY",
            "confidence": flag.get("confidence"),
        })

    # Anything the table caught that the model did not mention is still a
    # finding: the deterministic check is the floor, not a second opinion.
    mentioned = {(f["asset_id"], f["claim"]) for f in out}
    for asset_id, claims in sorted(confirmed.items()):
        for claim in sorted(claims):
            if (asset_id, claim) in mentioned:
                continue
            rule = engine.CLAIM_RULES[claim]
            out.append({
                "asset_id": asset_id,
                "listing_id": base.assets[asset_id].listing_id,
                "excerpt": "", "claim": claim, "severity": "HARD",
                "status": "CONFIRMED", "confidence": 1.0,
                "why": (f"'{claim}' holds only if {rule.statement}, and the "
                        f"corrected values no longer support it"),
            })

    confirmed_count = sum(1 for f in out if f["status"] == "CONFIRMED")
    return {
        "claim_flags": out,
        "status": "CLAIMS_SCANNED",
        "errors": errors,
        "usage": _spend("scan_claims", *spent),
        "trace": [step("scan_claims",
                       f"{confirmed_count} confirmed, "
                       f"{len(out) - confirmed_count} advisory"
                       + (" (rule table only, no model)" if errors else ""),
                       claims=sorted({f["claim"] for f in out}))],
    }


def scan_claims_inputs(state: FactoryState) -> tuple[list[dict], list[dict],
                                                     dict[str, set[str]]]:
    """What the claim scan reads: corrected rows, the copy they reach, and the
    claims the deterministic table already says no longer hold.

    Public for the same reason ``extract_messages`` is: ``scripts/evaluate.py``
    scores the model's flags against ``confirmed``, and a scorer that assembled
    its own inputs would be measuring a scan nobody runs.
    """
    base = baseline_mod.get()
    actions = (_chosen(state).get("delta") or {}).get("actions") or []
    corrected = {f"{a['entity_id']}:{a['attribute_path']}": a
                 for a in actions if a.get("kind") == str(ActionKind.SET_ATTRIBUTE)}
    if not corrected:
        return [], [], {}

    values = _effective_values(state, actions)
    assets = _affected_assets(base, corrected)
    rows = [{"entity_id": a["entity_id"], "attribute_path": a["attribute_path"],
             "value": a.get("new_value"), "unit": a.get("unit"),
             "doc": (a.get("source") or {}).get("doc_id", ""),
             "version": (a.get("source") or {}).get("version", "")}
            for a in corrected.values()]
    return rows, assets, _unsupported_claims(base, assets, values)


def _affected_assets(base, corrected: dict) -> list[dict]:
    """Prepared copy built on a value the resolution moves."""
    out: dict[str, dict] = {}
    for ref in sorted(corrected):
        for asset_id in base.assets_derived_from.get(ref, []):
            asset = base.assets[asset_id]
            listing = base.listings[asset.listing_id]
            row = out.setdefault(asset_id, {
                "id": asset.id, "field": asset.field, "listing_id": listing.id,
                "channel_id": listing.channel_id, "variant_id": listing.variant_id,
                "text": asset.text, "claims_used": sorted(asset.claims_used),
                "built_at_version": asset.built_at_version,
                "derived_from": sorted(asset.derived_from), "stale_refs": [],
            })
            row["stale_refs"].append(ref)
    return [out[k] for k in sorted(out)]


def _unsupported_claims(base, assets: list[dict],
                        values: dict) -> dict[str, set[str]]:
    """Claims each asset leans on that the corrected values no longer carry.

    The engine's own table, not a second copy of it: a scanner whose idea of
    "substantiated" differs from the validator's is a machine for producing
    findings nobody can act on.
    """
    out: dict[str, set[str]] = {}
    for row in assets:
        variant_id = row["variant_id"]
        merged = {path: values.get((variant_id, path))
                  for (entity_id, path) in values if entity_id == variant_id}
        claimed = set(row["claims_used"]) | {
            str(c) for c in (merged.get("claims") or [])}
        for claim in sorted(claimed):
            rule = engine.CLAIM_RULES.get(claim)
            if rule is None or any(merged.get(p) is None for p in rule.paths):
                continue
            try:
                holds = rule.holds(merged)
            except (TypeError, ValueError):
                holds = False  # a value of the wrong shape substantiates nothing
            if not holds:
                out.setdefault(row["id"], set()).add(claim)
    return out


# ---------------------------------------------------------------------------
# regenerate - the sentences the record cannot settle
# ---------------------------------------------------------------------------


def regenerate(state: FactoryState) -> dict:
    """Rewrite the copy the deterministic pass could not.

    ``propagate`` has already swapped every superseded figure it could
    attribute and rebuilt every machine field. What is left is the half that
    needs writing rather than substituting: an allergen warning that was never
    there to edit, a comparison row whose number belongs to two variants, a
    sentence leaning on a claim the corrected values withdrew.

    Every number the writer may use is supplied in the attribute table, the
    channel budget is re-validated after it answers, and the reply is checked
    against the superseded literal before it is accepted - a rewrite that still
    quotes the old figure is rejected however well it reads. Every action
    carries the SourceRef: an uncited change to published content is a HARD
    ``citation_missing`` violation by design, not a stylistic lapse.

    Capped at ``MAX_REGENERATIONS``, and what was skipped is recorded. A
    reviewer told twelve of nineteen fields were rewritten can act on the
    remaining seven; one shown twelve and no count cannot.
    """
    base = baseline_mod.get()
    chosen = _chosen(state)
    actions = (chosen.get("delta") or {}).get("actions") or []
    corrected = {f"{a['entity_id']}:{a['attribute_path']}": a
                 for a in actions if a.get("kind") == str(ActionKind.SET_ATTRIBUTE)}
    if not corrected:
        return {"regenerated": [],
                "trace": [step("regenerate", "no corrected values to write from")]}

    values = _effective_values(state, actions)
    # The text ``propagate`` already settled for each asset. Kept rather than
    # reduced to a set of ids: an asset this node cannot improve is still going
    # to publish that text, and a row reporting no text at all reads as if
    # nothing had been done to a field that has in fact already been corrected.
    settled = {a["asset_id"]: a["proposed_text"] for a in actions
               if a.get("kind") == str(ActionKind.REGENERATE_COPY)
               and a.get("proposed_text")}
    at_risk = {f["asset_id"] for f in state.get("claim_flags") or []
               if f.get("status") == "CONFIRMED"}
    claims_at_risk: dict[str, list[str]] = {}
    for flag in state.get("claim_flags") or []:
        if flag.get("status") == "CONFIRMED" and flag.get("claim"):
            claims_at_risk.setdefault(flag["asset_id"], []).append(flag["claim"])
    source = next((a.get("source") for a in actions if a.get("source")), None)

    # Unsettled first. An asset the deterministic pass could not touch is
    # wrong right now; one it rewrote correctly but that still leans on a
    # withdrawn claim needs a sentence reworked, which is the lesser problem.
    # Under a cap, that ordering is what decides which fields get fixed.
    affected = _affected_assets(base, corrected)
    targets = ([row for row in affected if row["id"] not in settled]
               + [row for row in affected
                  if row["id"] in settled and row["id"] in at_risk])
    skipped = [row["id"] for row in targets[MAX_REGENERATIONS:]]
    targets = targets[:MAX_REGENERATIONS]

    standards = _render(retrieve.search(
        "product content standards claims substantiation channel copy",
        top_k=3, doc_types=["STANDARD", "CHANNEL"]))
    table = _attribute_table(base, corrected)

    written: list[dict] = []
    proposed: list[dict] = []
    errors: list[str] = []
    spent: list[LlmUsage] = []

    def rewrite_one(row: dict) -> tuple:
        """One target, with its own error and spend collections.

        The shared lists the serial loop appended to are exactly what a pool
        breaks: ``errors`` is deduplicated with a membership test and ``spent``
        with an append, and neither is atomic. Each worker owns its own, and the
        assembly below folds them back in target order - so two runs that raced
        differently still produce the same lists in the same order.
        """
        asset = base.assets[row["id"]]
        listing = base.listings[asset.listing_id]
        channel = base.channels[listing.channel_id]
        budget, used = _budget(base, channel.id, asset.field, asset.text)
        worker_errors: list[str] = []
        worker_spent: list[LlmUsage] = []
        result = _rewrite(state, row, listing, channel, budget, table,
                          standards, source, base, values,
                          worker_errors, worker_spent)
        return result, budget, used, worker_errors, worker_spent

    # Every input to a rewrite - the attribute table, the standards, the
    # effective values, the catalog - is settled before this point, so the
    # targets are independent and the loop was serial only by habit. With one
    # worker this is exactly the loop it replaces, which is what makes the
    # equality test meaningful rather than circular.
    if len(targets) > 1 and MAX_REGEN_WORKERS > 1:
        with ThreadPoolExecutor(
                max_workers=min(MAX_REGEN_WORKERS, len(targets)),
                thread_name_prefix="regenerate") as pool:
            # `map` yields in the order it was given, never completion order.
            outcomes = list(pool.map(rewrite_one, targets))
    else:
        outcomes = [rewrite_one(row) for row in targets]

    for row, outcome in zip(targets, outcomes):
        (text, status, note, citations), budget, used, w_errors, w_spent = outcome
        for message in w_errors:
            # The same deduplication the serial path did, done once the pool has
            # drained: one gateway outage is one fact about the run, however
            # many workers met it.
            if message not in errors:
                errors.append(message)
        spent.extend(w_spent)

        asset = base.assets[row["id"]]
        listing = base.listings[asset.listing_id]
        channel = base.channels[listing.channel_id]

        if text is None and asset.id in settled:
            # Nothing this node could add, but the field is not unchanged: the
            # deterministic pass corrected it and that text is what publishes.
            # What is left open is the claim, which only a rewrite can drop.
            claims = ", ".join(sorted(claims_at_risk.get(asset.id, [])))
            text, status = settled[asset.id], "SETTLED"
            note = (f"corrected deterministically; still leans on {claims}, "
                    f"which only a rewrite can drop" if claims
                    else "corrected deterministically in the propagation pass")

        record = {
            "asset_id": asset.id, "listing_id": listing.id,
            "channel_id": channel.id, "field": asset.field,
            "old_text": asset.text, "proposed_text": text or "",
            "status": status, "note": note, "citations": citations,
            "budget": budget, "used": used,
        }
        written.append(record)
        if text and status not in ("SKIPPED", "SETTLED"):
            proposed.append({
                "id": f"RC-{asset.id}",
                "kind": str(ActionKind.REGENERATE_COPY),
                "listing_id": listing.id, "asset_id": asset.id,
                "field": asset.field, "old_excerpt": asset.text[:200],
                "proposed_text": text, "reason": note,
                "source": source,
                "rationale": f"rewritten for {', '.join(row['stale_refs'])}",
            })

    valid, dropped = _validate_actions(proposed, base)
    return {
        "ranked": _append_actions(state, valid),
        "regenerated": written,
        "rejected_actions": (state.get("rejected_actions") or []) + dropped,
        "status": "REGENERATED",
        "errors": errors,
        # One entry for the node, not one per field rewritten.
        "usage": _spend("regenerate", *spent),
        "trace": [step("regenerate",
                       f"{sum(1 for r in written if r['status'] == 'WRITTEN')} "
                       f"field(s) rewritten, "
                       f"{sum(1 for r in written if r['status'] == 'TEMPLATED')} "
                       f"templated, "
                       f"{sum(1 for r in written if r['status'] == 'SETTLED')} "
                       f"already corrected deterministically, "
                       f"{sum(1 for r in written if r['status'] == 'SKIPPED')} "
                       f"left unchanged"
                       + (f", {len(skipped)} over the cap" if skipped else ""),
                       skipped=skipped,
                       fields=[r["field"] for r in written])],
    }


def _rewrite(state, row, listing, channel, budget, table, standards, source,
             base, values, errors, spent) -> tuple[str | None, str, str, list[str]]:
    """One field, rewritten by the model or by template. Never by guesswork."""
    asset = base.assets[row["id"]]

    def templated() -> tuple[str | None, str, str, list[str]]:
        text = _template_text(base, asset, values)
        if text is None or _over_budget(base, channel.id, asset.field, text):
            return (None, "SKIPPED",
                    "the record cannot settle this field and no template fits "
                    "the channel budget", [])
        return text, "TEMPLATED", "rebuilt from the attribute table", (
            [source["doc_id"]] if source and source.get("doc_id") else [])

    if asset.field not in NL_FIELDS:
        return templated()

    try:
        reply, usage = gateway.complete_json(
            [{"role": "system", "content": prompts.REGENERATE_SYSTEM},
             {"role": "user", "content": prompts.regenerate_user(
                 row, listing.model_dump(mode="json"),
                 channel.model_dump(mode="json"),
                 {"field": asset.field, "max": budget,
                  "counts": ("entries" if asset.field in engine.COUNTED_FIELDS
                             else "characters")},
                 table, standards, source)}],
            model=reasoning_model(), agent="regenerate", run_id=state["run_id"])
        spent.append(usage)
    except GatewayError as exc:
        outage = f"regenerate: {exc}"
        # Same rule as the extract stage: one outage is one fact about the run,
        # whichever of the gateway's two phrasings this worker happened to meet.
        if not any(_same_outage(outage, e) for e in errors):
            errors.append(outage)
        return templated()

    text = str(reply.get("text") or "").strip()
    citations = [str(c) for c in reply.get("citations") or []]
    if not reply.get("changed") or not text or text == asset.text:
        return (None, "SKIPPED",
                str(reply.get("note") or "the writer returned it unchanged")[:200],
                citations)
    if not citations:
        # The prompt says an uncitable field comes back unchanged; a reply that
        # changed the text anyway is not one to publish on.
        return templated()
    if _over_budget(base, channel.id, asset.field, text):
        return templated()
    if _still_quotes_superseded(base, asset, text, values):
        return templated()

    return text, "WRITTEN", str(reply.get("note") or "")[:200], citations


def _attribute_table(base, corrected: dict) -> list[dict]:
    """The corrected values, as the only source of any number a writer uses."""
    return [{
        "entity_id": action["entity_id"],
        "attribute_path": action["attribute_path"],
        "value": action.get("new_value"),
        "unit": action.get("unit"),
        "doc": (action.get("source") or {}).get("doc_id", ""),
        "version": (action.get("source") or {}).get("version", ""),
    } for _, action in sorted(corrected.items())]


def _budget(base, channel_id: str, field: str, text: str) -> tuple[int | None, int]:
    """The MAX_LEN this channel imposes, and what the copy spends.

    Counted the way the engine counts it - a PDP is allowed five bullets, not
    five letters - so the number the writer is shown is the number that binds.
    """
    used = (len(text.splitlines()) if field in engine.COUNTED_FIELDS
            else len(text))
    for rule in base.rules_by_channel.get(channel_id, []):
        if rule.field == field and str(rule.kind) == "MAX_LEN":
            return int(rule.value), used
    return None, used


def _over_budget(base, channel_id: str, field: str, text: str) -> bool:
    budget, used = _budget(base, channel_id, field, text)
    return budget is not None and used > budget


def _still_quotes_superseded(base, asset, text: str, values: dict) -> bool:
    """Whether a rewrite left the figure it was written to replace.

    Checked with the validator's own matcher, so a rewrite that would fail
    ``stale_literal`` downstream fails here instead, where the deterministic
    template can still stand in.

    A figure that is *still correct* for another entity the same asset quotes is
    not evidence of anything. The comparison table on the base model's page
    carries both variants' wattage; under a reading that moves one of them the
    other's 45 W belongs there, and vetoing the rewrite over it rejected every
    version of the one asset this node exists to write.
    """
    for ref in sorted(asset.derived_from):
        entity_id, _, path = ref.partition(":")
        old = base.attr_values.get((entity_id, path))
        new = values.get((entity_id, path))
        if old == new or isinstance(old, bool) or not isinstance(old, (int, float)):
            continue
        if any(other != ref and other.partition(":")[2] == path
               and values.get((other.partition(":")[0], path)) == old
               for other in asset.derived_from):
            continue
        definition = base.attr_defs.get(path)
        unit = definition.unit if definition else None
        if engine._literal_pattern(old, unit).search(text):
            return True
    return False


def _row_addressed_text(base, asset, values: dict) -> str | None:
    """Rewrite a table whose rows name the variant each one is about.

    This is the one place the ambiguity that stops the deterministic
    substitution can be settled without writing anything. The comparison table
    quotes both variants' wattage and at baseline both read 45 W, so a literal
    swap across the whole asset cannot say which occurrence is which and
    ``a2a.agents._ambiguous`` refuses it - correctly. Row by row the attribution
    is the row's own first cell, so the correction lands on exactly the model it
    belongs to, and the other row keeps the figure that is still true for it.

    Refuses anything that is not a table of named rows: substituting into free
    prose is what this exists to avoid.
    """
    lines = asset.text.splitlines()
    if len(lines) < 2 or not all("|" in line for line in lines):
        return None

    variant_of_name = {base.variants[v].name: v for v in sorted(base.variants)}
    rewritten: list[str] = []
    changed = False

    for line in lines:
        variant_id = variant_of_name.get(line.split("|", 1)[0].strip())
        if variant_id is None:
            rewritten.append(line)  # a header, or a row naming nothing we hold
            continue
        updated = line
        for path in sorted(base.attr_defs):
            old = base.attr_values.get((variant_id, path))
            new = values.get((variant_id, path))
            if old == new or isinstance(old, bool) or not isinstance(old, (int, float)):
                continue
            definition = base.attr_defs.get(path)
            # The validator's own matcher, so a row it would call stale is the
            # row this rewrites.
            updated = engine._literal_pattern(
                old, definition.unit if definition else None).sub(
                    lambda m: m.group(0).replace(str(old), str(new), 1), updated)
        changed = changed or updated != line
        rewritten.append(updated)

    return "\n".join(rewritten) if changed else None


def _template_text(base, asset, values: dict) -> str | None:
    """The deterministic rewrite: the attribute table, rendered.

    Deliberately narrow. It settles a table row against the variant the row
    names, restores a declaration the record requires and can render exactly -
    the allergen statement, an allergen facet - and refuses everything else. An
    obvious hole is a better answer than an invented sentence, and a reviewer
    can see a hole.
    """
    row_addressed = _row_addressed_text(base, asset, values)
    if row_addressed is not None:
        return row_addressed

    variant_id = base.listings[asset.listing_id].variant_id
    merged = {path: values.get((entity_id, path))
              for (entity_id, path) in values if entity_id == variant_id}

    contains = [str(a) for a in (merged.get("food.allergens.contains") or [])]
    may = [str(a) for a in (merged.get("food.allergens.may_contain") or [])]
    if not (contains or may):
        return None

    lowered = asset.text.lower()
    missing = [a for a in contains + may if a.lower() not in lowered]
    if not missing:
        return None

    if asset.field == "facets":
        lines = {line.strip() for line in asset.text.splitlines() if line.strip()}
        lines.update(f"allergen:{a}" for a in missing)
        return "\n".join(sorted(lines))

    statement = engine.ALLERGEN_FORMATS["allergen_statement"](contains, may)
    return f"{asset.text.rstrip()} {statement}".strip()


# ---------------------------------------------------------------------------
# enrich - fill a mandatory gap, or ask the supplier
# ---------------------------------------------------------------------------


def enrich(state: FactoryState) -> dict:
    """Fill mandatory attributes that have no value, from supplied extracts only.

    Runs only where a completeness gap actually exists, which on a clean
    catalog is usually nowhere. The rule that outranks every other rule here is
    that a value nobody can point at in a supplied chunk is not filled: it
    becomes a REQUEST_SUPPLIER_INPUT, which is deliberately not executable.
    Inventing a product fact is the worst thing this system could do - a
    plausible allergen list is not an allergen list, and it gets printed on a
    label and read by somebody who needs it to be right.
    """
    base = baseline_mod.get()
    chosen = _chosen(state)
    actions = (chosen.get("delta") or {}).get("actions") or []
    values = _effective_values(state, actions)
    listings = _propagation_listings(
        base,
        {f"{a['entity_id']}:{a['attribute_path']}": a.get("new_value")
         for a in actions if a.get("kind") == str(ActionKind.SET_ATTRIBUTE)},
        chosen)
    gaps = _completeness_gaps(base, listings, values)

    if not gaps:
        return {"enrichments": [],
                "trace": [step("enrich", "no completeness gaps in the "
                                         "affected scope")]}

    entities = sorted({g["entity_id"] for g in gaps})
    chunks = retrieve.search(
        " ".join(sorted({g["attribute_path"] for g in gaps}))[:200] or "attribute",
        top_k=6, doc_types=["STANDARD", "CHANNEL", "POLICY"], entities=entities)
    supplied = retrieve.cite(chunks)
    definitions = [{"path": g["attribute_path"], "dtype": g["dtype"],
                    "unit": g["unit"], "ordered": g["ordered"]} for g in gaps]

    spent: list[LlmUsage] = []
    try:
        reply, usage = gateway.complete_json(
            [{"role": "system", "content": prompts.ENRICH_SYSTEM},
             {"role": "user", "content": prompts.enrich_user(
                 gaps, supplied, definitions)}],
            model=fast_model(), agent="enrich", run_id=state["run_id"])
        spent.append(usage)
        fills = reply.get("fills") or []
        unresolved = reply.get("unresolved") or []
        errors: list[str] = []
    except GatewayError as exc:
        # Nothing is filled without a model to read the extracts, and nothing
        # is guessed either. Every gap becomes a question for the supplier.
        fills, errors = [], [f"enrich: {exc}"]
        unresolved = [{"entity_id": g["entity_id"],
                       "attribute_path": g["attribute_path"],
                       "why": "no model was available to read the source extracts"}
                      for g in gaps]

    recorded = _iso(state.get("as_of_recorded"))
    known_chunks = {c["chunk_id"] for c in supplied}
    enrichments: list[dict] = []
    proposed: list[dict] = []
    refused: list[dict] = []

    for fill in fills:
        if not isinstance(fill, dict):
            continue
        row, why = _validated_fill(base, fill, known_chunks)
        if row is None:
            refused.append({"fill": fill, "why": why})
            continue
        citation = next((c for c in supplied
                         if c["chunk_id"] == row["chunk_id"]), {})
        source = {"doc_id": citation.get("doc_id", ""),
                  "version": "", "excerpt": row["quote"][:300],
                  "chunk_id": row["chunk_id"]}
        ingest.record_attribute(
            entity_id=row["entity_id"], attribute_path=row["attribute_path"],
            value=row["value"], valid_from=_iso(state.get("as_of")),
            source_doc=citation.get("doc_id", ""), confidence=row["confidence"],
            agent="enrich", model=fast_model(), run_id=state["run_id"],
            recorded_at=recorded)
        enrichments.append({**row, "source": source, "status": "FILLED"})
        proposed.append({
            "id": f"SA-{row['entity_id']}-{row['attribute_path']}",
            "kind": str(ActionKind.SET_ATTRIBUTE),
            "entity_id": row["entity_id"],
            "attribute_path": row["attribute_path"],
            "old_value": None, "new_value": row["value"],
            "confidence": row["confidence"], "source": source,
            "rationale": f"filled a mandatory gap from {row['chunk_id']}",
        })

    for gap in unresolved:
        if not isinstance(gap, dict):
            continue
        entity_id = str(gap.get("entity_id") or "")
        supplier = _supplier_of(base, entity_id)
        if not supplier:
            continue
        path = str(gap.get("attribute_path") or "")
        proposed.append({
            "id": f"RQ-{entity_id}-{path}",
            "kind": str(ActionKind.REQUEST_SUPPLIER_INPUT),
            "supplier": supplier,
            "doc_ref": entity_id,
            "question": (f"{entity_id} has no value on file for {path}, which "
                         f"is mandatory on the channels it publishes to. "
                         f"{str(gap.get('why') or '')[:200]}"),
            "rationale": "no supplied extract carries this value",
        })
        enrichments.append({"entity_id": entity_id, "attribute_path": path,
                            "status": "UNRESOLVED",
                            "why": str(gap.get("why") or "")[:300]})

    valid, dropped = _validate_actions(proposed, base)
    return {
        "ranked": _append_actions(state, valid),
        "enrichments": enrichments,
        "citations": supplied,
        "rejected_actions": (state.get("rejected_actions") or []) + dropped + refused,
        "status": "ENRICHED",
        "errors": errors,
        "usage": _spend("enrich", *spent),
        "trace": [step("enrich",
                       f"{len(gaps)} gap(s): "
                       f"{sum(1 for e in enrichments if e['status'] == 'FILLED')} "
                       f"filled from source, "
                       f"{sum(1 for e in enrichments if e['status'] == 'UNRESOLVED')} "
                       f"referred to the supplier",
                       gaps=[f"{g['entity_id']}:{g['attribute_path']}"
                             for g in gaps][:8],
                       refused=[r["why"] for r in refused][:4])],
    }


def _completeness_gaps(base, listings: list[str], values: dict) -> list[dict]:
    """Mandatory attributes with nothing on file, in the affected scope.

    An empty list is not a gap: an empty ``may_contain`` is a declared absence
    of allergens and a complete answer. Counting it would report a clean
    catalog as incomplete, and a reviewer stops believing the number.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for listing_id in listings:
        listing = base.listings.get(listing_id)
        if listing is None:
            continue
        for definition in base.applicable_attrs(listing.variant_id):
            if listing.channel_id not in definition.required_for:
                continue
            key = (listing.variant_id, definition.path)
            if key in seen:
                continue
            value = values.get(key)
            if value is not None and value != "":
                continue
            seen.add(key)
            out.append({
                "entity_id": listing.variant_id,
                "attribute_path": definition.path,
                "label": definition.label,
                "dtype": definition.dtype,
                "unit": definition.unit,
                "ordered": definition.ordered,
                "required_by": listing.channel_id,
                "listing_id": listing_id,
            })
    return out


def _validated_fill(base, fill: dict, known_chunks: set[str]):
    """A fill is only a fill if it names its chunk, its quote and its type."""
    entity_id = str(fill.get("entity_id") or "")
    path = str(fill.get("attribute_path") or "")
    chunk_id = str(fill.get("chunk_id") or "")
    quote = str(fill.get("quote") or "")

    if entity_id not in base.variants and entity_id not in base.products:
        return None, f"no such product or variant: {entity_id!r}"
    if path not in base.attr_defs:
        return None, f"no such attribute: {path!r}"
    if chunk_id not in known_chunks:
        return None, (f"{chunk_id!r} is not one of the supplied extracts, so "
                      f"the value has no source")
    if not quote.strip():
        return None, "a fill without the sentence it was read from is not a fill"

    value, why = _coerce(fill.get("value"), base.attr_defs[path].dtype)
    if why:
        return None, f"{entity_id} {path}: {why}"

    try:
        confidence = max(0.0, min(1.0, float(fill.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = FALLBACK_CONFIDENCE

    return {"entity_id": entity_id, "attribute_path": path, "value": value,
            "chunk_id": chunk_id, "quote": quote, "confidence": confidence}, ""


def _supplier_of(base, entity_id: str) -> str:
    product_id = (entity_id if entity_id in base.products
                  else base.product_of_variant.get(entity_id, ""))
    product = base.products.get(product_id)
    return product.supplier if product else ""


# ---------------------------------------------------------------------------
# validate_final
# ---------------------------------------------------------------------------


def validate_final(state: FactoryState) -> dict:
    """Re-validate the chosen resolution with every follow-on action attached.

    The candidate was priced on its attribute changes alone. What the reviewer
    approves is the whole thing - the rewritten copy, the withheld listings,
    the facets, the supplier questions - so the figures they are shown have to
    come from a pass over that, not over the version it started as.
    """
    chosen = _chosen(state)
    if not chosen:
        return {"final_validation": {},
                "trace": [step("validate_final", "no resolution to validate")]}

    delta = chosen.get("delta") or {}
    result = planning.run_scenario(delta, as_of=state.get("as_of"),
                                   as_of_recorded=state.get("as_of_recorded"))

    ranked = [dict(r) for r in state.get("ranked") or []]
    ranked[0] = {**ranked[0], **result}
    # Re-scored so the comparison table stays internally consistent: the head
    # has moved and the normalisation the score depends on moves with it.
    scored = planning._score(ranked, state.get("weights") or {})
    reordered = sorted(scored, key=lambda r: r.get("kpis", {}).get("safety_flags", 0))

    kpis = result.get("kpis", {})
    binding = [v for v in result.get("violations") or []
               if v.get("severity") == "HARD"]
    return {
        "ranked": reordered,
        "final_validation": {
            "scenario_id": chosen.get("scenario_id"),
            "name": chosen.get("name"),
            **result,
        },
        "status": "VALIDATED",
        "trace": [step("validate_final",
                       f"{kpis.get('listings_ready_pct', 0)}% of affected "
                       f"listings publishable, {len(binding)} binding rule(s), "
                       f"{kpis.get('channels_blocked', 0)} channel(s) blocked",
                       feasible=result.get("feasible"),
                       trace_hash=result.get("trace_hash"),
                       binding=[v.get("detail") for v in binding][:4])],
    }


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------


def recommend(state: FactoryState) -> dict:
    """Write the recommendation a content reviewer approves or rejects.

    The diff is assembled first, from the change set and the derivation graph:
    source -> old value -> new value -> impacted outputs, one row per corrected
    field. That sentence is what the brief requires every generated change to
    be able to produce about itself, so it is built rather than written, and
    the model is handed it and asked for the narrative around it.

    The model may only name a scenario that was actually validated. Anything
    else is a resolution nobody has checked, and the top-ranked one stands
    instead.
    """
    base = baseline_mod.get()
    ranked = state.get("ranked", [])
    if not ranked:
        return {"status": "NO_OPTIONS",
                "trace": [step("recommend", "no validated resolution to recommend")]}

    top = ranked[0]
    citations = state.get("citations", [])
    summary = _case_summary(state)

    try:
        written, usage = gateway.complete_json(
            [{"role": "system", "content": prompts.RECOMMEND_SYSTEM},
             {"role": "user", "content": prompts.recommend_user(
                 ranked, _change_lines(base, state, top), citations, summary,
                 state.get("weights") or {},
                 plan_diff=state.get("plan_diff") or {},
                 blocked=state.get("blocked") or {},
                 clarification=state.get("clarification") or {},
                 precedent=state.get("precedent") or {})}],
            model=reasoning_model(), agent="recommend", run_id=state["run_id"])
    except GatewayError as exc:
        return _recommendation_update(state, base, top,
                                      _templated_narrative(state, top),
                                      citations, error=f"recommend: {exc}")

    # The model may only recommend a resolution that was actually validated.
    chosen = next((r for r in ranked
                   if r["scenario_id"] == written.get("scenario_id")), top)
    return {**_recommendation_update(state, base, chosen, written, citations),
            "usage": _spend("recommend", usage)}


def _case_summary(state: FactoryState) -> str:
    return "; ".join(s.get("summary", "")
                     for s in state.get("signals", []))[:800]


def _templated_narrative(state: FactoryState, top: dict) -> dict:
    """The recommendation when no model is available.

    Every figure in it is one the validator produced, which is the only reason
    a template can stand in for a narrative at all.
    """
    kpis = top.get("kpis", {})
    scope = (top.get("delta") or {}).get("scope") or {}
    return {
        "scenario_id": top["scenario_id"],
        "confidence": 0.5,
        "narrative": (
            f"{top.get('name', 'the top-ranked resolution')} applies the "
            f"correction to {', '.join(scope.get('entities') or []) or 'no variant'} "
            f"under the {scope.get('level')} reading. It moves "
            f"{kpis.get('fields_affected', 0)} field(s), leaves "
            f"{kpis.get('assets_stale', 0)} asset(s) stale and "
            f"{kpis.get('channels_blocked', 0)} channel(s) blocked, and takes "
            f"{kpis.get('listings_ready_pct', 0)}% of the affected listings to "
            f"publishable. No model was available to argue the trade-off, so "
            f"the deterministic ranking stands as written."),
        "assumptions": ["the deterministic ranking is the whole of the argument: "
                        "no narrative was generated for this run"],
        "trade_offs": [],
    }


def _change_lines(base, state: FactoryState, scenario: dict) -> list[dict]:
    """The reviewer's diff, assembled from the catalog before anyone writes prose.

    Every field is deterministic: the document and version the value stands on,
    what it was, what it becomes, and every asset and channel that quoted it.
    The narrative restates this; it never derives it.
    """
    actions = (scenario.get("delta") or {}).get("actions") or []
    lines: list[dict] = []

    for action in sorted(actions, key=lambda a: a.get("id", "")):
        if action.get("kind") != str(ActionKind.SET_ATTRIBUTE):
            continue
        entity_id = action["entity_id"]
        path = action["attribute_path"]
        definition = base.attr_defs.get(path)
        assets = base.assets_derived_from.get(f"{entity_id}:{path}", [])
        listings = ({base.assets[a].listing_id for a in assets}
                    | set(listings_for(base, entity_id)))
        source = action.get("source")
        lines.append(ChangeSummaryLine(
            entity_id=entity_id,
            attribute_path=path,
            old_value=action.get("old_value"),
            new_value=action.get("new_value"),
            unit=definition.unit if definition else action.get("unit"),
            source=SourceRef.model_validate(source) if source else None,
            confidence=action.get("confidence"),
            impacted_assets=sorted(assets),
            impacted_channels=sorted({base.listings[l].channel_id
                                      for l in listings if l in base.listings}),
            safety=bool(definition and definition.safety_class),
        ).model_dump(mode="json"))
    return lines


def _rejected_alternatives(chosen: dict, ranked: list[dict]) -> list[dict]:
    """Why each validated option that was not recommended lost.

    Measured, not argued. "Why not that one instead" is the reviewer's next
    question, and an answer written by the model would be an answer nobody
    could check - so every figure here comes out of the two ``SimResult``s
    being compared and the scopes their change sets declare.
    """
    out: list[dict] = []
    for other in ranked:
        if other.get("scenario_id") == chosen.get("scenario_id"):
            continue
        out.append({
            "scenario_id": other.get("scenario_id", ""),
            "name": other.get("name", ""),
            "why": _why_rejected(chosen, other),
        })
    return out


def _scope_width(scenario: dict) -> int:
    return len(((scenario.get("delta") or {}).get("scope") or {}).get("entities")
               or [])


def _why_rejected(chosen: dict, other: dict) -> str:
    """One sentence per losing option, in the order the ranking weighed them.

    Safety first because it is the pre-sort rather than a weight, then
    publishability, then the scope the evidence supports, then readiness. The
    score is the answer only when nothing measurable separates them.
    """
    ours, theirs = chosen.get("kpis") or {}, other.get("kpis") or {}
    reasons: list[str] = []

    if theirs.get("safety_flags", 0) > ours.get("safety_flags", 0):
        reasons.append(f"carries {theirs['safety_flags']} open safety flag(s) "
                       f"against {ours.get('safety_flags', 0)}")
    if chosen.get("feasible") and not other.get("feasible"):
        binding = sum(1 for v in other.get("violations") or []
                      if v.get("severity") == "HARD")
        reasons.append(f"{binding} binding rule(s) leave it unpublishable")
    if _scope_width(other) > _scope_width(chosen):
        reasons.append(f"applies the correction to {_scope_width(other)} "
                       f"variant(s) where the evidence supports "
                       f"{_scope_width(chosen)}")
    if theirs.get("listings_ready_pct", 0) < ours.get("listings_ready_pct", 0):
        reasons.append(f"takes {theirs['listings_ready_pct']}% of affected "
                       f"listings to publishable against "
                       f"{ours.get('listings_ready_pct', 0)}%")

    if not reasons:
        return (f"scored {other.get('score')} against {chosen.get('score')} on "
                f"the reviewer's weights")
    return "; ".join(reasons)


def _review_grounds(base, scenario: dict,
                    state: FactoryState | None = None) -> list[str]:
    """The measured grounds on which approval stops being optional.

    Four of them, and every one is read off the run's own measurements: a
    regulated product or a safety-class attribute anywhere the correction
    reaches, a safety or allergen declaration still open on the resolution, or a
    listing the resolution withholds. Withholding is the ground that was
    missing, and it is the one that matters most - a run that takes four
    channels off air under a safety hold is not a run anybody may wave through.

    The first ground is ``_forced_escalation``, the same measurement triage uses
    to make a correction CRITICAL whatever a model said. Sharing it is the
    point: a run cannot report CRITICAL because a regulated product is exposed
    and then report that approval is optional, because both sentences now come
    out of one function over one blast radius.

    Nothing here is asked of a model. A verdict a model could argue down is a
    verdict it could publish around, and ``request_approval`` derives it a
    second time from this function so that no edit upstream can lower it.
    """
    delta = scenario.get("delta") or {}
    actions = delta.get("actions") or []
    grounds: list[str] = []

    blast = (state or {}).get("affected") or {}
    if blast.get("affected"):
        escalation = _forced_escalation((state or {}).get("signals") or [], blast,
                                        str((state or {}).get("case_id") or ""))
        if escalation:
            grounds.append(escalation)

    # Every variant this resolution touches, however it touches it: through the
    # reading's scope, through an attribute change, or through a listing it
    # rewrites or withholds. A withheld listing on a regulated product is the
    # case a scope-only or action-only read misses.
    entities = {str(e) for e in (delta.get("scope") or {}).get("entities") or []}
    for action in actions:
        if action.get("entity_id"):
            entities.add(str(action["entity_id"]))
        listing = base.listings.get(str(action.get("listing_id") or ""))
        if listing is not None:
            entities.add(listing.variant_id)

    regulated = sorted({p for p in (
        e if e in base.products else base.product_of_variant.get(e, "")
        for e in entities) if p and base.products[p].regulated})
    if regulated:
        grounds.append(f"{', '.join(regulated)} is regulated")

    safety = sorted({str(a.get("attribute_path")) for a in actions
                     if a.get("kind") == str(ActionKind.SET_ATTRIBUTE)
                     and getattr(base.attr_defs.get(
                         str(a.get("attribute_path") or "")), "safety_class", False)})
    if safety:
        grounds.append(f"{', '.join(safety)} is safety-class")

    open_gate = sorted({str(v.get("constraint")) for v in
                        scenario.get("violations") or []
                        if v.get("constraint") in planning.SAFETY_GATE})
    if open_gate:
        grounds.append(f"{', '.join(open_gate)} is open on an affected listing")

    withheld = sorted({str(a.get("listing_id")) for a in actions
                       if a.get("kind") == str(ActionKind.WITHHOLD_CHANNEL)})
    if withheld:
        grounds.append(f"{len(withheld)} listing(s) held back under a safety "
                       f"hold: {', '.join(withheld)}")

    return grounds


def _governed(base, state: FactoryState, recommendation: dict) -> dict:
    """Stamp the review obligation onto a recommendation.

    Cheap, deterministic and idempotent, so it can be run again at the approval
    gate. That is the point: ``requires_review`` is not a field anything is
    trusted to have set correctly, it is a function of the run and the
    resolution, and the gate computes it rather than reading it.
    """
    if not recommendation:
        return recommendation
    grounds = _review_grounds(base, {
        "delta": recommendation.get("delta") or {},
        "violations": recommendation.get("violations") or [],
    }, state)
    return {**recommendation, "requires_review": bool(grounds),
            "review_grounds": grounds}


def _recommendation_update(state: FactoryState, base, chosen: dict, written: dict,
                           citations: list[dict],
                           error: str | None = None) -> dict:
    lines = _change_lines(base, state, chosen)
    final = state.get("final_validation") or {}
    diff = state.get("plan_diff") or {}
    # Everything the reviewer view renders, in one object: the verdict, the
    # diff, the evidence and the losing options with the reason each lost. The
    # model contributes the narrative, the assumptions and the trade-offs, and
    # nothing else - every figure below is copied from the SimResult the
    # validator produced for `chosen` or from the change set it priced.
    recommendation = {
        "id": _uid("REC"),
        "incident_id": state.get("incident_id", ""),
        "scenario_id": chosen["scenario_id"],
        "scenario_name": chosen.get("name", ""),
        "confidence": float(written.get("confidence") or 0.6),
        "narrative": str(written.get("narrative", "")),
        "assumptions": written.get("assumptions", []),
        "trade_offs": written.get("trade_offs", []),
        "rejected_alternatives": _rejected_alternatives(
            chosen, state.get("ranked") or []),
        "changes": lines,
        "evidence": sorted({str((line.get("source") or {}).get("doc_id", ""))
                            for line in lines if line.get("source")} - {""}),
        "kpis": chosen.get("kpis", {}),
        # Absent is not the same as feasible: a resolution nobody could price
        # is one nobody should publish.
        "feasible": bool(chosen.get("feasible")),
        "violations": chosen.get("violations", []),
        "delta": chosen.get("delta", {}),
        "scope": (chosen.get("delta") or {}).get("scope") or {},
        "claim_flags": state.get("claim_flags") or [],
        "final_validation": final,
        "citations": citations[:8],
        # What this recommendation was made against. A later revision compares
        # its own signals to this list to work out what is genuinely new, which
        # is the difference between "the world changed" and "we ran it twice".
        "signals_seen": [{"id": s.get("id"), "kind": s.get("kind")}
                         for s in state.get("signals", [])],
        "revision": int(state.get("revision") or 0),
        "supersedes": (state.get("previous_recommendation") or {}).get("id"),
        # What moved since the plan this one replaces. The headline is computed
        # by `_plan_diff`; the model may only phrase it.
        "change": str(written.get("change") or diff.get("headline", "")),
        "provenance": {"kind": str(ProvenanceKind.INFERRED), "agent": "recommend",
                       "model": reasoning_model(), "run_id": state["run_id"]},
    }
    # The review obligation is stamped on last, from the run's blast radius and
    # the change set and violations already in the object above. It is never one
    # of the fields the narrative can influence.
    recommendation = _governed(base, state, recommendation)
    return {
        "recommendation": recommendation,
        "status": "AWAITING_APPROVAL",
        "errors": [error] if error else [],
        "trace": [step("recommend", f"recommending {chosen.get('name', '')}"
                       + (f" - {diff['headline']}" if diff else ""),
                       confidence=recommendation["confidence"],
                       requires_review=recommendation["requires_review"],
                       review_grounds=recommendation["review_grounds"],
                       revision=recommendation["revision"],
                       changes=len(lines),
                       ready=chosen.get("kpis", {}).get("listings_ready_pct"))],
    }


# ---------------------------------------------------------------------------
# approval - the graph genuinely stops here
# ---------------------------------------------------------------------------


def request_approval(state: FactoryState) -> Command:
    """Pause the run until a reviewer decides.

    ``interrupt()`` suspends the graph and persists the checkpoint. The process
    can be killed here and the run resumed later from the same point - which is
    what makes this an approval gate rather than a modal dialog, and what makes
    "recover safely from partial execution" true rather than claimed.

    The review obligation is recomputed here rather than read out of the
    recommendation. It is a function of the change set, so the gate can derive
    it - and a gate that derives it cannot be told the wrong answer by anything
    that wrote the recommendation, this run or a resumed one.
    """
    # Recomputed, then written back, so the incident record, the interrupt
    # payload and the state all carry the same governed answer.
    recommendation = _governed(baseline_mod.get(), state,
                               state.get("recommendation") or {})
    state = {**state, "recommendation": recommendation}
    _persist_incident(state)

    decision = interrupt({
        "kind": "APPROVAL_REQUIRED",
        "incident_id": state.get("incident_id"),
        "recommendation": recommendation,
        "options": _ranked_for_prompt(state.get("ranked", [])),
        "changes": recommendation.get("changes", []),
        "requires_review": recommendation.get("requires_review", False),
        "review_grounds": recommendation.get("review_grounds", []),
        "severity": state.get("severity"),
    })

    verdict = str(decision.get("decision", "REJECT")).upper()
    actor = str(decision.get("actor", "reviewer"))
    comment = str(decision.get("comment", ""))
    scenario_id = decision.get("scenario_id") or recommendation.get("scenario_id")

    approval = {"id": _uid("APP"), "incident_id": state.get("incident_id"),
                "scenario_id": scenario_id, "decision": verdict, "actor": actor,
                "comment": comment, "decided_at": datetime.now().isoformat()}
    _persist_approval(approval, state)

    return Command(
        goto="publish" if verdict == ApprovalDecision.APPROVE else "close",
        update={"approval": approval,
                "recommendation": recommendation,
                "status": f"DECIDED_{verdict}",
                "trace": [step("approval",
                               f"reviewer {verdict.lower()}d {scenario_id}",
                               actor=actor, comment=comment,
                               requires_review=recommendation.get(
                                   "requires_review", False),
                               review_grounds=recommendation.get(
                                   "review_grounds", []))]},
    )


def _title(state: FactoryState) -> str:
    signals = state.get("signals", [])
    if not signals:
        return "Correction run"
    if len(signals) == 1:
        return signals[0].get("summary", "Correction")[:120]
    return f"{len(signals)} concurrent corrections"


def _persist_incident(state: FactoryState) -> None:
    incident_id = state.get("incident_id")
    if not incident_id:
        return
    doc = {k: state.get(k) for k in
           ("signals", "affected", "causal_chain", "root_causes", "symptoms",
            "citations", "prior_incidents", "recommendation", "triage_reason",
            "scope_candidates", "chosen_scope", "claim_flags", "regenerated",
            "enrichments", "final_validation")}
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO incidents (id, thread_id, opened_at, status, severity,"
            " title, doc) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status = excluded.status,"
            " severity = excluded.severity, doc = excluded.doc",
            (incident_id, state.get("thread_id", ""), datetime.now().isoformat(),
             IncidentStatus.AWAITING_APPROVAL, state.get("severity", "MEDIUM"),
             _title(state), db.dumps(doc)))
        for scenario in state.get("ranked", []):
            conn.execute(
                "INSERT INTO scenarios (id, incident_id, name, score, feasible,"
                " pareto, doc) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET score = excluded.score,"
                " doc = excluded.doc",
                (scenario["scenario_id"], incident_id, scenario["name"],
                 scenario.get("score"), int(bool(scenario.get("feasible"))),
                 int(bool(scenario.get("pareto_optimal"))),
                 db.dumps(scenario)))


def _persist_approval(approval: dict, state: FactoryState) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO approvals (id, incident_id, scenario_id, decision,"
            " actor, comment, decided_at) VALUES (?,?,?,?,?,?,?)",
            (approval["id"], approval["incident_id"], approval["scenario_id"],
             approval["decision"], approval["actor"], approval["comment"],
             approval["decided_at"]))
        planning.audit(approval["actor"], "DECIDE", "incident",
                       approval["incident_id"],
                       {"decision": approval["decision"],
                        "scenario": approval["scenario_id"],
                        "comment": approval["comment"]},
                       Provenance(kind=ProvenanceKind.DECIDED,
                                  source_id=approval["id"],
                                  run_id=state.get("run_id")),
                       conn=conn)


# ---------------------------------------------------------------------------
# publish and close
# ---------------------------------------------------------------------------


def publish(state: FactoryState) -> dict:
    """Push the approved resolution to the channels.

    Idempotency-keyed on the incident and the scenario, so a resumed thread
    cannot publish twice. The gates that can still refuse it live in
    ``commit_plan`` rather than here - no approval on file, a source version
    that moved since the resolution was validated, or an open safety or
    allergen declaration - so no future edit to this graph can route around
    them.

    A lock conflict is not a failure to report and stop at: another run may
    have claimed the same batch while this one awaited a decision, and
    re-planning against what is left is a better answer. One retry, then a
    human arbitrates.
    """
    approval = state.get("approval") or {}
    recommendation = state.get("recommendation") or {}
    scenario_id = approval.get("scenario_id")
    delta = next((r["delta"] for r in state.get("ranked", [])
                  if r["scenario_id"] == scenario_id),
                 recommendation.get("delta") or {"id": "D", "actions": []})

    result = planning.commit_plan(
        incident_id=state.get("incident_id", ""), scenario_id=scenario_id,
        actions=delta, actor=approval.get("actor", "reviewer"),
        as_of=state.get("as_of"),
        idempotency_key=f"publish:{state.get('incident_id')}:{scenario_id}")

    if result.get("error") == "conflict":
        retries = int(state.get("publish_retries") or 0)
        if retries < MAX_PUBLISH_RETRIES:
            return {"commit_result": result, "publish_retries": retries + 1,
                    "status": "REPLANNING_AFTER_CONFLICT",
                    "trace": [step("publish",
                                   "another run published these batches while "
                                   "this one awaited a decision - re-planning "
                                   "against what is left",
                                   conflicts=result.get("conflicts"),
                                   attempt=retries + 1)]}
        return {"commit_result": result, "status": "CONFLICT_UNRESOLVED",
                "trace": [step("publish",
                               "still conflicting after a retry - a reviewer "
                               "has to arbitrate between the two runs",
                               conflicts=result.get("conflicts"))]}

    if not result.get("committed"):
        return {"commit_result": result, "status": "PUBLISH_REFUSED",
                "trace": [step("publish",
                               f"refused: {result.get('detail', '')}",
                               error=result.get("error"),
                               violations=[v.get("detail") for v in
                                           result.get("violations") or []][:4])]}

    return {"commit_result": result, "status": "PUBLISHED",
            "trace": [step("publish",
                           f"{len(result.get('actions', []))} action(s) "
                           f"published under {len(result.get('locks', []))} "
                           f"publish lock(s)",
                           committed=True,
                           idempotent=bool(result.get("idempotent_replay")),
                           trace_hash=result.get("trace_hash"))]}


def ack_and_park(state: FactoryState) -> dict:
    """Triaged as immaterial: recorded, not escalated.

    Parking is a decision with a reason attached, so it lands in the audit
    ledger. "Nothing happened" and "we looked and it did not matter" are
    different answers, and only one of them is defensible afterwards.
    """
    planning.audit("triage", "PARK", "incident",
                   state.get("incident_id", "-"),
                   {"reason": state.get("triage_reason", "")},
                   Provenance(kind=ProvenanceKind.INFERRED, agent="triage",
                              run_id=state.get("run_id")))
    return {"status": "PARKED",
            "trace": [step("ack_and_park",
                           state.get("triage_reason",
                                     "no published content reached"))]}


def close(state: FactoryState) -> dict:
    """Terminal bookkeeping.

    A published run has already had its incident marked COMMITTED inside the
    publish transaction; overwriting that here would let the closing step
    contradict the ledger.
    """
    status = state.get("status", "CLOSED")
    incident_id = state.get("incident_id")
    published = bool((state.get("commit_result") or {}).get("committed"))

    if incident_id and not published:
        final = (IncidentStatus.PARKED if not state.get("material")
                 else IncidentStatus.REJECTED)
        conn = db.connect()
        conn.execute("UPDATE incidents SET status = ? WHERE id = ?",
                     (str(final), incident_id))
        conn.commit()

    keep = published or status.startswith("DECIDED")
    return {"status": status if keep else "CLOSED",
            "trace": [step("close", f"run finished: {status}")]}
