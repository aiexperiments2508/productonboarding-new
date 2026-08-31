"""The peer agents, and what each of them is for.

The correction pipeline was one process calling its own functions. That is a
perfectly good way to build it and a poor way to demonstrate anything about
agent interoperability, because nothing crosses a boundary another team could
implement against.

So the four capabilities that are genuinely separable become A2A peers, each
with an Agent Card another organisation's agent could discover and call:

    lineage-analyst      given a correction, what content does it reach
    resolution-planner   given the reach, which readings of it are arguable
    validator            given one reading, is it publishable - deterministic
    copywriter           given a corrected value, what should the copy say

The split is not arbitrary. Each of these is a different kind of work with a
different failure mode: the analyst walks the derivation graph, the planner
enumerates readings and can enumerate nonsense, the validator must be
reproducible to the digit, and the copywriter writes. Splitting them at those
seams means a peer can replace one without touching the others - which is the
only reason to have a protocol at all.

The copywriter is the seam that most obviously belongs to somebody else. A
retailer already owns a brand voice and a model tuned to it; the value here is
that the deterministic renderer below is a drop-in default which another team
can replace without the factory noticing. It rewrites what the record can settle
- a wattage quoted in a title, a marketplace feed field - and reports what it
could not, rather than inventing a sentence to cover the gap.

What deliberately does NOT become an agent: the approval gate, and publish. A
human decision is not a capability to delegate, and a peer that could publish is
a peer that could publish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

# The literal matcher and the channel formatters are imported from the engine
# rather than reimplemented. A renderer whose idea of "the old number" differs
# from the validator's is a machine for producing copy that passes here and
# fails there.
from sc.sim.engine import (
    ALLERGEN_FORMATS, CLAIM_RULES, COUNTED_FIELDS, INGREDIENT_FORMATS,
    _literal_pattern,
)


@dataclass(frozen=True)
class PeerAgent:
    """One A2A peer: its identity, its skill, and the work it does."""

    id: str
    name: str
    description: str
    skill_id: str
    skill_name: str
    skill_description: str
    examples: tuple[str, ...]
    #: Called with the request payload, returns the result payload. Sync: the
    #: work underneath is CPU-bound validation and blocking catalog reads, and
    #: pretending otherwise would only move the blocking somewhere less
    #: visible.
    handler: Callable[[dict], dict]
    #: What this peer is not permitted to do, declared beside the handler that
    #: would have to do it.
    #:
    #: Stated rather than left to be inferred from absence: a directory that
    #: merely omits the approval gate invites a reader to conclude it was
    #: forgotten. Declared *here* rather than authored in the directory because
    #: a limit written somewhere else is a limit that goes stale - an agent
    #: whose handler quietly gained the ability to publish would carry on
    #: advertising that it cannot.
    #:
    #: Two are universal and set below for every peer: a human decision is not a
    #: capability to delegate, and a peer that could publish is a peer that
    #: could publish.
    may_not: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Reading a request
#
# Callers phrase the same question three ways - a bare entity, a list, or the
# correction signals the graph is carrying - and a peer that only understood
# one of them would be a peer for this graph rather than for the protocol.
# ---------------------------------------------------------------------------


def _entities(payload: dict) -> list[str]:
    named = list(payload.get("entities") or [])
    if payload.get("entity_id"):
        named.append(str(payload["entity_id"]))
    for signal in payload.get("signals") or []:
        named.extend(signal.get("entities") or [])
    return sorted({str(e) for e in named if e})


def _paths(payload: dict) -> list[str]:
    paths = list(payload.get("attribute_paths") or [])
    for signal in payload.get("signals") or []:
        paths.extend(signal.get("attribute_paths") or [])
    return sorted({str(p) for p in paths if p})


def _safety(base, path: str) -> bool:
    definition = base.attr_defs.get(path)
    return bool(definition and definition.safety_class)


# ---------------------------------------------------------------------------
# Handlers
#
# Each delegates to the same tools the in-process graph uses. That is the
# point: one implementation, reachable two ways, so a peer calling over A2A and
# a node calling directly cannot drift apart.
# ---------------------------------------------------------------------------


def _lineage(payload: dict) -> dict:
    """Everything a correction reaches, unioned over its entities.

    Computed from the derivation graph the content was actually built with,
    never from a model - this is the figure the triage prompt is told to treat
    as authoritative.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import network

    base = baseline_mod.get()
    roots = _entities(payload)
    depth = int(payload.get("depth", 3))
    as_of = payload.get("as_of")

    keys = ("products", "variants", "attributes", "assets", "listings", "channels")
    scope: dict[str, set[str]] = {k: set() for k in keys}
    chain: list[dict] = []
    drawn: set[tuple[str, str, str]] = set()

    for root in roots:
        trace = network.trace_dependencies(root, depth=depth, as_of=as_of)
        for key in keys:
            scope[key].update(trace["affected"].get(key) or [])
        for link in trace["chain"]:
            edge = (link["from"], link["to"], link["relation"])
            if edge not in drawn:
                drawn.add(edge)
                chain.append(link)

    affected = {key: sorted(scope[key]) for key in keys}
    safety = [ref for ref in affected["attributes"]
              if _safety(base, ref.partition(":")[2])]
    regulated = [p for p in affected["products"] if base.products[p].regulated]

    return {
        "roots": roots,
        "affected": affected,
        "chain": chain,
        "totals": {
            "fields": len(affected["attributes"]),
            "assets": len(affected["assets"]),
            "listings": len(affected["listings"]),
            "channels": len(affected["channels"]),
            "safety_flags": len(safety),
            "regulated": len(regulated),
        },
        "safety_attributes": safety,
        "summary": (f"{len(affected['attributes'])} fields on "
                    f"{len(affected['variants'])} variants reach "
                    f"{len(affected['assets'])} content assets across "
                    f"{len(affected['listings'])} listings and "
                    f"{len(affected['channels'])} channels"
                    + (f", {len(safety)} of them safety-classed" if safety else "")),
    }


# The three questions the record can answer about a scope reading. Confidence
# is the fraction of them this reading passes - a number with an arithmetic
# behind it rather than a feeling. It is display only: the ranker prices
# precision in fields actually touched, exactly so that a candidate cannot
# promote itself by claiming certainty.
_SCOPE_CHECKS = ("hint", "named", "independent")


def _resolutions(payload: dict) -> dict:
    """Which readings of a correction the catalog can actually support.

    The ambiguity is real and it is the whole of scenario one: a spec sheet says
    the Northaven AP300 draws 65 W without saying whether it means the base model,
    the Max, or both. This enumerates the readings and attaches the evidence for
    each; it does not choose. Choosing is the validator's job, and the reason it
    can be done by measurement is that every candidate here is a change set the
    validator can price.
    """
    from sc.contracts import ChangeScope, ScopeLevel
    from sc.state import baseline as baseline_mod
    from sc.tools import network

    base = baseline_mod.get()
    named = _entities(payload)
    paths = _paths(payload)
    hint = str(payload.get("applies_to") or "UNCLEAR").upper()

    product_id = payload.get("product") or _product_of(base, named)
    if product_id is None:
        return {"error": "no product in scope", "candidates": []}

    diff = network.variant_diff(product_id, as_of=payload.get("as_of"))
    if "error" in diff:
        return {**diff, "candidates": []}

    variants = [v["id"] for v in diff["variants"]]
    base_variants = [v["id"] for v in diff["variants"] if v["is_base"]]
    named_variants = sorted(set(named) & set(variants))
    rows = [r for r in diff["attributes"] if not paths or r["path"] in paths]

    readings: list[tuple[str, list[str]]] = [(str(ScopeLevel.ALL), variants)]
    if base_variants:
        readings.append((str(ScopeLevel.BASE), base_variants))
    for variant_id in variants:
        readings.append((str(ScopeLevel.VARIANT), [variant_id]))

    seen: set[tuple[str, ...]] = set()
    candidates: list[ChangeScope] = []
    for level, entities in readings:
        key = tuple(sorted(entities))
        if not entities or key in seen:
            continue
        seen.add(key)
        passed = _scope_checks(level, entities, variants, named_variants, hint, rows)
        candidates.append(ChangeScope(
            level=level,
            entities=sorted(entities),
            confidence=round(sum(passed.values()) / len(_SCOPE_CHECKS), 2),
            rationale=_scope_rationale(level, entities, variants, passed),
            evidence=_scope_evidence(product_id, entities, rows),
        ))

    # Narrowest first. A reading that touches fewer pages is the one a reviewer
    # has to argue against, and the order has to be the same on every refresh.
    candidates.sort(key=lambda c: (len(c.entities), str(c.level), c.entities))

    return {
        "product": product_id,
        "attribute_paths": paths or sorted({r["path"] for r in rows}),
        "variants": diff["variants"],
        "attributes": rows,
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "summary": (f"{len(candidates)} readings of {product_id} across "
                    f"{len(variants)} variants"),
    }


def _product_of(base, entities: list[str]) -> str | None:
    for entity_id in entities:
        if entity_id in base.products:
            return entity_id
    for entity_id in entities:
        if entity_id in base.variants:
            return base.product_of_variant[entity_id]
    return None


def _scope_checks(level: str, entities: list[str], variants: list[str],
                  named: list[str], hint: str, rows: list[dict]) -> dict[str, int]:
    """Does the record support this reading? Three yes/no questions.

    ``independent`` is the one that carries the scenario. Narrowing to the Max
    is defensible only because the base model's wattage stands on a *different*
    document - the portal feed that certified it a fortnight earlier - so the
    correction leaves nothing behind unexplained. Where every variant stands on
    the same source there is nothing in the record to narrow on, and the widest
    reading is the one the evidence supports.
    """
    inside, outside = set(entities), set(variants) - set(entities)

    sources_inside = _sources(rows, inside)
    sources_outside = _sources(rows, outside)

    return {
        "hint": int(hint == level),
        "named": int(bool(named) and set(named) == inside),
        "independent": int(bool(sources_outside)
                           and not (sources_inside & sources_outside)
                           if outside else len(sources_inside) == 1),
    }


def _sources(rows: list[dict], variants: set[str]) -> set[str]:
    return {f"{row['values'][v]['doc']} {row['values'][v]['version']}".strip()
            for row in rows for v in variants
            if v in row["values"] and row["values"][v]["doc"]}


def _scope_rationale(level: str, entities: list[str], variants: list[str],
                     passed: dict[str, int]) -> str:
    """Why the record supports this reading. Evidence only.

    The level and the entity list are fields of their own, so restating them
    here wrote the menu of levels the caller offers into the field meant to
    justify one of them - and a reviewer shown "ALL: apply to every variant of
    the product (2) - ..." is reading the question back, not the answer.
    """
    reasons = []
    if passed["hint"]:
        reasons.append("the notice itself scopes the correction this way")
    if passed["named"]:
        reasons.append("the correction names exactly these entities")
    if passed["independent"]:
        reasons.append("the variants left out stand on a different source document"
                       if len(entities) != len(variants)
                       else "every variant stands on the same source document, so "
                            "there is nothing in the record to narrow on")
    return "; ".join(reasons) or ("no evidence in the record distinguishes this "
                                  "reading from the others")


def _scope_evidence(product_id: str, entities: list[str],
                    rows: list[dict]) -> list[str]:
    docs = sorted(_sources(rows, set(entities)))
    return [f"variant_diff:{product_id}"] + [f"source:{d}" for d in docs]


def _validate(payload: dict) -> dict:
    """Validate one candidate resolution. Deterministic to the digit."""
    from sc.tools import planning

    return planning.run_scenario(payload["delta"], as_of=payload.get("as_of"),
                                 as_of_recorded=payload.get("as_of_recorded"))


def _copy(payload: dict) -> dict:
    """Rewrite affected copy from a supplied attribute table.

    The numbers arrive in ``values``; nothing here originates one. What this
    does is mechanical and therefore trustworthy: a marketplace feed field is
    rebuilt from the corrected value under the channel's own field name, and a
    superseded figure quoted in prose is swapped for the new one using the same
    matcher the validator uses to detect it.

    Where the record cannot settle the sentence - an allergen warning that has
    to be *written* rather than substituted - the asset comes back unchanged
    with the reference listed under ``unresolved`` and the values it must carry
    attached. That is the seam the graph's ``regenerate`` node fills with a
    model call, and leaving the gap visible is the point: an invented allergen
    sentence is worse than an obvious hole.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    values = {str(k): v for k, v in (payload.get("values") or {}).items()}
    source = payload.get("source")

    rendered = [_render(base, base.assets[asset_id], values, source)
                for asset_id in _assets_in_scope(base, payload, values)]

    return {
        "values": values,
        "copy": rendered,
        "totals": {
            "assets": len(rendered),
            "rewritten": sum(1 for r in rendered if r["changed"]),
            "unresolved": sum(1 for r in rendered if r["unresolved"]),
            "over_budget": sum(1 for r in rendered if r["over_budget"]),
        },
        "summary": (f"{sum(1 for r in rendered if r['changed'])} of "
                    f"{len(rendered)} assets rewritten deterministically"),
    }


def _assets_in_scope(base, payload: dict, values: dict) -> list[str]:
    """Which assets to rewrite: the ones asked for, or every one that quotes a
    corrected value. The default is the useful one - the caller has the change
    set, not the derivation index."""
    asked = payload.get("assets") or payload.get("asset_ids") or []
    named = [a.get("id") if isinstance(a, dict) else str(a) for a in asked]
    if not named:
        named = [asset_id for ref in sorted(values)
                 for asset_id in base.assets_derived_from.get(ref, [])]
    return sorted({a for a in named if a in base.assets})


def _render(base, asset, values: dict, source: object) -> dict:
    listing = base.listings[asset.listing_id]
    refs = [r for r in sorted(asset.derived_from) if r in values]

    if asset.field == "feed_row":
        text, outcome = _render_feed_row(base, listing, asset, values, refs)
    else:
        text, outcome = _substitute(base, asset.text, values, refs,
                                    asset.derived_from)

    budget, used = _budget(base, listing.channel_id, asset.field, text)
    changed = text != asset.text

    row = {
        "asset_id": asset.id,
        "listing_id": listing.id,
        "channel_id": listing.channel_id,
        "field": asset.field,
        "built_at_version": asset.built_at_version,
        "old_text": asset.text,
        "proposed_text": text,
        "changed": changed,
        "rewritten": outcome["rewritten"],
        "absent": outcome["absent"],
        "unresolved": outcome["unresolved"],
        "targets": {ref: values[ref] for ref in outcome["unresolved"]},
        "claims_at_risk": _claims_at_risk(base, listing.variant_id, asset, values),
        "budget": budget,
        "used": used,
        "over_budget": budget is not None and used > budget,
    }
    if changed:
        # Shaped as a RegenerateCopyAction so the graph can adopt it without
        # rebuilding it. The source travels with it because an uncited change to
        # published content is a HARD violation, not a stylistic lapse.
        row["action"] = {
            "id": f"RC-{asset.id}",
            "kind": "REGENERATE_COPY",
            "listing_id": listing.id,
            "asset_id": asset.id,
            "field": asset.field,
            "old_excerpt": asset.text[:200],
            "proposed_text": text,
            "reason": ("rebuilt from the corrected values for "
                       + ", ".join(outcome["rewritten"])),
            "source": source,
        }
    return row


def _substitute(base, text: str, values: dict, refs: list[str],
                kin: list[str]) -> tuple[str, dict]:
    """Swap superseded values out of prose, one reference at a time."""
    outcome: dict[str, list[str]] = {"rewritten": [], "absent": [], "unresolved": []}

    for ref in refs:
        entity_id, _, path = ref.partition(":")
        old, new = base.attr_values.get((entity_id, path)), values[ref]
        if old == new:
            continue
        if _ambiguous(base, ref, kin):
            outcome["unresolved"].append(ref)
            continue
        definition = base.attr_defs.get(path)
        updated = _swap(text, old, new, definition.unit if definition else None)
        if updated is None:
            outcome["unresolved"].append(ref)
        elif updated == text:
            outcome["absent"].append(ref)
        else:
            outcome["rewritten"].append(ref)
            text = updated

    return text, outcome


def _ambiguous(base, ref: str, kin: list[str]) -> bool:
    """Whether a literal in this asset can be attributed to one variant.

    The comparison table on the base model's page quotes both variants' wattage,
    and at baseline both read 45 W. Substituting the corrected figure would
    rewrite the base model's row too - which is the exact error the whole
    base-versus-variant story is about, arrived at by a regex instead of by a
    bad decision. Where the same number belongs to two entities the record
    cannot say which occurrence is which, so the asset is handed on unchanged.
    """
    entity_id, _, path = ref.partition(":")
    old = base.attr_values.get((entity_id, path))
    return any(
        other != ref
        and other.partition(":")[2] == path
        and base.attr_values.get((other.partition(":")[0], path)) == old
        for other in kin)


def _swap(text: str, old: object, new: object, unit: str | None) -> str | None:
    """Replace one superseded value in a string, or refuse.

    ``None`` means the record cannot settle it - a list that was empty has no
    old rendering to find, and an allergen warning that was never written cannot
    be edited into existence. Returning the text unchanged instead would report
    a gap as a success.
    """
    if isinstance(old, bool) or isinstance(new, bool):
        return None

    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        # Rewriting only the digits keeps whatever the writer chose around them:
        # "45W" stays tight, "45 W" keeps its space, and the unit is untouched.
        return _literal_pattern(old, unit).sub(
            lambda m: m.group(0).replace(str(old), str(new), 1), text)

    if isinstance(old, list) and isinstance(new, list):
        rendered = ", ".join(str(x) for x in old)
        if not rendered or rendered not in text:
            return None
        return text.replace(rendered, ", ".join(str(x) for x in new))

    if isinstance(old, str) and old and old in text:
        return text.replace(old, str(new))

    return None


def _render_feed_row(base, listing, asset, values: dict,
                     refs: list[str]) -> tuple[str, dict]:
    """Rebuild a marketplace feed row under the channel's own field names.

    Machine fields are regenerated rather than edited: the channel's
    ``attribute_map`` says what it calls each internal path, and the same
    formatters the validator checks against produce the value. Free text inside
    the row - a title carrying the wattage - is then substituted like any other
    prose, which is what stops the row and the title asset from disagreeing.
    """
    outcome: dict[str, list[str]] = {"rewritten": [], "absent": [], "unresolved": []}
    try:
        row = json.loads(asset.text)
    except ValueError:
        row = None
    if not isinstance(row, dict):
        return asset.text, {**outcome, "unresolved": list(refs)}

    variant_id = listing.variant_id
    merged = dict(base.attrs_for(variant_id))
    for ref, value in values.items():
        entity_id, _, path = ref.partition(":")
        if entity_id == variant_id:
            merged[path] = value

    for ref in refs:
        entity_id, _, path = ref.partition(":")
        if base.attr_values.get((entity_id, path)) == values[ref]:
            continue
        field = base.channel_field(listing.channel_id, path)
        if field not in row:
            outcome["absent"].append(ref)
            continue
        row[field] = _channel_value(field, path, merged, values[ref])
        outcome["rewritten"].append(ref)

    for key, value in sorted(row.items()):
        if not isinstance(value, str):
            continue
        row[key], prose = _substitute(base, value, values, refs,
                                      asset.derived_from)
        for bucket in ("rewritten", "unresolved"):
            outcome[bucket].extend(r for r in prose[bucket]
                                   if r not in outcome[bucket])

    # A reference the machine field settled is settled, whatever the free text
    # in the row did or did not contain.
    for bucket in ("absent", "unresolved"):
        outcome[bucket] = [r for r in outcome[bucket]
                           if r not in outcome["rewritten"]]

    # Keys sorted and non-ASCII left alone, so a row rebuilt from an untouched
    # asset comes back byte-identical to the one the catalog holds - which is
    # what lets "did this change" be answered by comparing strings.
    return json.dumps(row, sort_keys=True, ensure_ascii=False), outcome


def _channel_value(field: str, path: str, merged: dict, value: object) -> object:
    """One channel-side field, rendered the way that channel wants it."""
    if field in ALLERGEN_FORMATS:
        return ALLERGEN_FORMATS[field](
            list(merged.get("food.allergens.contains") or []),
            list(merged.get("food.allergens.may_contain") or []))
    if field in INGREDIENT_FORMATS:
        return INGREDIENT_FORMATS[field](list(merged.get(path) or []))
    return value


def _claims_at_risk(base, variant_id: str, asset, values: dict) -> list[str]:
    """Claims the copy leans on that the corrected values no longer support.

    Advisory, and deliberately the same table the validator binds on: a bullet
    that says "ultra-quiet" beside a corrected 44 dB is a claim_consistency
    violation waiting to happen, and the writer should be told before it writes
    rather than after.
    """
    merged = dict(base.attrs_for(variant_id))
    for ref, value in values.items():
        entity_id, _, path = ref.partition(":")
        if entity_id == variant_id:
            merged[path] = value

    at_risk = []
    for claim in sorted(set(asset.claims_used)):
        rule = CLAIM_RULES.get(claim)
        if rule is None or any(p not in merged for p in rule.paths):
            continue
        try:
            if not rule.holds(merged):
                at_risk.append(claim)
        except (TypeError, ValueError):
            # A value of the wrong shape cannot substantiate a claim either.
            at_risk.append(claim)
    return at_risk


def _budget(base, channel_id: str, field: str, text: str) -> tuple[int | None, int]:
    """The MAX_LEN the channel imposes on this field, and what the copy spends.

    Counted the way the engine counts it - a PDP is allowed five bullets, not
    five letters - so the number a writer sees is the number that will bind.
    """
    used = len(text.splitlines()) if field in COUNTED_FIELDS else len(text)
    for rule in base.rules_by_channel.get(channel_id, []):
        if rule.field == field and rule.kind == "MAX_LEN":
            return int(rule.value), used
    return None, used


# ---------------------------------------------------------------------------
# The roster
# ---------------------------------------------------------------------------


#: True of every peer, and true because the graph never routes either to one.
#: A peer that could approve would make the reviewer optional; a peer that could
#: publish would make the approval gate a suggestion.
UNIVERSAL_LIMITS: tuple[str, ...] = (
    "approve a resolution",
    "publish to a channel",
)


def limits_of(agent: "PeerAgent") -> tuple[str, ...]:
    """What a peer may not do: the universal two, plus its own.

    Read from the peer rather than from a list beside it, so a limit cannot
    describe an agent that no longer has it.
    """
    return UNIVERSAL_LIMITS + tuple(
        limit for limit in agent.may_not if limit not in UNIVERSAL_LIMITS)


AGENTS: tuple[PeerAgent, ...] = (
    PeerAgent(
        id="lineage-analyst",
        name="Lineage Analyst",
        description=(
            "Traces a corrected attribute through the derivation graph to every "
            "content asset, listing and channel that was built from it. Answers "
            "with identifiers and counts, never with an opinion - the walk is "
            "deterministic and the result is authoritative."),
        skill_id="trace-blast-radius",
        skill_name="Trace blast radius",
        skill_description=(
            "Given a corrected entity or a set of correction signals, return "
            "every attribute, asset, listing and channel downstream of them, "
            "with totals and the causal chain."),
        examples=(
            "What does correcting VAR-01B specs.power_w reach?",
            "Which channels are exposed if the allergen declaration on PRD-02 changes?",
        ),
        handler=_lineage,
        # A lineage walk reads the catalog and nothing else. Saying so is
        # what makes handing it to a stranger uninteresting.
        may_not=("write a fact", "change a listing"),
    ),
    PeerAgent(
        id="resolution-planner",
        name="Resolution Planner",
        description=(
            "Enumerates the readings of an ambiguous correction and attaches "
            "the evidence for each. A correction that names a product but not a "
            "variant has more than one honest answer; this returns all of them "
            "with the documents behind them, and leaves the choosing to the "
            "validator."),
        skill_id="enumerate-scope-candidates",
        skill_name="Enumerate scope candidates",
        skill_description=(
            "Given a product and the attribute paths a correction touches, "
            "return the candidate scopes - base only, one named variant, or "
            "every variant - each with the source documents that support it."),
        examples=(
            "The spec sheet says the Northaven AP300 is 65 W - which variants does that mean?",
            "Does this allergen change apply to the multipack as well as the single bar?",
        ),
        handler=_resolutions,
        may_not=("write a fact", "choose between the readings it enumerates"),
    ),
    PeerAgent(
        id="validator",
        name="Deterministic Validator",
        description=(
            "Validates one candidate resolution against the catalog, the "
            "channel rules and the claim substantiation table. The same change "
            "set against the same state returns the same trace_hash, every time "
            "- this agent is the reason no model in the system is ever asked "
            "for a number or a publish verdict."),
        skill_id="validate-change-set",
        skill_name="Validate a change set",
        skill_description=(
            "Given a change set, return publishability, every binding rule "
            "violation with the rule that bound, the KPIs and a trace hash."),
        examples=(
            "Does scoping the 65 W correction to the Max leave every channel publishable?",
            "What breaks if the ingredient order changes on Marketplace B?",
        ),
        handler=_validate,
        # It scores a change set. It does not apply one, and the
        # distinction is the reason its answer can be trusted.
        may_not=("apply a change set", "write a fact"),
    ),
    PeerAgent(
        id="copywriter",
        name="Copywriter",
        description=(
            "Regenerates the copy a correction invalidated, from the supplied "
            "attribute table and nothing else. Machine fields are rebuilt under "
            "each channel's own field names; a superseded figure quoted in prose "
            "is swapped for the corrected one. Sentences the record cannot "
            "settle come back flagged rather than invented, and every claim the "
            "copy leans on is checked against the substantiation table first."),
        skill_id="regenerate-affected-copy",
        skill_name="Regenerate affected copy",
        skill_description=(
            "Given corrected attribute values, return proposed replacement text "
            "for every affected content asset, with the channel budget it must "
            "fit, the claims now at risk, and whatever could not be resolved "
            "deterministically."),
        examples=(
            "Rewrite the Northaven AP300 Max copy for a corrected 65 W rating.",
            "Rebuild the Marketplace B feed row after the ingredient reorder.",
        ),
        handler=_copy,
        may_not=("change an attribute value", "publish the copy it writes"),
    ),
)

BY_ID = {a.id: a for a in AGENTS}
