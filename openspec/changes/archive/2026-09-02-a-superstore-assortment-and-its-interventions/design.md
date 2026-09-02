## Context

Most of this change is data. The interesting part is that widening the data
makes existing machinery reachable rather than requiring new machinery - and
that three of the new arcs are not corrections at all, which is where the
existing machinery turns out to be wrong.

## Decisions

### The assortment is data, and the platform reads it from the baseline

The branches, taxonomy, supplier roster, catalogue and per-branch facts live in
a profile file selected by environment variable, the way the data seed already
is.

The load-bearing half is what happens next: the parts the platform consults are
written into the catalog, and the modules that had category prefixes spelled out
in them read the baseline instead. A profile that could be swapped while three
modules still contained `home.` is a profile that can only be swapped for
another one shaped exactly like it.

### Widening the attributes is how the existing machinery becomes reachable

Twelve attributes to twenty-six, six of them safety-class rather than two.

Escalation, mandatory review, the fail-closed confidence gate, withholding
instead of copy-rewriting, and the per-channel redaction path are all already
built. None of them was reachable outside two allergen paths, which meant the
system's most careful behaviour was also its least exercised. **This is a data
change that buys behaviour coverage, not a feature change** - and it is worth
recording as a decision because the alternative reading is that the new
behaviour needs new rule code, which it does not.

### Three of the new arcs are not corrections, and that breaks the safety gate

A withdrawal notice, an export-control classification and a lapsing certificate
are interventions rather than corrections. The system has no shape for them, and
the naive shape is actively dangerous.

**A takedown recorded as an ordinary fact would escalate and then publish.** The
safety gate only ever fires on a *low-confidence inference*. A withdrawal notice
recorded confidently - which it would be, because it is a document from a market
authority saying so - sails through it. The product is escalated for review, the
review agrees the notice is real, and the publish gate has no objection.

So `sale_prohibited` becomes its own publish-time constraint in the safety gate,
independent of confidence. And `sale_permitted` becomes a **seventh
deterministic readiness check**, so a withdrawn product does not read as merely
incomplete whenever the gateway is down. A withdrawal is not something copy can
fix, and it blocks every listing the product reaches rather than the one that
noticed.

### A notice outranks label artwork, and no supplier may issue one

`NOTICE` joins the source precedence at 50, above label artwork.

The argument is narrow and worth writing down: **artwork is the legal source for
what a pack says; a notice is the legal source for whether the pack may be sold
at all.** They answer different questions, and the second outranks the first
whenever they meet. It is also the only source kind no supplier can issue, which
is what keeps the ranking from being a lever a supplier could pull.

### Two defects that were true by coincidence

**Hero membership was a string prefix.** Background variants numbered from 200
were treated as hero products because the test was "does the identifier not
start with VAR-1" - true while the background stopped at 199, and quietly false
once it did not. Membership is now recorded rather than pattern-matched.

**The engine kept its own copy of the allergen code map.** A second copy of a
table is fine until the two are asked about something neither was written
against: an assortment that declares celery made the generator and the engine
disagree about what a declaration renders as. Both now read it from the catalog,
and a test asserts the classifier's kind table and the generator's are the same
table.

### Arc targets are selected, not named

The seven new arcs select their targets from the assortment and prefer
undamaged ones. Naming targets would tie the arcs to a particular generated
catalog; preferring undamaged ones means the finding a presenter points at is
the arc's own rather than something the background happened to break.

The original six arcs keep their days, so the demonstration script's spine does
not move.

## Risks / Trade-offs

- **A profile swap is only as complete as the extraction into the catalog.** A
  prefix left in rule code would not fail loudly - it would silently apply to
  nothing under a different taxonomy. The three known sites are moved; a fourth
  appearing later would have the same shape.
- **Twenty-six attributes make every assessment wider**, and the readiness pass
  is on the product-open path. Mitigated by the rule-only default.
- **Nine new corpus documents are nine more things to keep in force.** They
  exist so that every new finding cites something openable, which is the
  standing requirement, not an optional nicety.

## Open Questions

- A lapsing certificate is modelled as an intervention on the product. It is
  arguably a fact about the *supplier* whose certificate lapsed, which would
  reach every product that supplier sends. Left as the narrower reading.
