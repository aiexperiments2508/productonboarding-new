## Context

See proposal.md - Why. The relevant starting state is that the day-0 contract
module was already split in two: a domain half describing plants, lanes,
materials and SKUs, and a provenance half describing how anything at all is
known - facts, events, approvals, audit, retrieval. Only the first half was ever
supply-chain specific, but that had never been tested, because only one problem
had ever been in the room.

Constraints that shape the approach:

- SQLite with no server, so exclusivity and atomicity have to be expressible as
  indexes and transactions rather than as a coordination service.
- The seed pack must be byte-identical for a given `DATA_SEED` across Python
  versions and machines: recorded expectations in tests and in the acceptance
  walkthrough name entity ids and counts literally.
- The whole test suite must run with no model gateway reachable, which means the
  lexical half of retrieval carries CI and the semantic half must degrade rather
  than error.
- The corpus is hand-authored and referenced by identifier from tests and from
  the tape, so entity ids cannot be generated.

## Goals / Non-Goals

**Goals:**

- Establish the record - facts, provenance, lineage, as-of reads - as the single
  answer to "what is true, what did we believe, and on whose authority".
- Establish the corpus and its retrieval as the single answer to "what rule
  governs this, and where is it written".
- Prove the provenance half is problem-independent by changing the problem and
  leaving it, and its tests, alone.

**Non-Goals:**

- Validation, propagation, ingestion and publishing. This change lays the
  record and the corpus; the deterministic decision layer that reads them is a
  separate change.
- Any model call. Nothing in this change invokes a gateway; the embedding matrix
  is an optional artefact built by a script.
- A migration path for existing data. There is no production instance; the pack
  is regenerated.

## Decisions

**Two time axes in one table, with one query rule.** A fact carries a validity
interval and a recording instant; the winning row for a pair of instants is the
one with the greatest recording instant among those whose interval covers the
world instant and which were recorded at or before the recording instant.
Corrections then need no special mechanism at all - a correction is another row
with a later recording instant, and it wins from the moment it arrives and not
one instant earlier.

*Alternatives considered.* Updating rows in place with a separate audit log:
answers "what changed" but not "what did we believe on Monday", which is the
question a defensible recommendation needs. A separate history table: two places
to look and two chances to disagree. A single `is_current` flag: makes the
as-of read impossible without reconstructing history.

**Lineage is recorded but not load-bearing for reads.** `supersedes_id` exists
so a reviewer can be shown what a value replaced. The as-of query never consults
it, so a broken chain degrades the display and not the answer.

**A far-future sentinel for open validity intervals.** Open-ended intervals are
compared as ISO strings against a sentinel rather than branching on NULL in
every predicate. One predicate, reused by the single read and the windowed bulk
read, is one place for the rule to be wrong.

**Provenance is a closed set of five kinds, not a boolean.** Observed, concluded,
decided, validated and published are five different warrants for a value, and
collapsing any pair of them makes a badge in the UI decorative. In particular
the observed/concluded split is what a fail-closed safety rule keys on later.

*Alternative considered.* A `confidence` field alone, with no kind. It cannot
distinguish a human decision at 100% from an observation, and it gives an
auditor nothing to filter on.

**A local PRNG in the generator rather than the standard library's shuffle.**
CPython does not guarantee shuffle stability across versions, and a pack that
drifts silently invalidates every literal count in the tests and the acceptance
walkthrough. A mulberry32 implementation is twenty lines and is pinned by
`DATA_SEED`.

**Entity ids are hardcoded constants, not generated.** The corpus is authored by
hand and names `PRD-01` and `VAR-01B` literally; generated ids would put the
corpus and the catalog one regeneration apart from disagreeing.

**The generator asserts its own output and exits non-zero.** The strongest
assertion is that the untouched catalog validates with zero violations. Every
number the run later reports is a delta from that baseline, so a pack that
quietly starts dirty would make all of them meaningless rather than merely
wrong.

**The baseline is internally consistent and deliberately wrong.** Both purifier
variants start at 45 W and 38 dB, because the mix-up the supplier's correction
describes genuinely contaminated the record. A baseline seeded with the right
answer would make the scope question rhetorical.

**Policy lives in prose a person owns, and is enforced in code.** The
claim-substantiation table and the source-precedence order each exist twice: as
a document in the corpus and as a rule the engine applies. The redundancy is
deliberate - a reviewer who is blocked is shown the same rule in a form they can
argue with, and the document is the thing a policy owner edits.

*Trade-off accepted.* Two copies can disagree. The mitigation is that the code
side is asserted against a fixed set in tests and the document side is asserted
retrievable by name.

**Retrieval keeps an identifier-preserving tokenizer and hybrid fusion.** The
tokenizer indexes an identifier whole and by its parts. This mattered before and
matters more now: embeddings place `VAR-01A` and `VAR-01B` almost on top of each
other, while they hold opposite answers to the only question anyone asks about
them. Fusion is reciprocal-rank based, so the lexical half alone is a complete
answer when no embedding matrix exists.

**Semantic tests skip loudly rather than fail or pretend.** They check for the
matrix file at collection time and skip with a reason naming the script that
builds it. CI gets the lexical golden set, which is the half that must never
regress.

**Publish locks reuse the reservation ledger's shape.** A capacity reservation
and a publish lock are the same object - an exclusive claim on a resource for a
bucket date - so the partial unique index that made duplicate reallocation
impossible now makes duplicate republishing impossible. Exclusivity is enforced
by the database rather than by application logic, which is what makes a
conflicting concurrent publish a failed insert rather than a race.

## Risks / Trade-offs

**Deliberately retained names no longer describe what they do** - a validation
pass still called a simulation, a correction case still called an incident, a
catalog read still living in a module named for a network. → The specs are
written against observable behaviour, never against those names, and the
project context records the mismatch so a later reader does not take the name
for the contract.

**Hand-authored corpus can drift from the code that enforces it.** → The claim
set is asserted exactly in the validation tests, and each load-bearing document
is asserted retrievable by a golden query naming it.

**The semantic half of retrieval is unexercised in CI.** → The lexical golden
set covers the queries that name things, which is every query the pipeline
actually issues for a rejection code or an identifier; the paraphrase set is
run when a matrix is built, and skips with a reason rather than silently.

**A byte-identical pack is a hard dependency of many literal assertions.** Any
change to the generator invalidates recorded counts across the suite. → The
generator validates its own output and exits non-zero, so the failure is at
generation time rather than a confusing test failure three files away.

**Keeping the provenance half untouched risks fitting the new problem badly in a
way nobody notices,** because its tests were written for the old one. → Accepted
knowingly: the tests are about the store's temporal properties, not about
suppliers, and they were re-read rather than merely re-run. Where the new
problem needed something the old contracts lacked - a citation, a safety class -
it was added rather than approximated.

## Migration Plan

1. Regenerate the seed pack; the generator refuses to emit a pack that does not
   validate clean.
2. Drop and re-initialise the database, then rebuild the retrieval index. The
   index build takes an `embed` flag; without a gateway it builds the lexical
   half only.
3. Rollback is `git revert` of the three commits plus a regenerate; there is no
   persisted state worth preserving.
