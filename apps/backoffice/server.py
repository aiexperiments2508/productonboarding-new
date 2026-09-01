"""Back Office - the four reference systems, read over MCP.

The vendor portal is where data comes *in* and the storefront and ops console
are where it goes *out*. This is neither. It is the systems a retailer runs
that have opinions about a product without ever asserting anything about it: a
warehouse knows where a thing is, a trading system knows what it sold for, a
campaign manager knows who it was shown to, a certificate register knows what
paper it stands on.

None of that is launch readiness, and none of it reaches the fact store. It is
the other half of what a merchant needs to know, and until now the platform had
nowhere to show it.

**It reads and it never writes.** All four systems declare ``accepts=()`` in the
manifest, so there is no intake endpoint to address even if this console wanted
one. Every screen here is the same two calls - ``recent_deliveries`` to list
what arrived, ``fetch_payload`` to open one - which is deliberate: it makes the
protocol legible instead of hiding it behind a bespoke endpoint per screen.
That is the same argument ``apps/ops`` makes by using three tools and no more.

Run it with ``python -m apps.backoffice.server``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI

from apps import _env, _serve
from apps._mcp import Client

WEB = Path(__file__).resolve().parent / "web"
NAME = "back-office"
TITLE = "Back Office"

#: The four systems and the tab each one fills. Held here rather than
#: discovered for the reason the vendor portal gives for the same thing: a
#: console whose first screen depends on a reachable platform shows a spinner
#: when the platform is down, instead of saying the platform is down.
SYSTEMS = {
    "wms-inventory": {
        "title": "Warehouse Management", "tab": "stock",
        "blurb": "Six depots, and what is on a pallet in each of them.",
    },
    "trading-epos": {
        "title": "Trading and EPOS", "tab": "trading",
        "blurb": "What each market charged, and what it actually sold.",
    },
    "campaign-manager": {
        "title": "Campaign Management", "tab": "campaigns",
        "blurb": "Campaigns, their mechanics, and who they are aimed at.",
    },
    "cert-registry": {
        "title": "Certification Registry", "tab": "compliance",
        "blurb": "Certificates, the rules they satisfy, the markets that "
                 "enforce them.",
    },
}

client = Client(_env.platform_url())
bus = _serve.Broadcaster()
app: FastAPI = _serve.build(NAME, TITLE, WEB, client, bus)

#: The newest event id seen per system, so the poller can tell "nothing new"
#: from "nothing at all".
_seen: dict[str, str] = {}


def _path(system_id: str) -> str:
    """The read-only estate endpoint.

    Not ``/mcp/intake/``. These four accept nothing, so there is no intake
    surface to address - which is a property of the manifest rather than a
    decision taken here.
    """
    return f"/mcp/{system_id}/"


async def _call(system_id: str, tool: str, arguments: dict):
    """One tool call, with an unreachable platform as a result rather than a raise.

    A console that 500s because the platform is restarting is a console that
    cannot report the one thing it is for.
    """
    if system_id not in SYSTEMS:
        return {"error": f"unknown system {system_id!r}"}
    try:
        return await client.call(system_id, _path(system_id), tool, arguments)
    except Exception as exc:  # noqa: BLE001 - an unreachable platform is news
        return {"error": f"the platform did not answer: {exc}"[:300],
                "unreachable": True}


@app.get("/back-api/systems")
async def systems() -> dict:
    """The tab strip. Answered locally, so the page renders before any dialling.

    Deliberately not a tool call. The four systems are what this console *is*;
    making the shell wait on a network round trip would mean a platform outage
    looked like a broken application.
    """
    return {
        "systems": [{"id": system_id, **spec}
                    for system_id, spec in SYSTEMS.items()],
        "platform": client.base_url,
    }


@app.get("/back-api/{system_id}")
async def describe(system_id: str) -> dict:
    """What a system says about itself, in its own words.

    Includes its declared defects and rate, which for these four is none - and
    a system that says how it misbehaves is more useful than one that claims it
    does not.
    """
    return {"system": system_id, "described": await _call(
        system_id, "describe_system", {})}


@app.get("/back-api/{system_id}/deliveries")
async def deliveries(system_id: str, limit: int = 60) -> dict:
    """What this system has delivered, newest first."""
    rows = await _call(system_id, "recent_deliveries", {"limit": limit})
    if isinstance(rows, dict):          # an error envelope, not a list
        return {"system": system_id, "deliveries": [], **rows}
    return {"system": system_id, "deliveries": rows}


@app.get("/back-api/{system_id}/payload/{event_id}")
async def payload(system_id: str, event_id: str) -> dict:
    """One delivery, opened.

    The estate server refuses a cross-system read, so a console cannot use this
    to browse a neighbour's traffic - and that refusal is the platform's, not
    something this page is trusted to respect.
    """
    return {"system": system_id, "event_id": event_id,
            "payload": await _call(system_id, "fetch_payload",
                                   {"event_id": event_id})}


async def _tick() -> bool:
    """Poll the four systems; publish only when something actually moved.

    Returning False backs the poll off from one second to five, which is what
    keeps a parked demo from costing anything.
    """
    moved = False
    for system_id in SYSTEMS:
        rows = await _call(system_id, "recent_deliveries", {"limit": 5})
        if not isinstance(rows, list) or not rows:
            continue
        newest = rows[0].get("event_id", "")
        if newest and newest != _seen.get(system_id):
            _seen[system_id] = newest
            bus.publish("delivered", {"system": system_id, "rows": rows})
            moved = True
    return moved


@app.on_event("startup")
async def _startup() -> None:
    app.state.poller = asyncio.create_task(_serve.poll_forever(bus, _tick))


@app.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(app.state, "poller", None)
    if task is not None:
        task.cancel()
    await client.close()


def main() -> None:
    port = _env.port("BACKOFFICE_PORT", 8140)
    _serve.run(app, port, banner=(
        f"\n  {TITLE}\n"
        f"  {'-' * len(TITLE)}\n"
        f"  http://127.0.0.1:{port}\n"
        f"  four reference systems, read over MCP from {client.base_url}\n"))


if __name__ == "__main__":
    main()
