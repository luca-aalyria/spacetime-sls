# Jio minimal scenario (pybuilder sources)

This folder archives the pybuilder sources for the Jio 200-satellite NMTS
scenario. The build home is the Minkowski monorepo — copy these files to
`spacebox/archon/scenarios/pybuilder/` there and build with Bazel. They do
not run from this repository.

## Files

- `jio_min_scenario.py` — the scenario: Walker 200/20/1 at 48 deg, 650 km;
  251 user terminals on India H3 res-3 cell centers; 3 India gateways; a PoP;
  502 bidirectional SR-TE path requests.
- `india_cells.py` — generated list of 251 India H3 res-3 cell centers.
- `BUILD.pybuilder` — the BUILD additions (`jio_min_scenario_builder`
  py_binary + `jio_min_scenario` py_scenario_rule). Rename to `BUILD` content
  in the monorepo package.

## Build and load

```bash
cd <minkowski>  # with the files in spacebox/archon/scenarios/pybuilder/
bazel build //spacebox/archon/scenarios/pybuilder:jio_min_scenario
D=bazel-bin/spacebox/archon/scenarios/pybuilder/jio_min_scenario_scenario
SC=bazel-bin/tools/storectl/storectl_/storectl
for f in $D/model/*.txtpb; do
  $SC import -e localhost:9996 --flavor=fragment --ignore-consistency --file $f
done
$SC import -e localhost:9996 --flavor=entities --ignore-consistency \
  --file $D/storage/provisioning.txtpb
```

Output: 9,834 entities, 18,740 relationships (459 fragments + 502
provisioning entities).

## Model requirements found on the pinned instance (2026-08-18/19)

- Satellite user antennas MUST carry `field_of_regard` (conic, 75 deg, as on
  fss01's DRA antennas). Without it, the link predictor emits link reports
  but zero BEAM_CANDIDATE_SEGMENT entities, and satsolver reports every UT
  as "missing beam candidates" and routes nothing.
- Satellite Keplerian elements MUST carry an explicit `epoch` (fss01 does).
  Without it, solver components propagate from unix 0, and the NetOps UI
  draws no orbits and places no satellites, so every node looks unconnected.
- The PoP network node has no platform parent. fss01 shares this shape;
  satsolver logs a warning and continues.
