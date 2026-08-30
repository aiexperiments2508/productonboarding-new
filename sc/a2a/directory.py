"""One document naming everything this estate can do.

Agent Cards were already published, one per peer, at the address the A2A
specification puts them:

    /a2a/{agent}/.well-known/agent-card.json

That is correct and it is not discoverable. A peer that already knows an agent's
identifier can fetch its card; a peer that knows only the host cannot find out
what is here. Every agent broadcasting its own capability is not the same as the
estate having a capability directory, and the difference shows the moment
somebody asks "what can this system do" and has to be handed a list by a person.

So there is one more document:

    /.well-known/agent-cards.json

It carries every published capability, and it is built **from the same cards**
rather than beside them. A directory assembled from its own list of names would
drift from the cards it claims to index within a release, and it would drift
silently - the directory would still look complete.

Two kinds of entry appear in it, and the distinction is kept rather than
smoothed away:

*   **peers**, which are capabilities this system implements and another
    organisation's agent may call over JSON-RPC;
*   **systems**, which are capabilities reached over MCP that this system merely
    knows how to talk to.

Flattening those into one list would say this estate can do things it can only
ask somebody else to do.
"""

from __future__ import annotations

from sc.a2a.agents import AGENTS
from sc.a2a.server import AGENT_VERSION

#: Where the directory lives. Under `.well-known` because that is where a
#: stranger looks, which is the entire point of publishing it.
PATH = "/.well-known/agent-cards.json"


def _peer_entries(base_url: str, mounted: list[dict]) -> list[dict]:
    """The peers, described from the cards actually served.

    ``mounted`` is what `a2a.server.mount` returned, so an agent that failed to
    mount is absent here rather than advertised as available - a directory
    listing a capability nobody can reach is worse than one that is short.
    """
    reachable = {entry["id"] for entry in mounted}
    entries = []
    for agent in AGENTS:
        if agent.id not in reachable:
            continue
        entries.append({
            "kind": "peer",
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "version": AGENT_VERSION,
            "protocol": "A2A/JSONRPC",
            "card_url": f"{base_url}/a2a/{agent.id}/.well-known/agent-card.json",
            "endpoint": f"{base_url}/a2a/{agent.id}",
            "skills": [{
                "id": agent.skill_id,
                "name": agent.skill_name,
                "description": agent.skill_description,
                "examples": list(agent.examples),
            }],
            # What this capability may not do, stated rather than implied. The
            # approval gate and publishing are deliberately not peers: a human
            # decision is not a capability to delegate, and a peer that could
            # publish is a peer that could publish.
            "may_not": ["approve a resolution", "publish to a channel"],
        })
    return entries


def _system_entries() -> list[dict]:
    """The connected systems, as capabilities this estate can reach.

    Read from the connection records rather than from the manifest, so a system
    that is not answering is described as degraded instead of being advertised
    as though it were.

    ``admitted`` is carried because it is the difference between what a system
    says it can do and what this system will let a model ask it to do.
    Publishing the first without the second would misdescribe the boundary.
    """
    from sc.mcp import connections

    entries = []
    for record in connections.all_connections():
        entries.append({
            "kind": "system",
            "id": record["id"],
            "name": record["title"],
            "description": record["detail"],
            "owner": record["owner"],
            "protocol": f"MCP/{record['transport']}",
            "endpoint": record["url"],
            "state": record["state"],
            "tools": record["discovered_tools"],
            "admitted": record["admitted_tools"],
        })
    return entries


def build(base_url: str, mounted: list[dict]) -> dict:
    """The directory document.

    Counts are derived from the entries rather than tracked beside them, so the
    summary cannot disagree with the list under it.
    """
    peers = _peer_entries(base_url, mounted)
    systems = _system_entries()
    return {
        "provider": {
            "organization": "Product Intelligence Factory",
            "url": base_url,
        },
        "version": AGENT_VERSION,
        "capabilities": peers + systems,
        "counts": {
            "peers": len(peers),
            "systems": len(systems),
            "reachable": sum(1 for s in systems
                             if s["state"] == "connected") + len(peers),
        },
    }
