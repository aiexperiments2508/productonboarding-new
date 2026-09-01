"""Make the process usable regardless of how it was entered.

There are several front doors to this system - the FastAPI app, LangGraph
Studio, the MCP server, and the build/demo scripts - and only the first one
used to set anything up. Studio imports ``build_graph`` and nothing else, so on
a fresh machine it ran the graph against a database with no schema and an event
table with no events: the graph found nothing wrong and parked immediately,
which looks like a broken agent rather than a missing setup step.

The same argument applies to configuration. ``run.py`` read .env and no other
door did, so a script that needed the model gateway looked for it on the
default port and reported it unreachable while the app three metres away was
talking to it happily. Reading .env belongs to entry, not to one entry point.

Everything here is idempotent, so any door can call it on every entry.
"""

from __future__ import annotations

import os
from pathlib import Path

from sc import db

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> bool:
    """Read .env into the environment. Returns whether a file was found.

    Uses ``setdefault``, so a real environment variable and a command-line
    override both still win over the file - which is what lets a test pin
    DB_PATH before importing anything and not have it quietly replaced.

    Deliberately hand-rolled rather than python-dotenv: this runs before
    dependencies are guaranteed importable, and the format we use is one
    KEY=value per line.
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


def ensure_ready(index: bool = True) -> dict:
    """Schema, event tape, and retrieval index. Safe to call repeatedly.

    ``index`` builds the lexical half only - embeddings need the gateway, and
    a front door should open without waiting on a network call.

    The reference pack loads beside the tape rather than on the clock. It is
    not part of the recording - see the lane note in ``sc/replay/tape.py`` -
    and a knowledge graph that only filled in once somebody pressed play would
    be a graph nobody ever saw. A checkout that has not generated the pack yet
    boots without it.
    """
    from sc.replay import tape

    db.init_db()
    tape_status = tape.load_tape()
    reference_status = tape.load_reference()

    index_status: dict = {"skipped": True}
    if index:
        from sc.rag import index as rag_index

        if rag_index.status()["chunks"] == 0:
            index_status = rag_index.build(embed=False)

    return {"events": tape_status.get("total", 0),
            "reference": reference_status.get("total", 0),
            "index": index_status}


def release_to_inject(extra_steps: int = 12) -> dict:
    """Advance the replay clock to just past the finale inject.

    Used when opening a door that has no replay controls of its own - Studio
    can run the graph but cannot drive the tape, and a graph with nothing to
    recover from demonstrates nothing.
    """
    from sc.replay import ingest, tape

    ensure_ready()
    target = tape.inject_seq() + extra_steps
    released = tape.jump_to(target)
    signals = ingest.ingest(released)

    return {
        "released": len(released),
        "signals": len(signals),
        "cursor": tape.cursor(),
        "sim_clock": tape.sim_now().isoformat(),
    }
