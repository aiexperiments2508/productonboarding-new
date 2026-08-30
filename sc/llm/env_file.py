"""Read and update ``.env`` in place, preserving comments and ordering.

Model selection has to survive a restart, so it is written back to ``.env``
rather than living only in the database. That file is also hand-edited by the
team, so a naive rewrite that drops the comments and reorders the keys would be
actively hostile - the next person to open it would lose the documentation of
what every setting does.

This updates the value on an existing key's own line, appends genuinely new
keys under a marked section, and leaves everything else byte-identical.

Secrets are never introduced by this module. It will update a key that is
already present, but it will not invent ``GEMINI_API_KEY`` into a file that
does not have it - writing a credential to disk is the operator's decision.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

MANAGED_HEADER = "# --- managed by the application (model selection) ---"

# Keys this module is allowed to create if absent. Anything else may only be
# updated where it already exists.
CREATABLE = frozenset({
    "LITELLM_DEFAULT_MODEL",
    "LITELLM_EMBED_MODEL",
    "LITELLM_FAST_MODEL",
    "LITELLM_REASONING_MODEL",
    "LITELLM_HOST",
    "LITELLM_PORT",
    "LLM_CACHE",
    "USE_A2A",
    "USE_MCP",
})

_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")


def env_path() -> Path:
    return Path(os.environ.get("ENV_FILE", ".env"))


def read() -> dict[str, str]:
    path = env_path()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE.match(line)
        if match:
            values[match.group(2)] = match.group(4).strip()
    return values


def ensure_exists() -> Path:
    """Create ``.env`` from the example if it is missing.

    The example carries no live credential, so this is safe: it produces a
    documented file with placeholder values rather than a secret.
    """
    path = env_path()
    if path.exists():
        return path
    example = Path(".env.example")
    if example.exists():
        path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        path.write_text(f"{MANAGED_HEADER}\n", encoding="utf-8")
    return path


def update(values: dict[str, str], create_missing: bool = True) -> dict:
    """Write values back, preserving the rest of the file exactly.

    Returns what was changed so the caller can report it rather than claiming
    a write that did not happen.
    """
    path = ensure_exists()
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()

    remaining = dict(values)
    updated: dict[str, str] = {}
    out: list[str] = []

    for line in lines:
        match = _LINE.match(line)
        if match and match.group(2) in remaining:
            key = match.group(2)
            new_value = remaining.pop(key)
            if match.group(4).strip() != new_value:
                updated[key] = new_value
            # Rebuild the line, keeping indentation and spacing around '='.
            out.append(f"{match.group(1)}{key}{match.group(3)}{new_value}")
        else:
            out.append(line)

    appended: dict[str, str] = {}
    if create_missing:
        creatable = {k: v for k, v in remaining.items() if k in CREATABLE}
        if creatable:
            if MANAGED_HEADER not in original:
                if out and out[-1].strip():
                    out.append("")
                out.append(MANAGED_HEADER)
            for key, value in creatable.items():
                out.append(f"{key}={value}")
                appended[key] = value

    skipped = sorted(set(remaining) - set(appended))
    text = "\n".join(out).rstrip("\n") + "\n"
    if text != original:
        path.write_text(text, encoding="utf-8")

    return {"path": str(path), "updated": updated, "created": appended,
            "skipped": skipped}


def apply_to_process(values: dict[str, str]) -> None:
    """Hot-load: make the change effective immediately, without a restart.

    ``os.environ`` is assigned directly rather than via ``setdefault`` - the
    point is to override what the process started with.
    """
    for key, value in values.items():
        os.environ[key] = value
