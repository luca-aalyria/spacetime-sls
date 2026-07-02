# NGSO SLS Toolkit — Requirements

## Last Updated: 2026-07-02

Tracks requirements from the original design (`references/spacetime_ngso_sls_toolkit_brainstorming.md`, archived locally/gitignored)
plus ones identified during design. Status: ☐ planned · ◐ in design · ☑ designed · ✓ implemented.
Slice: A–E (see `design.md`).

**Slice A Milestone 1 (MVP) implemented (2026-06-30):** N1 (runs Colab+local), N2 (seeded config),
N4 (availability CSV — one output), N6 (oracle: two-body + SSO regression), SA1 (`max_elev`/`n_in_view`),
SA2 (coverage-availability output #3), SA5 (lat/lon grid). Remaining sub-items land in M2–M8.

**Slice A Milestone 3 (sharding) implemented (2026-06-30):** SA5 (H3 grid added → both grids done),
S4 (single-owner `cellToParent` shards + conservative cap pre-filter, ~18× sat-axis pruning),
S6 (`sharded == monolithic` bit-identical CI test), N3/N7 (chunked+sharded engine lifts the memory
ceiling; shards embarrassingly parallel — multi-worker still to be wired). 29 tests passing.

## Anchors
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| A1 | Jio design-time feasibility: greenfield 1600-sat dual shell; min-N subset to serve India at an acceptable grade | A | ◐ |
| A2 | Telesat CCMS ops-time: service feasibility (activation/quotation), capacity planning; per-UT CIR vs SLA, percentile/CDF stat-blocks; ~1000 sim-min ≤1 min wall-clock | B/E | ☐ |

## Functional (spec §2.2)
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| F1 | Coverage & capacity analysis | A (cov) / B (cap) | ◐ |
| F2 | Capacity estimation & optimization | B/C | ☐ |
| F3 | Beam-hopping schedule (32 beams/sat), pluggable scheduler | B | ☐ |
| F4 | Frequency assignment & reuse efficiency | B/C | ☐ |
| F5 | Coverage enhancement & resource optimization | C | ☐ |
| F6 | RF & payload-level planning | B | ☐ |

## Non-functional (spec §2.4, amended)
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| N1 | Runs end-to-end in Colab; pip-installable; no native build on critical path | A | ☑ |
| N2 | Reproducible: seeded, versioned inputs; same inputs → same outputs | A | ☑ |
| N3 | Scale ~1600 sats × 24 h on Colab. **Amended:** accuracy needs step ≤~30 s; few-minute step is a flagged fast-preview, not the accurate default (see C1/S5) | A | ☑ |
| N4 | CSV import every input dataset / export every output dataset | A | ☑ |
| N5 | NMTS TextProto export | D | ☐ |
| N6 | Numerical methods documented + unit-tested vs reference cases (oracle) | A | ☑ |
| N7 | Multi-worker scaling validated in the testing strategy (single-worker default now; sharding structured 1→n; scale tests as workers grow) | A core / test | ◐ |

## Interop & Viz (spec §4, §6, §8)
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| I1 | CSV in/out for all datasets | A | ☑ |
| I2 | NMTS TextProto export (reuse `scenarios/builder/py`) | D | ☐ |
| I3 | GeoJSON service-area / AOR support | A | ☑ |
| I4 | Live Spacetime NBI integration (pull state / push scenarios → real Solver) | E | ☐ |
| V1 | 2D maps + statistical charts for coverage outputs | A | ☑ |
| V2 | Cesium/WebGL 3D viewer | C | ☐ |

## Solver alignment (emergent)
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| S1 | Build core as close as possible to the Spacetime Solver (interchangeable/comparable) | all | ☑ |
| S2 | Mirror netsolve three-tier (core/adapter/driver) + phase vocab load→enumerate→aggregate→write | A | ☑ |
| S3 | Pluggable propagator seam (Kepler+J2 now; SGP4/Orekit/Principia later) | A | ☑ |
| S4 | Sharding: single-owner H3 `cellToParent` compute shard; conservative cap pre-filter (no false negatives); user-cluster + regulatory-area as reporting overlays | A | ☑ |
| S5 | Time alignment: `step_s`/`quantum_width` configurable **floats**, default 10 s; support frame-aligned quanta (5G NR SFN wrap = 10.24 s); record quantum in manifest | A | ☑ |
| S6 | `sharded == monolithic` determinism invariant (CI test) | A | ☑ |
| S7 | Comparability = set-containment (LP-accessible ⊆ SLS-in-view) + measured error budget; NOT value equality / not a wiring-only engine swap | A/E | ☑ |

## Configurability & data (emergent)
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| C1 | Time-step, availability target, k-coverage grade, headline metric are all simulation parameters with sensible defaults (step 10 s; target=none; k≥1; both metrics) | A | ☑ |
| C2 | Always emit full availability-vs-elevation and coverage-vs-N curves even when a target threshold is set | A | ☑ |
| C3 | Headline metric reports BOTH %-of-cells (area) and population-weighted %-of-users | A | ☑ |
| D1 | Ingest population-density maps from public, validated datasets | A | ◐ |

## Slice-A specifics
| ID | Requirement | Slice | Status |
|----|-------------|-------|--------|
| SA1 | `max_elev(cell,time)` canonical primitive + `n_in_view(cell,time)` | A | ☑ |
| SA2 | Outputs: sats-in-view-vs-lat, visibility heatmap, coverage availability per cell/AOR, min-N sweep | A | ☑ |
| SA3 | Elevation-threshold sweep + serving-elevation CDF | A | ☑ |
| SA4 | UT distributions as evaluation points (`terminals/`); user-weighted availability; %-users-covered | A | ☑ |
| SA5 | Both grids: H3 per-AOR + lat/lon global | A | ☑ |
| SA6 | Coverage-only scope (no link budget / capacity / beams / interference / optimization) | A | ☑ |
| SA7 | In-view interval (visibility-window) family: per-(sat, cell/UT) intervals (elevation≥min_elev) + distributions + count/frequency + in-view fraction, censoring-flagged; "dwell" reserved for Slice B | A | ☑ |
| SA8 | Cell/beam layout resolved: geometry is **layout-independent** (TS 38.300 §16.14.1). `cell_layout∈{EFC,QEFC,EMC,UNSPEC}` = inert metadata; `beam_layout`→Slice B; no WarpField CellMode semantics (H4); CI layout-independence guard | A | ☑ |
| SA9 | Point-evaluation assumption: coverage/elevation/intervals evaluated at a representative point per cell/UT; area-integrated cell coverage is future | A | ☑ |
| SA10 | Multi-k min-N analysis: sweep constellation size for k=1 (single) and k=2 (handover) coverage over an AOR; per-k min-N | A | ☑ |
| SA11 | **Coarse terrain masking** (mountains): **Tier-2 engine done** — azimuth (`az_el_deg`) + per-cell azimuth-binned horizon from a DEM (`terrain.horizon_mask_from_dem`, curvature-corrected) + visibility test `elev ≥ max(min_elev, mask[cell,az])` + Coverage-Explorer toggle. Real DEM via runtime fetch (`fetch_dem_erddap` — NOAA ERDDAP ETOPO, no key, bbox subset) or loaders (`dem_from_geotiff`, `dem_from_xyz_csv`); synthetic ridge for offline demo/tests; Explorer terrain-source selector (Demo ridge / ETOPO fetch). Format = lat_1d asc, lon_1d asc (-180..180), elev_2d[m]. **Note:** ERDDAP endpoint verifiable only in Colab (sandbox egress limited); distant terrain has small effect on a dense LEO constellation — matters most for local relief / high min-elev / sparse constellations | A | ◐ |

| SA12 | **Generalized constellation model**: `ConstellationModel` SoA + generators (Walker shim byte-identical, explicit-planes, phase-slot/lattice, multi-shell concat with plane_uid renumbering); propagation/coverage generator-independent. Design: `slice-a-revisions` | A | ☑ |
| SA13 | **Make-before-break handover continuity**: continuous k=1 + mandatory 2-sat overlap ≥ τ_overlap. **LIVE end-to-end** (`run_coverage_h3(continuity_overlap_s=…)`): grid-quantized detection (±step_s), different-**sat** serving-path gate, Nyquist precondition, resolution metadata (`detection_step_s`, `refine_tol_s`). **Built + unit-tested but NOT YET wired into the pipeline** (core-ready seams; `plane_uid` threaded but unconsumed): the **different-plane rule** + **merged-interval worst-gap** (`mbb_continuity_cell_req`) and **sub-second endpoint refinement** (`coverage/refine.py`) — so the design's "authoritative refined gate" is not yet realized in `run_coverage_h3`. **Inert** `SimConfig` knobs (no consumer yet): `max_buffered_gap_s`, `min_target_dwell_s`, `max_handover_rate_hz`, buffered-break. **Deferred**: full §6 event bracketing, rigorous k≥2 continuum verdict, worst link margin → Slice B. Promotes FUT4 | A | ◐ |
| SA14 | **Multi-shape min-sat sweep**: 2D planes × sats/plane grid with `multi_shape_sweep` (grid cap, gate, Pareto/min-N); 1D coverage-vs-N scatter + 2D P×spp heatmap (lazy plotly); Explorer planes-range + multi_shape branch + CSV | A | ☑ |
| SA15 | **Patent-shape screening post-check** (⏸️ deferred, lower priority): flag simulated shapes that may fall within a patented constellation geometry per `references/constellation-shapes-patent-analyis/` (19 families, 11 RED). Tiers: GEOMETRIC (auto) vs PRECONDITION/REVIEW (operational). Catalog-driven (`ngso_sls/data/patent_shapes.json`), configurable, **engineering flag not legal FTO**; must NOT flag ordinary Walker. Consumes the SA12 model. Stub: `slice-a-patent-screening.md` | A | ☐ |

## Process (emergent)
| ID | Requirement | Status |
|----|-------------|--------|
| P1 | Adversarial verification of every non-trivial design decision | ✓ ongoing |
| P2 | Concise, essentials-only documentation | ✓ ongoing |
| P3 | Maintain living docs (design, requirements, progress) | ✓ ongoing |

## Future (named, deferred)
| ID | Requirement | Status |
|----|-------------|--------|
| FUT1 | User types: fixed residential broadband, automotive, aero/IFC, UAV, maritime | ☐ |
| FUT2 | Population bands aligned with 3GPP NTN models (urban-macro, suburban, rural) | ☐ |
| FUT3 | Mobile terminals / routes (TimeGrid-shaped positions) | ☐ |
| FUT4 | Revisit time / max coverage gap / handover-continuity metrics | ☐ |
| FUT5 | Higher-fidelity propagators (SGP4, Orekit, Principia n-body) | ☐ |
