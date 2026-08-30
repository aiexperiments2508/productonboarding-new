"""A2A peers.

``agents`` is the roster and the work; ``server`` publishes them; ``client``
calls them. The graph reaches peers through ``client``, which falls back to the
in-process handler when A2A is switched off - so the protocol is a transport
decision, not a behavioural one.
"""

from sc.a2a.agents import AGENTS, BY_ID, PeerAgent

__all__ = ["AGENTS", "BY_ID", "PeerAgent"]
