## Why

The graph tab draws a hairball.

A force solver has no opinion, which is the wrong tool when the data already
knows three things: there is a centre - the product somebody opened - every node
has a hop distance from it, and every node has a domain. Physics is
rediscovering all three, badly, and discarding the answer it started with.

The renderer is hand-rolled SVG, which is also why every node carries its own
DOM element and the whole thing slows as the neighbourhood grows.

## What Changes

- **A radial layout, so position carries the information the data already
  holds.** Rings are hop distance; sectors are domains in a fixed order, so two
  products' neighbourhoods are comparable at a glance. A crowded domain grows
  thicker through sub-rings rather than reaching into the next hop's ring,
  because distance has to keep meaning hops.
- **NVL replaces the hand-rolled SVG** - the renderer under Neo4j's own browser
  and visualisation tools. **This is the first graph library in a repository
  whose README ruled one out**, so it is taken deliberately with its costs
  measured rather than assumed:
  - the bundle goes from 610 kB to 2,401 kB (183 to 706 kB gzipped);
  - two of its dependencies never reach the browser - the bundler drops them,
    verified by grepping the built output - but the audit tool reports four high
    advisories in the installed tree;
  - telemetry is disabled on the instance.
- **The official React wrapper is deliberately not installed.** It declares an
  exact peer dependency on a React version this project does not use, which
  would not resolve and would make a legacy-peer-deps flag permanent. Binding
  the renderer to React by hand is about forty lines and installation keeps
  working with no flags.
- **Colours are converted by rasterising a pixel**, because the renderer parses
  colours with a library that predates the colour space every design token in
  this repository uses. Reading the computed value back does not convert it, and
  neither does a canvas fill round-trip - the browser preserves the authored
  colour space in both. Rasterising one pixel and reading its bytes is the only
  conversion that cannot be preserved away.
- **A real focusable list beneath the canvas**, because a canvas has no DOM per
  node and the per-node label and tab stop the SVG carried have nowhere to live.
- Neo4j's own browser is linked from the back office header, in a new tab and
  never an iframe - it refuses to be embedded.

## Capabilities

### Modified Capabilities

- `knowledge-graph`: the arrangement of a neighbourhood is derived from hop
  distance and domain rather than from a force solver, and the rendered graph
  keeps a keyboard-reachable equivalent.

## Impact

- `frontend/src/components/kg/radialLayout.ts` - rings as hops, sectors as
  domains, sub-rings for crowding.
- `frontend/src/components/kg/forceLayout.ts` - replaced.
- `frontend/src/components/kg/GraphCanvas.tsx` - the renderer bound to React by
  hand, the colour conversion, the focusable list.
- `frontend/package.json` - the renderer, without its React wrapper.
- `apps/backoffice/web/` - the link out to Neo4j's own browser.
