"""content-store - the DAM, over MCP.

    python -m sc.mcp.content_store

Read-only, and deliberately so. The store holds the publish locks that make two
runs republishing the same product to the same channel impossible - exclusivity
is enforced by a partial unique index, not by a caller checking first - but
*taking* one is a publishing act and lives on the publishing server. Reading who
holds what is not.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.tools import planning

mcp = FastMCP("content-store")


@mcp.tool()
def open_reservations(incident_id: str | None = None) -> dict:
    """Publish locks currently held, by (channel, product) and batch date."""
    def run() -> dict:
        return {"reservations": planning.open_reservations(incident_id)}

    run.__name__ = "open_reservations"
    return instrumented(run)()


if __name__ == "__main__":
    serve(mcp, "content-store")
