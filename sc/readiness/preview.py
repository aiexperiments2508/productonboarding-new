"""The staging page, and the one genuinely generative surface in this system.

Everything else a model touches here produces a *candidate* that a rule then
admits or drops. The value differentiator is different: it is prose written for
a shopper, and there is no rule that can check whether a sentence is good.

So it is fenced by construction rather than by judgement. A differentiator may
rest on exactly two things:

*   an attribute the record actually holds, and
*   a passage the corpus actually carries.

Both, every time. "Comfortable in summer" needs a summer *and* a reason, and
either one alone is a sentence somebody made up. A differentiator that can cite
only one of the two is not shown - not softened, not marked uncertain, not
shown, because this is the last surface before publication and the first one a
reviewer trusts.

Whatever the model returns is then checked against the prohibited-content rules
rather than requested politely in the prompt. A prompt saying "do not make
medical claims" is a preference; a check that strips them is a control.

With no gateway, the same two inputs produce the same sentence by template. The
surface degrades rather than disappearing, which matters because a venue with no
network should still see the feature.
"""

from __future__ import annotations

from sc.llm import gateway
from sc.llm.gateway import GatewayError
from sc.rag import retrieve
from sc.readiness import verdict as verdict_mod
from sc.readiness import checks as checks_mod
from sc.readiness.checks import FORBIDDEN_PHRASES, Record

#: Attributes worth leading with, by category prefix. Drawn from MKT-002, which
#: records what shoppers actually ask in store - not from what happens to be
#: numerically largest.
#:
#: The entries here are the *finer* than-branch ones, which a profile does not
#: express: an air purifier leads on coverage and an oven does not, and both
#: are `home.`. The branch-level answers come from the catalog's own profile
#: and are merged underneath these, longest prefix winning.
SALIENT: dict[str, tuple[str, ...]] = {
    "home.air-treatment": ("specs.noise_db", "specs.coverage_m2",
                           "specs.power_w", "specs.filter_type"),
    "home.kitchen": ("specs.power_w", "energy.class"),
    "home.": ("specs.power_w", "specs.noise_db", "energy.class"),
    "food.": ("food.net_weight_g", "food.fibre_g", "food.allergens.contains"),
    "audio.": ("specs.power_w",),
}

DIFFERENTIATOR_SYSTEM = (
    "You write one or two sentences saying why a shopper would choose this "
    "product, now.\n"
    "You may use ONLY the attribute values given and the market context given. "
    "Do not introduce a fact, a number, a comparison or a superlative that is "
    "not in one of them.\n"
    "No medical, health, safety or guaranteed-outcome claims of any kind.\n"
    "Name the attributes you leaned on and cite the context passage you used.\n"
    'Reply as JSON: {"text": str, "attributes": [str], "citation": str}'
)


def _salient_table(base) -> dict[str, tuple[str, ...]]:
    """Branch defaults from the catalog, with the finer rules layered on top.

    A profile knows that clothing leads on fibre composition. It does not know
    that air purifiers lead on coverage area while kettles lead on wattage,
    because that is a distinction inside one branch. So the two compose rather
    than one replacing the other, and the longest prefix wins either way.
    """
    branches = (getattr(base.catalog, "profile", None) or {}).get("branches")
    if not branches:
        return SALIENT
    table = {f"{key}.": tuple(spec.get("salient", ()))
             for key, spec in branches.items()}
    table.update(SALIENT)
    return table


def _salient_paths(category: str, base=None) -> tuple[str, ...]:
    table = SALIENT if base is None else _salient_table(base)
    for prefix in sorted(table, key=len, reverse=True):
        if category.startswith(prefix):
            return table[prefix]
    return ()


def salient(record: Record, base) -> list[dict]:
    """The specification a shopper reads first.

    Ordered by what the category is bought on rather than by attribute path,
    because a page that leads with the GTIN is a page written for a database.
    """
    rows = []
    for path in _salient_paths(record.category, base):
        if path not in record.values:
            continue
        definition = base.attr_defs.get(path)
        rows.append({
            "path": path,
            "label": definition.label if definition else path,
            "value": record.values[path],
            "unit": definition.unit if definition else None,
        })
    return rows


def _substantiated_claims(record: Record, base) -> list[str]:
    """Claims the record supports, checked against the same table the validator
    uses.

    A claim on the preview that the validator would refuse at publish is a
    claim the reviewer approves and the channel rejects, which is the worst of
    both.
    """
    from sc.sim import engine

    held = record.values.get("claims") or []
    if not isinstance(held, list):
        return []
    values = dict(record.values)
    kept = []
    for claim in held:
        rule = engine.CLAIM_RULES.get(str(claim))
        if rule is None:
            # A claim the substantiation table has no predicate for. Not shown,
            # because "we have no rule for this" is not the same as "this is
            # true", and the preview may only carry what the record supports.
            continue
        try:
            supported = rule.holds(values)
        except (KeyError, TypeError, ValueError):
            # The predicate reads an attribute this record does not hold, so
            # the claim is unsubstantiated rather than false. Narrow on
            # purpose: a bare `except` here once hid a wrong call and reported
            # every claim as unsupported, which looks exactly like a clean
            # record.
            continue
        if supported:
            kept.append(str(claim))
    return kept


def _forbidden(text: str) -> str | None:
    haystack = f" {text.lower()} "
    for phrase, why in FORBIDDEN_PHRASES:
        if f" {phrase} " in haystack or f" {phrase}." in haystack:
            return why
    return None


def _template(record: Record, base, rows: list[dict], passage) -> dict:
    """The differentiator without a model.

    Deliberately flat. It names the same attributes and cites the same passage
    the model would have been given, so what degrades is the prose and never the
    grounding - and a reviewer can see that the two forms rest on the same two
    things.
    """
    variant = base.variants[record.entity_id]
    parts = [f"{v['label']} {v['value']}{(' ' + v['unit']) if v['unit'] else ''}"
             for v in rows[:3]]
    text = (f"{variant.name}: " + ", ".join(parts) + "."
            if parts else f"{variant.name}.")
    return {
        "text": text,
        "attributes": [v["path"] for v in rows[:3]],
        "citation": passage.chunk.id,
        "source": passage.chunk.doc_id,
        "written_by_model": False,
        "note": "written without a model, from the same attributes and the "
                "same passage",
    }


def differentiator(record: Record, base, *, use_model: bool = True,
                   run_id: str = "") -> dict | None:
    """Why somebody would buy this, here, now - or nothing.

    Returns None when it cannot be grounded twice. That is the intended
    outcome, not a failure: a page with no differentiator is a page that says
    less, and a page with an ungrounded one is a page that is wrong.
    """
    rows = salient(record, base)
    if not rows:
        return None

    passages = retrieve.for_product(
        f"who buys {record.category} and when",
        record.entity_id, top_k=2, doc_types=["MARKET"],
        related=[record.product_id])
    if not passages:
        # No context. The record alone can say what a product *is* and never
        # why it matters this month, and asserting the second from the first is
        # the exact fabrication this surface exists to prevent.
        return None

    passage = passages[0]
    if not use_model:
        return _template(record, base, rows, passage)

    context = "\n\n".join(f"[{p.chunk.id}] {p.chunk.text}" for p in passages)
    attributes = "\n".join(
        f"- {v['label']} ({v['path']}) = {v['value']}"
        f"{(' ' + v['unit']) if v['unit'] else ''}" for v in rows)
    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": DIFFERENTIATOR_SYSTEM},
             {"role": "user",
              "content": (f"Product: {base.variants[record.entity_id].name}\n"
                          f"Category: {record.category}\n\n"
                          f"Attributes:\n{attributes}\n\n"
                          f"Market context:\n{context}")}],
            model=_reasoning(), agent="preview.differentiator", run_id=run_id)
    except GatewayError:
        return _template(record, base, rows, passage)

    text = str((reply or {}).get("text") or "").strip() if isinstance(
        reply, dict) else ""
    if not text:
        return _template(record, base, rows, passage)

    # Checked, not requested. A prompt saying "no medical claims" is a
    # preference; this is a control, and it runs whatever the model returned.
    if _forbidden(text):
        return _template(record, base, rows, passage)

    # Resolved against paths *and* labels. A model asked which attributes it
    # leaned on answers "Sound level" at least as often as "specs.noise_db",
    # and rejecting the first would fail a differentiator that is perfectly
    # grounded for naming the attribute the way a person would. The gate is
    # that the attribute is one the record holds - not that it was spelled the
    # way the database spells it.
    by_label = {}
    for path in record.values:
        definition = base.attr_defs.get(path)
        if definition is not None:
            by_label[definition.label.strip().lower()] = path
    named: list[str] = []
    for claimed in reply.get("attributes") or []:
        text_claim = str(claimed).strip()
        path = (text_claim if text_claim in record.values
                else by_label.get(text_claim.lower()))
        if path and path not in named:
            named.append(path)
    cited = str(reply.get("citation") or "")
    known = {p.chunk.id for p in passages} | {p.chunk.doc_id for p in passages}
    if not named or not any(k and k in cited for k in known):
        # Grounded on one leg or none. Withheld rather than shown with a
        # caveat: a caveat on a product page is read by nobody.
        return _template(record, base, rows, passage)

    return {
        "text": text[:400],
        "attributes": [str(p) for p in named],
        "citation": cited,
        "source": passage.chunk.doc_id,
        "written_by_model": True,
        "note": "",
    }


def _reasoning() -> str:
    from sc.graph.nodes import reasoning_model

    return reasoning_model()


def build(entity_id: str, assessment: dict, *, use_model: bool = True,
          run_id: str = "", record=None) -> dict:
    """The staging page for a ready record, or a refusal with its reasons.

    A page that renders a blocked product is a page somebody screenshots, so
    the refusal is the whole response rather than a banner across the top of
    one.
    """
    from sc.readiness import record as record_mod
    from sc.state import baseline as baseline_mod

    if assessment.get("verdict") != verdict_mod.READY:
        return {
            "entity_id": entity_id,
            "rendered": False,
            "verdict": assessment.get("verdict"),
            "findings": assessment.get("findings", []),
            "reason": "a preview is produced only for a record that is ready "
                      "to launch",
        }

    base = baseline_mod.get()
    # Handed in by the route, which has already built it to assess the record.
    # Building it again here was a second pass over the fact store to produce
    # an identical object, on the slowest interaction in the application.
    if record is None:
        record = record_mod.build(entity_id)
    if record is None:
        return {"entity_id": entity_id, "rendered": False,
                "reason": "no such product"}

    variant = base.variants[record.entity_id]
    product = base.products[record.product_id]
    return {
        "entity_id": entity_id,
        "rendered": True,
        "verdict": verdict_mod.READY,
        "sku": variant.sku,
        "title": f"{product.name} - {variant.name}",
        "category": product.category,
        # Every figure here comes from the record, unchanged. Nothing is
        # computed, rounded or reworded: this is the last surface before
        # publication and a figure that appears here and nowhere in the record
        # is a figure nobody can trace.
        "specification": salient(record, base),
        # Every slot this category has, held or not, from the same table the
        # required_media check binds on. A staging page that silently omitted
        # the panel it is missing would be a page that looks finished.
        "media": checks_mod.media_status(record, base),
        "claims": _substantiated_claims(record, base),
        "differentiator": differentiator(record, base, use_model=use_model,
                                         run_id=run_id),
    }
