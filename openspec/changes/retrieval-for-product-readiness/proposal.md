## Why

Retrieval answers one kind of question well: what do our own written standards
say. Four document types over fifteen authored markdown files - content
standards, channel specifications, policy and postmortems - fused BM25 and
dense, with metadata filters applied before ranking. It is a good index and it
is the wrong shape for what comes next.

Deciding whether a product may launch asks three questions the corpus cannot
answer at all.

**What does the regulator require of this category?** Not what our policy says
about allergens - what a mandate says about whether this thing may be sold at
all. `POL-001` is our reading of the rules; it is not the rules, and a system
that cites its own policy as evidence of compliance is marking its own homework.

**What does our own internal documentation say?** A retailer has buying guides,
category playbooks and onboarding rules that are neither a published standard
nor a postmortem. They are the things a new starter is told and a system never
checks.

**Why would anybody buy this, here, now?** Region, season, festivity and
popular usage are the difference between a specification and a product page.
None of it is in the corpus, so a model asked for it today would answer from
whatever it happens to believe - which is the definition of an ungrounded claim
on a page a shopper reads.

There is a fourth gap that is structural rather than editorial. The index holds
prose. The *product record* - the merged, in-force attribute values with their
sources - is not retrievable at all, so a question about a product has to be
answered by joining a retrieval result to a database read by hand, in every
caller that wants one.

## What Changes

- **Three document types beside the four that exist**: `REGULATION` for
  government and market-authority mandates, `INTERNAL` for the retailer's own
  documentation, and `MARKET` for the seasonal, regional and cultural context a
  product page is written against.
- **The product record is indexed.** Each product's in-force values, with the
  document behind each one, are chunked and indexed like any other passage, so
  "what do we hold about PRD-01" and "what does the regulation say about
  purifiers" are the same kind of question with the same kind of citation.
- **Retrieval is scopeable to a product.** The entity filter already exists and
  is already applied before ranking; what was missing was anything to filter
  *to*. A readiness check must not retrieve another product's regulation, and
  after this it cannot.
- **A corpus that has the material.** Regulatory notices for the two regulated
  categories, internal buying and onboarding documentation, and market context
  covering the seasons and festivities the demo runs through.
- **Nothing about the retriever itself changes.** The fusion weights, the RRF
  damping, the tokeniser that keeps `VAR-01B` whole, and the golden set that
  tuned them are untouched. This change gives that machine more to read; it
  does not second-guess it.

## Capabilities

### New Capabilities

None. This extends what the existing retrieval capability holds and can be
asked, and adds no behaviour that is not already its job.

### Modified Capabilities

- `standards-retrieval`: regulatory, internal and market-context documents are
  indexed alongside the written standards, the product record itself is
  retrievable, and a query can be narrowed to one product.

## Impact

- `sc/rag/chunk.py` - the new document types are accepted rather than silently
  coerced to `STANDARD`; a chunker for the structured product record.
- `sc/rag/retrieve.py` - the new types join the reference set; a
  product-scoped entry point.
- `corpus/regulation/`, `corpus/internal/`, `corpus/market/` - new authored
  documents.
- `scripts/build_index.py` - indexes the product record beside the corpus.
- `tests/test_rag.py` - the new types are found, a product-scoped query does
  not cross products, and the existing fusion golden set still passes.
