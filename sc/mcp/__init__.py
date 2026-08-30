"""MCP toolsets, partitioned by owning system.

See ``registry`` for what the partition is and why it exists. Import that
rather than reaching into the server modules - they are entry points, not a
library.
"""

from sc.mcp.registry import BY_ID, TOOLSETS, Toolset, describe, owner_of

__all__ = ["BY_ID", "TOOLSETS", "Toolset", "describe", "owner_of"]
