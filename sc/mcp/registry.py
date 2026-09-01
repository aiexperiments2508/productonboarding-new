"""What the toolsets are, and who owns them.

The brief is sceptical about MCP, and correctly: "MCP is justified only if
several independently owned systems are exposed as reusable tools; otherwise
ordinary APIs are simpler." A single server exposing seventeen flat tools does
not pass that test - it is one system with a protocol bolted on.

So the toolset is partitioned the way product information is actually owned in
a retailer. Each of these stands for a system with its own team, its own release
cycle and its own idea of what an identifier means:

    product-catalog       the PIM - products, variants, attributes and the
                          lineage every derived output was built from
    channel-registry      the channel integration layer - what each destination
                          demands and what one listing currently says
    content-store         the DAM - prepared copy and the publish locks on it
    knowledge-base        the document system - standards, channel specs,
                          policy, postmortems
    event-plane           the integration bus - what arrived, and when
    publishing-execution  the publishing pipeline, and the only toolset that
                          writes anything

That last line is the one that makes the partition worth having. A correction
that reaches five systems is read from five owners; only one of them can push
content to a channel. Splitting them means the dangerous surface is a named
server with four mutating tools rather than four entries in a list of
seventeen, and an operator can hand out the first five without handing out the
sixth.

The event plane is the one qualified exception. ``advance_events`` writes,
because releasing the next event from the tape is a demo control - in a real
deployment events arrive because the world produced them and nothing would
expose a tool that manufactures them. It changes the clock, never the catalog.

Each server runs on its own:

    python -m sc.mcp.product_catalog
    python -m sc.mcp.publishing_execution

or all of them together through ``sc.mcp_server``, which is the convenience
form and not the architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Toolset:
    id: str
    module: str
    title: str
    #: The real-world system this stands in for.
    owner: str
    why: str
    tools: tuple[str, ...]
    #: Tools that change state. Empty means the whole server is safe to expose.
    mutating: tuple[str, ...] = field(default=())

    @property
    def read_only(self) -> bool:
        return not self.mutating


TOOLSETS: tuple[Toolset, ...] = (
    Toolset(
        id="product-catalog",
        module="sc.mcp.product_catalog",
        title="Product catalog",
        owner="Product information management",
        why="Products, variants, attribute values and the derivation graph the "
            "prepared content was built from. The question 'does this "
            "correction apply to the base model or the variant' is answered "
            "here and nowhere else - a document can only assert it.",
        tools=("get_network_state", "trace_dependencies", "variant_diff",
               "get_derivation"),
    ),
    Toolset(
        id="channel-registry",
        module="sc.mcp.channel_registry",
        title="Channel registry",
        owner="Channel integration",
        why="What each destination demands - field names, schemas, budgets, "
            "freeze windows - and what one listing currently says. A rejected "
            "feed is a fact about this system, not about the correction.",
        tools=("channel_rules", "get_listing_state"),
    ),
    Toolset(
        id="content-store",
        module="sc.mcp.content_store",
        title="Content store",
        owner="Digital asset management",
        why="Prepared copy and the publish locks held over it. The reservation "
            "index that makes two runs republishing the same product to the "
            "same channel impossible lives behind these.",
        tools=("open_reservations",),
    ),
    Toolset(
        id="control-tower",
        module="sc.mcp.control_tower",
        title="Control tower",
        owner="Category and platform operations",
        why="Where every feed's rows have got to, the KPIs over a window, and "
            "what the models spent reaching them. Nothing here decides "
            "anything - it joins what the readiness, onboarding and lifecycle "
            "surfaces already derived, which is why it is read-only and why "
            "the spend cap that goes with it is not a tool.",
        tools=("tower_flow", "tower_feeds", "tower_feed", "tower_kpis",
               "tower_spend"),
    ),
    Toolset(
        id="knowledge-base",
        module="sc.mcp.knowledge_base",
        title="Knowledge base",
        owner="Document management",
        why="Content standards, channel specifications, policy and "
            "postmortems. Retrieval is fused BM25 and dense, so an identifier "
            "query still works when the embeddings are missing.",
        tools=("search_docs", "get_doc"),
    ),
    Toolset(
        id="event-plane",
        module="sc.mcp.event_plane",
        title="Event plane",
        owner="Integration bus",
        why="Supplier feeds, spec documents and channel acknowledgements as "
            "they arrived, with per-consumer cursors. Advancing the tape is a "
            "demo control, which is why it is not read-only.",
        tools=("query_events", "advance_events", "replay_state"),
        mutating=("advance_events",),
    ),
    Toolset(
        id="publishing-execution",
        module="sc.mcp.publishing_execution",
        title="Publishing and execution",
        owner="Publishing pipeline",
        why="Validation, and the only tools in the estate that change what a "
            "channel sees. commit_plan still refuses without a recorded "
            "approval - exposing a tool over MCP does not exempt it from the "
            "safeguards.",
        tools=("run_scenario", "compare_scenarios", "propose_change",
               "commit_plan", "rollback", "reserve_publish"),
        mutating=("propose_change", "commit_plan", "rollback",
                  "reserve_publish"),
    ),
)

BY_ID = {t.id: t for t in TOOLSETS}


def describe() -> list[dict]:
    """The registry as the API and the console render it."""
    return [
        {
            "id": t.id,
            "module": t.module,
            "title": t.title,
            "owner": t.owner,
            "why": t.why,
            "tools": list(t.tools),
            "mutating": list(t.mutating),
            "read_only": t.read_only,
            "command": f"python -m {t.module}",
        }
        for t in TOOLSETS
    ]


def owner_of(tool: str) -> str:
    """Which toolset a tool belongs to. Used to label calls in the console."""
    for toolset in TOOLSETS:
        if tool in toolset.tools:
            return toolset.id
    return "unknown"
