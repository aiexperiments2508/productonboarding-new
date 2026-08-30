"""Model discovery, tier classification, hot reload and .env write-back."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_models.db")
os.environ.setdefault("ENV_FILE", "data/test_models.env")

from sc import db  # noqa: E402
from sc.llm import env_file, gateway, models  # noqa: E402

EXAMPLE = Path(".env.example")


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    path = Path(os.environ["ENV_FILE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    models._CACHE.update({"models": None, "fetched_at": 0.0})
    yield
    db.close()
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_id,tier", [
    ("gemini-2.5-pro", "reasoning"),
    ("gemini-3.1-pro-preview", "reasoning"),
    ("claude-opus-4-5", "reasoning"),
    ("gemini-flash", "fast"),
    ("gemini-2.5-flash-lite", "fast"),
    ("gpt-4o-mini", "fast"),
    ("claude-haiku-4-5", "fast"),
    ("gemini-embedding-001", "embedding"),
    ("text-embedding-3-large", "embedding"),
])
def test_tier_classification(model_id, tier):
    assert models.classify(model_id) == tier


def test_gemini_is_not_mistaken_for_a_mini_model():
    """The substring trap: "gemini" contains "mini".

    Matching hints as substrings files every Gemini model - Pro included - as a
    small model, which silently routes the reasoning work to the cheap tier.
    Tokens, not substrings.
    """
    assert models.classify("gemini-2.5-pro") == "reasoning"
    assert models.classify("gemini-2.5-pro") != models.classify("gpt-4o-mini")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _shipped_aliases() -> set[str]:
    """The model_name entries in litellm/config.yaml, read the way _fallback
    reads them."""
    import re as _re

    text = Path("litellm/config.yaml").read_text(encoding="utf-8")
    return set(_re.findall(r"^\s*-\s*model_name:\s*(\S+)\s*$", text, _re.MULTILINE))


def test_fallback_is_parsed_from_the_shipped_config():
    """With no gateway reachable, the list comes from litellm/config.yaml so it
    cannot drift from what the gateway would actually serve.

    Asserted against the file rather than against a hard-coded alias: pinning a
    name here would mean retuning the deployment's model list breaks a test
    about parsing.
    """
    listing = models.list_models(refresh=True)
    ids = {m["id"] for m in listing["models"]}

    assert listing["source"] == "fallback"
    assert listing["error"]
    assert ids == _shipped_aliases()
    assert any(models.classify(i) == "embedding" for i in ids)


def test_listing_groups_by_tier():
    """Every model lands in exactly one tier.

    Note what is NOT asserted: that the reasoning tier is populated. A gateway
    serving only flash-class models genuinely has none, and demanding one here
    would make the test a claim about a particular deployment.
    """
    listing = models.list_models(refresh=True)
    by_tier = listing["by_tier"]

    assert by_tier["fast"]
    assert by_tier["embedding"]

    grouped = [m for tier in ("fast", "reasoning", "embedding")
               for m in by_tier[tier]]
    assert sorted(grouped) == sorted(m["id"] for m in listing["models"])


def test_reasoning_degrades_to_the_strongest_fast_model():
    """A tier with nothing in it must not be a failure.

    Node code asks for "the reasoning model" unconditionally. On a flash-only
    gateway the honest answer is the best model available, not an exception
    raised in the middle of a run.
    """
    listing = models.list_models(refresh=True)
    if listing["by_tier"]["reasoning"]:
        pytest.skip("this gateway serves a reasoning tier")

    chosen = models.resolve_tier("reasoning")
    assert chosen in listing["by_tier"]["fast"]


def test_a_tier_can_be_pinned_per_deployment(monkeypatch):
    """Tier hints read names, and several flash-class models differ in
    capability but not in name. A deployment gets the last word."""
    listing = models.list_models(refresh=True)
    target = sorted(listing["by_tier"]["fast"])[0]

    monkeypatch.setenv("LITELLM_REASONING_MODEL", target)
    assert models.resolve_tier("reasoning") == target


def test_a_pin_the_gateway_does_not_serve_is_refused(monkeypatch):
    """A retired alias should surface here, not as a 404 from inside a run."""
    monkeypatch.setenv("LITELLM_REASONING_MODEL", "gemini-9.9-imaginary")

    with pytest.warns(RuntimeWarning):
        chosen = models.resolve_tier("reasoning")

    assert chosen != "gemini-9.9-imaginary"
    assert chosen in {m["id"] for m in models.list_models()["models"]}


# ---------------------------------------------------------------------------
# Selection: hot reload plus persistence
# ---------------------------------------------------------------------------


def test_selection_is_hot_loaded_and_persisted():
    target = sorted(models.list_models(refresh=True)["by_tier"]["fast"])[0]
    result = models.select(model=target)

    assert result["active_model"] == target
    # hot: effective immediately, without a restart
    assert os.environ["LITELLM_DEFAULT_MODEL"] == target
    assert gateway.default_model() == target
    # persistent: survives one
    assert env_file.read()["LITELLM_DEFAULT_MODEL"] == target


def test_write_back_preserves_comments_and_other_keys():
    """The team hand-edits .env. A rewrite that drops the documentation of what
    each setting does would be worse than not persisting at all."""
    before = Path(os.environ["ENV_FILE"]).read_text(encoding="utf-8")
    models.select(model="gemini-2.5-pro", cache_enabled=False)
    after = Path(os.environ["ENV_FILE"]).read_text(encoding="utf-8")

    comments = lambda t: [l for l in t.splitlines() if l.startswith("#")]  # noqa: E731
    # Every existing comment survives. Writing a key that was not present adds
    # the managed-section header, so the set may grow - it must never shrink.
    assert set(comments(before)) <= set(comments(after))
    assert "GEMINI_API_KEY" in after


def test_write_back_never_invents_a_credential():
    """Updating a key that exists is fine. Creating a secret is not."""
    path = Path(os.environ["ENV_FILE"])
    path.write_text("# minimal\nAPI_PORT=8000\n", encoding="utf-8")

    result = env_file.update({"GEMINI_API_KEY": "leaked-secret",
                              "LITELLM_DEFAULT_MODEL": "gemini-flash"})

    assert "GEMINI_API_KEY" in result["skipped"]
    assert "leaked-secret" not in path.read_text(encoding="utf-8")
    assert result["created"]["LITELLM_DEFAULT_MODEL"] == "gemini-flash"


def test_cache_toggle_round_trips():
    models.select(cache_enabled=False)
    assert gateway.cache_enabled() is False
    assert env_file.read()["LLM_CACHE"] == "0"

    models.select(cache_enabled=True)
    assert gateway.cache_enabled() is True
    assert env_file.read()["LLM_CACHE"] == "1"


def test_embed_model_selection_is_honoured_at_runtime():
    models.select(embed_model="gemini-embedding-2")
    assert gateway.embed_model() == "gemini-embedding-2"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_model_is_rejected_before_it_reaches_a_run():
    """Failing here is cheap. Failing inside a graph run is not."""
    result = models.select(model="definitely-not-a-model")
    assert result["error"] == "unknown_model"
    assert "LITELLM_DEFAULT_MODEL" not in env_file.read() or \
        env_file.read()["LITELLM_DEFAULT_MODEL"] != "definitely-not-a-model"


def test_embedding_model_cannot_be_selected_for_chat():
    result = models.select(model="gemini-embedding-001")
    assert result["error"] == "wrong_tier"


def test_no_change_writes_nothing():
    before = Path(os.environ["ENV_FILE"]).read_text(encoding="utf-8")
    models.select()
    assert Path(os.environ["ENV_FILE"]).read_text(encoding="utf-8") == before
