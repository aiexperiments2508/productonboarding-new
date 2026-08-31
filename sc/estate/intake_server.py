"""The vendor intake, one MCP server per system that accepts submissions.

``server.py`` publishes every system in the estate as a read-only endpoint: ask
a supplier system what it is, what it has sent, and what one payload contained.
This is the other direction, and it exists for three systems only - the ones
whose manifest entry declares an ``accepts`` list.

**The tool list is derived, never written down.** Each endpoint exposes what
its system accepts and nothing more, so narrowing a system in the manifest
removes its upload tools here with no code change. That is also the only way it
can work: a test walks every module under ``sc/`` and fails if a system
identifier appears outside the manifest, which is exactly the rule that stops
an estate turning into a list of special cases.

**Appending is not writing.** Nothing here reaches the fact store. A tool call
appends an event and the platform's own ingestion judges it, under the same
precedence policy and the same materiality threshold as the recording - see
``intake.py``, which is where that argument is made at length. The safeguard is
structural rather than a permission check, and it is checked by a test that
walks this module's imports.

**The endpoints are not connections.** They are addresses others reach us at,
not systems we reach out to, and the ``connections`` table means the second
thing. Mixing them would make "what can this platform reach" unanswerable, so
these are listed separately.
"""

from __future__ import annotations

from typing import Any

from sc.datapack import read as read_mod
from sc.estate import intake
from sc.estate.manifest import SYSTEMS, System

#: Which tools an accepted event type buys. The map is the whole configuration:
#: a system that accepts only attribute rows gets the reads and the
#: specification change, and does not get an upload surface it has no
#: real-world equivalent for.
TOOLS_BY_ACCEPTS: dict[str, tuple[str, ...]] = {
    "SUPPLIER_FEED": ("submit_specification_change",),
    "SPEC_DOC": ("upload_document", "create_product_draft"),
    "CATALOG_UPDATE": ("upload_image",),
}

#: Tools that need more than one thing accepted, and so cannot be expressed by
#: the map above. A product feed is attribute rows and photographs in one
#: archive; an endpoint that cannot take both has no real-world equivalent of
#: one, and would have to answer half of every bundle with a refusal.
TOOLS_BY_ALL_OF: dict[tuple[str, ...], tuple[str, ...]] = {
    ("SUPPLIER_FEED", "CATALOG_UPDATE"): ("submit_product_feed",),
}

#: Available on every intake endpoint, whatever it accepts. Reading what you
#: sent is not a privilege that depends on what you may send next.
ALWAYS: tuple[str, ...] = ("describe_intake", "list_my_products",
                           "get_product_spec", "submission_status",
                           "fetch_feed_template")


def vendor_facing() -> list[System]:
    """The systems a supplier can send through, from the manifest alone."""
    return [s for s in SYSTEMS if s.accepts]


def tools_for(system: System) -> tuple[str, ...]:
    """What this endpoint exposes, derived from what its system accepts."""
    tools = set(ALWAYS)
    for accepted in system.accepts:
        tools.update(TOOLS_BY_ACCEPTS.get(accepted, ()))
    for needed, granted in TOOLS_BY_ALL_OF.items():
        if set(needed) <= set(system.accepts):
            tools.update(granted)
    return tuple(sorted(tools))


#: The tools that change something. Declared rather than inferred from a name,
#: because "which of these can act" is the question an operator handing out an
#: endpoint actually asks.
MUTATING: tuple[str, ...] = ("submit_specification_change", "upload_document",
                             "upload_image", "create_product_draft",
                             "submit_product_feed")


def _describe(system: System) -> dict:
    return {
        "id": system.id,
        "title": system.title,
        "owner": system.owner,
        "accepts": list(system.accepts),
        "tools": list(tools_for(system)),
        "mutating": [t for t in tools_for(system) if t in MUTATING],
        "suppliers": sorted(intake.known_suppliers()),
        "max_upload_bytes": intake.MAX_UPLOAD_BYTES,
        "max_bundle_bytes": read_mod.MAX_BUNDLE_BYTES,
        "max_bundle_rows": read_mod.MAX_BUNDLE_ROWS,
        "precedence": system.precedence,
        "note": ("this endpoint appends events. It cannot write a value into "
                 "the retailer's catalog: what you send is recorded as a "
                 "document version, and the platform's own extraction and "
                 "rules decide what it means"),
        "identity": ("the system is bound by the endpoint you called. The "
                     "supplier is an argument and is used for scoping and "
                     "attribution - it is not authentication, and there is no "
                     "identity provider anywhere in this system"),
    }


def build(system: System) -> Any:
    """One system's intake server.

    Built per system rather than parameterised at call time, so that each
    endpoint's tool list is genuinely that system's own - the difference
    between three servers and one server with a system argument.
    """
    from mcp.server.fastmcp import FastMCP

    # Served at the root of its own app, for the reason `server.py` gives:
    # mounted at `/mcp/intake/{id}`, FastMCP's default sub-path would put the
    # endpoint at `/mcp/intake/{id}/mcp`, so the advertised address would not
    # be the answering one.
    mcp = FastMCP(f"{system.id}-intake", streamable_http_path="/")
    exposed = tools_for(system)

    @mcp.tool()
    def describe_intake() -> dict:
        """What this endpoint accepts, from whom, and what it will not do."""
        return _describe(system)

    @mcp.tool()
    def list_my_products(supplier: str, q: str = "", limit: int = 50,
                         offset: int = 0) -> dict:
        """The products this supplier owns, and what it last sent about each."""
        return intake.list_my_products(supplier, system.id, q=q, limit=limit,
                                       offset=offset)

    @mcp.tool()
    def get_product_spec(supplier: str, product_id: str,
                         as_of: str = "") -> dict:
        """What is held against a product, and how much of it you asserted."""
        return intake.get_product_spec(supplier, product_id, as_of or None)

    @mcp.tool()
    def submission_status(supplier: str, submission_id: str) -> dict:
        """Where one submission got to, stage by stage."""
        from sc.estate import submissions

        return submissions.status(supplier, submission_id)

    if "submit_specification_change" in exposed:
        @mcp.tool()
        def submit_specification_change(
                supplier: str, entity_id: str, attribute_path: str,
                new_value: str, unit: str = "", effective_from: str = "",
                note: str = "", doc_id: str = "",
                idempotency_key: str = "") -> dict:
            """Send a corrected specification, optionally effective from a date.

            Declared with explicit typed parameters rather than forwarded
            through the idempotency decorator, whose wrapper takes ``*args``.
            FastMCP derives a tool's schema by introspection, so decorating
            this function directly would publish a tool that appears to take
            anything at all.
            """
            return intake.submit_specification_change(
                supplier=supplier, system_id=system.id, entity_id=entity_id,
                attribute_path=attribute_path, new_value=new_value, unit=unit,
                effective_from=effective_from, note=note, doc_id=doc_id,
                idempotency_key=idempotency_key or None)

    if "upload_document" in exposed:
        @mcp.tool()
        def upload_document(supplier: str, product_id: str, filename: str,
                            content_base64: str, media_type: str = "",
                            text: str = "", doc_id: str = "", note: str = "",
                            idempotency_key: str = "") -> dict:
            """Send a document. Supply ``text`` if you want it read."""
            return intake.upload_document(
                supplier=supplier, system_id=system.id, product_id=product_id,
                filename=filename, content_base64=content_base64,
                media_type=media_type, text=text, doc_id=doc_id, note=note,
                idempotency_key=idempotency_key or None)

    if "create_product_draft" in exposed:
        @mcp.tool()
        def create_product_draft(supplier: str, name: str, category: str,
                                 attributes: dict | None = None,
                                 note: str = "",
                                 idempotency_key: str = "") -> dict:
            """Propose a new line. Held as a draft until a reviewer accepts it."""
            return intake.create_product_draft(
                supplier=supplier, system_id=system.id, name=name,
                category=category, attributes=attributes, note=note,
                idempotency_key=idempotency_key or None)

    if "upload_image" in exposed:
        @mcp.tool()
        def upload_image(supplier: str, entity_id: str, role: str,
                         filename: str, content_base64: str,
                         media_type: str = "", alt_text: str = "",
                         idempotency_key: str = "") -> dict:
            """Send an image for a variant, in one of the declared roles."""
            return intake.upload_image(
                supplier=supplier, system_id=system.id, entity_id=entity_id,
                role=role, filename=filename, content_base64=content_base64,
                media_type=media_type, alt_text=alt_text,
                idempotency_key=idempotency_key or None)

    if "fetch_feed_template" in exposed:
        @mcp.tool()
        def fetch_feed_template(branch: str = "", fmt: str = "csv",
                                filled: bool = False) -> dict:
            """The template for one part of the assortment, base64 encoded.

            Available on every endpoint, including the ones that cannot take a
            bundle back: knowing what we ask for is not a privilege that
            depends on how you are allowed to send it.

            ``fmt`` is csv, txt, xlsx, docx or json. ``branch`` names a part of
            the assortment for csv, txt and xlsx, and is ignored for docx and
            json, which cover the whole pack. ``filled`` asks for the worked
            example rather than the blank template.
            """
            return intake.fetch_feed_template(branch=branch, fmt=fmt,
                                              filled=filled)

        @mcp.tool()
        def describe_feed() -> dict:
            """Which templates exist, and whether this endpoint takes one back.

            Both halves, because they are different questions and the answer to
            the second is no on two of the three endpoints. A portal that
            offered an upload form wherever it could offer a template would be
            offering a door that answers every knock with a refusal.
            """
            exposed_here = tools_for(system)
            return {
                **intake.feed_branches(),
                "accepts_bundle": "submit_product_feed" in exposed_here,
                "why_not": ("" if "submit_product_feed" in exposed_here else
                            f"{system.title} accepts "
                            f"{', '.join(system.accepts)}. A product feed is "
                            f"attribute rows and photographs in one archive, "
                            f"so it is taken only where both are accepted"),
            }

    if "submit_product_feed" in exposed:
        @mcp.tool()
        def submit_product_feed(supplier: str, filename: str,
                                content_base64: str, note: str = "",
                                idempotency_key: str = "") -> dict:
            """Send a whole product feed: one .zip of rows and photographs.

            The archive holds one data file at its root - the .csv, .txt or
            .xlsx from the template - and an optional images/ folder whose file
            names the rows refer to.

            Every row is judged on arrival exactly as a taped one would be.
            Nothing here writes a value into the catalog by itself, and a row
            naming a product we do not have is held as a draft rather than
            creating one.

            Declared with explicit typed parameters for the same reason as
            ``submit_specification_change``: FastMCP reads the signature, and
            the idempotency decorator's wrapper takes ``*args``.
            """
            return intake.submit_product_feed(
                supplier=supplier, system_id=system.id, filename=filename,
                content_base64=content_base64, note=note,
                idempotency_key=idempotency_key or None)

    return mcp


#: Built servers, held so their session managers start with the application.
_SERVERS: list[Any] = []


async def start(stack) -> int:
    """Run every mounted intake server's session manager. See ``server.start``."""
    started = 0
    for server in _SERVERS:
        await stack.enter_async_context(server.session_manager.run())
        started += 1
    return started


def endpoint(system_id: str, base_url: str = "") -> str:
    """Where an intake surface answers. One place that knows the URL shape."""
    return f"{base_url}/mcp/intake/{system_id}/"


def mount(app) -> list[dict]:
    """Publish every vendor-facing system's intake onto a FastAPI app.

    A system that fails to mount is reported and skipped, for the reason the
    read-only estate gives: two portals and a note is a better demo than a
    stack trace.
    """
    mounted: list[dict] = []
    for system in vendor_facing():
        path = f"/mcp/intake/{system.id}"
        try:
            server = build(system)
            app.mount(path, server.streamable_http_app())
            _SERVERS.append(server)
        except Exception as exc:  # noqa: BLE001 - one endpoint is not the estate
            mounted.append({"id": system.id, "url": path,
                            "error": str(exc)[:200]})
            continue
        mounted.append({
            "id": system.id,
            "title": f"{system.title} intake",
            "owner": system.owner,
            "url": f"{path}/",
            "transport": "http",
            "accepts": list(system.accepts),
            "tools": list(tools_for(system)),
            "mutating": [t for t in tools_for(system) if t in MUTATING],
        })
    return mounted
