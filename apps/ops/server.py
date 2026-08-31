"""Ops Console - the downstream application nobody outside the business sees.

The storefront shows the three channels a shopper reaches. This shows the three
that need somebody to do something: a print run that has already gone to press,
shelf labels that have to be walked to and reprinted, and the search index.

It is also where the work a correction leaves behind is tracked. A redaction on
a web page is finished the moment it is written. A redaction on a printed
catalogue is not a redaction at all - it is an obligation, and an obligation
nobody can close is not an obligation. So this console can discharge them, and
that is deliberately the only kind of writing it does.

**It cannot approve anything.** The two human decisions in this system - that a
value is wrong, and that its replacement may go out - are taken in the
platform's own review surface and nowhere else. This console shows what is
waiting on them and links back. A downstream publisher that could authorise its
own publish is exactly the thing the whole design is arranged to prevent.

Run it with ``python -m apps.ops.server``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Body, FastAPI

from apps import _env, _serve
from apps._mcp import Client

WEB = Path(__file__).resolve().parent / "web"
NAME = "ops-console"
TITLE = "Ops Console"

#: The channels an operations team owns. The two marketplaces and the website
#: are the storefront's business; these three are the ones where a correction
#: turns into somebody's afternoon.
CHANNELS = {
    "ch-print": {"title": "Store Catalogue & Print", "kind": "Print",
                 "why": "Cannot be recalled once it has gone to press."},
    "ch-shelf": {"title": "Shelf-Edge Labels", "kind": "Shelf",
                 "why": "Physical labels. Stays wrong in the aisle until reprinted."},
    "ch-search": {"title": "Search Facets", "kind": "Search",
                  "why": "Filters a shopper trusts to exclude things."},
}

#: Every channel, for the estate-wide views. An operator wants to see the whole
#: pipe, even the parts they do not own.
ALL_CHANNELS = ["ch-web", "ch-mkt-a", "ch-mkt-b", "ch-print", "ch-shelf",
                "ch-search"]

client = Client(_env.platform_url())
bus = _serve.Broadcaster()
app: FastAPI = _serve.build(NAME, TITLE, WEB, client, bus)

_cursors: dict[str, int] = {}


def _path(channel: str) -> str:
    return f"/mcp/publish/{channel}/"


async def _call(channel: str, tool: str, arguments: dict) -> dict:
    try:
        return await client.call(channel, _path(channel), tool, arguments)
    except Exception as exc:  # noqa: BLE001 - an unreachable channel is news
        return {"error": f"{channel} did not answer: {exc}"[:300],
                "unreachable": True}


@app.get("/ops-api/channels")
async def channels() -> dict:
    """The estate, as each channel describes itself."""
    out = []
    for channel in ALL_CHANNELS:
        described = await _call(channel, "describe_channel", {})
        mine = CHANNELS.get(channel, {})
        # What the channel says about itself first, then what this console
        # knows. The order matters: the channel calls itself `pub-ch-web`,
        # this console addresses it as `ch-web`, and letting the former win
        # would leave every link on the page pointing at nothing.
        out.append({
            **(described if isinstance(described, dict) else {}),
            "id": channel,
            "system_id": (described or {}).get("id", ""),
            "mine": channel in CHANNELS,
            "title": mine.get("title") or (described or {}).get("title", channel),
            "kind": mine.get("kind", ""),
            "why": mine.get("why", ""),
        })
    return {"channels": out, "platform": client.base_url}


@app.get("/ops-api/queues")
async def queues() -> dict:
    """What is waiting, per channel, including what a channel will not take."""
    out = []
    for channel in ALL_CHANNELS:
        pending = await _call(channel, "pending_corrections", {})
        if isinstance(pending, dict) and not pending.get("error"):
            out.append({"channel": channel, **pending})
    return {"queues": out}


@app.get("/ops-api/log")
async def log(channel: str = "", limit: int = 60) -> dict:
    """The ledger, per channel or across the estate."""
    wanted = [channel] if channel else ALL_CHANNELS
    entries = []
    for one in wanted:
        rows = await _call(one, "delivery_log", {"limit": limit})
        if isinstance(rows, list):
            entries += [{**row, "channel": one} for row in rows]
    entries.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return {"entries": entries[:limit]}


@app.get("/ops-api/{channel}/listing/{sku}")
async def listing(channel: str, sku: str) -> dict:
    """What one channel is carrying for one SKU, redactions included."""
    return await _call(channel, "current_listing", {"sku": sku})


@app.post("/ops-api/discharge")
async def discharge(body: dict = Body(...)) -> dict:
    """Mark an erratum published, or a reprint confirmed.

    The only write this console makes, and it is not an approval. It records
    that work owed to the world has been done - which nobody but the team that
    did it can know.
    """
    result = await _call(body.get("channel", ""), "discharge_obligation", {
        "obligation_id": body.get("obligation_id", ""),
        "evidence": body.get("evidence", ""),
        "actor": body.get("actor") or "ops",
    })
    bus.publish("discharged", {"result": result})
    return result


async def _tick() -> bool:
    moved = False
    for channel in ALL_CHANNELS:
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
    for channel in ALL_CHANNELS:
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
    port = _env.port("OPS_PORT", 8130)
    _serve.run(app, port, banner=(
        f"\n  {TITLE}\n"
        f"  {'-' * len(TITLE)}\n"
        f"  http://127.0.0.1:{port}\n"
        f"  the whole publication estate, read over MCP from {client.base_url}\n"))


if __name__ == "__main__":
    main()
