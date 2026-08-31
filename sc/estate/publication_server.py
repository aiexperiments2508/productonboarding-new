"""Each publication system, as its own MCP endpoint.

The ingest estate is ten servers because ten systems send data. The publication
estate is six because six channels own listings, and the same argument applies:
one server with a channel argument is one system with a protocol bolted on.

What is different here, and it is the whole reason this file is separate from
`server.py`, is that these systems **change what a shopper sees**. So the
partition matters more rather than less.

**The safeguards travel with the tool, not with the caller.** The three refusals
- a recorded approval, evidence that has not moved, no open safety violation -
are enforced at the planning boundary, and every path through here goes through
it. Reaching `publish` over a pipe does not exempt it, and there is deliberately
no code here that could publish on its own: the tool asks `remediation`, which
asks `tools.planning`, which refuses on its own terms.

**Reading is separate from writing, per system.** `impact` and `plan` answer
what a correction reaches and what would happen, and neither writes. An operator
who wants to show somebody the blast radius does not have to hand over the
ability to act on it.

The freeze rule is applied here as well as in the report, because a tool that
would attempt a print run inside its window is a tool that should not exist -
not one whose caller is expected to check first.
"""

from __future__ import annotations

from typing import Any

from sc.estate import publication
from sc.estate.redaction import NOTICE

#: What a publication system exposes.
#:
#: It began as two reads and one write. The reads grew because the downstream
#: applications are built on this surface and nothing else - a storefront that
#: had to ask the platform's REST API what it was showing would not be a
#: separate system, it would be another view of this one. The writes grew
#: because taking a wrong value *down* is a different act from replacing it,
#: needs a different authority, and happens at a different moment.
#:
#: Reading is still separate from writing, per system. An operator who wants to
#: show somebody what a channel is carrying does not have to hand over the
#: ability to change it.
TOOLS: tuple[str, ...] = (
    # reads
    "describe_channel", "impact", "shelf", "current_listing", "delivery_log",
    "pending_corrections", "changes_since",
    # writes - every one of them goes through the planning boundary
    "publish_correction", "redact_field", "withdraw_listing",
    "restore_listing", "discharge_obligation",
)

#: Which of them can change what a shopper sees. Declared rather than inferred
#: from a name, because that is the question an operator handing out an
#: endpoint actually asks.
MUTATING: tuple[str, ...] = ("publish_correction", "redact_field",
                             "withdraw_listing", "restore_listing",
                             "discharge_obligation")

#: The servers, held so their session managers can be started with the
#: application - mounting a Starlette sub-app does not run its lifespan.
_SERVERS: list[Any] = []


def _describe(system) -> dict:
    return {
        "id": system.id,
        "channel_id": system.channel_id,
        "title": system.title,
        "owner": system.owner,
        # The two facts that decide how a correction reaching this channel is
        # handled, said plainly rather than left for a caller to infer from a
        # number of days.
        "recallable": system.recallable,
        "freeze_days": system.freeze_days,
        "note": ("what this channel publishes cannot be recalled"
                 if not system.recallable
                 else "published content can be replaced in place"),
    }


def _impact(system, entity_id: str) -> dict:
    """What a correction to this entity would mean *for this channel*.

    Scoped to the asking system. A marketplace connector has no business
    enumerating what the print channel is about to publish, and an estate where
    every publisher can read every other's queue is one database with six front
    doors.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    mine = [group for group in publication.blast_to_systems(trace, base)
            if group["system"] == system.id]
    if not mine:
        return {"channel_id": system.channel_id, "affected": False,
                "skus": [], "listings": []}
    group = mine[0]
    return {
        "channel_id": system.channel_id,
        "affected": True,
        "skus": group["skus"],
        "listings": group["listings"],
        "recallable": system.recallable,
    }


def _publish(system, incident_id: str, scenario_id: str,
             entity_id: str) -> dict:
    """Push an approved correction to this channel.

    Every gate is somewhere else and every one of them still binds. This
    function cannot publish; it asks the thing that can, and that thing refuses
    without a recorded approval whichever server it was reached through.

    A channel whose artefact cannot be recalled, inside its window, is refused
    here rather than attempted - a tool that would start a print run it cannot
    stop should not exist, rather than existing and expecting its caller to
    check first.
    """
    from sc.estate import remediation
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    if not system.recallable and system.freeze_days:
        return {
            "channel_id": system.channel_id,
            "sent": False,
            "reason": (f"{system.channel_id} is inside a "
                       f"{system.freeze_days}-day freeze window and what it "
                       f"publishes cannot be recalled"),
        }

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    result = remediation.dispatch(incident_id, scenario_id, trace, base)
    mine = [row for row in result["systems"] if row["system"] == system.id]
    return {
        "channel_id": system.channel_id,
        "sent": bool(result["committed"]) and bool(
            mine and mine[0]["outcome"] == remediation.SENT),
        "reason": (mine[0]["reason"] if mine else "")
                  or ("" if result["committed"] else result.get("reason", "")),
        "committed": result["committed"],
    }


def _listings_of(system) -> list[str]:
    """Every listing this channel owns. The scope of every read below."""
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    return sorted(base.listings_by_channel.get(system.channel_id, []))


def _listing_for(system, sku: str) -> str | None:
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    wanted = (sku or "").strip().upper()
    for listing_id in _listings_of(system):
        listing = base.listings[listing_id]
        variant = base.variants.get(listing.variant_id)
        if variant is not None and (variant.sku or "").upper() == wanted:
            return listing_id
    return None


def _shelf(system, limit: int) -> dict:
    """The SKUs this channel is carrying, newest listing first.

    Scoped to the asking system, like ``impact`` and for the same reason. That
    is what makes this safe to add beside a ``current_listing`` that
    deliberately will not confirm a SKU it does not carry: refusing to say
    whether *another* channel has a line is a boundary, and refusing to tell a
    channel what is on its own shelf is not - it published it.

    A downstream application needs this or it needs a list of SKUs written down
    somewhere, and a list written down is a list that is wrong the first time a
    product is renamed. Ours was: the storefront's front page named four SKUs
    that stopped existing when the assortment was rebranded, so the shop showed
    an empty shelf on every channel and nothing anywhere said why.
    """
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    # The catalog's own order, which is the order the retailer's lines were
    # authored in - so the products the assortment leads with come first and a
    # shop showing six of them shows the six worth showing. Sorting by SKU
    # would order the shelf by brand prefix, which is alphabetical rather than
    # meaningful.
    rank = {product_id: index
            for index, product_id in enumerate(base.products)}
    skus: list[dict] = []
    for listing_id in _listings_of(system):
        listing = base.listings.get(listing_id)
        if listing is None:
            continue
        variant = base.variants.get(listing.variant_id)
        if variant is None or not variant.sku:
            continue
        product = base.products.get(variant.product_id)
        skus.append({
            "sku": variant.sku,
            "variant_id": variant.id,
            "name": getattr(product, "name", variant.name),
            "category": getattr(product, "category", ""),
        })
    skus.sort(key=lambda row: (rank.get(
        base.variants[row["variant_id"]].product_id, len(rank)),
        row["sku"]))
    return {"channel_id": system.channel_id, "total": len(skus),
            "skus": skus[:max(0, limit)]}


def _current_listing(system, sku: str) -> dict:
    """What this channel is showing right now, redactions included.

    Built from the listing state the rest of the system already derives rather
    than from a second rendering pass - the storefront and the blast radius
    have to agree about what is on the page, and two renderers would disagree
    the first time either was edited.

    An unknown SKU comes back ``found: false`` in the same shape ``impact``
    uses, which is what stops a marketplace discovering, by exhaustive
    guessing, which SKUs the print channel carries.
    """
    from sc.tools import network as network_tools
    from sc.tools import planning

    listing_id = _listing_for(system, sku)
    if listing_id is None:
        return {"channel_id": system.channel_id, "sku": sku, "found": False,
                "reason": f"{system.channel_id} carries no listing for {sku!r}"}

    state = network_tools.get_listing_state(listing_id)
    if state.get("error"):
        return {"channel_id": system.channel_id, "sku": sku, "found": False,
                "reason": state["error"]}

    hidden = {row["attribute_path"]: row
              for row in planning.open_redactions([listing_id])}

    fields = {}
    for path, cell in (state.get("values") or {}).items():
        redacted = hidden.get(path)
        fields[path] = {
            "value": None if redacted else (cell or {}).get("value"),
            "unit": (cell or {}).get("unit"),
            "doc": (cell or {}).get("doc"),
            "redacted": bool(redacted),
            "placeholder": (redacted or {}).get("placeholder", ""),
            "notice": (redacted or {}).get("notice", ""),
            "since": (redacted or {}).get("since", ""),
        }

    # Copy quotes values. A redaction that hid the allergen *field* and left
    # the bullet saying "may contain milk" two inches above it would have
    # withheld nothing that matters - and the page would be more misleading
    # than before, because it would now look as though somebody had checked.
    #
    # Which copy quotes which value is not a guess: every asset carries the
    # attribute references it was built from, and that lineage is what the
    # blast radius has always been computed from. The same lineage answers this.
    hidden_refs = {f"{state['variant']['id']}:{path}" for path in hidden}
    copy = []
    for asset in state["assets"]:
        quotes = sorted(set(asset["derived_from"]) & hidden_refs)
        copy.append({
            "field": asset["field"],
            "text": "" if quotes else asset["text"],
            "redacted": bool(quotes),
            "quotes": [ref.split(":", 1)[1] for ref in quotes],
            "notice": NOTICE if quotes else "",
            "stale": asset["stale"],
            "stale_refs": asset["stale_refs"],
        })

    withheld = state["status"] == "WITHHELD"
    return {
        "channel_id": system.channel_id,
        "sku": sku,
        "found": True,
        "listing_id": listing_id,
        "status": state["status"],
        "withheld": withheld,
        "published_version": state["published_version"],
        "product": state["product"],
        "variant": state["variant"],
        "recallable": system.recallable,
        "fields": fields,
        "redacted_fields": sorted(hidden),
        "copy": copy,
        "media": _media_for(state["variant"]["id"]),
        "as_of": state["as_of"],
        "notice": next((r["notice"] for r in hidden.values() if r.get("notice")),
                       ""),
    }


def _media_for(variant_id: str) -> list[dict]:
    """The imagery a shopper would see, seeded plus whatever has arrived."""
    from sc.readiness import record as record_mod

    record = record_mod.build(variant_id)
    if record is None:
        return []
    return [{"role": str(a.role), "uri": a.uri, "alt_text": a.alt_text}
            for a in record.media]


#: Ledger verbs that describe something happening to a listing. Anything else
#: in the audit table is about an incident or a document and is not this
#: channel's business.
_DELIVERY_ACTIONS = ("COMMIT", "REDACT", "RESTORE", "ERRATUM_OPEN",
                     "ERRATUM_DISCHARGE", "REPRINT_QUEUE", "REPRINT_CONFIRM",
                     "ROLLBACK")


def _delivery_log(system, limit: int = 50, after: int = 0) -> list[dict]:
    """What this channel has been told, newest first.

    Read from the append-only ledger rather than from a log of its own. Two
    accounts of what a channel was told is one account too many, and the
    ledger is already the one that cannot be edited.
    """
    from sc import db

    listings = _listings_of(system)
    if not listings:
        return []
    placeholders = ",".join("?" * len(listings))
    rows = db.query(
        f"SELECT rowid AS seq, ts, actor, action, entity_id, detail, provenance"
        f"  FROM audit WHERE entity_type = 'listing'"
        f"   AND entity_id IN ({placeholders}) AND rowid > ?"
        f" ORDER BY rowid DESC LIMIT ?",
        (*listings, after, limit))
    return [{
        "seq": r["seq"], "ts": r["ts"], "actor": r["actor"],
        "verb": r["action"], "listing_id": r["entity_id"],
        "detail": db.loads(r["detail"]),
        "approval_ref": (db.loads(r["provenance"]) or {}).get("source_id", ""),
    } for r in rows]


def _pending(system) -> dict:
    """What is approved and queued for this channel, deferrals included.

    The only place a frozen print channel can say, honestly, that there is a
    correction it is not going to take.
    """
    from sc.estate import redaction
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    obligations = redaction.open_obligations(system.id)
    return {
        "channel_id": system.channel_id,
        "recallable": system.recallable,
        "freeze_days": system.freeze_days,
        "frozen": bool(not system.recallable and system.freeze_days),
        "obligations": obligations,
        "withheld": [row["listing_id"] for row in
                     _withheld_listings(system, base)],
    }


def _withheld_listings(system, base) -> list[dict]:
    from sc.tools import planning

    return planning.open_redactions(_listings_of(system))


def _changes_since(system, cursor: int = 0, limit: int = 100) -> dict:
    """Everything that has happened to this channel since a cursor.

    The cursor is the ledger's own rowid. The ledger is append-only and never
    deleted, so the rowid is monotonic and needs no column of its own - and it
    is deliberately not a timestamp: ``audit.ts`` is wall clock while every
    fact runs on the simulated clock, and a cursor spanning both would be a
    generator of bugs nobody could reproduce.
    """
    changes = _delivery_log(system, limit=limit, after=cursor)
    highest = max([c["seq"] for c in changes] + [cursor])
    return {"channel_id": system.channel_id, "cursor": highest,
            "changes": list(reversed(changes))}


# ---------------------------------------------------------------------------
# Writes. None of these contains code that could act; each asks the thing that
# can, and that thing refuses on its own terms.
# ---------------------------------------------------------------------------


def _redact_field(system, sku: str, attribute_path: str, reason: str,
                  incident_id: str, actor: str) -> dict:
    from sc.estate import redaction
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    listing_id = _listing_for(system, sku)
    if listing_id is None:
        return {"channel_id": system.channel_id, "redacted": False,
                "reason": f"{system.channel_id} carries no listing for {sku!r}"}

    base = baseline_mod.get()
    entity_id = base.listings[listing_id].variant_id
    result = redaction.redact(
        incident_id, entity_id, [attribute_path], actor=actor, reason=reason,
        trace=network_tools.trace_dependencies(entity_id), base=base,
        only_system=system.id)

    mine = next((r for r in result["systems"] if r["channel_id"]
                 == system.channel_id), None)
    if mine is None:
        return {"channel_id": system.channel_id, "redacted": False,
                "reason": f"{attribute_path} does not reach {system.channel_id}"}
    return {
        "channel_id": system.channel_id, "sku": sku, "listing_id": listing_id,
        # An erratum is never reported as a redaction. Nothing came down.
        "redacted": bool(mine.get("redacted")),
        "kind": mine["kind"], "outcome": mine["outcome"],
        "reason": mine["reason"],
        "obligation_id": mine.get("obligation_id", ""),
        "authorised": result["authorised"],
    }


def _restore_field(system, sku: str, attribute_path: str, incident_id: str,
                   actor: str) -> dict:
    from sc.estate import redaction
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools

    listing_id = _listing_for(system, sku)
    if listing_id is None:
        return {"channel_id": system.channel_id, "restored": False,
                "reason": f"{system.channel_id} carries no listing for {sku!r}"}

    base = baseline_mod.get()
    entity_id = base.listings[listing_id].variant_id
    result = redaction.restore(
        incident_id, entity_id, [attribute_path], actor=actor,
        trace=network_tools.trace_dependencies(entity_id), base=base,
        only_system=system.id)
    mine = next((r for r in result["systems"] if r["channel_id"]
                 == system.channel_id), None)
    return {"channel_id": system.channel_id, "sku": sku,
            "restored": bool(mine and mine.get("restored")),
            "reason": (mine or {}).get("reason", "")}


def build(system) -> Any:
    """One publication system's MCP server."""
    from mcp.server.fastmcp import FastMCP

    # Served at the root of its own app, for the same reason the ingest servers
    # are: mounted at a path, FastMCP's default sub-path would put the endpoint
    # somewhere the connection record does not name.
    mcp = FastMCP(system.id, streamable_http_path="/")

    @mcp.tool()
    def describe_channel() -> dict:
        """What this channel is, and whether what it publishes can be recalled."""
        return _describe(system)

    @mcp.tool()
    def impact(entity_id: str) -> dict:
        """Which SKUs on this channel a correction to an entity would reach."""
        return _impact(system, entity_id)

    @mcp.tool()
    def publish_correction(incident_id: str, scenario_id: str,
                           entity_id: str) -> dict:
        """Push an approved correction to this channel.

        Refuses without a recorded approval, without unmoved evidence, and with
        an open safety violation - none of which is checked here, and all of
        which still bind.
        """
        return _publish(system, incident_id, scenario_id, entity_id)

    @mcp.tool()
    def shelf(limit: int = 24) -> dict:
        """The SKUs this channel is carrying. Its own shelf, nothing else."""
        return _shelf(system, limit)

    @mcp.tool()
    def current_listing(sku: str) -> dict:
        """What this channel is showing for a SKU right now.

        Redactions appear as redactions rather than as the old value: a page
        that rendered a suppressed allergen line would defeat the point of
        suppressing it.
        """
        return _current_listing(system, sku)

    @mcp.tool()
    def delivery_log(limit: int = 50) -> list[dict]:
        """What this channel has been told, newest first, with who and why."""
        return _delivery_log(system, limit)

    @mcp.tool()
    def pending_corrections() -> dict:
        """What is queued for this channel, including what it will not take."""
        return _pending(system)

    @mcp.tool()
    def changes_since(cursor: int = 0, limit: int = 100) -> dict:
        """Everything since a cursor, for a client that wants to keep up."""
        return _changes_since(system, cursor, limit)

    @mcp.tool()
    def redact_field(sku: str, attribute_path: str, reason: str,
                     incident_id: str, actor: str = "operator") -> dict:
        """Take a wrong value down on this channel.

        Needs a recorded approval on the incident, which is checked at the
        planning boundary and not here. A channel whose artefact cannot be
        recalled is never reported as redacted: it opens an erratum instead,
        because saying a printed run was redacted would be false.
        """
        return _redact_field(system, sku, attribute_path, reason, incident_id,
                             actor)

    @mcp.tool()
    def withdraw_listing(sku: str, attribute_path: str, reason: str,
                         incident_id: str, actor: str = "operator") -> dict:
        """Take the whole listing off air over a wrong field.

        The same authority and the same refusals as ``redact_field`` - this is
        the shape that redaction takes when the field is one the channel
        declares it cannot publish without.
        """
        return _redact_field(system, sku, attribute_path, reason, incident_id,
                             actor)

    @mcp.tool()
    def restore_listing(sku: str, attribute_path: str, incident_id: str,
                        actor: str = "operator") -> dict:
        """Put back what a redaction hid. Refuses where nothing was hidden."""
        return _restore_field(system, sku, attribute_path, incident_id, actor)

    @mcp.tool()
    def discharge_obligation(obligation_id: str, evidence: str = "",
                             actor: str = "operator") -> dict:
        """Mark this channel's erratum published or its reprint confirmed."""
        from sc.estate import redaction

        return redaction.discharge(obligation_id, actor=actor,
                                   evidence=evidence, system_id=system.id)

    return mcp


async def start(stack) -> int:
    """Run every mounted publisher's session manager for the life of the app."""
    started = 0
    for server in _SERVERS:
        await stack.enter_async_context(server.session_manager.run())
        started += 1
    return started


def mount(app) -> list[dict]:
    """Publish every publication system onto a FastAPI app.

    The trailing slash is load-bearing: Starlette's Mount strips the prefix, so
    a sub-app whose only route is "/" answers 405 without it.
    """
    from sc.state import baseline as baseline_mod

    mounted: list[dict] = []
    try:
        systems = publication.systems(baseline_mod.get())
    except Exception as exc:  # noqa: BLE001 - no catalog, no publishers
        return [{"error": str(exc)[:200]}]

    for system in systems:
        path = f"/mcp/publish/{system.channel_id.lower()}"
        try:
            server = build(system)
            app.mount(path, server.streamable_http_app())
            _SERVERS.append(server)
        except Exception as exc:  # noqa: BLE001 - one channel is not the estate
            mounted.append({"id": system.id, "url": path,
                            "error": str(exc)[:200]})
            continue
        mounted.append({
            "id": system.id,
            "channel_id": system.channel_id,
            "title": system.title,
            "url": f"{path}/",
            "transport": "http",
            "tools": list(TOOLS),
            # Named here so an operator can see, from the listing alone, which
            # of these servers can change what a shopper sees.
            "mutating": list(MUTATING),
        })
    return mounted
