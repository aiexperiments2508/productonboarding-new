## ADDED Requirements

### Requirement: A neighbourhood is arranged by what the data already knows

The rendered neighbourhood SHALL derive each node's position from its hop
distance from the opened product and from its domain. It SHALL NOT be arranged
by a force solver.

The data already carries a centre, a hop distance and a domain. A solver
rediscovers all three approximately, having discarded the exact answer it was
handed.

Distance from the centre SHALL mean hops and nothing else. Where a domain holds
more nodes than its sector can show, it SHALL grow within its own band rather
than into the next hop's - a layout in which ring position means "hops, unless
that domain was busy" is not one a reader can hold.

Domains SHALL occupy a fixed arrangement, so that two products' neighbourhoods
are comparable at a glance.

#### Scenario: Position encodes hops and domain

- **WHEN** a neighbourhood is laid out
- **THEN** ring position follows hop distance and sector follows domain, in a
  fixed order
- **AND** this is verified by inspection of the layout module; no frontend test
  covers it, and the hop distances and domains it consumes are asserted by
  `tests/test_kg_insights.py::test_a_neighbourhood_grows_with_depth_and_stops_at_the_cap`
  and `::test_every_edge_joins_two_labels_the_model_admits`

### Requirement: A rendered graph keeps a keyboard-reachable equivalent

Where the graph is drawn without a document element per node, a focusable list
of the nodes SHALL be provided alongside it.

The previous renderer carried a label and a tab stop per node because it drew
each one as an element. Accessibility of the surface must not regress because
the drawing technique changed, and there is nowhere on a canvas for a per-node
tab stop to live.

#### Scenario: Every node is reachable without the canvas

- **WHEN** the graph is rendered
- **THEN** a focusable list of its nodes accompanies it
- **AND** this is verified by inspection of the graph component; there is no
  frontend test in this repository
