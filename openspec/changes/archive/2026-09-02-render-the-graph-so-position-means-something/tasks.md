## 1. The layout

- [x] 1.1 Place nodes on rings by hop distance from the opened product
- [x] 1.2 Place domains in sectors in a fixed order, so two products'
      neighbourhoods are comparable at a glance
- [x] 1.3 Grow a crowded domain through sub-rings rather than into the next
      hop's ring, so ring position keeps meaning hops
- [x] 1.4 Replace the force layout, which was rediscovering the centre, the hop
      distance and the domain that the data already carried

## 2. The renderer

- [x] 2.1 Replace the hand-rolled SVG with NVL
- [x] 2.2 Measure the bundle cost rather than assuming it: 610 kB to 2,401 kB,
      183 to 706 kB gzipped
- [x] 2.3 Verify by grepping the built output that the two dependencies which
      must not reach the browser do not, and record that the audit tool still
      reports four high advisories against the installed tree
- [x] 2.4 Disable telemetry on the instance
- [x] 2.5 Bind the renderer to React by hand rather than installing the official
      wrapper, whose exact peer dependency would make a legacy-peer-deps flag
      permanent

## 3. Colour

- [x] 3.1 Convert design-token colours by rasterising a pixel and reading its
      bytes, the renderer's colour parser predating the authored colour space
- [x] 3.2 Record that reading the computed style back does not convert, and
      neither does a canvas fill round-trip - current browsers preserve the
      authored colour space through both

## 4. Keyboard and links

- [x] 4.1 Put a real focusable list beneath the canvas, replacing the per-node
      label and tab stop the SVG carried
- [x] 4.2 Link Neo4j's own browser from the back office header, in a new tab and
      never an iframe, since it refuses to be framed

## 5. Coverage

- [ ] 5.1 Cover the layout and the renderer. No test covers either today: this
      change is entirely client-side rendering and there is not one frontend test
      in this repository. The layout's inputs - hop distance and domain - come
      from the graph projection, which `tests/test_kg_insights.py` asserts
