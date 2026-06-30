# Slice A — SLS Engine Core (Offline) — Detailed Design

## Last Updated: 2026-06-27

## Status

- §1 Package layout & module boundaries — **APPROVED**
- §2 Data model & pluggable propagator seam — **APPROVED**
- §3 Compute pipeline & sharding — **APPROVED (revised post adversarial review)**
- §4 Outputs — **APPROVED** (acceptance rule + temporal policy resolved as sim parameters)
- §5 CSV schemas (v1) — **APPROVED**
- §6 Validation & comparability — **APPROVED (revised)**

Solver-alignment and sharding were verified against minkowski source via two adversarial
workflows; corrections below supersede the earlier drafts. See [[spacetime-sls-project]].

## Scope (locked)

In: constellation generation (Walker T/P/F + custom shells), analytic Kepler+J2 propagation
behind a pluggable seam, geometry/access at min-elevation, the four outputs below, CSV
import/export, 2D viz. Out (deferred to later slices): link budget, beam-hopping, demand
*modeling* (only a population overlay is in), optimization (ILP), interference, NMTS, 3D viewer.

**Four required outputs (definition of done):**
1. Sats-in-view vs latitude (with optional population-per-degree overlay).
2. Global visibility heatmap (sats-in-view across lat/lon or H3).
3. Coverage availability per cell/AOR (% timesteps serviceable at min-elev; mean & p5).
4. Min-satellite subset answer (coverage-vs-N sweep for the Jio question).

**Compute approach:** Approach 3 (hybrid) — Astropy for time/frame correctness; vectorized
NumPy for the hot path. Target NFR: ~1,600 sats × 24 h × few-minute step on Colab-class HW.

---

## §1. Package layout & module boundaries — APPROVED

```
spacetime-sls/
  ngso_sls/
    __init__.py
    config.py            # SimConfig, TimeGrid, seeds, units
    constellation/       # walker.py, shells.py
    propagation/         # base.py (Propagator seam), kepler_j2.py
    geometry/            # frames.py (ECI/ECEF/geodetic, GMST), access.py
    grids/               # aor.py (H3 + lat/lon)
    coverage/            # visibility.py, availability.py, sweep.py
    demand/              # population.py (overlay only)
    io/                  # csv_io.py
    viz/                 # plots.py
  notebooks/01_slice_a_coverage.ipynb
  tests/
  pyproject.toml
  README.md
```

Module contracts (one job each):

| Module | Does | Depends on |
|---|---|---|
| constellation | Walker/custom shells → classical elements; gateways | numpy |
| propagation | elements + time grid → ECI state tensor, behind an interface | numpy, astropy consts |
| geometry | frame transforms + look-angle/access geometry | numpy, astropy |
| grids | AOR → cell centers (H3 + lat/lon) | h3, shapely/geopandas |
| coverage | visibility tensor → sats-in-view, availability, min-sat sweep | numpy |
| demand | population raster overlay (for sats-in-view plot only) | pandas |
| io | CSV import/export for all Slice-A datasets | pandas |
| viz | the four 2D outputs | matplotlib, cartopy |

Deferred modules (`linkbudget`, `beams`, `interference`, `optimize`, NMTS exporter, Cesium
viewer) are **not** created in Slice A.

---

## §2. Data model & pluggable propagator seam — APPROVED

Core dataclasses (frozen, seeded, serializable): `Shell` (walker_T/P/F, altitude, inclination,
raan0, phase0, ecc, arg_perigee, min_elev_user/feeder), `Constellation` (shells + gateways),
`TimeGrid` (epoch, duration_s, step_s, quantum_width_s — floats, default 10.0),
`ShardingConfig` (strategy, enabled=False, n_workers=1),
`SimConfig` (constellation + time_grid + sharding + seed + target_availability=None +
k_coverage=1 + cell_layout="UNSPEC"). `cell_layout ∈ {EFC,QEFC,EMC,UNSPEC}` is **inert metadata**
in Slice A (SA8): validated, stamped into manifest/CSV headers, never branched on. (`beam_layout`
is a Slice-B field — not present here.)

`walker.py` expands a Shell into an `(n_sat, 6)` classical-elements array via the Walker T/P/F
rule (P planes in RAAN; T/P sats per plane in mean anomaly; inter-plane phasing `F·360/T`).
Custom shells may be supplied directly as an elements CSV.

Propagator seam:

```python
class Propagator(Protocol):
    def propagate(self,
                  elements: ClassicalElements,   # (n_sat, 6)
                  times_s: np.ndarray             # (n_time,) since epoch
                  ) -> np.ndarray:                # (n_sat, n_time, 3) ECI position, km
        ...
```

- Slice A ships `KeplerJ2Propagator` (vectorized mean-motion + J2 secular drift on Ω, ω, M →
  elements→ECI). Pure NumPy, broadcast over `(n_sat, n_time)`.
- Future drop-ins (SGP4, Orekit, Principia n-body) implement the same signature, selected by
  config. Downstream (`geometry`, `coverage`, `viz`) only ever see the ECI tensor.
- Velocity intentionally excluded from the Slice-A interface (coverage doesn't need it);
  planned backward-compatible extension to `(position, velocity)` when a slice needs Doppler.

Units & frames: SI internally (km, s; radians in math, degrees at I/O boundary); ECI out of
propagation; ECEF/geodetic conversion only inside geometry via Astropy GMST.

---

## §3. Compute pipeline & sharding

Phase **vocabulary** borrowed from netsolve (prose only — no empty stubs in code):
**load → enumerate(access) → aggregate → write.** (Solver adds `select`=CP-SAT and
`reconcile`=DiffEngine between enumerate/aggregate in Slices B/E; Slice A omits them.)

1. **load** — SimConfig/CSV → Walker elements `(n_sat,6)`; build time grid + ground cell grid.
2. **enumerate** — `propagate(elements,times)→ECI (n_sat,n_time,3)`; geometry→ECEF (Astropy GMST)
   →topocentric elevation; conservative pre-filter prunes sats per shard.
3. **aggregate** — reduce to canonical primitive **`max_elev(cell,time)`** (best-sat elevation)
   + **`n_in_view(cell,time)`**; both are order-independent sat-axis reductions ⇒ deterministic
   under any chunking.
4. **write** — versioned CSVs + run manifest.

**Core import invariant** (mirrors netsolve-core): `constellation/propagation/geometry/coverage`
import only numpy (+astropy in geometry) — no pandas/matplotlib/NMTS/proto. Test-guarded; this is
what lets Slice E wrap the unchanged core.

**Sharding (corrected after adversarial review):**
- Compute shard = H3 `cellToParent`, **single-owner cells** (each cell in exactly one shard).
  Mirrors the solver's hierarchical shard; avoids the cross-shard `max()` undercount (a real FN).
- **Conservative satellite pre-filter** (SLS-original geometry — *not* the solver's CIR-gated
  k-ring). Exact fact: sat in view of ground point *G* ⟺ central angle(sub-point,*G*) ≤ cap
  half-angle **λ**, with `sin(η)=(Re/(Re+h))·cos(ε)`, `λ=90°−ε−η` (=9.674°≈1076 km at h=650,
  ε=25°). Rule: keep sat *s* for shard *S* iff at any sampled t its sub-point is within
  **λ + r_cell + Vground·step_s/2** of some cell *S* owns — dilating the cell-footprint **union**
  (not the coarse parent: a corner UT lies r_cell beyond the cell center) plus a half-step motion
  halo (`Vground≈6.84 km/s`). Implemented as 3 escalating tests: latitude band → longitude gate →
  exact great-circle `sinφs·sinφc+cosφs·cosφc·cosΔlon ≥ cos(λ+r_cell)` (only on survivors). Every
  test is a relaxation of true visibility ⇒ **zero false negatives** (dropped sats have
  elevation<ε all chunk); ~18× sat-axis pruning (≈90/1600 for India). The exact per-(sat,cell)
  elevation test still decides actual visibility; the pre-filter only decides what to test.
- Time-chunking = inner loop (memory only). Sharding optional; single-machine default = global.
- **user-cluster / regulatory-area = reporting/aggregation overlays** applied after per-cell
  coverage — NOT the compute shard (`GeographicRegion` is a provisioning target, not a shard key).
- CI invariant: **sharded output == global output, bit-identical.**

## §4. Outputs

`max_elev(cell,time)` powers all four required outputs plus two upgrades:
- **Elevation-threshold sweep:** availability(cell,θ) for a θ-vector via broadcast on max_elev
  (no re-propagation); serving-elevation CDF is its complement. Min-elev (user 25°/feeder 30°) are
  config cutoffs marking the operating point. Sats-in-view count uses the separate `n_in_view`.
- **In-view interval family** (a.k.a. visibility windows; "dwell" reserved for Slice B served beams).
  Needs the **sat-resolved** elevation array (before the best-sat max). Per-(sat, cell/UT) interval
  `(sat,cell,t_start,t_end,duration,max_elev_in_pass)`; distributions per cell/AOR
  (mean/median/min/max/p5/p50/p95/CDF); contact count/frequency; aggregate in-view fraction
  (== availability at k=1 under matching min_elev/grid/censoring). Window-truncated intervals are
  **censoring-flagged**. Optional inter-contact gap behind a flag. Pure geometry; feeds Telesat +
  Nguyen analyses. Evaluated at a representative point per cell/UT (area-integration = future).
- **UT/UE distributions:** first-class `terminals/` module; a `TerminalSet`
  (id,lat,lon,weight,type,min_elev_override) is another set of evaluation points on the identical
  access path. Generators: uniform-in-AOR, population-weighted, hotspot, polygon, density/count,
  CSV import (all seeded). Enables user-weighted availability + %-of-users-covered. Traffic/CIR/
  mobility deferred to Slice B (schema seam reserved).

Output 4 (Jio min-N): coverage-vs-N sweep. **All knobs are sim parameters** (SimConfig), defaults
in brackets: `step_s` float [10.0] (configurable; supports frame-aligned quanta, e.g. 5G NR SFN
wrap 10.24 s; ≤~30 s for accuracy, coarser = flagged fast-preview); `target_availability` [None →
emit full curve only]; `k_coverage` [1] (n-sats-in-view threshold, configurable); headline metric =
**both** %-of-cells (area) and population-weighted %-of-users. The full availability-vs-elevation
and coverage-vs-N **curves are always emitted** even when a target is set (C2). Population rasters
come from public validated datasets (D1). User-type taxonomy (fixed/auto/aero/UAV/maritime) and
3GPP-NTN population bands (urban-macro/suburban/rural) are a reserved schema seam → future (FUT1/2).

**Cell/beam layout (SA8 — resolved).** 3GPP TS 38.300 §16.14.1 defines EFC/QEFC/EMC by beam-coverage
behavior, not visibility geometry ⇒ sats-in-view, elevation, and in-view intervals at a fixed point
are **layout-independent** (H1/H2 confirmed). Slice A does **not** branch on layout: `cell_layout ∈
{EFC,QEFC,EMC,UNSPEC}` is **inert validated metadata** (manifest + CSV header only; EMC keeps the
grid Earth-fixed + stamps a "moving-footprint deferred to Slice B" note). `beam_layout` (EFB/EMB) is
**not** added to Slice A — it belongs to the Slice-B beams module. We do **not** mirror WarpField
`CellMode` semantics (mapped_cell_id/SIB19/SatSwitch/handover = category error, H4); only the
elevation-formula concept is reused (re-derived in NumPy). CI **layout-independence guard**: coverage
+ interval data bit-identical across all `cell_layout` values (manifest header excluded).

Deferred-but-named (not in DoD unless owner opts in): revisit time, max coverage gap, handover.
Deferred to Slice B+: serving-sat selection; service continuity (EFC SatSwitch, QEFC reposition/
re-sync, EMC moving footprint); EFB/EMB pointing; handover/L3/CHO; Mapped Cell ID (Slice-D/RAN);
link budget.

## §5. CSV schemas (v1)

Inputs: `shells`, `payload_beams` (only min-elev used in A), `gateways`, `aor` (GeoJSON),
`terminals`, `population` raster.
Outputs: `sats_in_view_vs_lat`, `visibility_heatmap` (cell_id,lat,lon,mean/p5/p95),
`coverage_availability` (cell_id, avail@cutoff, user-weighted), `availability_by_elevation`
(cell|AOR × θ), `serving_elevation_pctiles`, `in_view_intervals` (sat, cell/UT, t_start/end, duration, max_elev,
censored_flag) + `in_view_interval_stats` (per cell/AOR), `min_sat_sweep` (N, %cells, %users),
`shard_manifest`, `run_manifest` (incl. `cell_layout`). Every output embeds the run manifest (seed, propagator, step_s,
quantumWidth-for-reference) in its header.

## §6. Validation & comparability

- **Oracle:** KeplerJ2 ECI vs Skyfield/SGP4 — report along/cross/radial error vs propagation time
  (not a flat %).
- **Coverage metric:** boolean agreement + pass-boundary time-shift (thresholded in_view makes
  %-position-error the wrong bound).
- **`sharded == monolithic`** CI test (conservative-relaxation guard).
- **Layout-independence guard** CI test: coverage + interval data bit-identical across all
  `cell_layout` values for a fixed scenario + min_elev (manifest header excluded).
- **Interval censoring:** flag window-truncated (left/right) intervals so dwell stats aren't biased;
  in-view fraction == availability only at matching (min_elev, grid, censoring) at k=1 — pin in CI.
- **Monotonicity:** availability(θ) non-increasing — assert.
- **Determinism:** integer-count availability (#serviceable/n_time), stable hashes,
  location-derived shard keys (no order-dependent fallback).
- **Solver comparability (honest):** Slice A in-view is a **geometric upper-bound envelope**
  (necessary, not sufficient; real accessibility adds antenna-FOV + finite gain). Contract =
  **set-containment (LP-accessible ⊆ SLS-in-view) + measured gap**, not equality, not a
  wiring-only engine swap. `SatEngine.SolveInterval` consumes a richer input set
  (BeamCandidates, PropagationVectors, LinkRequests…) supplied by later slices.

## Divergences from the solver (deliberate)

- No MILP/CP-SAT, no intent reconcile, no RF/link-budget — coverage geometry only.
- Core is NMTS-free; conversion confined to the Slice-D/E adapter.
- Analytic Kepler+J2 vs solver STK-class engine (secular along-track drift; budgeted, not assumed).
- Compute shard = H3 cellToParent single-owner; user-cluster/regulatory = reporting overlays.
- `step_s`/`quantum_width` are configurable floats (default 10 s; e.g. 10.24 s for NR-aligned);
  quantum recorded in manifest only, not enforced as an integer multiple in TimeGrid.
- `cell_layout` is inert metadata; geometry is layout-independent. `beam_layout` and all serving/
  handover/beam-pointing behavior are Slice B+. Coverage evaluated at a representative point per
  cell/UT (area-integration deferred).
