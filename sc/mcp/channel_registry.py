"""channel-registry - the channel integration layer, over MCP.

    python -m sc.mcp.channel_registry

Read-only. What each destination demands is a fact about this system; what the
correction does about it is a fact about another.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.tools import network as network_tools

mcp = FastMCP("channel-registry")


@mcp.tool()
def channel_rules(channel_id: str, field: str | None = None) -> dict:
    """The rules in force for a channel, or for one of its fields.

    Rules are data, so this is a read rather than a description of code: a
    channel gains a rule without the validator changing, and the reviewer sees
    the same row the engine bound on. Also returns what the channel calls each
    internal attribute path.
    """
    return instrumented(network_tools.channel_rules)(channel_id, field)


@mcp.tool()
def get_listing_state(listing_id: str, as_of: str | None = None) -> dict:
    """One listing as it stands: its values, its copy, and what has moved
    underneath it since that copy was written."""
    return instrumented(network_tools.get_listing_state)(listing_id, as_of)


if __name__ == "__main__":
    serve(mcp, "channel-registry")
