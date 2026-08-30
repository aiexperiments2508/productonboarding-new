"""Put the system into its demo starting position.

    python scripts/prepare_demo.py            schema, tape, clock
    python scripts/prepare_demo.py --warm     and pay the model calls now

Creates the schema, loads the event tape, builds the lexical retrieval index,
and advances the replay clock past the finale inject so there is a live
correction to resolve.

Needed before opening a front door that cannot drive the replay itself -
LangGraph Studio can run the graph but has no transport controls, so without
this it opens on a clean catalog and the graph correctly does nothing.

``--warm`` runs one correction loop and throws the result away. That sounds
wasteful and is the opposite: every model call in this system is cached in
SQLite keyed on a hash of (model, temperature, messages), so a rehearsal
populates the cache and the run that a room watches reads from it. The point is
not to make the demo faster than it is - the loop finishes in about twenty
seconds cold - but to make it *the same every time*, independent of a venue's
wifi and of whatever a provider's latency is doing that afternoon.

The cache stays honest about itself. A served call is recorded as a hit rather
than as a call, so the usage panel says "four calls, four cache hits" rather
than reporting free work as work done. A cache that flattered the numbers would
undermine the thing it exists to protect.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Run as a script from anywhere - `python scripts/prepare_demo.py` puts
# scripts/ on sys.path, not the project root, so `sc` would not import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap  # noqa: E402


def warm(thread: str = "T-WARM") -> dict:
    """Run one correction loop so the model cache is populated.

    Its output is discarded and its thread is its own, so the warmed run leaves
    no pending approval for a presenter to find and no case half-worked. What it
    leaves behind is rows in ``llm_calls``.

    Never fatal. A venue with no gateway cannot warm a cache and should still
    get a prepared demo - the loop runs on its deterministic fallbacks either
    way, which is the property the whole design rests on.
    """
    from sc import db
    from sc.graph import build as graph_build

    before = db.one("SELECT COUNT(*) AS n FROM llm_calls")["n"]
    started = time.perf_counter()
    try:
        graph_build.start_run("INC-WARM", thread)
    except Exception as exc:  # noqa: BLE001 - a cold cache is not a failure
        return {"warmed": False, "reason": str(exc)[:200], "calls": 0,
                "seconds": round(time.perf_counter() - started, 1)}

    after = db.one("SELECT COUNT(*) AS n FROM llm_calls")["n"]
    return {"warmed": True, "reason": "", "calls": after - before,
            "seconds": round(time.perf_counter() - started, 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--warm", action="store_true",
        help="run one correction loop so the model cache is populated")
    args = parser.parse_args()

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

    if args.warm:
        result = warm()
        if result["warmed"]:
            print(f"  warmed the cache: {result['calls']} model call(s) in "
                  f"{result['seconds']}s - the next run of the same correction "
                  f"reads them back")
        else:
            print(f"  ! could not warm the cache: {result['reason']}",
                  file=sys.stderr)
            print("    The loop still runs on its deterministic fallbacks.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
