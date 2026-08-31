"""Client for the LiteLLM gateway, with a record/replay cache.

Every model call in the platform goes through here. Two reasons that matters:

*   **One egress point.** Model selection, token accounting and cost are
    captured in a single place, which is what the audit view reports on.
*   **Demo resilience.** Responses are cached in SQLite keyed by a hash of
    (model, temperature, messages). The first rehearsal populates the cache;
    every run afterwards is deterministic, instant, and independent of the
    venue's wifi. A flag flips it back to live to prove the calls are real.

The cache is not a performance optimisation bolted on late - it is the reason
a rehearsed demo behaves identically in front of judges.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any, Sequence

import httpx

from sc import db
from sc.contracts import LlmUsage, ModelInfo

DEFAULT_TIMEOUT = 120.0
MAX_ATTEMPTS = 3



class GatewayError(RuntimeError):
    """Raised with a message an operator can act on, not a stack trace."""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
# Refusing a TCP connection to a closed local port costs roughly two seconds on
# Windows, not the microseconds it costs elsewhere. With a node making several
# model calls, an unreachable gateway turns into twenty seconds of dead air per
# run - in front of judges, while the system is supposedly degrading
# gracefully. After a couple of consecutive connection failures we stop trying
# for a cooldown and fail instantly, so the fallback paths run at full speed.

CIRCUIT_THRESHOLD = 2
CIRCUIT_COOLDOWN = 30.0

_circuit: dict[str, float] = {"failures": 0.0, "open_until": 0.0}


def circuit_open() -> bool:
    return time.monotonic() < _circuit["open_until"]


def reset_circuit() -> None:
    """Called on success, and by the UI when the operator starts the gateway."""
    _circuit["failures"] = 0.0
    _circuit["open_until"] = 0.0


def _record_connection_failure() -> None:
    _circuit["failures"] += 1
    if _circuit["failures"] >= CIRCUIT_THRESHOLD:
        _circuit["open_until"] = time.monotonic() + CIRCUIT_COOLDOWN


def circuit_state() -> dict:
    remaining = max(0.0, _circuit["open_until"] - time.monotonic())
    return {"open": remaining > 0, "failures": int(_circuit["failures"]),
            "retry_in_seconds": round(remaining, 1)}


def base_url() -> str:
    host = os.environ.get("LITELLM_HOST", "127.0.0.1")
    port = os.environ.get("LITELLM_PORT", "4010")
    return os.environ.get("LITELLM_BASE_URL", f"http://{host}:{port}").rstrip("/")


def default_model() -> str:
    """The chat model to use when a caller does not name one.

    Falls back to whatever the gateway actually serves rather than to a
    hard-coded alias. Pinning a default couples the app to one deployment:
    point it at a gateway with a different catalogue and every unqualified
    call fails with a 404 from inside a run.
    """
    configured = (db.get_config("active_model")
                  or os.environ.get("LITELLM_DEFAULT_MODEL"))
    if configured:
        return configured
    # Imported lazily: models.py depends on this module.
    from sc.llm import models

    return models.resolve_tier("fast")


def embed_model() -> str:
    """The embedding model, from configuration or from what the gateway serves.

    The last alias named in application code lived here. It was right for one
    deployment and wrong for any other, and being right by luck is not a
    property worth keeping: point this at a gateway with a different catalogue
    and every index build failed with a 404 that named a model nobody had
    chosen.
    """
    configured = (db.get_config("embed_model")
                  or os.environ.get("LITELLM_EMBED_MODEL"))
    if configured:
        return configured
    # Imported lazily: models.py depends on this module.
    from sc.llm import models

    return models.resolve_tier("embedding")


def cache_enabled() -> bool:
    stored = db.get_config("llm_cache")
    if stored is not None:
        return stored == "1"
    return os.environ.get("LLM_CACHE", "1") == "1"


def set_cache_enabled(enabled: bool) -> None:
    db.set_config("llm_cache", "1" if enabled else "0")


def _cache_key(model: str, temperature: float, messages: Sequence[dict],
               suffix: str = "") -> str:
    payload = db.dumps({"m": model, "t": temperature,
                        "msgs": list(messages), "s": suffix})
    return hashlib.sha256(payload.encode()).hexdigest()


def _auth_headers() -> dict[str, str]:
    key = os.environ.get("LITELLM_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


# ---------------------------------------------------------------------------
# Chat completion
# ---------------------------------------------------------------------------


def complete(
    messages: Sequence[dict],
    model: str | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    agent: str | None = None,
    run_id: str | None = None,
    use_cache: bool | None = None,
) -> tuple[str, LlmUsage]:
    """One chat completion. Returns the text and what it cost.

    ``temperature`` defaults to 0: this system asks models to classify and
    extract, where variance is a defect rather than a feature.
    """
    model = model or default_model()
    want_cache = cache_enabled() if use_cache is None else use_cache
    key = _cache_key(model, temperature, messages, "json" if json_mode else "")

    if want_cache:
        hit = db.one("SELECT * FROM llm_calls WHERE cache_key = ?", (key,))
        if hit is not None:
            conn = db.connect()
            conn.execute("UPDATE llm_calls SET hits = hits + 1 WHERE cache_key = ?",
                         (key,))
            conn.commit()
            return hit["response"], LlmUsage(
                prompt_tokens=hit["prompt_tokens"],
                completion_tokens=hit["completion_tokens"],
                cost_usd=hit["cost_usd"],
                total_tokens=hit["prompt_tokens"] + hit["completion_tokens"],
                cached=True,
            )

    body: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": list(messages),
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    data = _post("/v1/chat/completions", body)
    latency_ms = (time.perf_counter() - started) * 1000

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise GatewayError(f"gateway returned no content for model '{model}'") from exc
    if not content or not content.strip():
        raise GatewayError(f"model '{model}' returned an empty response")

    usage = _usage(data)
    _record(key, model, temperature, messages, content, usage, latency_ms,
            agent, run_id)
    return content, usage


def complete_json(
    messages: Sequence[dict],
    model: str | None = None,
    agent: str | None = None,
    run_id: str | None = None,
) -> tuple[dict, LlmUsage]:
    """Chat completion parsed as JSON.

    Models sometimes fence JSON in markdown despite being asked not to, so the
    fence is stripped rather than treated as a failure - one retry costs three
    seconds of demo time.
    """
    text, usage = complete(messages, model=model, temperature=0.0,
                           json_mode=True, agent=agent, run_id=run_id)
    return _parse_json(text, model or default_model()), usage


def _parse_json(text: str, model: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return _object(json.loads(cleaned[start:end + 1]), model, cleaned)
            except json.JSONDecodeError:
                pass
        raise GatewayError(
            f"model '{model}' did not return valid JSON: {cleaned[:200]}"
        ) from exc
    return _object(parsed, model, cleaned)


def _object(parsed, model: str, cleaned: str) -> dict:
    """Every reply template in ``prompts`` is a JSON object, and every caller
    reads the reply with ``.get``. A model that answers with a bare array or a
    string has not answered the question asked, so it is refused as a gateway
    failure - which routes the caller into the deterministic fallback it already
    has, rather than into an AttributeError halfway down a node."""
    if isinstance(parsed, dict):
        return parsed
    raise GatewayError(
        f"model '{model}' returned {type(parsed).__name__}, not a JSON object: "
        f"{cleaned[:200]}")


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def _embed_key(model: str, text: str) -> str:
    payload = db.dumps({"m": model, "x": text})
    return hashlib.sha256(payload.encode()).hexdigest()


def embed(texts: Sequence[str], model: str | None = None) -> list[list[float]]:
    """Embed a batch, cached the same way completions are.

    This was the one model call in the platform that was not cached, on the
    assumption in its old docstring that only the RAG indexer used it. It is
    not: retrieval embeds the *query* on every search, so each readiness check
    paid a network round trip to ask a question it had already asked - three
    per product view, and the reason opening a product felt slow.

    Only the misses are sent. A batch where two of five texts are new posts one
    request for two inputs and reassembles the batch in order, so a caller
    always gets one vector per text in the order it asked.
    """
    model = model or embed_model()
    wanted = list(texts)
    if not wanted:
        return []

    want_cache = cache_enabled()
    vectors: list[list[float] | None] = [None] * len(wanted)
    keys = [_embed_key(model, text) for text in wanted]

    if want_cache:
        conn = db.connect()
        for i, key in enumerate(keys):
            hit = db.one("SELECT vector FROM llm_embeddings WHERE cache_key = ?",
                         (key,))
            if hit is not None:
                vectors[i] = db.loads(hit["vector"])
                conn.execute(
                    "UPDATE llm_embeddings SET hits = hits + 1 WHERE cache_key = ?",
                    (key,))
        conn.commit()

    missing = [i for i, vector in enumerate(vectors) if vector is None]
    if missing:
        data = _post("/v1/embeddings",
                     {"model": model, "input": [wanted[i] for i in missing]})
        items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        fresh = [item["embedding"] for item in items]
        if len(fresh) != len(missing):
            raise GatewayError(
                f"embedding count mismatch: asked for {len(missing)}, "
                f"got {len(fresh)}"
            )
        for position, vector in zip(missing, fresh):
            vectors[position] = vector
        if want_cache:
            conn = db.connect()
            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany(
                "INSERT OR REPLACE INTO llm_embeddings"
                " (cache_key, model, text, vector, created_at, hits)"
                " VALUES (?, ?, ?, ?, ?, 0)",
                [(keys[i], model, wanted[i], db.dumps(vectors[i]), now)
                 for i in missing])
            conn.commit()

    return [vector for vector in vectors if vector is not None]


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def _post(path: str, body: dict) -> dict:
    url = f"{base_url()}{path}"
    last_error = ""

    if circuit_open():
        # Known unreachable. Fail now rather than paying the connect timeout
        # again on every call for the rest of the run.
        raise GatewayError(
            f"LiteLLM gateway at {base_url()} is unreachable "
            f"(retrying in {circuit_state()['retry_in_seconds']:.0f}s). "
            "Start it with 'python run.py', or check LITELLM_PORT.")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(url, json=body, headers=_auth_headers(),
                                  timeout=DEFAULT_TIMEOUT)
        except httpx.ConnectError as exc:
            _record_connection_failure()
            raise GatewayError(
                f"cannot reach the LiteLLM gateway at {base_url()}. "
                "Start it with 'python run.py', or check LITELLM_PORT."
            ) from exc
        except httpx.TimeoutException as exc:
            last_error = f"timed out after {DEFAULT_TIMEOUT:.0f}s"
            if attempt == MAX_ATTEMPTS:
                raise GatewayError(f"gateway request {last_error}") from exc
            continue

        if response.status_code == 200:
            reset_circuit()
            return response.json()

        last_error = response.text[:400]
        # Rate limits are worth waiting out; nothing else is.
        if response.status_code != 429 or attempt == MAX_ATTEMPTS:
            raise GatewayError(_explain(response.status_code, last_error))
        time.sleep(0.5 * attempt)

    raise GatewayError(f"gateway request failed: {last_error}")


def _explain(status: int, body: str) -> str:
    """Turn provider errors into something actionable.

    A demo that dies on 'HTTP 401' wastes minutes; one that says the key is
    missing is fixed in seconds.
    """
    lowered = body.lower()
    if "api key not valid" in lowered or "api_key_invalid" in lowered or status == 401:
        return ("the provider rejected the request: GEMINI_API_KEY is missing or "
                "invalid in the gateway's environment. Check .env and restart.")
    if status == 404 or "not found" in lowered:
        return ("the selected model is not configured in litellm/config.yaml. "
                "Pick one of the listed aliases or add it there.")
    if status == 429:
        return "the provider is rate limiting. Retries are exhausted; wait and retry."
    return f"gateway request failed ({status}): {body[:200]}"


def _usage(data: dict) -> LlmUsage:
    usage = data.get("usage") or {}
    cost = (usage.get("response_cost")
            or usage.get("cost")
            or data.get("response_cost")
            or (data.get("_hidden_params") or {}).get("response_cost")
            or 0.0)
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return LlmUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=int(usage.get("total_tokens") or prompt + completion),
        cost_usd=float(cost),
        cached=False,
    )


def _record(key, model, temperature, messages, response, usage, latency_ms,
            agent, run_id) -> None:
    conn = db.connect()
    conn.execute(
        "INSERT INTO llm_calls (cache_key, model, temperature, request, response,"
        " prompt_tokens, completion_tokens, cost_usd, latency_ms, created_at,"
        " hits, run_id, agent) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)"
        " ON CONFLICT(cache_key) DO UPDATE SET hits = llm_calls.hits + 1",
        (key, model, temperature, db.dumps(list(messages)), response,
         usage.prompt_tokens, usage.completion_tokens, usage.cost_usd,
         round(latency_ms, 2), datetime.now().isoformat(), run_id, agent),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Introspection - powers the System Control tab
# ---------------------------------------------------------------------------


def available_models() -> list[ModelInfo]:
    """Ask the gateway what it actually serves.

    Nothing here names a model. Two lists of aliases used to live in this file
    as the offline fallback, and every one of them had gone stale against
    ``litellm/config.yaml`` - so a gateway outage produced a picker full of
    aliases the gateway would have 404'd on. A wrong answer offered
    confidently is worse than an empty one.

    When the gateway cannot be reached the registry answers from the shipped
    configuration, which it parses rather than duplicates, and says the answer
    came from a fallback. When there is no configuration either, the honest
    answer is that no model is available.
    """
    from sc.llm import models as model_registry

    listing = model_registry.list_models(refresh=True)
    return [ModelInfo(id=m["id"], tier=m["tier"]) for m in listing["models"]]


def health() -> dict:
    """Probe the gateway. A successful probe closes the circuit breaker, so
    starting the gateway mid-session recovers without a restart."""
    if circuit_open():
        return {"ok": False, "url": base_url(), "circuit": circuit_state(),
                "detail": "circuit breaker open after repeated connection "
                          "failures; not attempting a connection"}
    try:
        response = httpx.get(f"{base_url()}/health/readiness", timeout=5.0)
        ok = response.status_code == 200
        if ok:
            reset_circuit()
        else:
            _record_connection_failure()
        return {"ok": ok, "url": base_url(), "circuit": circuit_state(),
                "detail": response.json() if ok else response.text[:200]}
    except Exception as exc:
        _record_connection_failure()
        return {"ok": False, "url": base_url(), "circuit": circuit_state(),
                "detail": str(exc)[:200]}


def usage_summary(run_id: str | None = None) -> dict:
    """Token and cost ledger for the audit view."""
    where, params = ("WHERE run_id = ?", (run_id,)) if run_id else ("", ())
    row = db.one(
        f"SELECT COUNT(*) AS calls, SUM(hits) AS cache_hits,"
        f" SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion,"
        f" SUM(cost_usd) AS cost, AVG(latency_ms) AS avg_latency"
        f" FROM llm_calls {where}", params)
    return {
        "calls": row["calls"] or 0,
        "cache_hits": row["cache_hits"] or 0,
        "prompt_tokens": row["prompt"] or 0,
        "completion_tokens": row["completion"] or 0,
        "cost_usd": round(row["cost"] or 0.0, 6),
        "avg_latency_ms": round(row["avg_latency"] or 0.0, 1),
    }
