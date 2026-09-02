## Context

Every failure this change guards against is a *quiet* one. A withdrawn document
that still retrieves, a rule that has not commenced, a matrix sitting against
text it was not built from, a compliance check that passes because there is
nothing left to check it against - none of them raises, and all of them produce
answers that look exactly like correct answers. That is what the decisions below
are shaped around.

## Decisions

### No path arrives from a client

A caller names a document identifier. The library finds the file by reading
front matter across the corpus tree, and composes the path itself when creating
one.

This is a stronger guarantee than filtering. There is no traversal to defend
against because there is no caller-supplied path to traverse - and unlike
`..`-stripping, it does not have to be right about Windows drive letters, UNC
prefixes or normalisation order to hold. The identifier itself is validated
against a narrow pattern, and the composed path is asserted to be inside the
corpus root as a second line rather than the first.

### Removal is retirement, and destruction is a separately armed second act

A retired document keeps its file and its history and stops producing chunks.
"What did this say when the decision was made" has to stay answerable after the
document stops governing anything.

Destroying it refuses to run until the retirement has happened, and writes the
whole text into the audit ledger before unlinking. Recoverable has to mean
recoverable when the branch was never committed.

**The status filter lives where the corpus is walked, not where a file is
read.** `chunk_document` answers "what chunks does this text produce", which is
a fact about the text; `chunk_corpus` answers "what is in the index", which is a
fact about what is in force. Putting the filter in the first would move a
status under the tests asserting the second.

### What would notice a document leaving is shown before it leaves

This is the sharp edge of the whole feature, and it is worth stating plainly:
`saleability` returns no findings and reports the assessment complete when
nothing is retrieved. So do the other two reading checks that consult the
corpus.

Retiring the last REGULATION therefore does not break anything visibly. It
makes every product **pass** the check that exists to stop it, and reports the
assessment as complete. A fail-open that reads as a clean run is the worst shape
a compliance failure can take, and it is one retirement away.

So two things are shown before the act: the identifiers the code names
literally, and whether this is the last active member of a type something
load-bearing depends on. The refusal is a distinct error type from a malformed
request, because the request was well formed - the state of the corpus is what
refused it - and a reviewer who has read the list may repeat it having
acknowledged it.

### Saving rebuilds the lexical half, and that is only safe because of the fingerprint

Editing has to feel free or nobody edits: no gateway, no tokens, milliseconds.
So a save rebuilds the lexical index and leaves the matrix alone, and the index
reports that the vectors have fallen behind.

That report is only trustworthy because `build` stamps a fingerprint of the
chunk identifiers **and their text**, and `load` refuses a matrix that disagrees
with it. The distinction is the whole point: a chunk identifier is the document
and an ordinal, so correcting a sentence inside a document leaves every
identifier in the corpus unchanged, and the length check this replaces would
have accepted the old vectors against the new text. Row N would still be *a*
vector for chunk N, just the wrong one.

**A matrix from before the fingerprint existed is accepted as an upgrade and
reported unverified, not refused.** Refusing would switch dense search off on
every installation that had not reindexed - a worse failure, and a quieter one.

Rebuilds are serialised behind a lock. Two concurrent builds race on the matrix
write while the chunk list ends up holding the other one's rows, which is
precisely the misalignment the fingerprint exists to detect, arriving by a route
the fingerprint cannot prevent. The API runs these handlers in a threadpool, so
two reindex requests in flight is an ordinary Tuesday.

### Extraction is advisory, and the ordering is the safety argument

What comes out of the extractor lands in the editor for a person to read and
correct; what they press save on is what becomes a document.

A regulation is the thing three readiness checks are answerable to. A
mis-parsed table that silently becomes cited policy is a worse outcome than an
upload that needs five minutes of tidying. The known-bad case is worth naming
rather than hiding: a PDF of a table-heavy regulation extracts as interleaved
column fragments, and no amount of care in the extractor fixes that.

`.docx` is a zip of XML, so `zipfile` and `xml.etree` are enough and
`python-docx` stays out - it needs `lxml`, a compiled C extension, which is the
dependency line this application has held everywhere else. Style names map to
heading levels, which is what makes the result chunkable: a document arriving as
one unbroken block retrieves badly and cites worse. PDF needs `pypdf`, which is
pure Python, so it is feature-detected exactly like the spreadsheet writer and
named in its own requirements file; page markers are inserted because PDFs carry
no heading structure at all, and without them every chunk of a long regulation
cites the same empty heading.

### Commencement is read as of the replay clock, and is precomputed

A rule that has not commenced is not the answer to what may be published today.
Retrieving it as though it were is the same class of error as citing a withdrawn
policy and it is quieter: the document is real, it retrieves cleanly, the
excerpt reads correctly, the citation resolves, and every anti-fabrication gate
passes it, because nothing downstream knows what day it is.

The as-of default is the replay clock, because every other as-of read in this
system is, and a retrieval answering about a different instant than the catalog
it is compared against is a subtle way to be wrong. It falls back to the wall
clock rather than to "no date at all" if the tape is unreadable: both are
guesses, and only one of them silently reinstates rules that have not commenced.

An undated passage is always in force - correspondence, a catalog record and a
postmortem are statements about something that happened rather than rules that
commence. **A date that will not parse is treated as in force too**: a typo
should cost a document its commencement date, not its presence, and an
unfindable regulation is the failure this module exists to prevent.

Dates are precomputed onto the index rather than parsed per chunk per query.
Measured, that parsing was most of the cost of a lexical search.

### The reranker is a trade, not an improvement, so it is off by default

Fusion decides what is *plausible*; a reranker decides what is *relevant*. They
are different questions and the second is the one a reviewer asked.

It costs a model call on a path that had none, and identifier queries - which
are most of them - were already answered correctly by the lexical half. It earns
its place on paraphrase, which is where the fused ordering is weakest and where
somebody is reading the answer rather than following a link. A cross-encoder
would do the same job with no gateway and arrives as a compiled extension, which
is the dependency line held everywhere else here.

Three properties make it safe to leave in the path:

- **It can never invent.** Identifiers it was not given are dropped and counted.
- **It can never drop.** Candidates it fails to mention keep their fused place,
  so the worst a confused reranker can do is leave the fused ordering roughly
  alone.
- **It can never fail quietly.** A dead gateway, a refusal or an unparseable
  reply leaves the fused order untouched and the caller is told why. Reranking
  that silently did not happen looks identical to reranking that happened and
  agreed, and a reader deciding how much to trust an ordering has to be able to
  tell those apart.

It reads deeper than the caller asked for, because the passage it promotes to
first is often one the fused ordering had at eighth, and truncating first would
throw it away before anything looked at it.

## Risks / Trade-offs

- **A retired document's decisions still cite it.** That is deliberate, and it
  is why retirement keeps the file. The cost is that the corpus on disk grows
  with things no longer in force.
- **An unverified matrix is used.** Accepted as the lesser failure, and reported
  rather than hidden.
- **Extraction can produce nonsense from a table-heavy PDF.** Mitigated only by
  the editor standing between it and the corpus, which is the mitigation.
- **A reranked ordering costs a model call per search.** Off by default, and the
  caller can insist or decline per query.

## Open Questions

- Front matter carries `effective:` but not an expiry. A rule that ceases has to
  be retired by hand, and there is no reason the same as-of read could not
  answer that too. Left until a document needs it.
