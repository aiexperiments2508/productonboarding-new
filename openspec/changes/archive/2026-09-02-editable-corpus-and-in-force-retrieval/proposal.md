## Why

The documents this system is answerable to are twenty-nine markdown files you
need a checkout and a shell to touch. They are not reference material.
`saleability` retrieves REGULATION, `internal_contradiction` retrieves INTERNAL
and `policy_conformance` retrieves POLICY, and between them they decide what
publishes. A retailer who cannot add a regulation without a developer is a
retailer whose compliance surface is as current as its last deployment.

Three things about the corpus are wrong today, and each is quieter than the one
before.

**Retrieval does not know what day it is.** Front matter has always carried an
`effective:` date and nothing has ever looked at it. A rule that commences in
December is a real document with a real identifier: it retrieves cleanly, the
excerpt reads correctly, the citation resolves, and every anti-fabrication gate
in this system passes it - because nothing downstream knows the date. That is
the same class of error as citing a withdrawn policy, and it is harder to see.

**The embedding matrix is paired with the chunk list by length.** A chunk
identifier is the document and an ordinal, so rewording a sentence inside a
document leaves every identifier in the corpus exactly as it was. A length
check would wave the old matrix through to sit against text it was never built
from. Row N would still be *a* vector for chunk N, just the wrong one, and
every citation that followed would be specific, confident and wrong. Nothing
creates that case today - and an editable corpus creates it on the first save.

**Fusion decides what is plausible and nothing decides what is relevant.** RRF
knows BM25 put a passage third and the embedding put it seventh, and has no way
to notice it is the "Related documents" section of the right document rather
than the rule itself.

There is a smaller gap beside these: seven citation chips in the console render
a document identifier and do nothing, and the Ask panel throws away the
reference it has already computed.

## What Changes

- **A policy library in System Control** that can add, edit, upload, retire and
  destroy corpus documents, with an actor on every mutation and a row in the
  ledger - the same way the autonomy threshold works.
- **No path ever arrives from a client.** A caller names a document identifier;
  the server finds the file by reading front matter and composes the path
  itself when creating one. There is no traversal to filter because there is no
  caller-supplied path to traverse, which is a stronger guarantee than any
  amount of `..` stripping and does not have to be right about Windows drive
  letters to hold.
- **Removal is retirement first.** A retired document stops producing chunks
  and keeps its file, because a decision taken while it was in force has to stay
  readable against it. Destroying it is a second, separately armed act that
  refuses to run until the first has happened, and writes the whole text into
  the ledger before unlinking.
- **What would notice a document leaving is shown before it leaves**: the
  identifiers the code names literally, and whether this is the last active
  member of a load-bearing type. Retiring the last REGULATION makes every
  product *pass* the check that exists to stop it and reports the assessment as
  complete - a fail-open that reads as a clean run is the worst shape a
  compliance failure can take.
- **Saving rebuilds the lexical half only**, which is what makes editing feel
  free: no gateway, no tokens, milliseconds. Embedding stays a separate,
  explicit act because it costs money and can fail.
- **A fingerprint of the chunk identifiers *and their text*** is stamped when a
  matrix is written and checked on every load. A matrix from before the check
  is accepted as an upgrade and reported unverified rather than refused,
  because switching dense search off on every installation that has not
  reindexed is a worse failure and a quieter one.
- **Uploads read markdown, .txt and .docx with nothing installed**; PDF is
  feature-detected. Extraction is advisory: it fills the editor and a person
  presses save.
- **Retrieval filters on commencement**, as of the replay clock rather than as
  of today. An undated passage is always in force, and so is one whose date will
  not parse - a typo should cost a document its date, not its presence.
  Commencement is precomputed onto the index rather than parsed per chunk per
  query.
- **A reranker, off by default.** It can never invent a passage, never drop
  one, and never fail quietly - a dead gateway leaves the fused order untouched
  and says so, because reranking that silently did not happen looks identical to
  reranking that happened and agreed.
- **Citations are followable**: the peek opens on the passage retrieval scored
  and offers the whole document beneath it, falling back to the file on disk
  for a document the index no longer holds - which is exactly when a reader
  most needs it.

## Capabilities

### New Capabilities

- `corpus-library`: authoring, editing, uploading, retiring and destroying the
  documents the factory is answerable to, under an actor and a lock.

### Modified Capabilities

- `standards-retrieval`: a passage whose document has not commenced is not
  returned; the embedding matrix is paired with the chunk list by content
  rather than by length; a fused result list may be reordered by a reranker
  that can neither invent nor drop.

## Impact

- `sc/rag/library.py` - new; the door, the lock, the audit and the refusals.
- `sc/rag/extract.py` - new; docx via `zipfile`, PDF behind a feature check.
- `sc/rag/rerank.py` - new; off by default.
- `sc/rag/index.py` - the fingerprint, the build lock, the precomputed
  commencement dates.
- `sc/rag/chunk.py` - a retired document produces no chunks, filtered where the
  corpus is walked rather than where a file is read.
- `sc/rag/retrieve.py` - the in-force filter, the as-of default, the deeper
  candidate read when reranking.
- `sc/main.py` - the corpus routes and the rerank switch.
- `requirements-corpus.txt` - `pypdf`, named in its own file.
- `frontend/src/components/**` - the library editor, and the citation chips
  made live.
- `tests/test_corpus_library.py`, `tests/test_rerank.py`, `tests/test_rag.py`.
