"""Generate the back-office reference pack.

    python scripts/generate_backoffice.py           # write data/backoffice.jsonl
    python scripts/generate_backoffice.py --check   # verify, write nothing

Four systems' worth of reference data - stock, trading, campaigns and the
certificate register - derived from the seed and from the catalog that
``scripts/generate_data.py`` already wrote. Run it after that one; it reads
``catalog.json`` and ``attributes.jsonl`` and will say so if they are missing.

Unlike ``generate_data.py`` this may import ``sc``. That rule exists so the
answer key in ``data/golden/`` has an author independent of the code being
graded; this pack grades nothing, and reusing the payload models is what keeps
the generator and the projection from drifting apart about a field name.

``--check`` rebuilds the pack twice and compares, which is the property the
whole file is arranged around: same seed, same bytes, any machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as a script from anywhere - `python scripts/generate_backoffice.py` puts
# scripts/ on sys.path, not the project root, so `sc` would not import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap  # noqa: E402
from sc.kg import synth  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="build twice and compare; write nothing")
    parser.add_argument("--seed", type=int, default=None,
                        help=f"override DATA_SEED (default {synth.DEFAULT_SEED})")
    parser.add_argument("--out", type=Path, default=None,
                        help="where to write (default $DATA_DIR/backoffice.jsonl)")
    args = parser.parse_args()

    bootstrap.load_env()

    try:
        if args.check:
            first = json.dumps(synth.build(args.seed), sort_keys=True)
            second = json.dumps(synth.build(args.seed), sort_keys=True)
            if first != second:
                print("  ! the pack is not reproducible for this seed",
                      file=sys.stderr)
                raise SystemExit(1)
            print(f"  reproducible: {len(json.loads(first))} events")
            return

        result = synth.write(args.out, args.seed)
    except FileNotFoundError as exc:
        # The commonest way to run this wrong is to run it first.
        print(f"  ! {exc}", file=sys.stderr)
        print("    the seed pack has to exist before the reference pack can be",
              file=sys.stderr)
        print("    derived from it: python scripts/generate_data.py",
              file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"  wrote {result['path']}")
    print(f"  {result['events']} events")
    for event_type, count in sorted(result["by_type"].items()):
        print(f"    {event_type:<16} {count:>4}")
    print()
    print("  Loaded at boot by sc.bootstrap.ensure_ready, onto the REF lane.")
    print("  The transport does not play it and the live feed does not"
          " announce it.")


if __name__ == "__main__":
    main()
