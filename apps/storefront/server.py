"""Storefront - the downstream application a shopper would see.

Three sales channels render here: the retailer's own product page and the two
marketplaces. Each one asks its own publication server what it is currently
showing, and that server is the only thing this process can reach.

Which is the point. When a correction lands, this page is where the old value
is still wrong; when it is redacted, this page is where the wrong claim stops
being on sale and a notice appears instead. Neither of those is legible in a
table of listing identifiers, and both are obvious here.

Run it with ``python -m apps.storefront.server``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI

from apps import _env, _serve
from apps._mcp import Client

WEB = Path(__file__).resolve().parent / "web"
NAME = "storefront"
TITLE = "Storefront"

#: The shopper-facing channels, in the order a merchandiser thinks about them.
#: Held here rather than discovered because this application is *these three
#: channels* - the print catalogue and the shelf labels are somebody else's
#: screen, and putting them behind a tab here would make this a console rather
#: than a shop.
CHANNELS = {
    "ch-web": {"title": "Our website", "kind": "Own storefront"},
    "ch-mkt-a": {"title": "Marketplace A", "kind": "Marketplace listing"},
    "ch-mkt-b": {"title": "Marketplace B", "kind": "Marketplace listing"},
}

#: How many lines the front page shows. A storefront does not enumerate a
#: catalog of a hundred and fifty products to make its point; it shows the
#: shelf the demonstration is about, and lets anything else be reached by SKU.
#:
#: *Which* lines is asked of the channel rather than written down here. It used
#: to be a list of four SKUs, and when the assortment was rebranded all four
#: stopped existing - so every channel showed an empty shelf, and the page said
#: "this channel is not carrying any of these lines", which was true and
#: useless. A downstream application should not hold a copy of the catalog.
SHELF_SIZE = 6

client = Client(_env.platform_url())
bus = _serve.Broadcaster()
app: FastAPI = _serve.build(NAME, TITLE, WEB, client, bus)

_cursors: dict[str, int] = {}


def _path(channel: str) -> str:
    return f"/mcp/publish/{channel}/"


async def _call(channel: str, tool: str, arguments: dict) -> dict:
    if channel not in CHANNELS:
        return {"error": f"this shop does not have a {channel!r} channel"}
    try:
        return await client.call(channel, _path(channel), tool, arguments)
    except Exception as exc:  # noqa: BLE001 - an unreachable channel is news
        return {"error": f"{channel} did not answer: {exc}"[:300],
                "unreachable": True}


@app.get("/shop-api/channels")
async def channels() -> dict:
    return {"channels": [{"id": k, **v} for k, v in CHANNELS.items()],
            "shelf_size": SHELF_SIZE, "platform": client.base_url}


@app.get("/shop-api/{channel}/product/{sku}")
async def product(channel: str, sku: str) -> dict:
    """The page, exactly as this channel is currently serving it."""
    return await _call(channel, "current_listing", {"sku": sku})


@app.get("/shop-api/{channel}/shelf")
async def shelf(channel: str, limit: int = SHELF_SIZE) -> dict:
    """The front page: what this channel is actually carrying.

    Two calls rather than one because they answer different questions. The
    channel says which lines it has; ``current_listing`` says what each of them
    is showing *right now*, redactions included - and the second is the whole
    reason this shop exists, so it is not something to skip for a round trip.
    """
    carried = await _call(channel, "shelf", {"limit": limit})
    if not isinstance(carried, dict) or carried.get("error"):
        # A platform older than this tool answers with text rather than a
        # record, so the shape is checked before it is read. Saying which
        # channel and what came back beats a five hundred: the commonest cause
        # is a platform that has not been restarted, and that is a sentence
        # somebody can act on.
        detail = (carried.get("error") if isinstance(carried, dict)
                  else str(carried or "")[:200])
        return {"channel": channel, "products": [], "carrying": 0,
                "error": detail or f"{channel} did not say what it carries"}

    found = []
    for row in carried.get("skus", []):
        listing = await _call(channel, "current_listing", {"sku": row["sku"]})
        if isinstance(listing, dict) and listing.get("found"):
            found.append(listing)
    return {"channel": channel, "products": found,
            "carrying": carried.get("total", len(found))}


@app.get("/shop-api/{channel}/log")
async def log(channel: str, limit: int = 30) -> dict:
    """What this channel has been told. A shop would not show this; the demo
    needs somewhere to see that the page changed because of a decision, and
    not because somebody edited a file."""
    return {"channel": channel,
            "entries": await _call(channel, "delivery_log", {"limit": limit})}


async def _tick() -> bool:
    """Ask each channel what has happened since we last asked.

    One poller for the whole application rather than one per open tab: three
    channels at a poll a second is three calls, and three tabs of a per-tab
    poller would be nine - which would flush the platform's own protocol log,
    the thing somebody is most likely to be looking at while this runs.
    """
    moved = False
    for channel in CHANNELS:
        result = await _call(channel, "changes_since",
                             {"cursor": _cursors.get(channel, 0), "limit": 40})
        if not isinstance(result, dict) or result.get("error"):
            continue
        changes = result.get("changes") or []
        _cursors[channel] = result.get("cursor", 0)
        if changes:
            moved = True
            bus.publish("changed", {"channel": channel, "changes": changes})
    return moved


@app.on_event("startup")
async def _startup() -> None:
    # Start from where the ledger already is, so opening the shop does not
    # replay every correction the estate has ever taken as breaking news.
    for channel in CHANNELS:
        result = await _call(channel, "changes_since", {"cursor": 0,
                                                        "limit": 1000})
        if isinstance(result, dict):
            _cursors[channel] = result.get("cursor", 0)
    app.state.poller = asyncio.create_task(_serve.poll_forever(bus, _tick))


@app.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(app.state, "poller", None)
    if task is not None:
        task.cancel()
    await client.close()


def main() -> None:
    port = _env.port("STOREFRONT_PORT", 8120)
    _serve.run(app, port, banner=(
        f"\n  {TITLE}\n"
        f"  {'-' * len(TITLE)}\n"
        f"  http://127.0.0.1:{port}\n"
        f"  three sales channels, read over MCP from {client.base_url}\n"))


if __name__ == "__main__":
    main()
