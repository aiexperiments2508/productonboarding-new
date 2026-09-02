## Context

Eight unrelated observations, so most of this change is small and local. Four
decisions are worth recording, and three of them are about the same thing: a
surface that has done less work than usual must say so, in a way a caller
cannot render away.

## Decisions

### "Ready" is reserved, and the reservation lives in one helper

Making the assessment fast is easy. Making it *honest* is the part that needs a
rule, because a narrow assessment produces the same shape of answer as a
complete one and the difference is invisible at the point somebody reads it.

So the vocabulary is split: a complete assessment may say **ready**; a narrow
one says **no rule findings**, which is true, is weaker, and cannot be misread
as a clearance. Staging refuses to build from a narrow verdict, because the
whole purpose of staging is to show what would go live.

Five surfaces render a verdict. If each phrased it, the rule would hold in
whichever ones somebody remembered, so `verdict.ts` owns it and all five ask.
This is the same argument the readiness rollup makes for not letting a
dashboard reach its own conclusion, applied one layer up.

**A narrow assessment does not weaken its findings.** That is the other half
and it is easy to get backwards: fewer checks ran, so there is *less* evidence,
not *worse* evidence. A finding a rule raised is worth exactly what it was
worth before, and discounting it would make the fast path quietly less useful
than the slow one rather than merely narrower.

### The account of a finding runs after the verdict and cannot reach it

Joining a finding to the estate's declared behaviour is the sort of feature
that would be easy to let leak into the decision - a system "known to send
stale allergen data" is suggestive, and a system's reputation must not become
evidence about a product.

So the account is computed after the verdict, is handed the finding rather than
the record, and has no route back. It is fenced exactly like every other model
call here: it may use the finding, the declared behaviour and a retrieved
passage, and an account citing nothing retrievable is dropped for the
deterministic one. A clean product is offered no explanation at all, because
there is nothing to account for.

Where more findings exist than can be explained, the ones left out are
**counted rather than dropped**, and the worst is explained first. A surface
that silently explained three of eleven would read as though there were three.

### One reader for five spellings

The tape names a product five ways because five kinds of system wrote to it: a
channel acknowledgement says `variant_id`, a document and an email say
`entities`, and the structured feeds say `entity_id`. The resolver read one of
them, so six systems that had delivered dozens of events each appeared to have
delivered nothing.

The fix is not a longer conditional at the call site. It is a single reader
that knows every spelling, shared with the arrival window, so the map and the
window cannot disagree about whether a system has been heard from. A test
enumerates the spellings against the tape rather than against a list written
down beside the reader.

### The scoped map is a second route, not a parameter on the first

`/api/network` keeps its shape and its unscoped answer. The new route is scoped.

That is deliberate rather than duplicative: **a map showing ten of a hundred
and fifty is reasonable, and a blast radius showing ten of a hundred and fifty
is wrong.** The two surfaces want opposite defaults, and a shared route with a
limit parameter would put the burden of remembering that on every caller. The
scoped route says "+N not drawn" instead of truncating silently, and its frame
grows with the busiest tier rather than being fixed.

### A missing image must not look like a working page

The asset mount is registered ahead of the SPA catch-all, so a missing file is
a 404. Before this, `/media/whatever.jpg` returned `index.html` with a 200 -
which the browser renders as a broken image, exactly as it renders a genuinely
missing photograph, so the two failures were indistinguishable from the outside.

Assets are drawn deterministically per seed rather than shipped as binaries,
which keeps the seed pack reproducible and keeps image bytes out of the
repository. A role the category requires that nobody delivered is a gap that
names the system that owes it - the media strip and the readiness finding read
the same source, so a strip showing a gap and a check reporting none is not a
state the two can reach.

## Risks / Trade-offs

- **The fast path is the default, so most readers see a narrow verdict.** That
  is the intended trade and it is why the vocabulary change is not optional: the
  cost of defaulting to narrow is entirely paid by saying so.
- **The catalog grows twenty-five-fold.** The six hero products and their arcs
  must not move, so the background draws from its own PRNG stream and its damage
  is declared in a registry the generator asserts against - the same property
  the extraction answer key has, extended to the half of the catalog nobody
  hand-wrote.
- **Explaining a finding costs a model call** on a path that had none. It is
  opt-in, runs after the verdict, and falls back deterministically.

## Open Questions

- The account reads what the estate *declares* about a system, which is
  authored rather than measured. A system whose declared behaviour and actual
  behaviour diverge would produce a confident and wrong account. Measuring it
  from the arrival record is possible and is not attempted here.
