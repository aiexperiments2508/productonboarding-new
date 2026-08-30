"""Build the retrieval index.

    python scripts/build_index.py            # semantic + lexical
    python scripts/build_index.py --lexical  # skip embeddings

Needs the gateway running for the semantic half. The lexical half always
builds, so the system still retrieves when the gateway is unavailable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a script from anywhere - `python scripts/build_index.py` puts
# scripts/ on sys.path, not the project root, so `sc` would not import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap, db  # noqa: E402
from sc.rag import index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexical", action="store_true",
                        help="skip embeddings; BM25 only")
    parser.add_argument("--no-comms", action="store_true",
                        help="index the reference corpus only")
    args = parser.parse_args()

    # Without this the embedding half looks for the gateway on the default
    # port and reports it unreachable, while the app is talking to the one
    # named in .env.
    bootstrap.load_env()
    db.init_db()
    result = index.build(include_comms=not args.no_comms, embed=not args.lexical)

    if result.get("error"):
        print(f"  ! {result['error']}", file=sys.stderr)
        raise SystemExit(1)

    print(f"  {result['chunks']} chunks from {result['documents']} documents")
    for doc_type, n in sorted(result["by_type"].items()):
        print(f"    {doc_type:12s} {n:4d}")

    if result["embedded"]:
        print(f"  embedded via {result['model']} ({result['dimensions']} dims)")
    else:
        print("  lexical only - BM25 index built, no embedding matrix")
        if result.get("embed_error"):
            print(f"    reason: {result['embed_error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
