## Context

The validator answers "is this change publishable on this channel" and answers
it well: rules as data, deterministic, reproducible, one trace hash. It presumes
a product that is already live and asks what one correction does to it.

Nothing asked whether a record was fit to go live in the first place. The
catalogue has no SKU, no media, no product view and no notion of readiness, so
the ten systems now feeding it deliver into something that cannot tell you
whether what they sent is any good.

Three things already in place decide most of this design. The rule tables are
data and are already read by one implementation. The estate now records which
system carried every value, which is what turns a finding into something
actionable. And retrieval now holds regulation, internal documentation and
market context, which is what lets a reading check cite rather than assert.

## Goals / Non-Goals

**Goals:**

- A product findable by the identifier everybody outside this system uses.
- A record that shows what was delivered, who delivered it, and what lost.
- Nine checks, and a verdict that is reproducible from their findings alone.
- A staging page for records that pass, with a differentiator grounded twice.
- The whole surface working with no model reachable, and saying so.

**Non-Goals:**

- A readiness score. Argued below; this is the decision most likely to be
  reversed by somebody who has not read the argument, so it is the first one.
- Automatic remediation. This surface says what is wrong and who has to fix it.
  Fixing it is the correction pipeline's job and it already exists.
- A shopper-facing page. This is staging, behind the reviewer boundary, and the
  differentiator is written for a reviewer to approve rather than for a shopper
  to read.

## Decisions

**No score, no percentage, no grade.** A product with three open findings is not
seventy per cent ready. It is not ready, and the three findings are the thing
somebody acts on.

A number would be easy to add and would look like progress. It would also
invite a threshold, and a threshold invites launching at ninety - which is
precisely how a missing allergen declaration reaches a shelf. There is no
number here that a reasonable person could not eventually be talked into
lowering.

*Alternative considered.* A score for sorting a list. The list sorts by verdict
and finding count, which is the same information without the invitation.

**Six checks decided by rules, three permitted to read.** The split is not
"where AI helps" but "where a rule can be correct". Completeness, type
conformance, channel requirements, media by role, source contradiction and
forbidden content all have a correct answer a table computes. Whether a
regulation's mandatory particulars are met, whether a sentence has quietly
become untrue, and whether the record contradicts internal documentation each
require reading prose no rule encodes.

**The citation is the gate, not the confidence.** A reading check returns a
candidate that must cite a passage the check actually retrieved. A candidate
citing something never in front of it is dropped - not softened, not flagged
low-confidence, dropped.

This is the most important decision in the change. A confidence threshold looks
like a control and is not one: the evaluation harness already measured this
gateway stating about 0.95 and being right 0.76 of the time. A citation is
checkable by a person in one click, and an unopenable finding against a product
is worse than a missed one because it costs a reviewer's trust in every other
finding beside it.

**Only saleability blocks, and only individually.** Blocking says a listing may
not lawfully be sold. Reaching that by accumulating quality findings would make
legality a matter of weight of evidence, which it is not. Eight missing images
are eight problems and not an offence.

**A finding names the system, not the supplier.** A supplier whose portal entry
was fine and whose data pool record was not is not at fault for the second one,
and telling them so wastes the correction. This is only expressible because the
estate records the carrier; before it, "the data is incomplete" was the best
this could have said.

**The differentiator is grounded twice or withheld.** An attribute the record
holds *and* a passage the corpus carries. "Comfortable in summer" needs a summer
and a reason; either alone is a sentence somebody made up.

*Where the first implementation was wrong, and it is worth recording.* The
grounding check originally matched the model's named attributes against
attribute *paths* only. The model named them the way a person does - "Sound
level", not `specs.noise_db` - so a perfectly grounded differentiator was
rejected on every request and the templated form was silently used instead. The
gate is now "is this an attribute the record holds", resolved against paths and
labels both. A gate that rejects the correct answer is not a strict gate, it is
a broken one, and it fails in the direction that looks like success.

**Forbidden content is checked after the model answers, not requested in the
prompt.** A prompt saying "no medical claims" is a preference. The check runs on
whatever came back.

**Search is not the retrieval index.** An exact and prefix match over a few dozen
rows. Fusing BM25 with embeddings to answer "which variant is NAV-AP300-MAX" would
be a slower way to get a worse answer, and an identifier query that sometimes
ranks second is worse than useless.

## Risks / Trade-offs

**The reading checks cost latency on a surface people click around.** A full
assessment is three model calls; measured at about 3.5 seconds against a live
gateway. The list view therefore runs the deterministic half only - twenty rows
would otherwise be sixty calls to render a page nobody has opened - and the
detail view asks for everything. The cost of that choice is that a list can say
"clear" about a product a reading check would have flagged, which is why the
detail view is where a verdict is acted on and the list is a way to find one.

**A narrow assessment can be mistaken for a clean one.** This is the dangerous
failure of the whole surface. Mitigated by carrying `checks_complete` and a
caveat through the API into the UI, and by a test asserting the caveat appears.
It is mitigation rather than prevention: a reader who ignores the banner gets a
narrow result and believes it.

**Media is declared, not verified.** The record says an asset exists at a URI.
Nothing fetches it, so a broken link reads as present. The check as built
answers "did the imaging system send us one", which is the question that
distinguishes the two failure modes it was built for.

**The forbidden-phrase list is a list.** It catches the phrasings it knows and
will not catch a novel one. It is deliberately narrow and deterministic rather
than broad and model-judged, because a false positive here silently rewrites a
product page.

## Migration Plan

The seed pack is regenerated, which this project treats as routine: variants
gain a SKU, the catalog gains media, and two products are deliberately missing
an image so the check has something real to find. Node coordinates were already
removed in the estate change.

`CatalogNode` and `Catalog` widen additively. Existing databases are reset the
way any schema change here is reset.

## Open Questions

- Whether readiness should run on ingestion rather than on request. Running it
  when a batch lands would let the estate panel show "three products became
  unready in the last hour", which is the thing a category manager actually
  watches. It is on request here because a scheduled assessment needs a place to
  put its history, and that is a bigger change than this one.
- Whether the differentiator should be re-generated per region rather than once.
  The market corpus carries regional notes and the current implementation reads
  whichever passage ranks first, which is closer to "a region" than "the right
  region".
- Whether a returned product should raise a correction signal, so the existing
  pipeline picks it up rather than a person carrying the finding across by hand.
