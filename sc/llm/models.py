"""Live model discovery and selection.

The model list is read from the gateway's ``/v1/models`` at runtime rather than
hard-coded. Adding a model to ``litellm/config.yaml`` and restarting the
gateway is therefore enough to make it selectable in the UI - no application
change, no redeploy, no list to keep in sync in two places.

Selecting a model takes effect on three levels at once:

*   **database** - the authoritative runtime value, read on every call;
*   **process environment** - so anything reading ``os.environ`` agrees;
*   **.env** - so the choice survives a restart.

All three are written together. Writing only the database would silently revert
on the next launch; writing only ``.env`` would need a restart to take effect.
"""

from __future__ import annotations

import os
import re
import time
import warnings
from typing import Any

import httpx

from sc import db
from sc.contracts import LlmConfig, ModelInfo
from sc.llm import env_file, gateway

# Tier hints, matched against whole tokens of the model id rather than as raw
# substrings. Substring matching is a trap here: "gemini" contains "mini", so a
# naive check files every Gemini model - including the Pro tier - as a small
# model. Splitting on separators first makes "mini" match gpt-4o-mini and not
# gemini-2.5-pro.
_EMBEDDING_HINTS = frozenset({"embed", "embedding", "embeddings"})
_REASONING_HINTS = frozenset({"pro", "opus", "reasoning", "thinking", "o1", "o3"})
_LITE_HINTS = frozenset({"lite", "mini", "small", "nano", "haiku", "8b"})

_SEPARATORS = re.compile(r"[-_./:\s]+")

_CACHE: dict[str, Any] = {"models": None, "fetched_at": 0.0, "source": "none"}
CACHE_TTL = 30.0


def classify(model_id: str) -> str:
    """Group a model id into a tier for the UI's model picker.

    Tokens, not substrings - see the note on the hint sets above.
    """
    tokens = {t for t in _SEPARATORS.split(model_id.lower()) if t}
    if tokens & _EMBEDDING_HINTS:
        return "embedding"
    if tokens & _LITE_HINTS:
        return "fast"
    if tokens & _REASONING_HINTS:
        return "reasoning"
    return "fast"


def fetch_live(timeout: float = 8.0) -> tuple[list[ModelInfo], str, str | None]:
    """Ask the gateway what it serves right now.

    Returns (models, source, error). ``source`` distinguishes a live answer
    from the configured fallback, so the UI can say which it is showing rather
    than presenting stale data as current.
    """
    url = f"{gateway.base_url()}/v1/models"
    try:
        response = httpx.get(url, headers=gateway._auth_headers(), timeout=timeout)
    except httpx.ConnectError:
        return _fallback(), "fallback", (
            f"gateway not reachable at {gateway.base_url()}")
    except Exception as exc:
        return _fallback(), "fallback", str(exc)[:200]

    if response.status_code == 401:
        return _fallback(), "fallback", (
            "gateway requires an API key - set LITELLM_API_KEY to the "
            "gateway's master key")
    if response.status_code != 200:
        return _fallback(), "fallback", (
            f"gateway returned {response.status_code}: {response.text[:150]}")

    try:
        data = response.json().get("data", [])
    except Exception:
        return _fallback(), "fallback", "gateway returned a non-JSON model list"

    ids = sorted({m.get("id") for m in data if m.get("id")})
    if not ids:
        return _fallback(), "fallback", "gateway reported no models"

    return [ModelInfo(id=i, tier=classify(i)) for i in ids], "gateway", None


def _fallback() -> list[ModelInfo]:
    """Aliases from the shipped config, used when the gateway cannot answer.

    Parsed from litellm/config.yaml rather than duplicated in code, so the
    fallback cannot drift from what the gateway would actually serve.
    """
    from pathlib import Path
    import re

    path = Path("litellm/config.yaml")
    if not path.exists():
        return [ModelInfo(id="gemini-flash", tier="fast")]
    names = re.findall(r"^\s*-\s*model_name:\s*(\S+)\s*$",
                       path.read_text(encoding="utf-8"), re.MULTILINE)
    return [ModelInfo(id=n, tier=classify(n)) for n in sorted(set(names))]


def list_models(refresh: bool = False) -> dict:
    """Cached model list. The UI polls this; the gateway should not be hit
    once per keystroke."""
    now = time.time()
    stale = now - float(_CACHE["fetched_at"]) > CACHE_TTL
    if refresh or _CACHE["models"] is None or stale:
        models, source, error = fetch_live()
        _CACHE.update({"models": models, "fetched_at": now, "source": source,
                       "error": error})

    models: list[ModelInfo] = _CACHE["models"]
    return {
        "models": [m.model_dump(mode="json") for m in models],
        "by_tier": {
            tier: [m.id for m in models if m.tier == tier]
            for tier in ("fast", "reasoning", "embedding")
        },
        "source": _CACHE["source"],
        "error": _CACHE.get("error"),
        "fetched_at": _CACHE["fetched_at"],
    }


def resolve_tier(tier: str, fallback: str | None = None) -> str:
    """Pick the best model the gateway actually serves for a tier.

    Node code asks for "the reasoning model", not for a specific alias.
    Hard-coding one couples the graph to a particular deployment: point it at a
    gateway that serves a different catalogue and every call fails with a 404
    from inside a run, which is a slow and confusing way to discover a config
    mismatch.

    When a tier is empty - a gateway serving only flash-class models has no
    reasoning tier - this falls back to the strongest fast model rather than
    failing. Degrading to a smaller model is better than not answering.

    A deployment can override the heuristic per tier with
    ``LITELLM_FAST_MODEL`` / ``LITELLM_REASONING_MODEL``. That is the honest
    answer for a gateway whose catalogue the tier hints cannot read - several
    flash-class models that differ in capability but not in name. The pin is
    checked against what the gateway actually serves rather than trusted: an
    alias that has been retired should surface here, at startup, and not as a
    404 from inside a run.
    """
    listing = list_models()
    by_tier = listing["by_tier"]

    pinned = os.environ.get(f"LITELLM_{tier.upper()}_MODEL", "").strip()
    if pinned:
        served = {m["id"] for m in listing["models"]}
        if not served or pinned in served:
            return pinned
        warnings.warn(
            f"LITELLM_{tier.upper()}_MODEL={pinned!r} is not served by the "
            f"gateway at {gateway.base_url()}; falling back to the {tier} tier",
            RuntimeWarning, stacklevel=2)

    candidates = by_tier.get(tier) or []
    if not candidates and tier == "reasoning":
        candidates = by_tier.get("fast") or []
    if not candidates:
        candidates = [m["id"] for m in listing["models"]
                      if classify(m["id"]) != "embedding"]
    if not candidates:
        return fallback or os.environ.get("LITELLM_DEFAULT_MODEL", "gemini-flash")

    return sorted(candidates, key=_capability_rank, reverse=True)[0]


def _capability_rank(model_id: str) -> tuple:
    """Order models by likely capability, strongest first.

    A heuristic, and openly so: prefer a full model over a cut-down one, then
    the highest version number. It only has to break ties sensibly - the tier
    split has already done the important part.
    """
    tokens = [t for t in _SEPARATORS.split(model_id.lower()) if t]
    is_lite = bool(set(tokens) & _LITE_HINTS)
    version = 0.0
    for token in tokens:
        try:
            version = max(version, float(token))
        except ValueError:
            continue
    return (0 if is_lite else 1, version, model_id)


def current() -> LlmConfig:
    listing = list_models()
    return LlmConfig(
        default_model=gateway.default_model(),
        embed_model=gateway.embed_model(),
        gateway_url=gateway.base_url(),
        cache_enabled=gateway.cache_enabled(),
        available_models=[ModelInfo.model_validate(m) for m in listing["models"]],
    )


def select(model: str | None = None, embed_model: str | None = None,
           cache_enabled: bool | None = None,
           persist: bool = True) -> dict:
    """Change model selection: hot-loaded now, written back to .env.

    Validated against the live list first. Selecting a model the gateway does
    not serve would fail later, inside a graph run, where the error is far
    harder to attribute.
    """
    listing = list_models(refresh=True)
    known = {m["id"] for m in listing["models"]}
    env_values: dict[str, str] = {}
    warnings: list[str] = []

    if model:
        if known and model not in known:
            return {"error": "unknown_model", "model": model,
                    "detail": f"'{model}' is not served by the gateway. "
                              f"Available: {sorted(known)}",
                    "available": sorted(known)}
        if classify(model) == "embedding":
            return {"error": "wrong_tier", "model": model,
                    "detail": f"'{model}' is an embedding model and cannot be "
                              "used for chat completion"}
        db.set_config("active_model", model)
        env_values["LITELLM_DEFAULT_MODEL"] = model

    if embed_model:
        if known and embed_model not in known:
            warnings.append(f"'{embed_model}' is not in the gateway's list")
        db.set_config("embed_model", embed_model)
        env_values["LITELLM_EMBED_MODEL"] = embed_model

    if cache_enabled is not None:
        gateway.set_cache_enabled(cache_enabled)
        env_values["LLM_CACHE"] = "1" if cache_enabled else "0"

    # Hot-load first so the change is live even if the file write fails.
    env_file.apply_to_process(env_values)
    written = env_file.update(env_values) if (persist and env_values) else {}

    return {
        "ok": True,
        "active_model": gateway.default_model(),
        "embed_model": gateway.embed_model(),
        "cache_enabled": gateway.cache_enabled(),
        "hot_loaded": env_values,
        "persisted": written,
        "warnings": warnings,
    }


def test_model(model: str | None = None) -> dict:
    """Round-trip one call so the UI can prove a model works before a run."""
    target = model or gateway.default_model()
    started = time.time()
    try:
        text, usage = gateway.complete(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            model=target, temperature=0.0, use_cache=False)
        return {"ok": True, "model": target, "response": text.strip()[:80],
                "latency_ms": round((time.time() - started) * 1000, 1),
                "usage": usage.model_dump(mode="json")}
    except Exception as exc:
        return {"ok": False, "model": target, "error": str(exc)[:400],
                "latency_ms": round((time.time() - started) * 1000, 1)}
