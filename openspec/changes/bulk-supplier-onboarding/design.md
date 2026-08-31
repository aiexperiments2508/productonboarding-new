## Context

The system already holds everything a supplier template needs to say, and says
none of it out loud. This change is mostly a matter of pointing the existing
machinery at a new question; the decisions worth recording are the four places
where the obvious implementation would have been wrong.

## Decisions

### The template is derived from the registry, and the derivation is shared

`sc/datapack/schema.py` builds a branch's column set from `base.attr_defs`
joined to `catalog.profile.branches`. The reader that takes a bundle back reads
against the same function. A template written by one definition and validated
by another is two definitions, which is the objection `sc/readiness/checks.py`
already makes about a rule with two implementations, applied to a schema.

The applicability predicate existed in three places — `Baseline.applicable_attrs`,
`checks.applicable_attributes` and `checks.mandatory_information`. It is now
`baseline.applies_to_category`, called by all three and by the pack. This is
the load-bearing part: `applies_to` holds taxonomy *prefixes*, and five
attributes are named leaf by leaf because a kettle is mains and a saucepan is
not and both are `home.`. Asking the predicate with a branch key rather than a
leaf silently returns only the universal attributes — a template that asks a
grocery supplier for no ingredients, and which would look plausible.

### openpyxl is taken; python-docx is not

The rule, so it does not have to be re-argued: **a pure-Python dependency that
does something we cannot meaningfully test is worth taking; a compiled one is
not.**

XLSX data validation means a styles table and a hidden lists sheet where every
element is an index into another table, and the failure mode is Excel silently
*repairing* the file — which no assertion in this suite could catch. openpyxl
passes that test, is pure Python with one pure-Python dependency, installs on
every version `requirements.txt` cares about, and reads as well as writes,
which the bundle reader needs when a supplier sends the workbook back.

The Word specification is prose and tables with no validation in it, and
`python-docx` requires `lxml`, a compiled C extension — precisely the class of
dependency `requirements.txt` spends three paragraphs refusing. So
`sc/datapack/writers/specdoc.py` writes it with `zipfile` and the standard
library in about two hundred lines, and the test unzips it and parses the XML.

It lives in `requirements-datapack.txt` rather than `requirements.txt`,
following the gateway and studio precedent: the pack is a build artefact, not a
runtime need, and an install that has to build a spreadsheet library to serve
an API is a slower install for everybody who never runs the generator.

### A row is a feed row against the supplier's own document

The temptation is to mint a document id per bundle. `baseline.precedence`
returns zero for a document the seed pack does not know, and
`ingest._attribute_row` refuses to record a material row whose document ranks
below the one in force — so a bundle with a fresh id would raise a conflict per
row and correct nothing, while returning `accepted: true`. Rows are asserted
against `_next_version(_default_doc(...))`, exactly as
`submit_specification_change` does.

### Every event carries a top-level `entities`

`frontend/src/liveImpact.ts` resolves an event to catalog nodes through a fixed
allowlist of *top-level* payload keys. A row event whose entity is only inside
its `rows` array would arrive correctly, record correctly, and light nothing —
the feed would fill and the map would stay dark, with no assertion anywhere
noticing. `tests/test_bundle_intake.py::test_every_row_event_carries_a_top_level_entities`
is the guard.

### One upload is one arrival

`tape.append_live` is per event: one transaction, one arrival row, one ingest,
one push. A forty-row bundle through it is forty-four of each — and forty-four
*delivery batches*, so `submissions._carried` would report that one spreadsheet
arrived in forty-four separate deliveries. That is not a performance objection;
it is a false statement about what happened. `append_live_many` does the same
work once.

The visible consequence is that the feed fills in one go rather than
progressively. That is correct — the bundle did arrive in one go — and the
progressive reveal the screen wants belongs to the assessment pass, where the
system genuinely is looking at one product at a time.

### A bad cell loses the cell, not the row

A row of twelve values with a unit typed into one of them is eleven values we
can use. Rejecting all twelve throws away good data to punish a typo, and
reports a bundle of forty as a bundle of thirty-nine. The cell is reported by
line and column and simply does not arrive, at which point the readiness check
reports it as missing — through the same check that would have reported it had
the supplier left the cell blank, which is the truth about a value that cannot
be read.

The summary keeps rejected *rows* and rejected *cells* as two numbers, because
"three rejected" reads as three lost products.

### The pass is `sc/readiness`, not the graph

Four reasons, in order of weight. The graph works an open correction *case*,
and a freshly onboarded product has no signal, so most of a batch would have no
case at all and the run would silently work something else. Every correction
run ends at `request_approval`, so forty products is forty pending approvals in
a queue built to hold one. Each run is many gateway calls. And the question
being asked — clean, broken, or fixable — is `readiness.assess`'s question
verbatim.

`sc/onboarding/assess.py` is `submissions._verdict`'s loop turned into a
generator: same resolution, same call, same caveat handling.

### "AI can fix" is a candidate count until it is applied

`enrich` writes facts as a side effect — `ingest.record_attribute` is called
before the action is appended — so there is no dry mode and the count cannot be
obtained by running it.

The question decomposes, and only half of it needs a model. *Is there a
supplied passage that could carry this value?* is retrieval, deterministic, and
yields a **sound negative**: `_validated_fill` drops any fill whose chunk is not
in the supplied set, so no passage means no fill. *Does a passage that exists
state the value?* needs the model. So the report loads with candidates labelled
"a source passage is on file", and applying upgrades each to a cited fill or to
a supplier request. The two counts differ, and that difference is the truthful
number.

Safety-class gaps are excluded before the question is asked, and counted.

### Applying does not publish

"Push it through" is a verdict, not an action: a product is `READY_TO_LAUNCH`
when it has no findings, which is arithmetic over what is on file. So the fix
endpoint writes cited fills, re-assesses, returns the new verdicts and stops.
Publishing still needs `commit_plan`, a recorded approval and a channel
reservation, none of which this touches — pinned by counting those three tables
before and after.

## Risks / Trade-offs

- **The candidate count is zero on the current seed pack.** Every attribute gap
  in the catalogue sits on a background product, and the corpus names only the
  hand-authored ones, so retrieval scoped to the entity finds nothing for any
  of them. That is the honest answer and the mechanism is right — it becomes
  non-zero the moment a document naming the product is retrievable. Widening
  the search to unscoped category-level guidance would raise the number and
  make it a lie: a standard saying "net weight is an integer in grams" does not
  state what this biscuit weighs.
- **Proposed new lines are not assessed.** A SKU the catalogue does not have is
  held as a draft, and a draft has no record to assess. The report counts them
  separately and says so rather than reporting six of eleven as the whole.
- **Bundle size is capped** at 200 rows and 24 MB. Above that it is an
  integration, which is what the PIM and data pool endpoints are for.
