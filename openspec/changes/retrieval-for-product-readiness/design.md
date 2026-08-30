## Context

The index is a few hundred chunks, held as a numpy matrix beside a BM25 index,
with metadata filters applied as a linear scan before ranking. That shape is
right at this size and nothing here argues with it: an ANN index would add a
dependency and an approximation to an operation that already takes under a
millisecond.

What the index holds is four authored document types over fifteen markdown
files. Launch readiness needs three more, and needs something the index has
never held at all - the catalog's own values.

The filters that make this cheap already exist. `search()` takes `doc_types`
and `entities` and applies both before ranking. So most of this change is
material rather than machinery.

## Goals / Non-Goals

**Goals:**

- Regulation, internal documentation and market context indexed alongside the
  written standards.
- The product record retrievable, citing the document behind each value.
- Retrieval narrowable to one product without losing the category-level
  passages that are the only things able to block it.
- The existing fusion behaviour untouched and its golden set still passing.

**Non-Goals:**

- Tuning the retriever. The weights, the RRF damping and the tokeniser were
  tuned against a golden set; this change gives that machine more to read and
  does not second-guess it.
- A second index. Two indexes is two things that can be stale, and the reason
  to have one is a scale this corpus is nowhere near.
- Authoring a regulation library. Two regulations covering the two regulated
  categories in the seed pack, and no more - a corpus that outruns the catalog
  it describes is a corpus nobody can check.

## Decisions

**Three new types, not one "reference" bucket.** They answer different
questions and carry different authority, and collapsing them would lose the
distinction that matters most: a regulation *requires*, a policy *interprets*,
and internal documentation *advises*. A readiness finding that cannot say which
of those it rests on is a finding a reviewer cannot weigh.

*The sharpest case.* `POL-001` is the retailer's allergen policy and it is
written to satisfy `REG-001`. A system citing `POL-001` as evidence of
regulatory compliance is marking its own homework, and until now it had nothing
else to cite.

**A record passage is per variant, not per attribute.** An attribute alone
retrieves badly - "45" is not a searchable idea - and a reviewer reading a
finding wants the surrounding record anyway. Per variant rather than per product
because the base-versus-variant distinction is the thing this whole system is
about, and a passage covering both would reintroduce the ambiguity.

*Alternative considered.* Answering product questions with a database read
beside the retrieval result, which is what callers do today. It works and it
means every caller joins the two by hand, in its own way, and cites them
differently. One index and one citation shape is the point.

**Record passages are built with the index, never carried beside it.** A
passage describing a value that has since been corrected is worse than no
passage: it is a citation that supports the wrong answer, and it looks exactly
like a citation that supports the right one. Rebuilding is cheap; staleness is
not detectable by the reader.

**An unknown document type is classified, never dropped.** Front matter is
hand-authored and will be mistyped. Losing a classification is a bad search
result; losing a document is a regulation nobody can find, and the second
failure is silent while the first is visible in the index status.

**Scoping keeps passages that name no entity.** This is the one filtering
decision that could have gone wrong quietly. A regulation covering purifiers
names the *category*, not `PRD-01`, so a strict entity filter would drop the
only document able to block `PRD-01` - and the check would report clean. Opt-in
rather than default, because the callers that scope in order to *narrow* do not
want the unscoped half back.

## Risks / Trade-offs

**The corpus can outrun the catalog.** A regulation naming a category the seed
pack does not carry is a document that can never be cited, and it reads as
coverage. The record passages are checked against the catalog by test; the
authored documents are not, and are kept deliberately few because of it.

**Record passages compete with prose for the same top-k.** A query about a
standard now has eight more passages to be crowded out by. They are worded as
records rather than as guidance, which keeps them off paraphrase queries, and
the golden set still passes - but this is the reason not to index every
attribute separately, which would have put a hundred short passages into a pool
tuned against a few hundred long ones.

**More types means more ways to file a document wrongly.** The mitigation is
that misfiling is visible in the index status and does not lose the document.

## Migration Plan

`python scripts/build_index.py` rebuilds everything, and the index is
regenerated rather than carried. No data migration. The `DocChunk` type union
widens, which is additive - existing chunks keep their types.

## Open Questions

- Whether market context should carry an expiry. A seasonal calendar is true
  for a year and a differentiator citing last year's Diwali dates is wrong in a
  way nothing here would catch. The passages carry `effective`, and nothing
  reads it yet.
- Whether the record should be indexed per variant *and* per product. Per
  variant is right for the correction loop; a shopper-facing question is more
  often about the product, and answering it currently means reading several
  variant passages.
