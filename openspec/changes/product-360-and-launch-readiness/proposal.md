## Why

This system reasons about *corrections to things already published*. It is good
at that: a supplier revises a specification, the blast radius finds every asset
built on the old value, a reviewer approves, and the correction propagates. The
premise of every arc in the seed pack is that the product was already live.

Nothing in it can answer the question that comes first. **Is this product fit
to publish at all?**

There is no SKU. The catalogue identifies things as `VAR-01B`, which is an
internal key; a buyer, a supplier and a marketplace all say "SKU" and mean the
thing printed on a purchase order. There is no media of any kind, so "are the
images there" is not a question the record can hold, let alone answer. There is
no product view - you cannot look one up by name, see what the estate has said
about it, or see where two systems disagree. And there is no notion of
readiness: the validator decides whether a *change* is publishable, never
whether a *record* is complete.

The consequence is that the ten systems now feeding the catalog deliver into
something that cannot tell you whether what they sent is any good. Arrivals are
counted and defects are stamped, and then nothing asks the only question a
category manager actually has: can this go live, and if not, whose fault is it
and what do they have to fix.

## What Changes

- **A SKU on every variant**, and search by it or by name across everything the
  estate has delivered. The internal key stays what it is; the SKU is what
  everybody outside this system calls the thing.
- **Media on the record.** A typed asset with a role - hero, in-situ, pack
  front, ingredient panel - so "the category requires an ingredient panel image
  and none arrived" is a finding rather than an impression.
- **A readiness assessment over nine checks**, each landing deliberately on one
  side of the governing rule. Six are decided by rules over the record and the
  channel tables. Three need reading - whether a mandate covers this product,
  whether a sentence is semantically wrong, whether internal documentation is
  contradicted - and on those a model *finds and cites* while a rule *decides*.
  Every model-flagged finding carries a citation or it is dropped.
- **A verdict that is arithmetic.** `READY_TO_LAUNCH` when no blocking finding
  is open; `RETURN_TO_SOURCE` naming the finding, the attribute and the
  **system** that supplied it. A model may write the covering note; it may not
  set the verdict, and there is no confidence threshold anywhere near it.
- **A staging product page** for records that pass, showing what the listing
  would look like, behind the same authorisation the approval gate uses.
- **A value differentiator on that page**, grounded twice over: it may assert
  only attributes the record holds and only context the corpus carries. Season,
  region, festivity and popular usage are authored documents, so a claim cites
  a passage rather than a belief. With no gateway it is a template over the
  same two inputs.

### What this deliberately does not do

- It does not gate on a score. Readiness is a set of named findings, and a
  product with three open findings is not "70% ready" - it is not ready, and
  the three findings are what somebody acts on.
- It does not let a model decide saleability. A regulation says a listing
  missing a mandatory particular is not saleable; that is a rule, and the
  model's job is to find the mandate and cite it.

## Capabilities

### New Capabilities

- `product-360`: finding a product by SKU or name across every stream, and the
  merged record - values, media, and where the systems that sent them disagree.
- `launch-readiness`: the nine checks, and the verdict that either releases a
  product downstream or returns it to the system that supplied the problem.
- `storefront-preview`: the staging page an authorised reviewer sees before
  launch, and the grounded value differentiator on it.

### Modified Capabilities

- `content-validation`: the readiness checks sit beside the publish-time rules
  and share the rule tables, so a product cannot pass one and fail the other on
  the same fact.
- `run-and-review-api`: the Product 360 routes.

## Impact

- `sc/contracts.py` - `sku` on the variant, a `MediaAsset`, readiness findings
  and a verdict.
- `sc/readiness/` - new: the checks, the verdict, and the differentiator.
- `scripts/generate_data.py` - SKUs, media, and deliberately incomplete media
  on some products so the check has something to find.
- `sc/main.py` - search, record, readiness and preview routes.
- `frontend/src/components/Product360.tsx` - new section.
- `frontend/src/app/nav.ts` - a sixth section.
- `tests/test_readiness.py`, `tests/test_preview.py` - new.
