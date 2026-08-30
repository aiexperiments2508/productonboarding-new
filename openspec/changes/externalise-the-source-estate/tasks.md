## 1. The manifest

- [x] 1.1 Declare at least ten external systems as data - identifier, title,
      owner, emitted event types, transport, conformance profile - in
      `sc/estate/manifest.py`; verify via
      `tests/test_estate.py::test_the_manifest_declares_ten_systems_with_owners`
- [x] 1.2 Keep every system name out of the ingest, connection and rendering
      modules; verify via
      `tests/test_estate.py::test_no_system_is_named_outside_the_manifest`
- [x] 1.3 Name the closed set of conformance defects in `sc/estate/defects.py`
      and spread them across the profiles so at least one system is clean and
      at least one is unreliable; verify via
      `tests/test_estate.py::test_the_estate_spans_good_and_bad_citizens`

## 2. Delivering in batches, at irregular times

- [x] 2.1 Build each system's delivery schedule from the configured seed, with
      varying batch sizes and intervals and every owned event in exactly one
      batch; verify via
      `tests/test_estate.py::test_a_system_delivers_in_batches_of_varying_size_and_spacing`
- [x] 2.2 Lay the estate's schedules on one timeline and confirm systems
      genuinely overlap; verify via
      `tests/test_estate.py::test_the_estate_delivers_concurrently`
- [x] 2.3 Assert the schedule is a function of the seed alone; verify via
      `tests/test_estate.py::test_the_same_seed_produces_the_same_schedule`
- [x] 2.4 Write one transaction per batch, never one per event, so ten
      producers do not contend on the single writer; verify by inspection of
      the emitter

## 3. Arrival, then sequencing

- [x] 3.1 Add an `arrivals` record carrying system, batch, arrival instant,
      event sequence and stamped defects; verify via
      `tests/test_estate.py::test_an_arrival_names_its_system_batch_and_instant`
- [x] 3.2 Release arrivals into ingestion in sequence order, leaving `ingest()`
      untouched, so an out-of-order arrival is not dropped against the single
      watermark; verify via
      `tests/test_estate.py::test_ingestion_follows_sequence_not_arrival`
- [x] 3.3 Assert the record is identical whichever order the batches landed in;
      verify via
      `tests/test_estate.py::test_arrival_order_does_not_change_the_record`
- [x] 3.4 Carry the system and any stamped defects through into the recorded
      fact; verify via
      `tests/test_ingest.py::test_a_recorded_fact_names_the_system_that_carried_it`
      and
      `tests/test_ingest.py::test_a_defect_stamped_on_arrival_survives_into_the_record`
- [x] 3.5 Assert every defect the estate can stamp is reported by something
      downstream; verify via
      `tests/test_estate.py::test_every_stamped_defect_is_detected`

## 4. Serving the estate over MCP

- [x] 4.1 Give each system an MCP server in `sc/estate/server.py`, mounted
      beside the peers by `run.py`, reachable without importing its module;
      verify via `tests/test_estate.py::test_every_system_exposes_an_mcp_surface`
- [ ] 4.2 Let `_Bridge` choose its transport from the connection record -
      spawned module or HTTP endpoint - without changing `call()`; verify via
      `tests/test_connections.py::test_two_transports_are_in_use_at_once_without_disagreeing`
      NOT DONE, and deliberately deferred. The handshake already picks its
      transport from the record, which is what connecting needs. Routing a
      *call* over HTTP only matters once a connected system's tool can be
      reached from inside a run, and admitting a tool to the evidence desk is
      `capability-registry-and-agent-cards`. Building the routing before the
      thing that would use it would be a transport with no caller.
- [x] 4.3 Confirm the existing stdio path and its tests are untouched; verify
      the nine assertions in `tests/test_protocols.py` still pass unmodified

## 5. Connections at runtime

- [x] 5.1 Add a `connections` store and a combined listing that leaves the
      built-in six unchanged; verify via
      `tests/test_connections.py::test_a_discovered_toolset_is_listed_beside_the_built_in_ones`
- [x] 5.2 Connect by address with a real handshake, recording what the system
      answered; verify via
      `tests/test_connections.py::test_a_system_is_connected_by_address_and_reports_its_tools`
- [x] 5.3 Record an unreachable address as degraded rather than raising; verify
      via `tests/test_connections.py::test_an_unreachable_address_is_recorded_not_raised`
- [x] 5.4 Refuse to let a discovered tool shadow a built-in name, and report the
      collision; verify via
      `tests/test_connections.py::test_a_discovered_tool_does_not_shadow_a_built_in_one`
- [x] 5.5 Degrade rather than fail when a connected system stops answering;
      verify via
      `tests/test_connections.py::test_an_unreachable_system_degrades_rather_than_failing`
- [x] 5.6 Make disconnect and reconnect idempotent; verify via
      `tests/test_connections.py::test_disconnecting_then_reconnecting_leaves_one_connection`

## 6. The map follows the estate

- [x] 6.1 Put connected systems on the derived map, including one that has
      delivered nothing; verify via
      `tests/test_connections.py::test_connected_systems_are_on_the_map_including_silent_ones`
- [x] 6.2 Stop emitting node coordinates from the generator and compute position
      from tier and live membership; verify via
      `tests/test_connections.py::test_no_node_position_is_stored`
- [x] 6.3 Degrade a disconnected system without retracting its facts; verify via
      `tests/test_connections.py::test_disconnecting_degrades_without_retracting`
- [x] 6.4 Emit topology changes on a stream that agrees with the listing; verify
      via `tests/test_connections.py::test_topology_changes_are_emitted_once_each`
      and `tests/test_connections.py::test_the_topology_stream_and_the_listing_agree`
- [x] 6.5 Give `NetworkMap.tsx` a systems tier that redraws on a topology
      message; verify by connecting and disconnecting a system from the UI and
      watching the map follow

## 7. The rename

- [x] 7.1 Rename the section label to Ingest Fabric in `nav.ts`, keeping the
      section identifier `tower` so routing and stored preferences are
      untouched; verify by inspection of the diff
- [x] 7.2 Update the prose that still says factory floor across the shell, the
      views and `sc/state/overlay.py`; verify no occurrence remains outside the
      archived OpenSpec changes
