"""Vendor Portal - the upstream application.

A supplier signs in as one of three systems the retailer runs an intake for,
picks one of its own products, and sends a corrected specification, a document
or an image. Everything it does crosses MCP to ``/mcp/intake/{system}`` on the
platform; this process holds no catalog, no database and no opinion about
whether a submission is any good.

**The supplier identity is held here, server-side.** It is set by signing in
and kept in this process, never read from a request body. That does not make it
authentication - there is no password anywhere in this system and the platform
says so about its own surfaces too - but it does mean a browser cannot claim to
be a supplier it is not, which is a different and achievable property.

Run it with ``python -m apps.vendor.server``.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastapi import Body, FastAPI, Response

from apps import _env, _serve
from apps._mcp import Client

WEB = Path(__file__).resolve().parent / "web"
NAME = "vendor-portal"
TITLE = "Vendor Portal"

#: The three intake endpoints, by the identity a supplier signs in as. Held
#: here rather than discovered so the sign-in page can be rendered before the
#: platform has answered anything - a portal whose first screen depends on a
#: reachable platform is a portal that shows a spinner when the platform is
#: down, rather than a portal that says the platform is down.
SYSTEMS = {
    "supplier-portal": {
        "title": "Supplier Portal",
        "blurb": "Type your own data. Specifications, documents and images.",
    },
    "supplier-pim": {
        "title": "Supplier PIM",
        "blurb": "Master data, machine to machine. Specifications and documents.",
    },
    "gdsn-pool": {
        "title": "GDSN Data Pool",
        "blurb": "Industry data pool. Attribute rows only, in pool vocabulary.",
    },
}

client = Client(_env.platform_url())
bus = _serve.Broadcaster()
app: FastAPI = _serve.build(NAME, TITLE, WEB, client, bus)

#: Submissions this portal is still watching: id -> (system, supplier, what the
#: platform last said). Watched here rather than in the page so that one
#: poller serves however many tabs are open, and so that a supplier who closes
#: the tab and comes back still finds the answer waiting.
_watched: dict[str, dict] = {}

#: How many to keep asking about. A portal that re-polled a fortnight of
#: submissions every second would be a load generator.
WATCH_LIMIT = 12


def _path(system_id: str) -> str:
    return f"/mcp/intake/{system_id}/"


async def _call(system_id: str, tool: str, arguments: dict) -> dict:
    if system_id not in SYSTEMS:
        return {"error": f"unknown system {system_id!r}"}
    try:
        return await client.call(system_id, _path(system_id), tool, arguments)
    except Exception as exc:  # noqa: BLE001 - an unreachable platform is news
        return {"error": f"the platform did not answer: {exc}"[:300],
                "unreachable": True}


@app.get("/portal-api/systems")
async def systems() -> dict:
    """Who you can sign in as. Rendered before anything is dialled."""
    return {"systems": [{"id": k, **v} for k, v in SYSTEMS.items()],
            "platform": client.base_url}


@app.get("/portal-api/intake/{system_id}")
async def intake(system_id: str) -> dict:
    """What this endpoint accepts, said by the endpoint itself."""
    return await _call(system_id, "describe_intake", {})


@app.get("/portal-api/{system_id}/products")
async def products(system_id: str, supplier: str, q: str = "") -> dict:
    return await _call(system_id, "list_my_products",
                       {"supplier": supplier, "q": q, "limit": 50})


@app.get("/portal-api/{system_id}/products/{product_id}")
async def product(system_id: str, product_id: str, supplier: str) -> dict:
    return await _call(system_id, "get_product_spec",
                       {"supplier": supplier, "product_id": product_id})


@app.post("/portal-api/{system_id}/spec")
async def submit_spec(system_id: str, body: dict = Body(...)) -> dict:
    result = await _call(system_id, "submit_specification_change", {
        "supplier": body.get("supplier", ""),
        "entity_id": body.get("entity_id", ""),
        "attribute_path": body.get("attribute_path", ""),
        "new_value": str(body.get("new_value", "")),
        "unit": body.get("unit", ""),
        "effective_from": body.get("effective_from", ""),
        "note": body.get("note", ""),
        "idempotency_key": body.get("idempotency_key", ""),
    })
    _remember(result, system_id, body.get("supplier", ""))
    bus.publish("submitted", {"result": result})
    return result


@app.post("/portal-api/{system_id}/document")
async def submit_document(system_id: str, body: dict = Body(...)) -> dict:
    result = await _call(system_id, "upload_document", {
        "supplier": body.get("supplier", ""),
        "product_id": body.get("product_id", ""),
        "filename": body.get("filename", ""),
        "content_base64": body.get("content_base64", ""),
        "media_type": body.get("media_type", ""),
        "text": body.get("text", ""),
        "note": body.get("note", ""),
        "idempotency_key": body.get("idempotency_key", ""),
    })
    _remember(result, system_id, body.get("supplier", ""))
    bus.publish("submitted", {"result": result})
    return result


@app.post("/portal-api/{system_id}/image")
async def submit_image(system_id: str, body: dict = Body(...)) -> dict:
    result = await _call(system_id, "upload_image", {
        "supplier": body.get("supplier", ""),
        "entity_id": body.get("entity_id", ""),
        "role": body.get("role", ""),
        "filename": body.get("filename", ""),
        "content_base64": body.get("content_base64", ""),
        "media_type": body.get("media_type", ""),
        "alt_text": body.get("alt_text", ""),
        "idempotency_key": body.get("idempotency_key", ""),
    })
    _remember(result, system_id, body.get("supplier", ""))
    bus.publish("submitted", {"result": result})
    return result


@app.get("/portal-api/{system_id}/feed")
async def describe_feed(system_id: str) -> dict:
    """Which templates the retailer publishes, and in what formats."""
    return await _call(system_id, "describe_feed", {})


@app.get("/portal-api/{system_id}/template")
async def template(system_id: str, branch: str = "", fmt: str = "csv",
                   filled: bool = False) -> Response:
    """A template, relayed as a download from this origin.

    The bytes cross MCP like everything else and are handed on from here. The
    page could not fetch them from the platform directly: it would need an
    absolute URL to another origin, which is the moment the supplier's identity
    stops being something this process holds and starts being something a tab
    claims. ``tests/test_app_boundary.py`` checks for exactly that.
    """
    result = await _call(system_id, "fetch_feed_template",
                         {"branch": branch, "fmt": fmt, "filled": filled})
    if not isinstance(result, dict) or result.get("error"):
        detail = (result or {}).get("error", "the platform did not answer")
        return Response(content=detail, status_code=400, media_type="text/plain")
    return Response(
        content=base64.b64decode(result["content_base64"]),
        media_type=result.get("media_type", "application/octet-stream"),
        headers={"Content-Disposition":
                 f'attachment; filename="{result["filename"]}"'})


@app.post("/portal-api/{system_id}/feed")
async def submit_feed(system_id: str, body: dict = Body(...)) -> dict:
    """Send a whole product feed as one archive.

    The archive is passed straight through. This process does not open it, and
    deliberately does not: validating here would be a second implementation of
    the reader, on the wrong side of the boundary, and the two would disagree
    about a row the day one of them was changed.
    """
    result = await _call(system_id, "submit_product_feed", {
        "supplier": body.get("supplier", ""),
        "filename": body.get("filename", ""),
        "content_base64": body.get("content_base64", ""),
        "note": body.get("note", ""),
        "idempotency_key": body.get("idempotency_key", ""),
    })
    _remember(result, system_id, body.get("supplier", ""))
    bus.publish("submitted", {"result": result})
    return result


@app.post("/portal-api/{system_id}/draft")
async def submit_draft(system_id: str, body: dict = Body(...)) -> dict:
    result = await _call(system_id, "create_product_draft", {
        "supplier": body.get("supplier", ""),
        "name": body.get("name", ""),
        "category": body.get("category", ""),
        "attributes": body.get("attributes") or {},
        "note": body.get("note", ""),
        "idempotency_key": body.get("idempotency_key", ""),
    })
    _remember(result, system_id, body.get("supplier", ""))
    bus.publish("submitted", {"result": result})
    return result


@app.get("/portal-api/{system_id}/submission/{submission_id}")
async def submission(system_id: str, submission_id: str,
                     supplier: str) -> dict:
    return await _call(system_id, "submission_status",
                       {"supplier": supplier, "submission_id": submission_id})


def _remember(result: dict, system_id: str, supplier: str) -> None:
    """Watch a submission, so the page can be told when the platform moves.

    The supplier is kept with it because the platform - quite correctly -
    refuses to hand a submission to a caller who cannot say whose it is.
    """
    if not (isinstance(result, dict) and result.get("submission_id")):
        return
    _watched[result["submission_id"]] = {
        "system": system_id, "supplier": supplier, "reached": ""}
    for stale in list(_watched)[:-WATCH_LIMIT]:
        _watched.pop(stale, None)


async def _tick() -> bool:
    """Re-ask the platform what became of what we sent.

    The relay back is the whole reason a supplier opens this page a second
    time: they want to know whether the correction landed, and - more often -
    why the product is still not launching when their part of it was fine.
    """
    moved = False
    for submission_id, watch in list(_watched.items()):
        status = await _call(watch["system"], "submission_status",
                             {"supplier": watch["supplier"],
                              "submission_id": submission_id})
        if not isinstance(status, dict) or status.get("error"):
            continue
        reached = ",".join(status.get("reached", []))
        if reached != watch["reached"]:
            watch["reached"] = reached
            bus.publish("progress", {"submission_id": submission_id,
                                     "status": status})
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
    port = _env.port("VENDOR_PORT", 8110)
    _serve.run(app, port, banner=(
        f"\n  {TITLE}\n"
        f"  {'-' * len(TITLE)}\n"
        f"  http://127.0.0.1:{port}\n"
        f"  talking to {client.base_url} over MCP, and to nothing else\n"))


if __name__ == "__main__":
    main()
