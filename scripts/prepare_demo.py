"""Put the system into its demo starting position.

    python scripts/prepare_demo.py

Creates the schema, loads the event tape, builds the lexical retrieval index,
and advances the replay clock past the finale inject so there is a live
correction to resolve.

Needed before opening a front door that cannot drive the replay itself -
LangGraph Studio can run the graph but has no transport controls, so without
this it opens on a clean catalog and the graph correctly does nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a script from anywhere - `python scripts/prepare_demo.py` puts
# scripts/ on sys.path, not the project root, so `sc` would not import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap  # noqa: E402


def main() -> None:
    bootstrap.load_env()
    ready = bootstrap.ensure_ready()
    print(f"  schema and tape ready ({ready['events']} events)")

    state = bootstrap.release_to_inject()
    print(f"  released {state['released']} events -> clock {state['sim_clock']}")
    print(f"  {state['signals']} correction signals ingested")

    if state["signals"] == 0 and state["released"] == 0:
        print("  ! nothing was released - the tape may already be at the end.",
              file=sys.stderr)
        print("    Reset with: python run.py --reset", file=sys.stderr)


if __name__ == "__main__":
    main()
