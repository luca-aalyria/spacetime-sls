# Recap — where we are vs the original spec & customer requirements

## Last Updated: 2026-07-01

Honest status of the build against `references/spacetime_ngso_sls_toolkit_brainstorming.md`
(the program design) and the two anchor customers. **TL;DR:** the offline **coverage/
availability foundation + an interactive Colab tool** is built and tested (42 tests), and it
answers the Jio *coverage / minimum-satellite* question geometrically. Capacity, beam-hopping,
frequency, interference, RF/payload, the Telesat CCMS service-feasibility path, NMTS export, the
3D viewer, and live Spacetime integration are **not yet built**.

## Program slices (spec §5 / roadmap §10)

| Slice | Scope | Status |
|---|---|---|
| **A** SLS engine core (offline coverage/availability) | constellation, propagation, geometry, coverage, grids, io, viz | **~60% — in progress** |
| **B** Capacity, link budget, demand, beam-hopping | linkbudget, beams, demand modeling | **not started** |
| **C** Optimization, interference, 3D Cesium viewer | optimize (ILP), interference (EPFD), viewer | **not started** |
| **D** NMTS TextProto export (reuse `scenarios/builder/py`) | io/nmts | **not started** |
| **E** Live Spacetime/Minkowski NBI integration | harness → real Solver | **not started** |

## Slice A milestones

| Milestone | Status |
|---|---|
| M1 coverage MVP (Walker, Kepler+J2, elevation, availability, CSV, 2D plot) | ✅ done |
| M3 H3 grid + single-owner shards + conservative pre-filter + `sharded==monolithic` | ✅ done |
| M7 minimum-satellite sweep (coverage-vs-N, min-N marker) — **%-of-area metric** | ✅ done (pop-weighting deferred) |
| Interactive Colab notebook (Coverage Explorer + sweep, country-shape maps, tabs, progress) | ✅ done (beyond original plan) |
| M2 oracle hardening (Skyfield/SGP4 ECI cross-check + error budget) | ☐ (M1 used physical oracles only) |
| M4 elevation-threshold sweep + serving-elevation CDF | ☐ |
| M5 terminals / UT distributions + user-weighted availability | ☐ |
| M6 in-view interval / contact-duration family (SA7) | ☐ (designed, not built) |
| M8 `cell_layout` metadata surfaced + layout-independence guard (SA8) | ◐ (field exists, inert; not surfaced/tested) |

## Functional capabilities (spec §2.2)

| # | Capability | Status |
|---|---|---|
| F1 | Coverage **and** capacity analysis | ◐ coverage ✅ · capacity ✗ |
| F2 | Capacity estimation & optimization | ✗ (Slice B/C) |
| F3 | Beam-hopping schedule (32 beams/sat) | ✗ (Slice B) |
| F4 | Frequency assignment & reuse efficiency | ✗ (Slice B/C) |
| F5 | Coverage enhancement & resource optimization | ◐ min-N sweep only; no gateway/ILP |
| F6 | RF & payload-level planning | ✗ (Slice B) |

## Non-functional (spec §2.4) & interop (§8) & value-adds (§1)

| Requirement | Status |
|---|---|
| Runs in Colab; pip-installable; no native build | ✅ |
| Reproducible (seeded, versioned) | ✅ |
| Scale ~1600 sats × 24 h at few-min step | ✅ engine scales (sharded/chunked); default runs modest |
| CSV import **every** input / export **every** output | ◐ availability + sweep CSV out; not "every dataset" |
| Numerical methods documented + unit-tested | ✅ (42 tests, oracle checks) |
| **NMTS TextProto export** (value-add 3) | ✗ (Slice D) |
| **CSV in/out** (value-add 2) | ◐ partial |
| **Cesium/WebGL 3D viewer** (value-add 1) | ✗ (Slice C) — 2D mats maps instead for now |
| **Live Spacetime NBI** (value-add 4) | ✗ (Slice E) |

## Output visual targets (spec §4)

| Target | Status |
|---|---|
| Coverage availability maps (per cell/AOR) | ✅ (country-shape H3 maps + histogram) |
| Satellites-in-view vs latitude | ✅ |
| Global instantaneous visibility heatmap | ◐ (per-cell sats-in-view map; "Global" AOR supported) |
| Capacity, utilization & beam statistics | ✗ (Slice B) |
| Live 3D constellation & coverage viewer | ✗ (Slice C) |

## Customer requirements

**Reliance Jio (design-time).**
- Minimum-subset to serve India → **✅ answered geometrically** (M7): e.g. single 48° shell needs
  ~800 sats for 95% of area @ 99% availability, k=1; ~400 covers ~76%. Full dual-shell + capacity
  grading still to come.
- Coverage & capacity analysis → coverage ✅, capacity ✗.
- Beam-hopping (32 beams), frequency assignment/reuse, RF/payload planning → ✗ (Slice B).

**Telesat CCMS (operations-time).**
- Service feasibility per UT vs CIR/SLA; percentile/CDF stat-blocks; PFD/EPFD control;
  ~1000 sim-min ≤ 1 min; live CNOS_S/Spacetime → **✗ not started** (needs Slice B capacity/link-
  budget + Slice E live integration; the fast sharded engine is a foundation for the perf bar).

## Honest gaps & recommended sequence

Built: a **correct, tested, scalable coverage/availability engine** + a **usable interactive
tool**, closing the Jio *coverage* question. Biggest missing pieces, in dependency order:
1. **Slice B — capacity & link budget** (turns "satellites in view" into Mbps; unlocks F1/F2/F6
   and the Telesat CIR path). Highest value next.
2. **Slice A finish** — M4 elevation sweep, M5 UT distributions + population-weighted %-users
   (finishes the Jio "users covered" headline), M6 contact/dwell, M2 oracle hardening.
3. **Slice D — NMTS export**, then **Slice E — live Spacetime** (the harness to the real Solver).
4. **Slice C — beam-hopping, interference/EPFD, 3D viewer**.
