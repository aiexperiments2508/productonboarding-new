## Why

A supplier can send one corrected value, one document or one image. That is the
right shape for the correction the demo is built round — a late change to a
product already on sale — and the wrong shape for the question a retailer asks
before any of that: **a supplier has forty new lines, how many of them are fit
to sell?**

Four things are missing, and each one on its own makes the question
unanswerable.

There is no artefact to hand a supplier. The system knows exactly what it wants
— twenty-six attributes with declared types, units, applicability and the
channels that refuse to publish without them — and none of it is expressible as
something a supplier can open. In practice that means a spreadsheet somebody
wrote by hand, which becomes a third statement of what a product record is
beside the registry and the checks, and the first thing it disagrees about is
the attribute somebody added last week.

There is no way to send more than one product. Forty lines through
`submit_specification_change` is four hundred calls, one per attribute per
variant, and the supplier has no way to send the photographs alongside them.

There is no notion of "this batch". `submissions` records what one call sent;
nothing groups an upload. So even though `rollup.tally` already counts cleared,
returned and blocked across a population, it can only count the whole catalogue
— never the thing that just arrived, which is the only population anybody wants
a number for at that moment.

And there is nothing that says which of the gaps could be closed without
writing to the supplier and waiting a fortnight. The graph's `enrich` node can
fill a mandatory gap from a passage it can cite, but it runs inside a
correction run, on one case, and writes as a side effect — so there is no way
to ask "how many of these forty could it close" without running it.

## What Changes

- **The supplier data pack is generated, never authored.** One template per
  branch the retailer trades, in CSV, a pipe-delimited flat file, an XLSX
  workbook, a Word specification and a JSON Schema. Every column is derived
  from the attribute registry joined to the retailer profile, so pointing
  `RETAILER_PROFILE` at another profile produces a different pack with no code
  change. Applicability is per taxonomy leaf, not per branch, because the
  registry names five attributes leaf by leaf.
- **One archive is one submission.** `submit_product_feed` takes a .zip of one
  data file and an `images/` folder. It is exposed only on a system whose
  manifest entry accepts both attribute rows and imagery — derived from the
  manifest, so narrowing a system removes the door with no code change.
- **A batch is a submission, not a new table.** The bundle's submission already
  records which entities it touched; that is the batch. No stored status, no
  stored verdict, no migration.
- **A sequential readiness pass**, streamed one product at a time, driving a
  highlight on the catalog map. Not a graph run: onboarding asks whether a
  record is fit to launch, which the readiness checks answer deterministically
  and in milliseconds, and forty products through a graph that ends at an
  approval interrupt would be forty suspended threads in a queue that exists to
  hold one.
- **A report scoped to the batch**, counting with `rollup.tally` so it cannot
  disagree with the product summary, and counting proposed new lines *apart*
  from assessed products rather than omitting them.
- **A bounded fill.** Gaps are classified deterministically into those with a
  source passage on file and those without, which is a sound negative rather
  than an estimate. Applying runs the model over the candidates only, writes
  INFERRED with the citation, and publishes nothing.

## Impact

- Affected specs: `supplier-data-packs` (ADDED), `bulk-onboarding` (ADDED),
  `protocol-surfaces` (MODIFIED)
- Affected code: `sc/datapack/` and `sc/onboarding/` (new); `sc/estate/intake.py`,
  `sc/estate/intake_server.py`, `sc/replay/tape.py`, `sc/main.py`,
  `sc/state/baseline.py`, `sc/readiness/checks.py`, `apps/vendor/`,
  `frontend/src/{api.ts,liveImpact.ts,app/nav.ts,app/App.tsx,components/}`
- New optional dependency: `openpyxl`, in its own `requirements-datapack.txt`.
  Nothing in `sc/` needs it at runtime and the pack degrades to four formats
  without it.
