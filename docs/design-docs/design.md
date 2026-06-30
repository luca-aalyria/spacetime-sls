# NGSO SLS Toolkit — Program-Level Design

## Last Updated: 2026-06-27

## 1. Purpose

A system-level simulator (SLS) for NGSO constellations, delivered as a pip-installable
Python package (`ngso_sls`) + Colab notebooks, benchmarked against NCAT, and ultimately
wired to a live Aalyria Spacetime / Minkowski instance. The full requirements are in the
`references/spacetime_ngso_sls_toolkit_brainstorming.md` (archived locally, gitignored). This document records the
**decomposition into buildable slices** and the **cross-cutting architecture** that holds
across them.

## 2. Anchor customers (both must be satisfiable by the shared engine)

- **Reliance Jio — design-time.** Greenfield 1,600-sat dual shell (Primary 1200/40/1 @48°,
  Secondary 400/20/7 @70°, 650 km, 32 beams/sat). Opening question: *what minimum subset
  (~400) can begin serving India at an acceptable coverage/capacity grade?*
- **Telesat CCMS — operations-time.** In-service Lightspeed Ka-band LEO. Service feasibility
  at activation/quotation and capacity planning, per-UT CIR against SLA, percentile/CDF
  stat-blocks, ~1,000 simulated minutes in ≤1 min wall-clock.

One engine, two front-ends. The clean split between the physical/RF constellation model
and the service/demand layer is what lets both anchors share code.

## 3. Slice decomposition

Each slice is an independent spec → plan → build cycle. Order is dependency-driven.

| Slice | Scope | Spec roadmap phase | Status |
|---|---|---|---|
| **A** | SLS engine core: constellation, propagation, geometry, coverage, CSV I/O, 2D viz | Phase 1 | **Designing** |
| **B** | Capacity, link budget, demand, pluggable beam-hopping scheduler | Phase 2 | Queued |
| **C** | Optimization (min-sat/gateway/freq), interference (ITU Art.22 GEO-arc), Cesium 3D viewer | Phase 3 | Queued |
| **D** | NMTS TextProto export (reuse/extend `minkowski_ws3/scenarios/builder/py`) | Phase 4 | Queued |
| **E** | Live Spacetime/Minkowski NBI integration (push scenarios / pull state, routes, telemetry) | Phase 5 | Queued |

User's two original asks map as: **the SLS** = {A, B, C}; **the Spacetime connection** = {D, E}.

## 4. Cross-cutting architecture (holds across all slices)

- **Modular Python package.** Each module has one job and a CSV-in/array-out (or
  CSV-in/CSV-out) contract plus an in-memory API. Modules are independently testable.
- **Propagator seam.** Propagation is pluggable behind a `Propagator` Protocol; the
  coverage/geometry/output layers never see the implementation. Slice A ships analytic
  Kepler+J2; later slices may add SGP4, Orekit, or an n-body engine (Principia).
- **Grids.** H3 hexagonal per AOR + lat/lon global fallback, so cell outputs map to
  NCAT-style heatmaps and to CSV.
- **Units & frames.** SI internally; ECI out of propagation; ECEF/geodetic only inside
  geometry. (See CLAUDE.md → Conventions.)
- **Interop surfaces.** CSV for data interchange (all slices); NMTS TextProto for topology
  (Slice D); Spacetime NBI gRPC for live state (Slice E).
- **Standalone now, monorepo-aware later.** No Bazel in this package. Slices D/E will import
  `minkowski_ws3` builder/protos (or published `spacetime-api` package) at the boundary only.

## 5. Spacetime / Minkowski integration landscape (for Slices D & E)

Observed in `minkowski_ws3` and the Rivada notebooks:

- `minkowski_ws3/scenarios/builder/py` — fluent **NMTS** model builder SDK (Walker-Delta gen,
  constellation presets, orbit types, serialization "for Spacetime"). Reuse target for Slice D.
- `minkowski_ws3/api/` — full proto tree (`nbi`, `provisioning`, `federation`, `model`,
  `scheduling`, `telemetry`); `nmts/` schema + `nmtscli` (validate / export dot|d2|html|...).
- **Two live-NBI client patterns** in the notebooks:
  - *Older:* clone a precompiled-proto repo, raw `grpc.secure_channel` + `SpacetimeCallCredentials`,
    `api.nbi.v1alpha.*`, `ListIntents` / `SignalPropagation.Evaluate`.
  - *Newer:* `pip install spacetime-api`, `aalyria.spacetime.api.*`, `auth.Credentials`,
    `ListP2pSrTePolicies` / `ListIntents`.
  Slice E will choose between these (decision deferred to Slice E design).

## 5b. Code provenance (what is inherited from minkowski/Spacetime)

- **Slice-A core (and the engine generally): no minkowski/Aalyria code.** Deps are only
  numpy/astropy/pandas/matplotlib (+ h3/shapely/etc. in later slices). Algorithms are standard
  astrodynamics written from scratch. minkowski's contribution is **design influence only**
  (phase vocabulary, propagator seam, single-owner `cellToParent` sharding, λ cap geometry, NMTS
  taxonomy, comparability contract) — verified against source, but not ported.
- **Slice D — NMTS export:** will *reuse/extend* `minkowski_ws3/scenarios/builder/py` (genuine code reuse).
- **Slice E — NBI harness:** the one necessary Aalyria *code* dependency — `aalyria.spacetime.api.*`
  protobuf/gRPC bindings (published `spacetime-api` pkg or stubs from `minkowski_ws3/api/`) to call a
  live Spacetime instance and push/pull data. Confined to the Slice-E adapter; the core stays proto-free.

## 6. Open program-level questions (resolve when the owning slice is reached)

- Slice E: read-only (pull state to seed/validate) vs full round-trip (push scenario →
  Spacetime computes → pull results), and which NBI client pattern.
- Slice D: how much of `scenarios/builder/py` to reuse vs wrap.
- Live instance access + credentials availability for Slice E.
