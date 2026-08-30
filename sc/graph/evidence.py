"""The evidence desk: the only tools the investigator is allowed to call.

The brief asks for an investigation whose path depends on what the correction
actually touches - one that "asks for missing evidence only when needed" and
decides "which evidence or tool to query next". That is the one place in this
system where a model chooses an action rather than describing one, so it is
also the one place that needs a real allowlist rather than a stated intention.

Three properties make this safe enough to hand to a model:

**Read-only by construction.** Every entry here answers a question. None of
them writes a fact, takes a publish lock, or moves a listing. The mutating
tools in ``sc.tools.planning`` are deliberately not reachable from this table,
so "the model asked for a bad tool" cannot escalate past "the model got an
error back". Publishing still goes through the approval gate and nothing here
changes that.

**Closed set, checked by name.** A request naming a tool that is not in
``TOOLS`` is refused and recorded as refused. The refusal is evidence too - a
reviewer reading the trace should see what the investigator wanted and did not
get, because that is often the more interesting half.

**Bounded.** ``MAX_PASSES`` and ``MAX_REQUESTS_PER_PASS`` cap the loop. An
investigation that cannot resolve a scope question in three passes is not going
to resolve it in thirty, and an uncapped loop against a paid gateway is a bill
rather than a feature.

The catalog lookups here route through ``sc.mcp.client``. With ``USE_MCP=1``
they leave the process and cross a real protocol boundary to the toolset that
owns them; otherwise they call the same function directly. The answer is
identical either way - that is what makes the switch a transport decision
rather than a behavioural one - and the console records which path each call
actually took.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from sc.mcp import client as mcp_client
from sc.rag import retrieve
from sc.replay import tape
# Version ranking is the validator's own, so the desk and the validator agree
# on what "newer" means instead of each deciding for itself.
from sc.sim.engine import _rank as version_rank
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod
from sc.state import store
from sc.tools import network as network_tools

# How many times the investigator may go back for more evidence. The first
# pass always happens; this bounds the extra ones.
MAX_PASSES = 2
MAX_REQUESTS_PER_PASS = 3

# The desk's own standing questions are bounded separately, because they are
# not the model's allowance to spend: a mandatory lookup that fell off the end
# of the agent's budget would be a governance rule the run quietly skipped.
MAX_REQUIRED = 6

# How many channels a safety-class correction pulls rules for. Past four this
# is a channel inventory rather than evidence.
MAX_SAFETY_CHANNELS = 4

# Truncation for anything that goes back into a prompt. Evidence that overruns
# the context window is evidence the model never reads.
MAX_CHARS = 1200

# How far back down the released tape a document history looks. The tape is a
# few hundred events and the desk never sees the future of it, so this is the
# whole of what has happened rather than a window onto it.
TAPE_SCAN = 1000

# The source-precedence policy, named so a citation can be followed.
PRECEDENCE_POLICY = "POL-002"


@dataclass(frozen=True)
class EvidenceTool:
    name: str
    takes: str
    describes: str
    run: Callable[[str], Any]


def _split_ref(ref: str) -> tuple[str, str]:
    """Split ``VAR-01B:specs.power_w`` or ``VAR-01B.specs.power_w``.

    Both spellings arrive: the qualified form is how ``derived_from`` names a
    field, and the dotted form is how a model writes one. Entity ids carry no
    dot and every attribute path does, so the first separator is the join.
    """
    entity_id, separator, path = ref.partition(":")
    if not separator:
        entity_id, _, path = ref.partition(".")
    return entity_id.strip(), path.strip()


def _fact_row(fact) -> dict:
    """One link of a fact chain, with everything needed to defend the value."""
    doc, _, version = (fact.provenance.source_id or "").partition(":")
    return {
        "value": fact.value,
        "doc": doc,
        "version": version,
        "provenance": str(fact.provenance.kind),
        "confidence": fact.provenance.confidence,
        "recorded_at": fact.recorded_at.isoformat(timespec="seconds"),
        "valid_from": fact.valid_from.isoformat(timespec="seconds"),
    }


def _lineage(ref: str) -> dict:
    """Where one attribute value came from, and what it replaced."""
    base = baseline_mod.get()
    entity_id, path = _split_ref(ref)
    entity_type = ("variant" if entity_id in base.variants
                   else "product" if entity_id in base.products else "")
    if not entity_type or not path:
        return {"error": "expected ENTITY.attribute.path, "
                         f"e.g. VAR-01B.specs.power_w; got {ref!r}"}

    # Both axes run on the replay clock. Letting the recorded axis default to
    # wall-clock time would ask about an instant outside the horizon and hide
    # every fact the run has produced - and the desk has to see exactly what
    # the validator sees, or it argues for a value the engine is not using.
    now = tape.sim_now()
    fact = store.get(entity_type, entity_id, path, as_of_valid=now,
                     as_of_recorded=now)
    history = [_fact_row(f) for f in (store.lineage(fact.id) if fact else [])]

    # The seed pack is the bottom of every chain: the value the prepared copy
    # was written against, which is the thing a correction is corrected *from*.
    key = (entity_id, path)
    if key in base.attr_values:
        source = base.attr_sources.get(key)
        history.append({
            "value": base.attr_values[key],
            "doc": source.doc_id if source else "",
            "version": source.version if source else "",
            "provenance": "RECORDED",
            "note": "the value the prepared content was written against",
        })

    definition = base.attr_defs.get(path)
    return {
        "ref": f"{entity_id}:{path}",
        "unit": definition.unit if definition else None,
        "safety_class": bool(definition and definition.safety_class),
        "in_force": history[0]["value"] if history else None,
        "corrections": max(len(history) - 1, 0),
        "history": history,  # newest first
    }


def _derived_outputs(entity_id: str) -> dict:
    """Everything downstream of an entity: fields, copy, listings, channels."""
    trace = mcp_client.call("trace_dependencies",
                            {"entity_id": entity_id, "depth": 3},
                            network_tools.trace_dependencies)
    # The full trace names every asset and every hop, which is thousands of
    # characters of no interest to a scope argument. Totals stay complete and
    # authoritative; the lists are a sample of what they count. Ordered so that
    # what survives the prompt budget is what a reviewer would have read first.
    affected = trace.get("affected", {})
    return {
        "root": trace.get("root"),
        "totals": trace.get("totals"),
        "variants": affected.get("variants", []),
        "channels": affected.get("channels", []),
        "listings": affected.get("listings", [])[:12],
        "attributes": affected.get("attributes", [])[:12],
        "assets": affected.get("assets", [])[:12],
        "chain": trace.get("chain", [])[:20],
    }


def _source_versions(doc_id: str) -> dict:
    """Every version of a supplier document this system has seen.

    The premise of the whole scenario is that a document was revised after the
    content was written, so "which version is in force, and what did the copy
    stand on before it" is a question the desk has to be able to answer without
    a model reading a covering email and guessing.
    """
    base = baseline_mod.get()
    doc = base.source_docs.get(doc_id)
    if doc is None:
        return {"error": f"no such source document: {doc_id}"}

    now = tape.sim_now()
    ov = overlay_mod.build(now)
    in_force = ov.doc_versions.get(doc_id, doc.version)
    standing = ov.doc_status.get(doc_id, doc.status)

    # The version on file when the prepared content was written is the bottom
    # of the stack; everything above it arrived on the tape.
    seen: dict[str, dict] = {doc.version: {
        "version": doc.version,
        "received_at": doc.received_at.isoformat(timespec="seconds"),
        "sender": doc.supplier,
        "event": "",
    }}
    # Oldest first, so a version keeps the arrival that introduced it while a
    # later withdrawal still overwrites its standing.
    for event in reversed(tape.released(limit=TAPE_SCAN)):
        payload = event.payload
        if str(payload.get("doc_id", "")) != doc_id:
            continue
        version = str(payload.get("doc_version", "")) or in_force
        row = seen.get(version)
        if row is None:
            row = seen[version] = {
                "version": version,
                "received_at": event.ts.isoformat(timespec="seconds"),
                "sender": str(payload.get("sender") or payload.get("supplier")
                              or doc.supplier),
                "event": event.id,
            }
        if payload.get("status"):
            row["status"] = str(payload["status"])

    versions = sorted(seen.values(), key=lambda r: version_rank(r["version"]))
    for row in versions:
        row.setdefault("status",
                       standing if row["version"] == in_force else "SUPERSEDED")
        row["in_force"] = row["version"] == in_force

    return {
        "document": {"id": doc.id, "title": doc.title, "supplier": doc.supplier,
                     "kind": str(doc.kind), "precedence": doc.precedence},
        "in_force": in_force,
        "status": standing,
        "versions": versions,
        # Precedence is a property of the document rather than of a version, so
        # it is reported once - and what it is *for* is settling a
        # disagreement, which is this list.
        "outranked_by": sorted(d for d in base.docs_by_supplier.get(doc.supplier, [])
                               if base.source_docs[d].precedence > doc.precedence),
        "precedence_policy": PRECEDENCE_POLICY,
    }


def _cell(cell: dict, unit: str | None) -> str:
    """One variant's value, and the document standing behind it."""
    rendered = f"{cell['value']}" + (f" {unit}" if unit else "")
    source = " ".join(part for part in (cell.get("doc"), cell.get("version")) if part)
    if cell.get("provenance") and cell["provenance"] != "RECORDED":
        source += f", {cell['provenance']}"
        if cell.get("confidence") is not None:
            source += f" {cell['confidence']:.2f}"
    return f"{rendered} ({source})" if source else rendered


def _variant_diff(product_id: str) -> dict:
    """The attribute table across a product's base and its variants."""
    table = mcp_client.call("variant_diff", {"product_id": product_id},
                            network_tools.variant_diff)
    if "error" in table:
        return table

    rows = []
    for row in table.get("attributes", []):
        rows.append({
            "path": row["path"],
            "differs": row["differs"],
            "safety_class": row["safety_class"],
            # Value and provenance on one line each, because the pairing *is*
            # the base-versus-variant argument: the base model was certified at
            # 45 W by its own document a fortnight before an ambiguous
            # correction named the product and not the variant.
            "values": {v: _cell(cell, row.get("unit"))
                       for v, cell in row["values"].items()},
        })
    # Differences first. The prompt budget truncates the tail, and a row every
    # variant agrees on is the half that can afford to be lost.
    rows.sort(key=lambda r: (not r["differs"], r["path"]))

    product = table.get("product", {})
    return {
        "product": {"id": product.get("id"), "name": product.get("name"),
                    "regulated": product.get("regulated")},
        "variants": {v["id"]: ("base" if v["is_base"] else "variant")
                     for v in table.get("variants", [])},
        "attributes": rows,
    }


def _channel_rules(pair: str) -> dict:
    """The rules in force for a channel, or for one of its fields.

    Argument is ``CH-MKT-A`` or ``CH-MKT-A>specs.power_w``.
    """
    channel_id, _, field = pair.partition(">")
    channel_id, field = channel_id.strip(), field.strip()
    if not channel_id:
        return {"error": "expected CHANNEL or CHANNEL>attribute.path, "
                         "e.g. CH-MKT-A>specs.power_w"}

    # Rules are written against the channel's own field names, so an internal
    # attribute path is translated before asking. A caller who already knows
    # the channel-side name passes through the identity mapping unchanged.
    base = baseline_mod.get()
    if field:
        field = base.channel_field(channel_id, field)

    answer = mcp_client.call("channel_rules",
                             {"channel_id": channel_id, "field": field or None},
                             network_tools.channel_rules)
    if "error" in answer:
        return answer

    # The channel's full record leads with its attribute map, and a 1200
    # character budget would spend itself there before reaching a rule.
    channel = answer.get("channel", {})
    return {
        "channel": {"id": channel.get("id"), "name": channel.get("name"),
                    "kind": channel.get("kind"),
                    "freeze_days": channel.get("freeze_days")},
        "field": field or None,
        "rules": [{k: v for k, v in (
            ("id", r["id"]), ("field", r["field"]), ("kind", r["kind"]),
            ("value", r["value"]), ("severity", r["severity"]),
            ("detail", r["detail"])) if v not in (None, "")}
            for r in answer.get("rules", [])],
        "fields": answer.get("fields", []),
        "required_attributes": answer.get("required_attributes", []),
        "attribute_paths": answer.get("attribute_paths", []),
    }


def _policy(question: str) -> dict:
    """Content standards, channel policy and the precedence order."""
    hits = retrieve.search(question, top_k=3, doc_types=["POLICY", "STANDARD"])
    return {"citations": retrieve.cite(hits)}


def _prior_incidents(question: str) -> dict:
    """Has a correction like this happened before, and what was learned."""
    hits = retrieve.search(question, top_k=3, doc_types=["POSTMORTEM"])
    return {"citations": retrieve.cite(hits)}


#: Spelled out rather than inlined. This module is edited often enough that
#: an escaped newline inside a join has been mangled by a shell more than
#: once, and a constant cannot be.
NEWLINE = chr(10)


TOOLS: dict[str, EvidenceTool] = {
    t.name: t for t in (
        EvidenceTool("lineage", "a field, e.g. VAR-01B.specs.power_w",
                     "where a value came from, what it replaced and when",
                     _lineage),
        EvidenceTool("derived_outputs", "any entity id, e.g. VAR-01B or DOC-01",
                     "the copy, listings and channels built on an entity, with totals",
                     _derived_outputs),
        EvidenceTool("source_versions", "a document id, e.g. DOC-01",
                     "every version of a supplier document, and which is in force",
                     _source_versions),
        EvidenceTool("variant_diff", "a product id, e.g. PRD-01",
                     "the attribute table across base and variants, marked where they differ",
                     _variant_diff),
        EvidenceTool("channel_rules", "CHANNEL or CHANNEL>path, e.g. CH-MKT-A>specs.power_w",
                     "what a channel demands of a field before it will publish",
                     _channel_rules),
        EvidenceTool("policy", "a question in plain words",
                     "content standards, channel policy, source precedence",
                     _policy),
        EvidenceTool("prior_incidents", "a question in plain words",
                     "postmortems from comparable past corrections",
                     _prior_incidents),
    )
}


def _affected(blast: dict) -> dict:
    """The blast radius, whether it arrived as one trace or a merged union."""
    return (blast or {}).get("affected") or blast or {}


def mandatory_requests(signals: list[dict], blast: dict) -> list[dict]:
    """The questions an investigation is not allowed to skip.

    These are resolved before the investigator is asked anything, for a reason
    that is about correctness rather than about prompting. "Does this
    correction apply to the base model or to the variant?" is a question about
    the *current catalog* - which document certified which value, and when. A
    retrieved postmortem will happily assert an answer, and a model reading one
    will believe it, but a document is a record of what was true when it was
    written and a catalog moves underneath it. Left to its own judgement the
    investigator consistently decides the corpus already told it, and scopes a
    correction on a citation instead of on the record.

    So the desk answers them from the catalog first, every time, and the
    investigator may then ask for whatever else it needs. Both kinds are
    recorded, and the trace labels which is which - a request the agent chose
    to make is a different claim from one the standard required, and collapsing
    them would overstate what the model decided.
    """
    base = baseline_mod.get()
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    safety = False

    def add(tool: str, argument: str, why: str) -> None:
        if not argument or (tool, argument) in seen:
            return
        seen.add((tool, argument))
        out.append({"tool": tool, "argument": argument, "why": why,
                    "origin": "REQUIRED"})

    for signal in signals or []:
        for entity in signal.get("entities", []) or []:
            add("variant_diff", _product_of(base, entity),
                "which variant a correction applies to is a fact about the "
                "current catalog, not something a document can settle")
        source = signal.get("source") or {}
        for doc_id in [source.get("doc_id", "")] + list(signal.get("entities") or []):
            if doc_id in base.source_docs:
                add("source_versions", doc_id,
                    "a correction is only a correction against the version the "
                    "content was actually built from")
        safety = safety or any(
            path in base.attr_defs and base.attr_defs[path].safety_class
            for path in signal.get("attribute_paths") or [])

    # A safety-class attribute fails closed, and what it fails closed *on* is a
    # channel rule. Sorted so the trace of a re-run is the trace of the run.
    if safety:
        for channel_id in sorted(_affected(blast).get("channels", []) or [])[
                :MAX_SAFETY_CHANNELS]:
            add("channel_rules", channel_id,
                "a safety-class correction is blocked or published by this "
                "channel's own rule, so the rule is evidence")

    return out[:MAX_REQUIRED]


def _product_of(base, entity_id: str) -> str:
    """The product a signal entity belongs to, whatever kind of id it is."""
    if entity_id in base.products:
        return entity_id
    if entity_id in base.listings:
        entity_id = base.listings[entity_id].variant_id
    return base.product_of_variant.get(entity_id, "")


def admitted_tools() -> list[dict]:
    """Tools an operator has admitted from connected systems.

    Discovery is not admission, and this function is where that distinction
    stops being a slogan. Connecting a system records what it says it can do
    and changes nothing about what a model may reach; a person then admits
    specific tools, and only then do they appear here.

    A tool joins the desk only while its connection is answering. A degraded
    system's tool is withdrawn rather than left on the list, because a
    catalogue offering something unreachable spends a model's bounded rounds
    discovering that.

    Never raises. A desk that an unreachable supplier could bring down would
    make an external system load-bearing for a correction run, which is the
    thing every other part of this design refuses.
    """
    try:
        from sc.mcp import connections

        admitted = []
        for record in connections.all_connections():
            if record["state"] != connections.CONNECTED:
                continue
            for tool in record["admitted_tools"]:
                admitted.append({"name": tool, "system": record["id"],
                                 "title": record["title"]})
        return admitted
    except Exception:  # noqa: BLE001 - the desk is not the estate's dependant
        return []



def catalogue() -> str:
    """The tool list, as the investigator prompt sees it."""
    lines = [f"- {t.name}({t.takes}) -> {t.describes}" for t in TOOLS.values()]
    # Admitted tools are listed apart and named with their system. A model
    # choosing between "policy" and something a supplier's server offers
    # should be able to see which is which - a flat list would make an
    # external system's answer indistinguishable from the catalog's own.
    lines += [f"- {t['name']}(...) -> from {t['title']}, admitted at runtime"
              for t in admitted_tools()]
    return NEWLINE.join(lines)


def run_requests(requests: list[dict]) -> list[dict]:
    """Execute an investigator's evidence requests against the allowlist.

    Returns one record per request, refusals included. Nothing raises: a tool
    that fails is a fact about the investigation, not a reason to abandon a run
    that still has a deterministic path to a recommendation.
    """
    out: list[dict] = []
    # Two budgets, because they bound two different things - see MAX_REQUIRED.
    budget = {"REQUIRED": MAX_REQUIRED, "AGENT": MAX_REQUESTS_PER_PASS + 2}

    for request in requests or []:
        name = str(request.get("tool", "")).strip()
        argument = str(request.get("argument", "")).strip()
        why = str(request.get("why", "")).strip()[:200]

        origin = "REQUIRED" if request.get("origin") == "REQUIRED" else "AGENT"
        if budget[origin] <= 0:
            continue
        budget[origin] -= 1

        base = {"tool": name or "(unnamed)", "argument": argument,
                "why": why, "origin": origin}

        tool = TOOLS.get(name)
        if tool is None:
            out.append({**base, "status": "REFUSED",
                        "result": {"error": f"{name!r} is not an allowed "
                                            f"evidence tool"}})
            continue
        if not argument:
            out.append({**base, "status": "REFUSED",
                        "result": {"error": f"{name} needs {tool.takes}"}})
            continue

        try:
            out.append({**base, "status": "OK", "result": tool.run(argument)})
        except Exception as exc:  # noqa: BLE001 - a failed lookup is evidence
            out.append({**base, "status": "ERROR",
                        "result": {"error": str(exc)[:200]}})
    return out


def render(records: list[dict]) -> str:
    """Evidence records, formatted for the next prompt pass."""
    blocks = []
    for r in records:
        body = json.dumps(r["result"], default=str)[:MAX_CHARS]
        blocks.append(f"[{r['tool']}({r['argument']}) - {r['status']}]\n{body}")
    return "\n\n".join(blocks) or "(no evidence returned)"


def citations_from(records: list[dict]) -> list[dict]:
    """Pull citation dicts out of whatever the retrieval-backed tools returned.

    Evidence the investigator fetched itself has to reach the Evidence panel
    the same way the opening retrieval does, or the UI shows a narrative
    resting on sources it does not list.
    """
    found: list[dict] = []
    for r in records:
        result = r.get("result")
        if isinstance(result, dict):
            found.extend(result.get("citations") or [])
    return found
