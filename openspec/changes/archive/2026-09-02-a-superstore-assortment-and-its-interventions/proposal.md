## Why

The seed pack is a hundred and fifty products across three branches, and a
hundred and forty-four of them are `{Stem} {number} {Noun}` filler - "Whirl 543
Vacuum Cleaner", "Hearthstone 448 Biscuits". It reads as generated because it
is.

That is a presentation problem on the surface and a coverage problem
underneath. **The whole catalog can only be wrong in three declared ways.**
Twelve attributes, two of them safety-class, and seven correction kinds. So a
large amount of machinery that already exists has nothing to exercise it:
forced escalation, mandatory review, the fail-closed confidence gate,
withholding instead of copy-rewriting, and the per-channel redaction path are
all built and none of them is reachable outside two allergen paths.

Three things a retailer actually deals with cannot be represented at all,
because they are not corrections:

- a market authority serving a **withdrawal notice**;
- an **export-control classification** landing on a product;
- a **conformity certificate lapsing**.

The first of these is the dangerous one. A takedown recorded as an ordinary
fact would escalate and then publish, because the safety gate only ever fires
on a low-confidence inference - so a product a regulator has banned would pass
the publish gate on the strength of the notice being *confidently* recorded.

Meanwhile the category prefixes the running system depends on are spelled out
in three modules, so the assortment cannot change without editing rule code.

Two defects sit underneath. Background variants numbered from 200 are treated
as hero products, because the hero test is a string prefix that happened to be
true while the background stopped at 199 and quietly stopped being true when it
did not. And the validation engine keeps its own copy of the generator's
allergen code map, so an assortment that declares celery makes the two disagree
about what a declaration renders as.

Product 360 has its own problems: five things in one unlabelled panel, its only
always-visible primary action inside a panel header beside a title that
truncates, and a single breakpoint below which two scroll regions fight over
one viewport.

## What Changes

- **Eight branches of a UK superstore** - grocery, home, clothing and footwear,
  electricals, household and personal care, baby, health, and general
  merchandise - with product lines a shopper would recognise under a fascia and
  supplier brands that are entirely invented.
- **None of it is hardcoded.** A retailer profile file carries the branches,
  the taxonomy, the supplier roster, the catalogue and the per-branch facts the
  running system needs, selected by environment variable the way the data seed
  already is. The parts the platform consults are written into the catalog, so
  the category prefixes that were spelled out in three modules are read from the
  baseline instead.
- **Attributes go from twelve to twenty-six, six of them safety-class.** Most of
  the new behaviour comes from that rather than from new rule code: escalation,
  mandatory review, the confidence gate, withholding and per-channel redaction
  all become reachable.
- **Correction kinds go from seven to fifteen**, with seven new arcs exercising
  them - a pack shrinking, a conformity certificate lapsing, a country of origin
  moving, a withdrawal notice, an export-control classification, a fibre label
  revised, and cosmetics mandatory particulars amended. The original six keep
  their days, so the demonstration's spine is untouched. Targets are selected
  from the assortment rather than named, and undamaged ones are preferred, so
  the finding a presenter points at is the arc's own.
- **A withdrawal is a publish-time constraint of its own**, not an inference to
  be scored. `sale_prohibited` joins the safety gate, and `sale_permitted`
  becomes a seventh deterministic readiness check - so a withdrawn product does
  not read as merely incomplete whenever the gateway is down.
- **Nine new corpus documents**, so every new finding cites something a reviewer
  can open.
- **A `NOTICE` source kind at precedence 50** - the only kind no supplier can
  issue, ranked above label artwork, because artwork is the legal source for
  what a pack says and a notice is the legal source for whether it may be sold
  at all.
- **Hero membership is recorded rather than pattern-matched**, and the allergen
  code map is read from the catalog by both the generator and the engine.
- **Product 360 is restructured** into four labelled panels under a sticky bar
  carrying the verdict and every action, with a control that jumps to a section.
  The record table overflows rather than compressing and shows superseded values
  inline rather than on hover.

## Capabilities

### New Capabilities

- `retailer-profile`: the assortment, taxonomy, supplier roster and per-branch
  facts as data the platform reads, rather than as constants it contains.

### Modified Capabilities

- `launch-readiness`: a seventh deterministic check answers whether the product
  may be sold at all, so a withdrawal is visible with no model reachable.
- `review-and-publish`: a prohibited sale is its own publish-time refusal rather
  than something the confidence gate might catch.
- `event-ingestion`: a notice outranks label artwork, and the correction kinds
  the tape can carry are the kinds the classifier offers.

## Impact

- `data/profiles/ashcombe.json` - the assortment as data; `RETAILER_PROFILE`
  selects it.
- `sc/readiness/checks.py`, `preview.py`, `sc/lifecycle/` - category prefixes
  read from the baseline rather than spelled out.
- `sc/readiness/reading.py` - `sale_permitted` as a deterministic check.
- `sc/sim/engine.py` - `sale_prohibited` in the safety gate; the allergen code
  map read from the catalog.
- `corpus/` - nine documents; `POL-002` gains the notice precedence.
- `scripts/generate_data.py` - eight branches, twenty-six attributes, fifteen
  correction kinds, seven new arcs, recorded hero membership.
- `frontend/src/sections/Product360.tsx` - four labelled panels under a sticky
  action bar.
- `tests/test_readiness.py`, `test_validator.py`, `test_golden.py`.
