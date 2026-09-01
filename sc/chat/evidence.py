"""The facts an answer is allowed to stand on.

Nothing in this module phrases anything. Each gatherer reads surfaces this
application already has - the merged record, the readiness verdict, the
knowledge graph, the document corpus - and returns what it found as a list of
sources. A gatherer that finds nothing returns nothing, and the answer built
on it is a refusal rather than a guess.

That split is the whole safety argument for the chat surface. The model
downstream never retrieves; it is handed the list below and asked to write a
sentence from it. It cannot cite a certificate that is not in the list, because
it is never given the means to go and look for one.

Every source carries its own ``detail`` - the fact itself, not a pointer to it.
A citation a reader has to go and fetch before they can check the sentence is a
citation that will not be checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sc.contracts import ChatIntent, ChatSource

#: How many facts of one kind an answer carries. Past a dozen a citation list
#: stops being evidence somebody checks and becomes a table they scroll - and
#: the phrasing step starts summarising the list instead of answering the
#: question it was asked.
MAX_PER_KIND = 12


@dataclass
class Evidence:
    """What was found, before anything has been said about it."""

    intent: ChatIntent
    sources: list[ChatSource] = field(default_factory=list)
    #: Graph node ids worth lighting up beside the answer. Empty is normal:
    #: most intents are answered from the record, which has no node.
    highlight: list[str] = field(default_factory=list)
    #: The deterministic answer, in one sentence. This is what gets said when
    #: the gateway is unreachable, and it is also the thing the model is asked
    #: to improve on rather than replace - so a template answer and a phrased
    #: answer state the same facts.
    headline: str = ""
    resolved: dict | None = None
    as_of: datetime | None = None

    @property
    def grounded(self) -> bool:
        """An answer with no sources is a refusal. There is no third state."""
        return bool(self.sources)

    def add(self, kind: str, label: str, detail: str, *,
            reference: str | None = None, section: str | None = None) -> None:
        self.sources.append(ChatSource(
            kind=kind, label=label, detail=detail,
            reference=reference, section=section))


# ---------------------------------------------------------------------------
# Reading the surfaces
# ---------------------------------------------------------------------------


def _fmt(value: object) -> str:
    """A value as a reader would say it out loud."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        # Empty comes back empty rather than as the word "nothing", so the
        # caller can tell "this field says nothing" from "this field is
        # blank" and phrase them differently.
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k} {_fmt(v)}" for k, v in value.items())
    return str(value)


def _nodes(key: str, domains: list[str], *, depth: int = 2) -> list:
    """Nodes in these domains hanging off *this variant*, and no other.

    Two hops, and deliberately no detour through CORE to widen the reach. That
    is a correctness constraint rather than a performance one. Walking out
    through the product to reach something also walks back *down* into the
    product's other variants, and their stock, certificates and sales then
    arrive labelled as this one's. Measured on VAR-01A, that turned three
    stock records into a hundred and eighty-one and one certificate into
    nineteen - an answer stated confidently and wrong by sixty-fold, which is
    the one failure this whole surface is arranged to prevent.

    What genuinely hangs off the product rather than the variant is reached by
    ``_product_nodes`` instead, which cannot stray for the same reason.
    """
    from sc import kg

    want = {d.upper() for d in domains}
    try:
        answer = kg.neighbourhood(key, depth=depth, domains=list(want),
                                  limit=200)
    except Exception:
        # The graph is an optional backend. A question about stock asked while
        # Neo4j is down should say nothing is recorded, not raise a 500.
        return []
    if not answer:
        return []
    return [n for n in answer.get("nodes", []) if n.domain.value in want]


def _product_nodes(product_id: str | None, domains: list[str]) -> list:
    """Nodes hanging directly off the *product*, for the things that do.

    A campaign promotes a product and a market restriction is recorded against
    one, so neither is reachable from the variant at all. One hop out from the
    product node reaches both, and cannot reach a sibling variant's facts -
    those hang off the sibling, not off the product they share.
    """
    from sc import kg
    from sc.contracts import GraphNodeLabel
    from sc.kg import project

    if not product_id:
        return []
    want = {d.upper() for d in domains}
    try:
        answer = kg.expand(project.node_id(GraphNodeLabel.PRODUCT, product_id),
                           domains=list(want), limit=40)
    except Exception:
        return []
    return [n for n in answer.get("nodes", []) if n.domain.value in want]


def _props(node) -> dict:
    return node.props or {}


def _corpus(question: str, entity_id: str | None) -> list[dict]:
    """What the written standards say, if anything. Never raises.

    The index is built by a script and may simply not exist yet. A chat
    surface that 500s because nobody has run ``build_index`` is worse than one
    that says it has nothing to go on.
    """
    from sc.rag import retrieve

    try:
        if entity_id:
            hits = retrieve.for_product(question, entity_id, top_k=4)
        else:
            hits = retrieve.search(question, top_k=4)
        return retrieve.cite(hits)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# One gatherer per intent
# ---------------------------------------------------------------------------


def _overview(question: str, ev: Evidence, ctx: dict) -> None:
    record, product, variant = ctx["record"], ctx["product"], ctx["variant"]
    if record is None or product is None or variant is None:
        return

    ev.add("record", "Product",
           f"{product.name}, sold as {variant.sku}, in category "
           f"{record.category}", reference=record.entity_id, section="record")
    ev.add("record", "Supplier",
           f"supplied by {product.supplier}"
           + (", and regulated" if record.regulated else ""),
           reference=product.supplier, section="record")
    ev.add("record", "What is held",
           f"{len(record.values)} attributes recorded, "
           f"{len(record.media)} images held, "
           f"{len(record.listings)} listings",
           section="record")

    summary = ctx["assessment"]
    if summary:
        ev.add("readiness", "Readiness",
               f"the verdict is {summary['verdict']} with "
               f"{len(summary['findings'])} open findings",
               section="findings")
    ev.headline = (f"{product.name} ({variant.sku}) is a {record.category} "
                   f"product from {product.supplier}.")


def _features(question: str, ev: Evidence, ctx: dict) -> None:
    record = ctx["record"]
    if record is None:
        return

    # Ordered by attribute path so two askings of the same question list the
    # same facts in the same order. An answer that reshuffles between asks
    # reads as though the data changed underneath it.
    for path in sorted(record.values)[:MAX_PER_KIND]:
        shown = _fmt(record.values[path])
        if not shown:
            # An empty value attributed to a system claims that the system
            # sent an emptiness, which is not what happened - the field is
            # simply blank. Saying so without a source is the honest form.
            ev.add("record", path, f"{path} is not recorded",
                   reference=path, section="record")
            continue
        system = record.systems.get(path) or "an unattributed source"
        ev.add("record", path,
               f"{path} is {shown}, as recorded by {system}",
               reference=path, section="record")

    if record.values:
        ev.headline = (f"{len(record.values)} attributes are recorded for "
                       f"{ctx['variant'].sku}.")


def _readiness(question: str, ev: Evidence, ctx: dict) -> None:
    summary = ctx["assessment"]
    if summary is None:
        return

    ev.add("readiness", "Verdict",
           f"{summary['verdict']}: {len(summary['blocking'])} of "
           f"{len(summary['findings'])} findings block a launch",
           section="findings")

    for finding in summary["findings"][:MAX_PER_KIND]:
        who = finding["system"] or "no system named"
        ev.add("readiness", finding["check"],
               f"{finding['detail']} ({finding['severity']}, {who})",
               reference=finding["subject"], section="findings")

    # An assessment that could not reach a model found fewer things, and the
    # rest of this application refuses to report that as clean. Neither does
    # this: the caveat is a source, so it is said out loud with the answer.
    if summary.get("caveat"):
        ev.add("readiness", "Caveat", summary["caveat"], section="findings")

    ev.headline = (f"The verdict is {summary['verdict']}, with "
                   f"{len(summary['blocking'])} blocking findings.")


def _media(question: str, ev: Evidence, ctx: dict) -> None:
    summary = ctx["assessment"]
    if summary is None:
        return

    slots = summary.get("media") or []
    required = [s for s in slots if s.get("required")]
    missing = [s for s in required if not s.get("held")]

    for slot in slots[:MAX_PER_KIND]:
        state = "held" if slot.get("held") else "missing"
        need = "required" if slot.get("required") else "optional"
        ev.add("record", str(slot.get("role", "image")),
               f"the {slot.get('role')} shot is {state} and is {need}",
               reference=slot.get("asset_id"), section="media")

    if slots:
        ev.headline = (
            f"{len(missing)} of the {len(required)} images this category "
            f"requires are missing." if missing
            else "Every image this category requires is held.")


def _compliance(question: str, ev: Evidence, ctx: dict) -> None:
    record = ctx["record"]
    if record is not None:
        for path in sorted(p for p in record.values
                           if p.startswith("compliance.")):
            ev.add("record", path, f"{path} is {_fmt(record.values[path])}",
                   reference=path, section="record")

    graph_nodes = (_nodes(ctx["key"], ["COMPLIANCE"])
                   + _product_nodes(ctx["product_id"], ["COMPLIANCE"]))
    for node in graph_nodes[:MAX_PER_KIND]:
        props = _props(node)
        if node.label.value == "Certificate":
            detail = f"certificate {node.name}"
            if props.get("expiresOn"):
                detail += f", expiring {props['expiresOn']}"
        elif node.label.value == "Market":
            detail = f"the market {node.name} is in scope"
        else:
            detail = f"{node.label.value.lower()} {node.name}"
        ev.add("graph", node.label.value, detail,
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    if ev.sources:
        ev.headline = (f"{len(ev.sources)} compliance facts are recorded for "
                       f"{ctx['variant'].sku}.")


def _stock(question: str, ev: Evidence, ctx: dict) -> None:
    nodes = _nodes(ctx["key"], ["WAREHOUSE"])
    levels = [n for n in nodes if n.label.value == "StockLevel"]
    depots = [n for n in nodes if n.label.value == "Warehouse"]

    levels.sort(key=lambda n: (-int(_props(n).get("onHandQty") or 0), n.id))
    total = sum(int(_props(n).get("onHandQty") or 0) for n in levels)

    for node in levels[:MAX_PER_KIND]:
        props = _props(node)
        code = props.get("warehouseCode", "an unnamed depot")
        low = (" and is below its reorder point"
               if props.get("belowReorderPoint") else "")
        ev.add("graph", str(code),
               f"{props.get('onHandQty', 0)} units on hand at {code} in the "
               f"week of {props.get('weekStart', 'an unknown week')}{low}",
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    for node in depots[:4]:
        country = _props(node).get("country", "an unnamed country")
        ev.add("graph", node.name, f"{node.name} is in {country}",
               reference=node.id, section="graph")

    if levels:
        ev.headline = (f"{total} units are held across {len(levels)} depot "
                       f"records.")


def _sales(question: str, ev: Evidence, ctx: dict) -> None:
    nodes = _nodes(ctx["key"], ["SALES"])
    prices = sorted((n for n in nodes if n.label.value == "PriceRecord"),
                    key=lambda n: n.id)
    facts = [n for n in nodes if n.label.value == "SalesFact"]
    listings = [n for n in nodes if n.label.value in ("Listing", "Channel")]

    for node in prices[:6]:
        props = _props(node)
        ev.add("graph", "Price",
               f"listed at {props.get('listPrice')} "
               f"{props.get('currency', '')} in {props.get('marketCode', '')}",
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    facts.sort(key=lambda n: (-int(_props(n).get("units") or 0), n.id))
    for node in facts[:6]:
        props = _props(node)
        rank = props.get("rankInCategory")
        place = f", ranked {rank} in its category" if rank else ""
        ev.add("graph", "Sales",
               f"{props.get('units')} units in {props.get('period')} in "
               f"{props.get('marketCode', '')} for revenue "
               f"{props.get('revenue')} {props.get('currency', '')}{place}",
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    for node in listings[:4]:
        ev.add("graph", node.label.value,
               f"{node.label.value.lower()} {node.name}",
               reference=node.id, section="graph")

    if facts:
        units = sum(int(_props(n).get("units") or 0) for n in facts)
        ev.headline = (f"{units} units sold across {len(facts)} recorded "
                       f"periods.")
    elif prices:
        ev.headline = f"{len(prices)} prices are recorded, and no sales yet."


def _marketing(question: str, ev: Evidence, ctx: dict) -> None:
    # Campaigns promote the product; keywords and promotions attach to the
    # variant. Both are this product's, and neither route can reach a
    # sibling's - see _nodes.
    graph_nodes = (_product_nodes(ctx["product_id"], ["MARKETING"])
                   + _nodes(ctx["key"], ["MARKETING"]))
    for node in graph_nodes[:MAX_PER_KIND]:
        props = _props(node)
        if node.label.value == "Campaign":
            detail = (f"the campaign {node.name} runs "
                      f"{props.get('startsOn', '?')} to "
                      f"{props.get('endsOn', '?')}")
        elif node.label.value == "Promotion":
            detail = (f"{node.name}, {props.get('depthPct', '?')}% off in "
                      f"{props.get('marketCode', '')}")
        elif node.label.value == "Keyword":
            detail = f"it ranks for the keyword {node.name}"
        else:
            detail = f"{node.label.value.lower()} {node.name}"
        ev.add("graph", node.label.value, detail,
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    if ev.sources:
        ev.headline = (f"{len(ev.sources)} marketing records name this "
                       f"product.")


def _connections(question: str, ev: Evidence, ctx: dict) -> None:
    from sc import kg

    try:
        answer = kg.neighbourhood(ctx["key"], depth=2, limit=200)
    except Exception:
        answer = None
    if not answer or not answer.get("nodes"):
        return

    nodes = answer["nodes"]
    by_domain: dict[str, int] = {}
    for node in nodes:
        by_domain[node.domain.value] = by_domain.get(node.domain.value, 0) + 1

    for domain in sorted(by_domain, key=lambda d: (-by_domain[d], d)):
        ev.add("graph", domain,
               f"{by_domain[domain]} {domain.lower()} nodes within two hops",
               section="graph")

    # The best-connected neighbours, named. A count alone answers "how much"
    # and not "what", and "what" is the question that was asked.
    ranked = sorted((n for n in nodes if n.id != answer.get("root")),
                    key=lambda n: (-n.degree, n.id))
    for node in ranked[:6]:
        ev.add("graph", node.label.value,
               f"{node.name}, a {node.label.value.lower()} in "
               f"{node.domain.value.lower()}",
               reference=node.id, section="graph")
        ev.highlight.append(node.id)

    ev.headline = (f"{len(nodes)} nodes sit within two hops, across "
                   f"{len(by_domain)} domains.")


def _standards(question: str, ev: Evidence, ctx: dict) -> None:
    record = ctx["record"]
    for hit in _corpus(question, record.entity_id if record else None):
        heading = f", {hit['heading']}" if hit.get("heading") else ""
        ev.add("corpus", hit["title"],
               f"{hit['title']}{heading}: {hit['excerpt']}",
               reference=hit["chunk_id"])

    if ev.sources:
        ev.headline = (f"{len(ev.sources)} passages in the written standards "
                       f"bear on this.")


_GATHERERS = {
    ChatIntent.OVERVIEW: _overview,
    ChatIntent.FEATURES: _features,
    ChatIntent.READINESS: _readiness,
    ChatIntent.MEDIA: _media,
    ChatIntent.COMPLIANCE: _compliance,
    ChatIntent.STOCK: _stock,
    ChatIntent.SALES: _sales,
    ChatIntent.MARKETING: _marketing,
    ChatIntent.CONNECTIONS: _connections,
    ChatIntent.STANDARDS: _standards,
}


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def gather(question: str, intent: ChatIntent, key: str | None) -> Evidence:
    """Everything that can be said in answer to this, and nothing else.

    ``key`` is a SKU, a variant id or a product id - whatever the screen
    happened to be holding. It is resolved once, here, and the resolution
    travels with the answer, so a reader is never left guessing which of the
    three the system thought they meant.
    """
    from sc.readiness import assess
    from sc.readiness import record as record_mod
    from sc.readiness import search
    from sc.replay import tape
    from sc.state import baseline as baseline_mod

    ev = Evidence(intent=intent, as_of=tape.sim_now())
    if intent is ChatIntent.UNANSWERABLE:
        return ev

    base = baseline_mod.get()
    resolved = search.resolve(key, base) if key else None
    ev.resolved = resolved

    record = product = variant = None
    if resolved is not None:
        record = record_mod.build(resolved["entity_id"], base=base)
        variant = base.variants.get(resolved["entity_id"])
        product = base.products.get(variant.product_id) if variant else None

    # The assessment is expensive enough to be worth building once, and only
    # for the intents that actually read it. ``use_model=False`` keeps this
    # surface answerable with no gateway - the same posture the product list
    # takes - and the caveat that comes back is carried into the answer rather
    # than swallowed.
    assessment = None
    if resolved is not None and intent in (
            ChatIntent.OVERVIEW, ChatIntent.READINESS, ChatIntent.MEDIA):
        assessment = assess(resolved["entity_id"], use_model=False,
                            include_record=False, record=record, base=base)

    ctx = {"key": resolved["entity_id"] if resolved else key,
           "product_id": resolved["product_id"] if resolved else None,
           "record": record, "product": product, "variant": variant,
           "assessment": assessment, "base": base}

    gatherer = _GATHERERS.get(intent)
    # STANDARDS is the one intent that means something with no product: the
    # corpus is a corpus whether or not a SKU is on screen.
    if gatherer is not None and (resolved is not None
                                 or intent is ChatIntent.STANDARDS):
        gatherer(question, ev, ctx)
    return ev
