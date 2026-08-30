"""The branch nodes, and the predicates that route to them.

A correction run is not one shape. A notice that restates a value nobody
publishes, a notice two supplier documents disagree about, and a notice whose
affected variant nothing in the record settles are three different problems,
and a pipeline that walked all three down the same nodes in the same order
would be describing a process rather than following one.

So the routes here are real decisions about the correction, read out of the
data:

    sources disagree, or the scope will not resolve -> supplier_clarification
    a comparable correction has a postmortem        -> apply_precedent
    nothing the content leg could publish           -> blocked_review
    the publish lost a race, or was overtaken       -> back to plan_candidates

Every predicate is a pure function of state - no retrieval, no catalog lookup,
no clock - so the same correction always takes the same route. This is variety,
not randomness: the trace hash and the audit trail both depend on a run being
reproducible, and a graph that rolled dice would trade the thing that makes the
system defensible for the appearance of sophistication. There is a test that
asserts it.

No node in this file calls a model. Two of them retrieve, and what they
retrieve is context for the writer downstream, never an instruction to anyone.
"""

from __future__ import annotations

from sc.contracts import ActionKind, CorrectionKind
from sc.graph import evidence, nodes
from sc.graph.state import RESET, FactoryState, step
from sc.rag import retrieve
from sc.state import baseline as baseline_mod

# Below this, the readings of a correction that the record supports are not
# actually separated by the evidence behind them. That is not a failure of the
# resolver - "the AeroPure 300 draws 65 W" genuinely does not say which model
# it means - and the honest answer is to say so and ask, rather than to publish
# the widest reading and call the ambiguity resolved. The gateway-down fallback
# deliberately reports 0.3, so a run with no model available lands here too.
SCOPE_CONFIDENCE_FLOOR = 0.55

# Violation constraints no amount of content work clears. A source version that
# moved under a resolution needs re-extracting, not rewriting; a batch another
# run already holds needs a different batch. Everything else the leg between
# `rank` and the approval gate settles one way or another - it rewrites the
# copy, rebuilds the feed row under the channel's own field names, adds the
# missing declaration, cites the change, or (for a safety inference it cannot
# raise the confidence of) withholds the listing, which is a decision rather
# than a failure. Written as the exception rather than the allowlist, because a
# new constraint name should default to "the leg has a go at it" rather than to
# "hand it straight to a human".
BEYOND_CONTENT = frozenset({"stale_version", "publish_conflict"})

# Publish refusals another pass could clear. Both are races rather than
# verdicts: another run took the batch, or the supplier sent a newer version
# while this one sat at the approval gate. ``commit_plan``'s other two refusals
# - no approval on file, an open safety hold - are not races, and re-planning
# would reproduce them exactly.
REPLANNABLE_REFUSALS = ("conflict", "stale_version")

# One retry after a refused publish. The counter lives on the state and is
# spent by whichever node saw the refusal first - `publish` for a lock
# conflict, `verify_publish` for a stale version - so the budget is imported
# rather than restated: two constants of the same name that had to agree would
# eventually not.
MAX_PUBLISH_RETRIES = nodes.MAX_PUBLISH_RETRIES

# The statuses that send a run back for another plan. `publish` writes the
# first when it loses a lock; this file writes the second when a source version
# moved under an already-approved resolution. The router reads the status
# rather than re-running the predicate, because by then the retry has been
# spent and the predicate would be answering for the next attempt.
REPLAN_AFTER_CONFLICT = "REPLANNING_AFTER_CONFLICT"
REPLAN_AFTER_STALE = "REPLANNING_AFTER_STALE_VERSION"
REPLANNING_STATUSES = frozenset({REPLAN_AFTER_CONFLICT, REPLAN_AFTER_STALE})

# How much retrieved prose a branch hands to the writer. Past this it is a
# document rather than guidance, and the recommendation prompt truncates it
# anyway.
MAX_GUIDANCE = 2500


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def is_immaterial(state: FactoryState) -> bool:
    """Did triage conclude there is nothing here worth propagating?

    Read from the verdict rather than re-derived from the signals. The verdict
    is not the model's alone - `triage` overrides it deterministically whenever
    a safety-class attribute or a regulated product is in scope - and a
    predicate that decided materiality for itself here would be a second
    opinion with the authority to route past that override.
    """
    return not state.get("material")


def sources_conflict(state: FactoryState) -> bool:
    """Is there a disagreement this run is not entitled to settle?

    Two ways to get here, and they are the same problem seen from either end.
    A SOURCE_CONFLICT signal is an explicit one: two documents assert different
    values for the same field and POL-002 decides which stands *for now*, which
    is not the same as deciding which is true. The other is quieter - every
    reading of the correction the record supports came back below
    ``SCOPE_CONFIDENCE_FLOOR``, which is the honest form of "nothing on file
    says which variant this applies to".

    Both end at the same place: a question only the supplier can answer, and a
    recommendation that does not present it as answered.
    """
    return bool(_open_conflicts(state)) or _scope_unclear(state)


def _open_conflicts(state: FactoryState) -> list[dict]:
    """Signals raised because two documents assert different values."""
    return [s for s in state.get("signals") or []
            if s.get("kind") == str(CorrectionKind.SOURCE_CONFLICT)]


def _scope_unclear(state: FactoryState) -> bool:
    """Did every reading of the correction come back below the floor?"""
    candidates = state.get("scope_candidates") or []
    if not candidates:
        return False
    return max(float(c.get("confidence") or 0.0)
               for c in candidates) < SCOPE_CONFIDENCE_FLOOR


def has_precedent(state: FactoryState) -> bool:
    """Has a correction like this one been through here before?

    Checked after `sources_conflict`, which is the sharper fact. A resemblance
    to a past incident is guidance; an unresolved disagreement between two
    supplier documents is a property of *this* correction, and it is the one
    that has to reach the reviewer.
    """
    return bool(state.get("prior_incidents"))


def nothing_publishable(state: FactoryState) -> bool:
    """Is there no candidate the content leg could carry to a channel?

    Deliberately not "no candidate is feasible". At `rank` the candidates are
    attribute changes and nothing else - every asset that quoted the old figure
    is still stale, every claim it substantiated still unsupported - so on any
    correction that matters *nothing* is feasible yet. Routing on feasibility
    here would send every real run to a reviewer with the content work undone,
    which is the one outcome that would make the whole leg pointless.

    The question is the narrower one: is any candidate still workable - does
    any of them have something to publish and nothing binding it that the
    content leg cannot address? Only when the answer is no does a reviewer get
    handed the list of what binds instead of a plan.
    """
    ranked = state.get("ranked") or []
    if not ranked:
        return True

    for option in ranked:
        if not (option.get("delta") or {}).get("actions"):
            continue  # an option that does nothing publishes nothing
        binding = {str(v.get("constraint") or "")
                   for v in option.get("violations") or []
                   if v.get("severity") == "HARD"}
        if not (binding & BEYOND_CONTENT):
            return False
    return True


def publish_conflicted(state: FactoryState) -> bool:
    """Was the publish refused for a reason another plan could clear?

    Says nothing about whether a retry is still allowed - that is the budget's
    question and it is asked in `verify_publish`, which holds the counter. A
    predicate that answered both would change its own answer by acting on it.
    """
    error = str((state.get("commit_result") or {}).get("error") or "")
    return error in REPLANNABLE_REFUSALS


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def apply_precedent(state: FactoryState) -> dict:
    """Pull out what a comparable correction taught, for the writer to use.

    A postmortem is the one document type that records what was actually done
    about a correction and whether it held. Retrieving the matched ones and
    handing them to the recommendation is the difference between an
    organisation that writes postmortems and one that reads them.

    **Guidance only, never actions.** Nothing here proposes a change, edits a
    scope or touches a change set. A remedy from last year is prose about a
    catalog that has moved since; what happens to this correction is settled by
    the validator against the record as it stands, and the postmortem's job is
    to tell a reviewer what went wrong the last time somebody was sure.
    """
    priors = [str(p) for p in state.get("prior_incidents") or [] if p]
    query = " ".join(s.get("summary", "")
                     for s in state.get("signals") or [])[:400]

    hits = retrieve.search(
        query or "a supplier corrected a specification after content had "
                 "already been prepared for several channels",
        top_k=4, doc_types=["POSTMORTEM"])
    # Only the incidents this correction actually matched. A remedy from an
    # unrelated failure is a confident wrong answer, and a confident wrong
    # answer is the one thing a postmortem should not produce.
    relevant = [h for h in hits if h.chunk.doc_id in set(priors)] or hits[:2]
    citations = retrieve.cite(relevant)

    return {
        "precedent": {
            "incidents": priors,
            "guidance": "\n\n".join(
                f"[{c['doc_id']} | {c['heading']}]\n{c['excerpt']}"
                for c in citations)[:MAX_GUIDANCE],
            "note": ("what a comparable correction cost last time - context "
                     "for the recommendation, not a plan to copy"),
        },
        "citations": citations,
        "status": "PRECEDENT",
        "trace": [step("apply_precedent",
                       f"prior incident {', '.join(priors[:2]) or '(unmatched)'} "
                       f"covers a correction like this one - its postmortem "
                       f"goes to the writer as context",
                       incidents=priors, chunks=len(citations))],
    }


def supplier_clarification(state: FactoryState) -> dict:
    """Assemble the question only the supplier can answer.

    Two documents disagreeing about a value, or a correction that never says
    which variant it belongs to, is not something this system is entitled to
    decide. What it *can* do is state the disagreement precisely: which
    documents, what each asserts, and which one the precedence order keeps in
    force meanwhile - that last part matters, because "unresolved" is not the
    same as "nothing is published", and a reviewer needs to know what shoppers
    are seeing while the question is open.

    The output is a REQUEST_SUPPLIER_INPUT action, and it is **deliberately not
    executable**. Sending a supplier a query about their own specification is a
    commercial act with a contract behind it; an agent that could send one
    could commit the company to a reading of it. So the action is assembled,
    validated against the catalog like any other, and handed to a human.

    Additive rather than terminal: the run still plans and still reaches the
    approval gate. An open question makes the plan provisional, it does not
    make it unnecessary - the wrong figure is live on six channels either way.
    """
    base = baseline_mod.get()
    conflicts = [s for s in state.get("signals") or []
                 if s.get("kind") == str(CorrectionKind.SOURCE_CONFLICT)]
    unclear = not conflicts and sources_conflict(state)

    docs = _documents_in_dispute(base, conflicts)
    leading = docs[0]["doc_id"] if docs else ""
    stands = leading or "the highest-precedence document"

    questions = [_conflict_question(base, s, docs, leading) for s in conflicts]
    if unclear:
        questions.extend(_scope_questions(base, state))

    proposed, suppliers = _supplier_requests(base, questions, leading)
    valid, dropped = nodes._validate_actions(proposed, base)

    hits = retrieve.search(
        "source precedence which document wins label artwork specification "
        "sheet portal feed content standards",
        top_k=4, doc_types=["POLICY", "CHANNEL"])
    citations = retrieve.cite(hits)

    return {
        "clarification": {
            "reason": "SOURCE_CONFLICT" if conflicts else "SCOPE_UNCLEAR",
            "documents": docs,
            "leading": leading,
            "precedence_policy": evidence.PRECEDENCE_POLICY,
            "questions": questions,
            "actions": valid,
            "suppliers": suppliers,
            "why": (f"{len(conflicts)} source disagreement(s) are open; "
                    f"{evidence.PRECEDENCE_POLICY} keeps {stands} in force "
                    f"until the supplier settles it"
                    if conflicts else
                    f"no reading of the correction on file clears "
                    f"{SCOPE_CONFIDENCE_FLOOR:.2f} confidence, so which variant "
                    f"it applies to is a question for the supplier rather than "
                    f"an inference for this system"),
            "terms": citations,
        },
        "citations": citations,
        "status": "CLARIFICATION_REQUESTED",
        "trace": [step("supplier_clarification",
                       f"{len(questions)} question(s) for "
                       f"{', '.join(suppliers) or 'the supplier'}; "
                       f"{evidence.PRECEDENCE_POLICY} keeps "
                       f"{leading or 'no document'} in force meanwhile",
                       reason="SOURCE_CONFLICT" if conflicts else "SCOPE_UNCLEAR",
                       documents=[d["doc_id"] for d in docs],
                       refused=[r["why"] for r in dropped][:3])],
    }


def _documents_in_dispute(base, conflicts: list[dict]) -> list[dict]:
    """The documents a conflict names, ordered by what POL-002 says wins.

    Precedence is a property of the document kind rather than of arrival order,
    which is the whole point of the policy: a sales email restating a figure
    does not overturn the pack label, however recently it was sent.
    """
    doc_ids: set[str] = set()
    for signal in conflicts:
        doc_ids.update(str(e) for e in signal.get("entities") or [])
        doc_ids.add(str((signal.get("source") or {}).get("doc_id") or ""))

    rows = []
    for doc_id in sorted(d for d in doc_ids if d in base.source_docs):
        doc = base.source_docs[doc_id]
        rows.append({"doc_id": doc.id, "title": doc.title, "kind": str(doc.kind),
                     "supplier": doc.supplier, "precedence": doc.precedence})
    rows.sort(key=lambda r: (-r["precedence"], r["doc_id"]))
    return rows


def _conflict_question(base, signal: dict, docs: list[dict], leading: str) -> dict:
    """One disagreement, phrased so the answer settles it."""
    entity_id = next((e for e in signal.get("entities") or []
                      if e in base.variants or e in base.products), "")
    path = next(iter(signal.get("attribute_paths") or []), "")
    definition = base.attr_defs.get(path)
    unit = f" {definition.unit}" if definition and definition.unit else ""
    named = ", ".join(f"{d['doc_id']} ({d['kind']}, precedence {d['precedence']})"
                      for d in docs) or "the documents on file"

    return {
        "signal_id": signal.get("id"),
        "entity_id": entity_id,
        "attribute_path": path,
        "supplier": nodes._supplier_of(base, entity_id),
        "ask": (f"{named} disagree on {entity_id} {path}: "
                f"{signal.get('old_value')}{unit} against "
                f"{signal.get('new_value')}{unit}. "
                f"{evidence.PRECEDENCE_POLICY} keeps {leading} in force until "
                f"this is settled - please confirm which value is correct and "
                f"which document supersedes the other."),
    }


def _scope_questions(base, state: FactoryState) -> list[dict]:
    """The quieter conflict: a correction that never says who it is about."""
    candidates = state.get("scope_candidates") or []
    readings = "; ".join(
        f"{c.get('level')} ({', '.join(c.get('entities') or []) or 'none'}) at "
        f"{float(c.get('confidence') or 0.0):.2f}" for c in candidates)

    out: list[dict] = []
    for signal in state.get("signals") or []:
        if not signal.get("attribute_paths") or signal.get("new_value") is None:
            continue
        entity_id = next((e for e in signal.get("entities") or []
                          if e in base.variants or e in base.products), "")
        if not entity_id:
            continue
        path = signal["attribute_paths"][0]
        definition = base.attr_defs.get(path)
        unit = f" {definition.unit}" if definition and definition.unit else ""
        product_id = (entity_id if entity_id in base.products
                      else base.product_of_variant.get(entity_id, ""))
        family = ", ".join(base.variants_of.get(product_id, [])) or entity_id
        source = signal.get("source") or {}

        out.append({
            "signal_id": signal.get("id"),
            "entity_id": entity_id,
            "attribute_path": path,
            "supplier": nodes._supplier_of(base, entity_id),
            "ask": (f"{source.get('doc_id', 'the notice')} "
                    f"{source.get('version', '')} corrects {path} to "
                    f"{signal.get('new_value')}{unit} but does not say which "
                    f"model it applies to; {product_id} has {family}. "
                    f"Readings on file: {readings or 'none'}. Please confirm "
                    f"which variants the corrected value covers."),
        })
    return out


def _supplier_requests(base, questions: list[dict],
                       leading: str) -> tuple[list[dict], list[str]]:
    """One request per supplier, carrying every question they can answer."""
    by_supplier: dict[str, list[dict]] = {}
    for question in questions:
        supplier = str(question.get("supplier") or "")
        if supplier:
            by_supplier.setdefault(supplier, []).append(question)

    proposed = []
    for supplier in sorted(by_supplier):
        asks = by_supplier[supplier]
        proposed.append({
            "id": f"RQ-{supplier}",
            "kind": str(ActionKind.REQUEST_SUPPLIER_INPUT),
            "supplier": supplier,
            "doc_ref": leading or (asks[0].get("entity_id") or ""),
            "question": " ".join(a["ask"] for a in asks)[:800],
            "rationale": ("the record cannot settle this; a human sends it, "
                          "because a query about a supplier's own "
                          "specification is a commercial act"),
        })
    return proposed, sorted(by_supplier)


def _gap(violation: dict) -> float:
    """How far a binding rule is from being satisfied.

    ``required`` is what the rule demands and ``available`` is what is on file,
    written in whichever direction the rule reads - a required attribute is 1
    against 0, a length budget is 80 against the 94 actually written. The
    distance between them is the size of the miss either way; the sign is a
    property of the rule rather than of the failure.
    """
    return round(abs(float(violation.get("required") or 0.0)
                     - float(violation.get("available") or 0.0)), 2)


def blocked_review(state: FactoryState) -> dict:
    """Nothing is publishable. Collect what binds, by channel, for a human.

    There is no resolution to recommend here, and manufacturing one would be
    the worst thing this system could do: every candidate leaves a HARD rule
    standing that no rewrite clears, so any pick is content that does not reach
    a shopper. What a reviewer needs instead is the list of what binds, on
    which channel, and by how much.

    Grouped by channel because that is the unit a content team owns - "CH-MKT-A
    refuses three of these" is a piece of work, twelve violations in rule order
    is a list. Worst gap first inside each group, because that is the order
    they get closed in.

    Additive rather than terminal: the run still goes to `recommend`, which is
    handed this and told to say plainly which channels do not go live. Reaching
    the approval gate with binding rules and no recommendation would be a worse
    answer, and it would break the property that the loop always produces
    something a human can act on even with the gateway down.
    """
    base = baseline_mod.get()
    ranked = state.get("ranked") or []

    groups: dict[str, dict] = {}
    for option in ranked:
        for violation in option.get("violations") or []:
            if violation.get("severity") != "HARD":
                continue
            channel_id = str(violation.get("channel_id") or "")
            group = groups.setdefault(channel_id, {"binding": {}, "listings": set()})
            group["listings"].update(
                nodes._listings_for_violation(base, violation))

            key = (violation.get("constraint"), violation.get("entity_id"))
            row = {
                "constraint": violation.get("constraint"),
                "entity_id": violation.get("entity_id"),
                "gap": _gap(violation),
                "beyond_content":
                    str(violation.get("constraint") or "") in BEYOND_CONTENT,
                "detail": violation.get("detail", ""),
            }
            held = group["binding"].get(key)
            # The same rule binds on every asset of a listing. The reviewer
            # needs the rule and its worst instance, not twelve rows of it.
            if held is None or row["gap"] > held["gap"]:
                group["binding"][key] = row

    channels = []
    for channel_id, group in groups.items():
        binding = sorted(group["binding"].values(),
                         key=lambda b: (-b["gap"], str(b["constraint"])))
        channels.append({
            "channel_id": channel_id or None,
            "channel": (base.channels[channel_id].name
                        if channel_id in base.channels else "no single channel"),
            "listings": sorted(group["listings"]),
            "binding": binding,
            "worst_gap": binding[0]["gap"] if binding else 0.0,
        })
    channels.sort(key=lambda c: (-c["worst_gap"], c["channel_id"] or ""))

    summary = (
        f"No candidate resolution survived planning, so there is nothing to "
        f"publish and nothing to compare."
        if not ranked else
        f"All {len(ranked)} validated resolutions leave at least one HARD rule "
        f"standing that rewriting the content cannot clear, across "
        f"{len(channels)} channel(s). The rule has to be relaxed, the record "
        f"corrected, or the listing withheld.")

    worst = channels[0] if channels else {}
    return {
        "blocked": {
            "channels": channels,
            "options_tested": len(ranked),
            "summary": summary,
        },
        "status": "NOTHING_PUBLISHABLE",
        "trace": [step("blocked_review",
                       f"nothing publishable across {len(ranked)} candidate(s) "
                       f"- {sum(len(c['binding']) for c in channels)} binding "
                       f"rule(s) on {len(channels)} channel(s), worst is "
                       f"{worst.get('channel_id') or 'unattributed'}",
                       channels=[c["channel_id"] for c in channels],
                       binding=[b["constraint"] for c in channels
                                for b in c["binding"]][:6])],
    }


def verify_publish(state: FactoryState) -> dict:
    """Check what the publish actually did, and decide whether to try again.

    Two of ``commit_plan``'s refusals are races rather than verdicts. A publish
    lock can be lost to another run that claimed the same batch while this one
    waited on a reviewer; and a source version can move under a resolution
    validated against the previous one - the print batch prepared under DOC-01
    v2 going out after v3 has landed is exactly what that gate exists to stop.
    Both are answered by planning again against what is true now. Neither is
    answered by reporting failure.

    The retry counter is shared with `publish`, which spends it itself on a
    lock conflict because it already knows that outcome at the point it happens.
    This node reads the status that node left rather than re-deciding, so one
    refusal cannot spend two retries and leave the graph circling.
    """
    result = state.get("commit_result") or {}
    status = str(state.get("status") or "")
    retries = int(state.get("publish_retries") or 0)

    # A retry re-validates from scratch. Leaving the first attempt's verdicts
    # in `sim_results` would put options scored against the world before the
    # conflict on the same comparison table as options scored after it.
    replan = {"sim_results": [RESET]}

    if status == REPLAN_AFTER_CONFLICT:
        return {**replan, "status": REPLAN_AFTER_CONFLICT,
                "trace": [step("verify_publish",
                               "the publish locks were taken by another run "
                               "while this one awaited a decision - planning "
                               "again against what is left",
                               conflicts=result.get("conflicts"),
                               attempt=retries)]}

    if status == "CONFLICT_UNRESOLVED":
        return {"trace": [step("verify_publish",
                               "still conflicting after a retry - a reviewer "
                               "has to arbitrate between the two runs",
                               conflicts=result.get("conflicts"))]}

    if result.get("error") == "stale_version":
        stale = [v.get("detail") for v in result.get("violations") or []]
        if retries < MAX_PUBLISH_RETRIES:
            return {**replan, "publish_retries": retries + 1,
                    "status": REPLAN_AFTER_STALE,
                    "trace": [step("verify_publish",
                                   "a later source version landed while this "
                                   "resolution was at the approval gate - "
                                   "re-planning against the version now in "
                                   "force",
                                   stale=stale[:4], attempt=retries + 1)]}
        return {"status": "STALE_UNRESOLVED",
                "trace": [step("verify_publish",
                               "still validated against a superseded source "
                               "after a retry - a reviewer has to decide which "
                               "version the content stands on",
                               stale=stale[:4])]}

    # Terminal. The status `publish` wrote is left alone: PUBLISHED and
    # PUBLISH_REFUSED are both final answers, and `close` reads them.
    committed = bool(result.get("committed"))
    return {
        "trace": [step("verify_publish",
                       f"{len(result.get('actions') or [])} action(s) published "
                       f"across {len(result.get('locks') or [])} publish lock(s)"
                       if committed
                       else f"nothing published: {result.get('detail', '')}",
                       committed=committed,
                       idempotent=bool(result.get("idempotent_replay")),
                       trace_hash=result.get("trace_hash"))],
    }
