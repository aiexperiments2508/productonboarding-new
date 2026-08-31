"""Configuration for an application that is not part of the platform.

This is a deliberate copy of ``sc.bootstrap.load_env``, and the duplication is
the point rather than an oversight. These applications reach the platform over
MCP and by no other route; importing ``sc`` to save fifteen lines would make
that claim false in the first line of the first file, and a test would - quite
correctly - start failing.

Fifteen lines is what the boundary costs. It is worth it.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> bool:
    """Read .env into the environment. Returns whether a file was found.

    ``setdefault``, so a real environment variable and a command-line override
    both still win over the file.
    """
    env_path = path or Path(os.environ.get("ENV_FILE") or (ROOT / ".env"))
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    return True


def platform_url() -> str:
    """Where the platform answers.

    From the environment, never a literal. The platform's port is settable in
    ``.env`` and overridable on its command line, and an application that
    hard-coded one would be pointed at whatever else happened to be listening
    there - which looks exactly like the platform being broken.
    """
    load_env()
    explicit = os.environ.get("PLATFORM_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    port = os.environ.get("API_PORT", "8000").strip() or "8000"
    host = os.environ.get("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    return f"http://{host}:{port}"


def port(name: str, default: int) -> int:
    """This application's own port."""
    load_env()
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default
