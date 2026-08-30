## Why

The world this system reasons about is four suppliers, six products, eight
variants and six channels, written as literal Python tuples in the generator.
The generator also emits the x and y coordinates the dependency map draws with,
which is the clearest statement of the problem: the picture of the estate is
data the estate cannot change, because there is no estate - there is a tape
that was written once.

The toolsets have the same shape. Six of them are declared in a frozen tuple
with their module paths and tool names spelled out, reachable only by spawning
a local Python module over stdio. That partition was argued for and it is
right, but it describes systems this repository owns. A retailer's product
information does not arrive from six modules in one package; it arrives from a
supplier portal, a PIM, an artwork library, an ERP, a data pool, a regulator, a
marketplace connector, a translation service, an imaging system and a market
feed - each with its own team, its own release cycle, its own idea of what an
identifier means, and its own standard of care. Some of them send incomplete
records, some send well-formed records in the wrong vocabulary, and some send
records that contradict a system that was right.

Nothing about the current design can express that, and nothing can be added or
removed while the thing is running. "Plug and play" was not a claim the code
could make good on.

## What Changes

- **The estate is declared as data and served over MCP.** Ten external systems,
  each an MCP server reachable over HTTP, each declaring what it emits, who
  owns it, and how well-behaved it is. Adding one is a URL. Removing one is a
  button.
- **A connection is a runtime record, not a constant.** Connecting performs a
  real handshake and records what the system said it can do. The six built-in
  toolsets stay exactly as they are and keep their ownership invariants; they
  are now the systems that happen to ship in the box rather than the only ones
  that can exist.
- **The dependency map gains the systems that feed it**, derived from the live
  connections rather than from coordinates baked into a seed file, and redraws
  when a system joins or leaves.
- **Arrivals are asynchronous, batched and jittered, and sequencing is the
  event plane's job.** Systems push batches at irregular intervals and the
  batches interleave. What arrives is recorded with the system that sent it and
  the moment it landed; what is *ingested* is still ordered by sequence, which
  is what keeps the same seed producing the same facts. This split is the whole
  correctness argument and is set out in `design.md`.
- **What arrives is not always good.** Each system carries a conformance
  profile, and a payload can be incomplete, wrongly typed, in a foreign
  vocabulary, out of format, stale, or in contradiction with a better source.
  Every defect is named on the arrival, so a validation result can be checked
  against a known answer rather than admired.
- **"Factory Floor" becomes "Ingest Fabric".** The old name described a
  metaphor the system had outgrown before this change and certainly has now.

## Capabilities

### New Capabilities

- `source-estate`: the external systems that feed the retailer - what each one
  is, what it emits, how it delivers, how well it conforms, and what a
  connection to one means while the system is running.

### Modified Capabilities

- `event-ingestion`: an arrival names the system that sent it and the batch it
  came in, and carries the conformance defects it is known to have.
- `protocol-surfaces`: a toolset may be discovered rather than declared, and
  may be reached over HTTP as well as stdio, without either loosening the
  ownership rules or making a transport load-bearing.
- `blast-radius`: the derived map includes the systems currently connected, and
  follows them as they connect and disconnect.
- `run-and-review-api`: connections are listed, added and removed through the
  API, and topology changes are readable as a stream.

## Impact

- `sc/estate/` - new: the manifest, the emitter that turns a profile into a
  jittered batch schedule, the defect catalogue, and the per-system MCP server.
- `sc/mcp/registry.py` - the built-in six are unchanged; a connection store and
  a combined listing are added beside them.
- `sc/mcp/client.py` - `_Bridge` picks its transport from the connection record
  rather than always spawning a module over stdio.
- `sc/replay/` - arrivals are recorded with their system, batch and defects;
  release into ingestion stays ordered.
- `sc/schema.sql` - `connections` and `arrivals` tables.
- `sc/main.py` - connection routes and a topology stream.
- `run.py` - mounts the estate's servers beside the peers.
- `scripts/generate_data.py` - events carry the system that emits them and the
  defects stamped on them; node coordinates are no longer emitted.
- `frontend/src/components/NetworkMap.tsx` - a systems tier, laid out from the
  live connection list rather than from seeded coordinates.
- `frontend/src/app/nav.ts` and the shell prose - the rename.
- `tests/test_estate.py`, `tests/test_connections.py` - new.
