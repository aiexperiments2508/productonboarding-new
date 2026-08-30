"""Publishing the peers as A2A agents.

Each agent in ``agents.AGENTS`` gets two things another organisation's agent
would need to use it: a discoverable Agent Card, and a JSON-RPC endpoint that
speaks the A2A task lifecycle.

    /a2a/{agent}/.well-known/agent-card.json    who I am, what I can do
    /a2a/{agent}                                message/send, tasks/get, ...

They are mounted onto the same FastAPI app the UI is served from. That is a
deployment choice, not an architectural one - the calls still cross the
protocol, the cards are still discoverable, and moving one agent to its own
host would be a change to a base URL. Running four processes to prove a point
about boundaries would cost a demo four things that can fail.

The SDK's types are protobuf messages in 1.x, so cards are built field by field
rather than from a dict. That is more verbose and it is also the reason the
card is guaranteed to be well-formed: a typo is an AttributeError here rather
than a client-side surprise later.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sc.a2a.agents import AGENTS, PeerAgent

log = logging.getLogger(__name__)

# Bumped when a skill's contract changes, not when its implementation does.
AGENT_VERSION = "1.0.0"


def _card(agent: PeerAgent, base_url: str) -> Any:
    """The Agent Card, as a protobuf message."""
    from a2a.types import (
        AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill,
    )

    return AgentCard(
        name=agent.name,
        description=agent.description,
        version=AGENT_VERSION,
        provider=AgentProvider(
            organization="Product Intelligence Factory",
            url="https://example.invalid/product-intelligence-factory",
        ),
        supported_interfaces=[
            AgentInterface(url=f"{base_url}/a2a/{agent.id}",
                           protocol_binding="JSONRPC"),
        ],
        capabilities=AgentCapabilities(streaming=False,
                                       push_notifications=False),
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=agent.skill_id,
                name=agent.skill_name,
                description=agent.skill_description,
                tags=["product-data", "correction", agent.id],
                examples=list(agent.examples),
                input_modes=["application/json"],
                output_modes=["application/json"],
            )
        ],
    )


class _Executor:
    """Adapts one peer's handler to the A2A executor contract.

    A2A carries a message; this pulls the JSON payload out of it, runs the
    handler, and puts the result back as a data part. The handler itself knows
    nothing about A2A, which is what lets the same function serve both the
    in-process graph and a remote peer.
    """

    def __init__(self, agent: PeerAgent) -> None:
        self.agent = agent

    async def execute(self, context, event_queue) -> None:  # noqa: ANN001
        payload = _payload_from(context)
        try:
            # The work is synchronous and CPU-bound. Handing it to a thread
            # keeps the event loop free for the other agents mounted on the
            # same app - four peers sharing one loop is exactly the case where
            # a blocking validation would stall the others.
            import anyio
            result = await anyio.to_thread.run_sync(self.agent.handler, payload)
        except Exception as exc:  # noqa: BLE001 - reported as a failed task
            log.exception("a2a peer %s failed", self.agent.id)
            result = {"error": str(exc)[:400], "agent": self.agent.id}

        await event_queue.enqueue_event(_agent_message(result, context))

    async def cancel(self, context, event_queue) -> None:  # noqa: ANN001
        """Nothing here is long-running enough to interrupt.

        A validation is milliseconds and a full regeneration pass is under a
        second; both finish faster than a cancel could be delivered. Declaring
        the method and refusing is honest, where accepting and ignoring would
        not be.
        """
        from a2a.utils.errors import ServerError
        from a2a.types import UnsupportedOperationError

        raise ServerError(error=UnsupportedOperationError())


def _agent_message(value: dict, context) -> Any:  # noqa: ANN001
    """The peer's answer, as an A2A message.

    Built field by field rather than through a helper: 1.x has no
    `new_agent_message` and constructing the protobuf directly is both explicit
    and version-proof. The context and task ids are echoed back so a caller
    correlating a conversation gets what it expects.
    """
    import uuid

    from a2a.types import Message, Role

    return Message(
        message_id=uuid.uuid4().hex,
        context_id=getattr(context, "context_id", "") or "",
        task_id=getattr(context, "task_id", "") or "",
        role=Role.ROLE_AGENT,
        parts=[_data_part(value)],
    )


def _data_part(value: dict) -> Any:
    """A JSON payload as an A2A part.

    Sent as text rather than a structured data part: the payload here is
    arbitrarily nested (KPI dicts, violation lists) and protobuf Struct is
    lossy about integers. A caller does one json.loads and gets exactly what
    the in-process path would have returned.
    """
    from a2a.types import Part

    return Part(text=json.dumps(value, default=str))


def _payload_from(context) -> dict:  # noqa: ANN001
    """Pull the request JSON out of an A2A message."""
    message = getattr(context, "message", None)
    for part in (getattr(message, "parts", None) or []):
        text = getattr(part, "text", "")
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
        data = getattr(part, "data", None)
        if data:
            from google.protobuf.json_format import MessageToDict
            return MessageToDict(data)
    return {}


def mount(app, base_url: str = "") -> list[dict]:
    """Publish every peer onto a FastAPI app. Returns what was mounted."""
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import (
        add_a2a_routes_to_fastapi, create_agent_card_routes,
        create_jsonrpc_routes,
    )
    from a2a.server.tasks import InMemoryTaskStore

    mounted: list[dict] = []
    for agent in AGENTS:
        card = _card(agent, base_url)
        handler = DefaultRequestHandler(
            agent_executor=_Executor(agent),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        card_url = f"/a2a/{agent.id}/.well-known/agent-card.json"
        rpc_url = f"/a2a/{agent.id}"

        add_a2a_routes_to_fastapi(
            app,
            agent_card_routes=create_agent_card_routes(card, card_url=card_url),
            # v0.3 compatibility on purpose. The 1.x SDK names its JSON-RPC
            # methods gRPC-style (SendMessage); every A2A client in the wild
            # sends the spec's `message/send`. Enabling compat accepts both,
            # and interoperability is the entire reason to publish a card.
            jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=rpc_url,
                                                 enable_v0_3_compat=True),
        )
        mounted.append({
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "skill": {"id": agent.skill_id, "name": agent.skill_name,
                      "description": agent.skill_description,
                      "examples": list(agent.examples)},
            "card_url": card_url,
            "rpc_url": rpc_url,
            "version": AGENT_VERSION,
        })
    return mounted
