"""product-catalog - the PIM, over MCP.

    python -m sc.mcp.product_catalog

Read-only. Answers the questions about the catalog that a document cannot
answer authoritatively: what a variant currently carries, which document each
value is standing on, and every piece of prepared content built from it.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.tools import network as network_tools

mcp = FastMCP("product-catalog")


@mcp.tool()
def get_network_state(as_of: str | None = None,
                      as_of_recorded: str | None = None) -> dict:
    """The catalog plus whatever has been corrected under it.

    as_of moves along valid time ("what is true then"); as_of_recorded moves
    along recorded time ("what was known then"). Both default to the simulated
    clock. ISO-8601 strings.
    """
    return instrumented(network_tools.get_network_state)(as_of, as_of_recorded)


@mcp.tool()
def trace_dependencies(entity_id: str, depth: int = 3,
                       as_of: str | None = None) -> dict:
    """Blast radius of a correction, from the lineage the content was built
    with. Accepts a document, attribute reference, variant, product, listing or
    channel id.

    Depth 1 stops at the fields, 2 adds the copy and its listings, 3 adds the
    channels and the sibling variants reached through a cross-variant asset.
    """
    return instrumented(network_tools.trace_dependencies)(entity_id, depth, as_of)


@mcp.tool()
def variant_diff(product_id: str, as_of: str | None = None) -> dict:
    """The attribute table across a product's base and variants.

    Every value carries the document and version it stands on, which is what
    makes "does this correction apply to the base model or the variant" a
    question about the record rather than a matter of opinion.
    """
    return instrumented(network_tools.variant_diff)(product_id, as_of)


@mcp.tool()
def get_derivation(entity_id: str) -> dict:
    """What an asset or a listing was built from, and at which version.

    Deliberately baseline-only: derived_from records what the copy was written
    against, and that does not move when a correction lands. What has moved
    since is get_listing_state's question, on the channel registry.
    """
    return instrumented(network_tools.get_derivation)(entity_id)


if __name__ == "__main__":
    serve(mcp, "product-catalog")
