"""Catalog state and the blast-radius traversal.

Read-only, pure, and never calls a model. The scope of a correction is *derived*
from the catalog's own structure - which document defines which attribute, which
copy quotes it, which listing carries that copy, which channel that listing feeds
- rather than guessed. That is what lets the reviewer be told "this correction
touches eleven listings across four channels" and be able to check it.

``get_network_state`` keeps its name because the API layer and the UI map call
it. The network it describes is a product catalog: suppliers, products,
variants, channels, and the listings that join them.

Routing note: these functions are the *direct* implementations. The MCP
transport switch is applied by the caller - ``sc.graph.evidence`` wraps them in
``sc.mcp.client.call(tool, args, direct_fn)``, and they are exposed as tools by
``sc.mcp.product_catalog`` (the catalog reads) and ``sc.mcp.channel_registry``
(``channel_rules`` and ``get_listing_state``). Routing here as well would make a
tool call itself: with ``USE_MCP=1`` the server subprocess would re-enter the
client and spawn another server per lookup.
"""

from __future__ import annotations

from datetime import datetime

from sc import db
from sc.contracts import AffectedScope, ProvenanceKind
from sc.replay import tape
# Version ranking is the validator's own, so the map and the validator agree on
# what "newer" means instead of each deciding for itself.
from sc.sim.engine import Overlay, _rank as version_rank
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod
from sc.state import store
from sc.state.baseline import Baseline

# The relations a causal chain may be drawn with. Anything outside this set is a
# hop the UI cannot label and a reviewer cannot read.
RELATIONS = ("contains", "defines", "derives", "feeds", "lists_on", "supersedes")

# A chain longer than this is a wall of text, not an explanation. The cap
# truncates what is *shown*; the affected lists and the totals stay complete.
MAX_CHAIN = 200


# ---------------------------------------------------------------------------
# Reading the catalog at an instant
# ---------------------------------------------------------------------------


def _instant(as_of: str | None) -> datetime:
    """Everything time-aware runs on the replay clock, never on wall clock."""
    return datetime.fromisoformat(as_of) if as_of else tape.sim_now()


def _key(ref: str) -> tuple[str, str]:
    entity_id, _, path = ref.partition(":")
    return entity_id, path


def _doc_ref(doc: str, version: str) -> str:
    return f"{doc}:{version}" if version else doc


def _paths_of(base: Baseline, ov: Overlay, entity_id: str) -> list[str]:
    """Every attribute with a value on file for one entity, corrections included."""
    return sorted({p for e, p in base.attr_values if e == entity_id}
                  | {p for e, p in ov.attr_values if e == entity_id})


def _all_refs(base: Baseline, ov: Overlay) -> list[str]:
    return sorted(f"{e}:{p}" for e, p in set(base.attr_values) | set(ov.attr_values))


def _source_of(base: Baseline, ov: Overlay, key: tuple[str, str]) -> tuple[str, str]:
    """The document and version a value is standing on at this instant.

    A corrected value's document is found by walking its fact lineage back to
    the assertion that produced it; an uncorrected one still stands on whatever
    the seed pack recorded. This is the pairing that lets the base-versus-variant
    question be settled by evidence: VAR-01A's wattage carries the portal feed
    that certified it, not the spec sheet that was later corrected.
    """
    state = ov.attr_values.get(key)
    if state is None:
        source = base.attr_sources.get(key)
        return (source.doc_id, source.version) if source else ("", "")
    chain = store.lineage(state.fact_id) if state.fact_id else []
    doc = (chain[0].provenance.source_id or "").partition(":")[0] if chain else ""
    return doc, state.version


def _value(base: Baseline, ov: Overlay, entity_id: str, path: str) -> dict | None:
    """One attribute value with everything needed to defend it."""
    key = (entity_id, path)
    state = ov.attr_values.get(key)
    if state is None and key not in base.attr_values:
        return None
    doc, version = _source_of(base, ov, key)
    return {
        "value": state.value if state else base.attr_values[key],
        "version": version,
        "doc": doc,
        "provenance": (state.provenance_kind if state
                       else str(ProvenanceKind.RECORDED)),
        "confidence": state.confidence if state else None,
    }


def _is_safety(base: Baseline, ref: str) -> bool:
    definition = base.attr_defs.get(_key(ref)[1])
    return bool(definition and definition.safety_class)


def _stale_refs(base: Baseline, ov: Overlay, asset) -> list[str]:
    """The values a content asset was built against that have since moved.

    The comparison is the validator's own ``_rank``, so the map calls an asset
    stale exactly when ``engine._check_staleness`` does rather than on a second
    opinion about what "newer" means.
    """
    built = version_rank(asset.built_at_version)
    return [ref for ref in sorted(asset.derived_from)
            if (row := _value(base, ov, *_key(ref))) is not None
            and version_rank(row["version"]) > built]


# ---------------------------------------------------------------------------
# The catalog, plus whatever has been corrected under it
# ---------------------------------------------------------------------------


def get_network_state(as_of: str | None = None,
                      as_of_recorded: str | None = None) -> dict:
    """The catalog plus whatever corrections are in force at the given instant.

    ``as_of`` moves along valid time (the UI's time scrubber); ``as_of_recorded``
    moves along recorded time, so the map can be drawn as it looked before a
    late correction arrived.
    """
    base = baseline_mod.get()
    valid = _instant(as_of)
    recorded = datetime.fromisoformat(as_of_recorded) if as_of_recorded else None
    ov = overlay_mod.build(valid, recorded)

    # Four tiers, so the edges are derived rather than stored: a listing is the
    # only join between a variant and a channel, and it carries its own state.
    edges: list[dict] = [
        {"from": p.supplier, "to": p.id, "relation": "supplies"}
        for p in sorted(base.catalog.products, key=lambda p: p.id)
    ]
    edges += [
        {"from": v.product_id, "to": v.id, "relation": "contains"}
        for v in sorted(base.catalog.variants, key=lambda v: v.id)
    ]
    for listing_id in sorted(base.listings):
        listing = base.listings[listing_id]
        edges.append({
            "from": listing.variant_id,
            "to": listing.channel_id,
            "relation": "lists_on",
            "listing": listing.id,
            "status": ov.channel_status.get(listing.id, listing.status),
        })

    # A document the prepared content can no longer cite as it stands:
    # withdrawn, superseded, or revised past the version the copy was built on.
    docs: list[str] = []
    for doc_id in sorted(set(ov.doc_versions) | set(ov.doc_status)):
        doc = base.source_docs.get(doc_id)
        status = ov.doc_status.get(doc_id, doc.status if doc else "")
        version = ov.doc_versions.get(doc_id, doc.version if doc else "")
        revised = doc is not None and version_rank(version) > version_rank(doc.version)
        if status != "ACTIVE" or revised:
            docs.append(doc_id)

    # The systems that fed all this, derived from the connection records and
    # what each has actually carried - never stored, for the same reason the
    # rest of the map is not: a tier whose membership changes while the
    # application is running cannot be a fact written at generation time.
    #
    # Failing softly on purpose. The estate explains where the catalog came
    # from; the catalog does not depend on it, and a map missing its left-hand
    # tier is better than a map that would not draw.
    try:
        from sc.estate import topology as estate_topology

        system_nodes, system_edges = estate_topology.nodes_and_edges()
    except Exception:  # noqa: BLE001 - the map must draw regardless
        system_nodes, system_edges = [], []

    return {
        "as_of": valid.isoformat(),
        "as_of_recorded": recorded.isoformat() if recorded else None,
        "nodes": ([n.model_dump(mode="json") for n in base.catalog.nodes]
                  + system_nodes),
        "edges": edges + system_edges,
        "products": [p.model_dump(mode="json") for p in base.catalog.products],
        "variants": [v.model_dump(mode="json") for v in base.catalog.variants],
        "channels": [c.model_dump(mode="json") for c in base.catalog.channels],
        "rules": [r.model_dump(mode="json")
                  for r in sorted(base.rules, key=lambda r: r.id)],
        "listings": [base.listings[l].model_dump(mode="json")
                     for l in sorted(base.listings)],
        "attributes": [a.model_dump(mode="json") for a in base.catalog.attributes],
        "horizon_start": base.horizon_start.isoformat(),
        "horizon_days": base.horizon_days,
        # Singular, because that is what the typed client declares: one
        # instant's worth of correction, not a history of them.
        "correction": {
            "docs": docs,
            "attributes": {f"{e}:{p}": _value(base, ov, e, p)
                           for e, p in sorted(ov.attr_values)},
            # Every listing whose status has moved, not only the blocked ones:
            # a listing the overlay has *restored* is what tells the map to stop
            # drawing the status baked into the listing row.
            "listings": {k: v for k, v in sorted(ov.channel_status.items())
                         if k in base.listings},
            "assets_stale": sum(1 for asset in base.assets.values()
                                if _stale_refs(base, ov, asset)),
            "channels": {k: v for k, v in sorted(ov.channel_status.items())
                         if k in base.channels},
            "summary": overlay_mod.summarise(ov),
        },
    }


# ---------------------------------------------------------------------------
# The blast radius
# ---------------------------------------------------------------------------


def _seed(base: Baseline, ov: Overlay,
          entity_id: str) -> tuple[set[str], set[str], set[str]]:
    """Resolve a root of any accepted kind into attribute, asset and listing seeds.

    An unknown root resolves to nothing rather than raising. The caller asked
    about something the catalog does not contain, and an empty scope is the
    honest answer to that question.
    """
    if entity_id in base.source_docs:
        return ({ref for ref in _all_refs(base, ov)
                 if _source_of(base, ov, _key(ref))[0] == entity_id}, set(), set())

    if entity_id in base.products:
        return ({f"{v}:{p}" for v in base.variants_of.get(entity_id, [])
                 for p in _paths_of(base, ov, v)}, set(), set())

    if entity_id in base.variants:
        return ({f"{entity_id}:{p}" for p in _paths_of(base, ov, entity_id)},
                set(), set())

    head, qualified, path = entity_id.partition(":")
    if qualified and head in base.variants and path in base.attr_defs:
        return {entity_id}, set(), set()

    if entity_id in base.assets:
        return set(base.assets[entity_id].derived_from), {entity_id}, set()

    if entity_id in base.listings:
        variant_id = base.listings[entity_id].variant_id
        return ({f"{variant_id}:{p}" for p in _paths_of(base, ov, variant_id)},
                set(), {entity_id})

    if entity_id in base.channels:
        listings = set(base.listings_by_channel.get(entity_id, []))
        return ({f"{base.listings[l].variant_id}:{p}" for l in listings
                 for p in _paths_of(base, ov, base.listings[l].variant_id)},
                set(), listings)

    return set(), set(), set()


def trace_dependencies(entity_id: str, depth: int = 3,
                       as_of: str | None = None) -> dict:
    """Walk outward from a correction to everything it can reach.

    This is the blast radius, and it follows the structure of the catalog:

        source_doc -defines-> attribute -derives-> asset -lists_on-> listing
        -feeds-> channel

    with product and variant membership as ``contains`` and document revisions
    as ``supersedes``. Nothing here asks a model what is affected - the answer
    is the lineage the content was built with.

    Depth bounds the walk: 1 stops at the fields and the variants carrying them,
    2 adds the copy and the listings it sits on, 3 adds the channels and the
    sibling variants reached through a cross-variant asset - the comparison
    table on the base model's page that quotes the Max's wattage.
    """
    base = baseline_mod.get()
    ov = overlay_mod.build(_instant(as_of))

    chain: list[dict] = []
    drawn: set[tuple[str, str, str]] = set()

    def link(from_ref: str, to_ref: str, relation: str) -> None:
        edge = (from_ref, to_ref, relation)
        if edge not in drawn:
            drawn.add(edge)
            chain.append({"from": from_ref, "to": to_ref, "relation": relation})

    attrs, assets, listings = _seed(base, ov, entity_id)
    variants: set[str] = set()
    channels: set[str] = set()

    # A document revision supersedes the version the copy was written against.
    doc = base.source_docs.get(entity_id)
    if doc is not None:
        in_force = ov.doc_versions.get(entity_id, doc.version)
        if in_force != doc.version:
            link(f"{entity_id}:{in_force}", f"{entity_id}:{doc.version}",
                 "supersedes")

    for ref in sorted(attrs):
        variant_id, path = _key(ref)
        if variant_id in base.variants:
            variants.add(variant_id)
            link(base.product_of_variant[variant_id], variant_id, "contains")
        source, version = _source_of(base, ov, (variant_id, path))
        if source:
            link(_doc_ref(source, version), ref, "defines")

    if depth >= 2:
        for ref in sorted(attrs):
            for asset_id in base.assets_derived_from.get(ref, []):
                assets.add(asset_id)
                link(ref, asset_id, "derives")
        for variant_id in sorted(variants):
            for listing_id in base.listings_of.get(variant_id, []):
                listings.add(listing_id)
                link(variant_id, listing_id, "lists_on")
        for asset_id in sorted(assets):
            listing_id = base.assets[asset_id].listing_id
            listings.add(listing_id)
            link(asset_id, listing_id, "lists_on")

    if depth >= 3:
        for listing_id in sorted(listings):
            listing = base.listings[listing_id]
            channels.add(listing.channel_id)
            link(listing_id, listing.channel_id, "feeds")
            # A sibling reached through a cross-variant asset is in scope, but
            # is not expanded again: the walk is staged rather than recursive,
            # so a catalog that references itself terminates by construction.
            if listing.variant_id not in variants:
                variants.add(listing.variant_id)
                link(base.product_of_variant[listing.variant_id],
                     listing.variant_id, "contains")

    scope = AffectedScope(
        products=sorted({base.product_of_variant[v] for v in variants}),
        variants=sorted(variants),
        attributes=sorted(attrs),
        assets=sorted(assets),
        listings=sorted(listings),
        channels=sorted(channels),
    )

    return {
        "root": entity_id,
        "affected": scope.model_dump(mode="json"),
        "chain": chain[:MAX_CHAIN],
        "totals": {
            "fields": len(scope.attributes),
            "assets": len(scope.assets),
            "listings": len(scope.listings),
            "channels": len(scope.channels),
            "safety_flags": sum(1 for ref in scope.attributes
                                if _is_safety(base, ref)),
            "regulated": sum(1 for p in scope.products if base.products[p].regulated),
        },
    }


# ---------------------------------------------------------------------------
# Base versus variant - the evidence, not the argument
# ---------------------------------------------------------------------------


def variant_diff(product_id: str, as_of: str | None = None) -> dict:
    """The attribute table across a product's base and variants.

    Every value carries the document and version it is standing on, which is
    what makes the scope question answerable from the record: the base model was
    independently certified at 45 W two weeks before an ambiguous correction
    named the product and not the variant.
    """
    base = baseline_mod.get()
    product = base.products.get(product_id)
    if product is None:
        return {"error": f"no such product: {product_id}"}

    ov = overlay_mod.build(_instant(as_of))
    # Base first, then by id: the base column is what the others are read
    # against, and the order has to be the same on every refresh.
    variants = sorted(base.variants_of.get(product_id, []),
                      key=lambda v: (not base.variants[v].is_base, v))

    rows = []
    for path in sorted({p for v in variants for p in _paths_of(base, ov, v)}):
        definition = base.attr_defs.get(path)
        values = {v: _value(base, ov, v, path) for v in variants}
        present = {v: row for v, row in values.items() if row is not None}
        rows.append({
            "path": path,
            "label": definition.label if definition else path,
            "unit": definition.unit if definition else None,
            "safety_class": bool(definition and definition.safety_class),
            "values": present,
            # A value one variant carries and another does not is a difference
            # too - a gap on the Max is exactly what the correction exposes.
            "differs": (len(present) != len(variants)
                        or len({db.dumps(r["value"]) for r in present.values()}) > 1),
        })

    return {
        "product": product.model_dump(mode="json"),
        "variants": [base.variants[v].model_dump(mode="json") for v in variants],
        "attributes": rows,
    }


# ---------------------------------------------------------------------------
# Lineage of one derived output
# ---------------------------------------------------------------------------


def _field_source(base: Baseline, ref: str, variant_id: str) -> dict:
    entity_id, path = _key(ref)
    source = base.attr_sources.get((entity_id, path))
    definition = base.attr_defs.get(path)
    return {
        "ref": ref,
        "entity_id": entity_id,
        "path": path,
        "label": definition.label if definition else path,
        "unit": definition.unit if definition else None,
        "safety_class": bool(definition and definition.safety_class),
        "value": base.attr_values.get((entity_id, path)),
        "doc": source.doc_id if source else "",
        "version": source.version if source else "",
        # The edge that makes a variant-scoped correction land on another
        # variant's page.
        "cross_variant": entity_id != variant_id,
    }


def _asset_derivation(base: Baseline, asset_id: str) -> dict:
    asset = base.assets[asset_id]
    listing = base.listings[asset.listing_id]
    return {
        "asset": asset.model_dump(mode="json"),
        "listing": listing.id,
        "channel": listing.channel_id,
        "variant": listing.variant_id,
        "built_at_version": asset.built_at_version,
        "claims_used": sorted(asset.claims_used),
        "derived_from": [_field_source(base, ref, listing.variant_id)
                         for ref in sorted(asset.derived_from)],
    }


def get_derivation(entity_id: str) -> dict:
    """What an asset or a listing was built from.

    Deliberately baseline-only: ``derived_from`` and ``built_at_version`` record
    what the copy was written against, and that does not move when a correction
    lands. What has moved *since* is ``get_listing_state``'s question.
    """
    base = baseline_mod.get()

    if entity_id in base.assets:
        return {"kind": "asset", **_asset_derivation(base, entity_id)}

    if entity_id in base.listings:
        listing = base.listings[entity_id]
        asset_ids = base.assets_by_listing.get(entity_id, [])
        return {
            "kind": "listing",
            "listing": listing.model_dump(mode="json"),
            "variant": listing.variant_id,
            "product": base.product_of_variant[listing.variant_id],
            "channel": listing.channel_id,
            "assets": [_asset_derivation(base, a) for a in asset_ids],
            "sources": sorted({ref for a in asset_ids
                               for ref in base.assets[a].derived_from}),
        }

    return {"error": f"no such asset or listing: {entity_id}"}


# ---------------------------------------------------------------------------
# What a channel demands, and what one listing currently says
# ---------------------------------------------------------------------------


def channel_rules(channel_id: str, field: str | None = None) -> dict:
    """The rules in force for a channel, or for one of its fields.

    Rules are data, so this is a read rather than a description of code: a
    channel gains a rule without the validator changing, and the reviewer sees
    the same row the engine bound on.
    """
    base = baseline_mod.get()
    channel = base.channels.get(channel_id)
    if channel is None:
        return {"error": f"no such channel: {channel_id}"}

    rules = base.rules_by_channel.get(channel_id, [])
    selected = [r for r in rules if field is None or r.field == field]

    return {
        "channel": channel.model_dump(mode="json"),
        "field": field,
        "rules": [r.model_dump(mode="json") for r in selected],
        "fields": sorted({r.field for r in rules}),
        "required_attributes": sorted(a.path for a in base.catalog.attributes
                                      if channel_id in a.required_for),
        # What this channel calls the internal paths it maps.
        "attribute_paths": sorted(p for p, f in channel.attribute_map.items()
                                  if field is None or f == field),
    }


def get_listing_state(listing_id: str, as_of: str | None = None) -> dict:
    """One listing as it stands: its values, its copy, and what has moved under it."""
    base = baseline_mod.get()
    listing = base.listings.get(listing_id)
    if listing is None:
        return {"error": f"no such listing: {listing_id}"}

    valid = _instant(as_of)
    ov = overlay_mod.build(valid)
    variant = base.variants[listing.variant_id]

    assets = []
    for asset_id in base.assets_by_listing.get(listing_id, []):
        asset = base.assets[asset_id]
        stale = _stale_refs(base, ov, asset)
        assets.append({
            "id": asset.id,
            "field": asset.field,
            "text": asset.text,
            "built_at_version": asset.built_at_version,
            "derived_from": sorted(asset.derived_from),
            "claims_used": sorted(asset.claims_used),
            "stale_refs": stale,
            "stale": bool(stale),
        })

    return {
        "as_of": valid.isoformat(),
        "listing": listing.model_dump(mode="json"),
        "variant": variant.model_dump(mode="json"),
        "product": base.products[variant.product_id].model_dump(mode="json"),
        "channel": base.channels[listing.channel_id].model_dump(mode="json"),
        "status": ov.channel_status.get(listing_id, listing.status),
        "channel_status": ov.channel_status.get(listing.channel_id, ""),
        "published_version": ov.published_version.get(listing_id,
                                                      listing.published_version),
        "values": {path: _value(base, ov, variant.id, path)
                   for path in _paths_of(base, ov, variant.id)},
        "assets": assets,
        "stale_assets": [a["id"] for a in assets if a["stale"]],
    }
