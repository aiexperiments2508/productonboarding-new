"""knowledge-base - the document system, over MCP.

    python -m sc.mcp.knowledge_base

Read-only. Content standards, channel specifications, policy and postmortems.
Retrieval fuses BM25 with dense search, so an identifier query ("VAR-01B") and
a paraphrase ("can we still change the catalogue") both land - the two failure
modes have different cures and the corpus needs both.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.rag import retrieve

mcp = FastMCP("knowledge-base")


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


@mcp.tool()
def search_docs(query: str, top_k: int = 5, doc_types: str | None = None,
                entities: str | None = None,
                include_comms: bool = False) -> dict:
    """Hybrid search over standards, channel specs, policies and postmortems.

    doc_types / entities: comma-separated filters, e.g. "POSTMORTEM" or
    "SUP-01,VAR-01B". Correspondence is excluded unless include_comms is set -
    an email is evidence, not guidance.
    """
    def run() -> dict:
        results = retrieve.search(
            query, top_k=top_k,
            doc_types=_csv(doc_types), entities=_csv(entities),
            include_comms=include_comms)
        return {"query": query, "results": retrieve.cite(results)}

    run.__name__ = "search_docs"
    return instrumented(run)()


@mcp.tool()
def get_doc(doc_id: str) -> dict:
    """Full text of one document, in order."""
    def run() -> dict:
        chunks = retrieve.get_document(doc_id)
        if not chunks:
            return {"error": f"no document {doc_id}"}
        return {"doc_id": doc_id, "title": chunks[0].title,
                "doc_type": chunks[0].doc_type,
                "metadata": chunks[0].metadata,
                "text": "\n\n".join(c.text for c in chunks)}

    run.__name__ = "get_doc"
    return instrumented(run)()


if __name__ == "__main__":
    serve(mcp, "knowledge-base")
