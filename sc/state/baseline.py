"""Immutable baseline snapshot loaded from the seed pack.

Split deliberately from the bitemporal store. The seed pack is the *static*
starting position - the catalog, the prepared content, the supplier documents
that were on file when the copy was written, and the attribute values those
documents asserted. It never changes during a run. The bitemporal store in
``store.py`` holds everything that *does* change: corrections, decisions,
published versions.

The validator composes the two: baseline, then the as-of overlay of facts, then
the candidate change set. Keeping the baseline immutable and cached is what
lets a dozen candidate resolutions validate concurrently without stepping on
each other, and what makes two runs over the same pack hash identically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sc.contracts import (
    AttributeDef,
    Catalog,
    Channel,
    ChannelRule,
    ContentAsset,
    Listing,
    Product,
    ScopeLevel,
    SourceDoc,
    SourceRef,
    Variant,
)


def data_dir() -> Path:
    import os

    return Path(os.environ.get("DATA_DIR", "data"))


def _jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


@dataclass
class Baseline:
    """Everything the validator needs that does not change during a run."""

    catalog: Catalog
    products: dict[str, Product]
    variants: dict[str, Variant]
    channels: dict[str, Channel]
    listings: dict[str, Listing]
    assets: dict[str, ContentAsset]
    attr_defs: dict[str, AttributeDef]  # keyed by path
    rules: list[ChannelRule]
    source_docs: dict[str, SourceDoc]

    # The values the prepared copy was written against, and where each came
    # from. Keyed by (entity_id, path) because the same attribute on two
    # variants of one product is exactly what scenario one is about.
    attr_values: dict[tuple[str, str], object]
    attr_sources: dict[tuple[str, str], SourceRef]
    inject: dict

    # --- derived lookups, built once ---------------------------------------
    #: Imagery held against each variant. Empty rather than absent for a variant
    #: nothing has been delivered for - "no media" is an answer, and a missing
    #: key is a lookup error at the call site.
    media_by_entity: dict[str, list] = field(default_factory=dict)
    variants_of: dict[str, list[str]] = field(default_factory=dict)
    product_of_variant: dict[str, str] = field(default_factory=dict)
    listings_of: dict[str, list[str]] = field(default_factory=dict)
    listings_by_channel: dict[str, list[str]] = field(default_factory=dict)
    assets_by_listing: dict[str, list[str]] = field(default_factory=dict)
    # "VAR-01B:specs.power_w" -> the assets that quote it. This index is the
    # propagation engine: correcting an attribute marks everything here stale
    # with no model involved in deciding what is affected.
    assets_derived_from: dict[str, list[str]] = field(default_factory=dict)
    rules_by_channel: dict[str, list[ChannelRule]] = field(default_factory=dict)
    docs_by_supplier: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for variant in self.catalog.variants:
            self.variants_of.setdefault(variant.product_id, []).append(variant.id)
            self.product_of_variant[variant.id] = variant.product_id

        for listing in self.catalog.listings:
            self.listings_of.setdefault(listing.variant_id, []).append(listing.id)
            self.listings_by_channel.setdefault(listing.channel_id, []).append(listing.id)

        for asset_id in sorted(self.assets):
            asset = self.assets[asset_id]
            self.assets_by_listing.setdefault(asset.listing_id, []).append(asset.id)
            for ref in asset.derived_from:
                self.assets_derived_from.setdefault(ref, []).append(asset.id)

        for rule in self.rules:
            self.rules_by_channel.setdefault(rule.channel_id, []).append(rule)

        for doc in self.source_docs.values():
            self.docs_by_supplier.setdefault(doc.supplier, []).append(doc.id)

        # Sorted everywhere. Blast-radius counts and trace hashes are built by
        # walking these lists, so their order is part of the answer.
        for index in (self.variants_of, self.listings_of, self.listings_by_channel,
                      self.assets_by_listing, self.assets_derived_from,
                      self.docs_by_supplier):
            for key in index:
                index[key].sort()
        for rules in self.rules_by_channel.values():
            rules.sort(key=lambda r: r.id)

    # --- convenience -------------------------------------------------------

    @property
    def horizon_start(self) -> date:
        return self.catalog.horizon_start

    @property
    def horizon_days(self) -> int:
        return self.catalog.horizon_days

    def days(self) -> list[date]:
        return [self.horizon_start + timedelta(days=i) for i in range(self.horizon_days)]

    def attrs_for(self, entity_id: str) -> dict[str, object]:
        return {path: value for (eid, path), value in sorted(self.attr_values.items())
                if eid == entity_id}

    def applicable_attrs(self, variant_id: str) -> list[AttributeDef]:
        """The attributes this variant's category is expected to carry.

        An empty ``applies_to`` means every category - GTIN and claims apply to
        a snack bar and an air purifier alike.
        """
        category = self.products[self.product_of_variant[variant_id]].category
        return [self.attr_defs[path] for path in sorted(self.attr_defs)
                if not self.attr_defs[path].applies_to
                or any(category.startswith(p) for p in self.attr_defs[path].applies_to)]

    def channel_field(self, channel_id: str, path: str) -> str:
        """What this channel calls an internal attribute.

        Falls back to the internal path: a channel that speaks the internal
        taxonomy has no mapping to look up, and the identity is the answer
        rather than a missing one.
        """
        channel = self.channels.get(channel_id)
        return channel.attribute_map.get(path, path) if channel else path

    def variants_in_scope(self, scope) -> list[str]:
        """Which variants one reading of a correction actually touches.

        Comparing these lists is how the validator prices precision: a scope
        that reaches two variants when the evidence supports one republishes a
        number on a page it does not belong on.
        """
        products: set[str] = set()
        named: list[str] = []
        for entity_id in scope.entities:
            if entity_id in self.variants:
                named.append(entity_id)
                products.add(self.product_of_variant[entity_id])
            elif entity_id in self.products:
                products.add(entity_id)

        family = sorted(v for p in products for v in self.variants_of.get(p, []))
        if scope.level is ScopeLevel.BASE:
            return [v for v in family if self.variants[v].is_base]
        if scope.level is ScopeLevel.ALL:
            return family
        # VARIANT named a product rather than a variant: widen to that product's
        # variants rather than returning nothing. A silently empty scope reads
        # as "nothing is affected", which is the one answer that is never right.
        return sorted(named) or family


def precedence(base: Baseline, doc_id: str) -> int:
    """How much authority a document carries, per POL-002.

    Lives here rather than beside either caller because both halves of the
    provenance split enforce it - ``sc.replay.ingest`` on structured feeds and
    ``sc.graph.nodes`` on what a model reads out of prose - and two copies of a
    policy are two policies as soon as one of them is edited. A document the
    seed pack does not know ranks below every document it does, so an
    unattributed value never displaces an attributed one.
    """
    doc = base.source_docs.get(doc_id)
    return doc.precedence if doc else 0


def load(directory: Path | None = None) -> Baseline:
    d = directory or data_dir()
    raw = json.loads((d / "catalog.json").read_text(encoding="utf-8"))
    catalog = Catalog.model_validate(raw)

    attr_values: dict[tuple[str, str], object] = {}
    attr_sources: dict[tuple[str, str], SourceRef] = {}
    for row in _jsonl(d / "attributes.jsonl"):
        key = (row["entity_id"], row["path"])
        attr_values[key] = row["value"]
        attr_sources[key] = SourceRef(doc_id=row["source_doc"],
                                      version=row["source_version"])

    assets = {r["id"]: ContentAsset.model_validate(r)
              for r in _jsonl(d / "content_assets.jsonl")}
    source_docs = {r["id"]: SourceDoc.model_validate(r)
                   for r in _jsonl(d / "source_docs.jsonl")}

    return Baseline(
        catalog=catalog,
        products={p.id: p for p in catalog.products},
        variants={v.id: v for v in catalog.variants},
        media_by_entity=_media_by_entity(catalog),
        channels={c.id: c for c in catalog.channels},
        listings={l.id: l for l in catalog.listings},
        assets=assets,
        attr_defs={a.path: a for a in catalog.attributes},
        rules=list(catalog.rules),
        source_docs=source_docs,
        attr_values=attr_values,
        attr_sources=attr_sources,
        inject=raw.get("inject", {}),
    )


def _media_by_entity(catalog) -> dict[str, list]:
    grouped: dict[str, list] = {v.id: [] for v in catalog.variants}
    for asset in catalog.media:
        grouped.setdefault(asset.entity_id, []).append(asset)
    for assets in grouped.values():
        # Sorted by role so a reader and a test see the same order twice.
        assets.sort(key=lambda a: (str(a.role), a.id))
    return grouped


@lru_cache(maxsize=1)
def get() -> Baseline:
    """Process-wide cached baseline. Call ``get.cache_clear()`` after a reseed."""
    return load()
