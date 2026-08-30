"""Calling a peer over A2A, with the in-process handler as the fallback.

``USE_A2A=1`` makes the graph delegate to its peers over the protocol: the
validation step becomes a JSON-RPC call to the validator agent, the blast
radius becomes a call to the lineage analyst. With it off, the same handlers
run in-process.

The result is identical either way, and that is the property worth protecting.
An A2A demonstration that changed the answers would not be demonstrating
interoperability, it would be demonstrating two implementations.

The fallback is not politeness. Four agents mounted on one app still share a
process, and a peer that fails to answer during a finale should cost a log line
rather than a correction run.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from threading import Lock

from sc.a2a.agents import BY_ID

log = logging.getLogger(__name__)

MAX_CALLS = 200
_calls: deque[dict] = deque(maxlen=MAX_CALLS)
_lock = Lock()
_seq = 0
_degraded: set[str] = set()


def enabled() -> bool:
    """Read per call, so the switch can be flipped mid-demo."""
    return os.environ.get("USE_A2A", "0").strip().lower() in {"1", "true", "yes"}


def base_url() -> str:
    port = os.environ.get("API_PORT", "8000").strip()
    return os.environ.get("A2A_BASE_URL", f"http://127.0.0.1:{port}").rstrip("/")


def _record(agent_id: str, transport: str, ms: float, ok: bool,
            detail: str = "") -> None:
    global _seq
    with _lock:
        _seq += 1
        _calls.append({
            "seq": _seq, "at": time.time(), "agent": agent_id,
            "skill": BY_ID[agent_id].skill_id if agent_id in BY_ID else "",
            "transport": transport, "ms": round(ms, 2), "ok": ok,
            "detail": detail[:200],
        })


def calls(limit: int = 60) -> list[dict]:
    with _lock:
        return list(reversed(list(_calls)))[:limit]


def revive() -> None:
    """Give retired peers another chance.

    A peer is retired after one failure so a misconfigured base URL does not
    cost a timeout on every call. That is right during a run and wrong after
    someone fixes the configuration, so flipping the switch clears the set.
    """
    _degraded.clear()


def status() -> dict:
    return {
        "enabled": enabled(),
        "base_url": base_url(),
        "agents": sorted(BY_ID),
        "degraded": sorted(_degraded),
    }


def _remote(agent_id: str, payload: dict, timeout: float) -> dict:
    """One JSON-RPC message/send round trip.

    Deliberately plain httpx rather than the SDK client. The SDK's client
    resolves a card, negotiates a transport and manages a session - all correct
    for a general consumer, and all overhead when the caller already knows the
    endpoint it published a moment ago. The wire format is the same, which is
    what conformance means here.
    """
    import httpx

    request = {
        "jsonrpc": "2.0",
        "id": f"{agent_id}-{int(time.time() * 1000)}",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"m-{int(time.time() * 1000)}",
                "role": "user",
                "parts": [{"text": json.dumps(payload, default=str)}],
            }
        },
    }
    with httpx.Client(timeout=timeout) as http:
        response = http.post(f"{base_url()}/a2a/{agent_id}", json=request)
        response.raise_for_status()
        body = response.json()

    if "error" in body:
        raise RuntimeError(str(body["error"])[:300])

    return _unwrap(body.get("result") or {})


def _unwrap(result: dict) -> dict:
    """Pull the payload back out of whatever the peer answered with.

    A2A allows a message or a task, and a task carries its output in artifacts.
    Handling both is what makes this a client rather than a client for one
    server.
    """
    def from_parts(parts) -> dict | None:
        for part in parts or []:
            text = part.get("text")
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
            if part.get("data") is not None:
                return part["data"]
        return None

    found = from_parts(result.get("parts"))
    if found is not None:
        return found

    for artifact in result.get("artifacts") or []:
        found = from_parts(artifact.get("parts"))
        if found is not None:
            return found

    history = result.get("history") or []
    for message in reversed(history):
        found = from_parts(message.get("parts"))
        if found is not None:
            return found

    return {}


def call(agent_id: str, payload: dict, timeout: float = 120.0) -> dict:
    """Delegate to a peer, over A2A when enabled and in-process otherwise."""
    agent = BY_ID[agent_id]

    if not enabled() or agent_id in _degraded:
        started = time.perf_counter()
        result = agent.handler(payload)
        _record(agent_id, "in-process",
                (time.perf_counter() - started) * 1000, True)
        return result

    started = time.perf_counter()
    try:
        result = _remote(agent_id, payload, timeout)
        _record(agent_id, "a2a", (time.perf_counter() - started) * 1000, True,
                f"message/send to {agent_id}")
        return result
    except Exception as exc:  # noqa: BLE001 - the correction run matters more
        # Retire the peer for the rest of the process rather than paying the
        # timeout again on every call.
        _degraded.add(agent_id)
        log.warning("a2a peer %s unreachable, falling back: %s", agent_id, exc)
        _record(agent_id, "a2a", (time.perf_counter() - started) * 1000, False,
                f"{exc} - falling back in-process")
        return agent.handler(payload)
