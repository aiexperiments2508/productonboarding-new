## Context

Two changes, and only the second one is the fix. Swapping the renderer without
the layout would have drawn a faster hairball.

## Decisions

### Position carries the information, rather than physics rediscovering it

The data already knows three things: there is a centre, every node has a hop
distance from it, and every node has a domain. A force solver has no opinion
about any of them and arrives at all three approximately, having thrown away the
exact answer it was given.

So rings are hop distance and sectors are domains in a **fixed** order. Fixed is
the load-bearing word: it is what makes two products' neighbourhoods comparable
at a glance, which a solver's arbitrary but stable output never is.

**A crowded domain grows thicker through sub-rings rather than reaching into the
next hop's ring.** Distance has to keep meaning hops. A layout that let a busy
sector spill outward would make ring position mean "hops, unless that domain was
busy", which is not a thing a reader can hold.

### Taking a graph library, and saying what it cost

The README ruled out a graph library. This takes one, so the costs are measured
rather than asserted:

- bundle 610 kB → 2,401 kB (183 → 706 kB gzipped);
- two dependencies never reach the browser - the bundler drops them, **verified
  by grepping the built output** rather than by trusting tree-shaking - but the
  audit tool still reports four high advisories against the installed tree,
  which is true and worth writing down even though the code is not shipped;
- telemetry is disabled on the instance.

The alternative was continuing to hand-roll SVG, which does not scale past a
neighbourhood of any size and gives every node its own DOM element.

### The official React wrapper is deliberately not installed

It declares an exact peer dependency on a React version this project does not
use. It would not resolve, and making it resolve means a legacy-peer-deps flag -
which, once added, is permanent and silences every future peer conflict as well.

Binding the renderer to React by hand is about forty lines, and installation
keeps working with no flags. Forty lines is cheaper than a permanently disabled
dependency check.

### Colours are converted by rasterising a pixel

Every node rendered blank at first. The renderer parses colours with a library
that predates the colour space every design token in this repository is authored
in.

Two obvious conversions do not work, and it is worth recording why so nobody
tries them again: **reading the value back from the computed style does not
convert it**, and **a canvas fill round-trip does not either** - current browsers
preserve the authored colour space through both.

Rasterising one pixel and reading its bytes is the only conversion that cannot
be preserved away, because at that point the value has to be device pixels.

### A canvas has no DOM, so the keyboard equivalent is a real list

The SVG carried a label and a tab stop per node. A canvas has neither, and the
accessibility of the surface cannot quietly regress because the renderer
changed.

So a real focusable list sits beneath it. Not an overlay of invisible elements -
an actual list, which is also useful to a sighted reader looking for a node by
name.

### Neo4j's own browser is linked, never embedded

It sends headers refusing to be framed, so an iframe would fail. It opens in a
new tab.

## Risks / Trade-offs

- **The bundle nearly quadruples.** Measured and stated. This surface is one tab
  of one section, and the alternative was a renderer that does not scale.
- **Four high advisories in the installed tree**, against code that is not
  shipped. Reported rather than explained away.
- **No test covers any of this.** It is entirely client-side rendering, and
  there is no frontend test in this repository. The layout's inputs - hop
  distance and domain - come from the graph projection, which is asserted.

## Open Questions

- Sub-ringing a crowded domain keeps hop distance honest but makes a very busy
  sector deep. At some density the right answer is probably to summarise the
  sector rather than draw all of it.
