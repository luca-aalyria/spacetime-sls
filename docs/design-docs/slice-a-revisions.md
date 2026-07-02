# Slice A — Revisions: generalized constellations + full handover continuity + multi-shape sweep

**Status:** design (adversarially verified — 9-agent workflow `wxiaf4yi2`, 4 skeptic lenses; all
blocker/major fixes folded in). Rebases on the **already-shipped** k=1 make-before-break
increment (`coverage/continuity.py` + pipeline/sweep/viz, 66 tests).

**Decisions locked** (owner): (1) handover = **hybrid** grid detection + sub-second endpoint
refinement; (2) generators = **Walker + explicit asymmetric + phase-slot/lattice + multi-shell**
(defer J2 repeating-ground-track); (3) sweep = **2D P×spp** with **1D scatter + 2D heatmap**
(defer T/P/F); (4) k=1 **handover-gate toggle**, failing shapes flagged **red**, `min_N` = smallest
passing shape.

## Three additions on the unchanged compute contract

Everything rides the canonical `(n_sat,6)` `[a_km,e,i_rad,raan_rad,argp_rad,M_rad]` array
(`kepler_j2.py:28`) and the vectorized tensor engine. SI internally, degrees at the I/O boundary,
propagator seam untouched, `sharded == monolithic` preserved.

### 1. Canonical model + generators (SA12) — core `constellation/model.py` (NEW)

Frozen **SoA `ConstellationModel`**: `elems (n_sat,6)` + parallel `plane_uid`/`slot_id`/`shell_id`/
`epoch_s` int/float arrays + `sat_id` tuple. SoA (not the reference's per-sat AoS) so the tensor
engine and core purity are untouched and `combine = np.vstack/concatenate`.

- **Engine reads only `.elems`;** metadata is inert to propagate/coverage. Only continuity reads
  `.plane_uid`.
- **`plane_uid` from the PHYSICAL plane** — `np.unique` over quantized `(raan, inc, a)`, so
  co-planar lattice/Flower/asymmetric sats **share** a uid and the different-plane rule works.
  Genuinely-unknown plane → sentinel `-1`, treated **conservatively** (a `-1` handover is rejected,
  never silently accepted). `concat` offsets each shell's non-`-1` uids for cross-shell uniqueness.
- **Generators:** `walker_model` (Walker becomes one generator), `explicit_planes_model` (uneven
  RAAN, unequal sats/plane, per-plane a/e/i/argp overrides, empty planes), `phase_slot_model`
  (Flower/lattice via explicit `(RAAN,M0)` pairs — external-solver seam), `combine = concat`
  (multi-shell). **Defer** the J2 repeating-ground-track resonant solver.
- **`walker_elements(shell)` becomes a byte-identical shim** over `walker_model` reusing the exact
  fused `M` expression at `walker.py:20` (a split-sum path differs ~1 ULP and can flip an
  elevation exactly at `min_elev`, desyncing sharded==monolithic). A `np.array_equal` guard test
  lands first.
- `config.Shell` kept **verbatim**; add `GeneralizedShell` alongside; `Constellation.shells`
  widened; one assembly path `constellation_model(c)`.

### 2. Full handover continuity (SA13) — EXTEND core `coverage/continuity.py` + `refine.py` (NEW)

The shipped pure-numpy evaluator stays **in core** (no `collections.deque` — the forward DP over
end-sorted intervals is the same serving-path property). Enhancements:

- **Full `ContinuityRequirement`:** `tau_overlap` / `max_gap` / `min_dwell` / `require_different_plane`
  (via `plane_uid`) / `require_different_sat` / `max_handover_rate_hz`. Buffered-break edges are
  reported **separately** and excluded from the continuous verdict. Reference `dwell = target.end −
  source.end` and the target-extension guard are **correct** and kept (a skeptic's "BUG1" relabel
  was judged wrong and dropped).
- **Authoritative gate = the REFINED verdict** (`overlap = min(end)−max(start)` on refined
  endpoints vs `tau`). The integer-step map is a **fast pre-screen only**, never the pass/fail.
  Strict **positive overlap even when `tau==0`** (keeps the real-2-sat-window floor).
- **`refine.py` (NEW, core, numpy + relative propagation + math, NO `bisect`):** for each detected
  interval endpoint, bracket from the two **adjacent already-computed ECI samples** (guaranteed
  `elevation−min_elev` sign change) and run fixed-iteration bisection (`n=⌈log2(step/tol)⌉`),
  **diagonal-batched** (all endpoints in one `propagate` per iteration). Window-truncated
  (**censored**) ends are verified at the exact boundary instant and admitted only if
  `elevation ≥ min_elev` (else the cell fails — no fabricated coverage). Censored ends flagged.
- **§8 metrics:** min instantaneous multiplicity, %region-and-time per k, worst uncovered gap
  (from **merged** intervals, so failing cells get a real number), worst valid overlap, failed
  transitions, handover-rate (max & avg), min dwell, worst elevation/slant-range and worst
  point+time; reported **separately for geometric vs usable-link**. `max_handover_rate_hz` is a
  configurable **constraint** that fails a thrashing candidate. Worst **link margin** deferred to
  Slice B.

### Fidelity honesty (blocker fix)

The verdict's soundness is bounded by the **detection `step_s`**, not the refinement `tol_s` —
refinement only sharpens endpoints of intervals the coarse grid already found; a pass/gap shorter
than `step_s` is invisible. Therefore:
- Claim is **"grid-detected continuity with sub-second endpoint refinement within `step_s`
  resolution,"** not "event-based continuity."
- When the gate/refine is ON, **`step_s ≤ 0.5·min(tau_overlap, max_gap)` is a HARD precondition**
  (raise), with a floor.
- Outputs carry **both `detection_step_s` and `refine_tol_s`**.
- **k≥2** verdict stays pure-tensor `(n_in_view≥2).all(time)` but **labelled grid-quantized**
  (same Nyquist guard); a rigorous k≥2 continuum verdict is deferred.

### Scale honesty (blocker fix)

Continuity stays **shard-local + chunk-streamed** exactly as `pipeline.py` does today
(`inview_shard` ≤ ~260 MB for an India shard); **no monolithic `(n_cell,n_time,n_sat)` cube** is
ever built. The whole-map **coarse** `mbb_feasible` map is still emitted; the expensive sub-second
**refinement** runs only on the **k=1 critical-cell set** (cells passing k=1 availability but
failing k≥2, + boundary/critical points), hard-capped by `n_refine_cells`. `max_alt` changed to
**apoapsis** `max(a·(1+e)) − RE_EQ` (correct/conservative for eccentric/per-plane-override;
prefilter dilation monotone in altitude → superset preserved).

### 3. Multi-shape sweep + viz (SA14) — `sweep.py`, `viz/plots.py`, `explorer.py`

- **`multi_shape_sweep(planes_values, spp_values, …)`** over P×spp (× optional inclination) via the
  new `run_coverage_h3_elements` seam, so any generator's elems can be swept. **Grid cap**
  `max_grid_cells` (default 256) refuses/warns on oversized grids. Gate ON → candidate passes iff
  `pct_by_k[1] ≥ area_grade` **AND** refined `mbb_pass` **AND** `handover_rate ≤ max`. `min_N` =
  smallest passing N; N-degeneracy resolved by lexicographic Pareto (§9: constraints → min N → min
  planes → max worst-overlap → min rate). Full curve always emitted.
- **Plot 1 `plot_multi_shape_scatter`** (headline): x=N, one point per (P,spp), Pareto staircase
  highlighted, gate-fail = distinct **red** marker + center cross (colorblind-safe), area-grade
  hline + min-N vline, discrete planes legend. No x-jitter (x=N stays truthful).
- **Plot 2 `plot_multi_shape_heatmap`**: `pcolormesh` explicit edges (honest non-uniform ticks),
  color = %-area, stepped iso-N polylines, min-N/Pareto cells highlighted **identically** to the
  scatter, gate-fail = bold cross + edge hatch. Matplotlib only; **plotly import made lazy** in
  `plot_availability_map` so matplotlib-only callers don't pull plotly.
- **Explorer:** keep `MinSatSweep.planes` as `planes_min` and **add** `planes_max/step`
  (`max==min` → today's 1D behavior; back-compat), plus gate + `tau/gap/dwell/max_rate/
  different-plane/buffered` controls. CSV `mode='multi_shape'` with the §8 columns + manifest.

## Module changes

| Module | Change |
|---|---|
| `constellation/model.py` **(NEW core)** | SoA `ConstellationModel` + `OrbitTemplate/PlaneSpec/PhaseSlot` + `walker_model/explicit_planes_model/phase_slot_model` + `concat`. numpy/dataclasses/typing only. |
| `constellation/walker.py` | `walker_elements` = byte-identical shim over `walker_model` (guard test first). |
| `config.py` | `GeneralizedShell` + `constellation_model(c)`; widen `shells`; `SimConfig` defaulted continuity params (incl. `max_handover_rate_hz=inf`). `Shell` verbatim. |
| `pipeline.py` | `run_coverage_h3_elements(elems, plane_uid, …)` seam; delegate; `max_alt`→apoapsis; `do_mbb` calls enhanced `continuity_map` + `refine` on k=1-critical cells; assert Nyquist precondition; emit `detection_step_s`/`refine_tol_s`. |
| `coverage/continuity.py` | Enhance in place to full `ContinuityRequirement` (numpy-only). |
| `coverage/refine.py` **(NEW core)** | Bracketed fixed-iteration bisection endpoint refinement, diagonal-batched, censored-boundary verification. |
| `coverage/prefilter.py` | No code change; caller passes apoapsis `max_alt` (+ monotonicity assert). |
| `sweep.py` | `multi_shape_sweep`; keep `min_sat_sweep`/`inclination_sweep` verbatim. |
| `viz/plots.py` | lazy plotly; `plot_multi_shape_scatter` + `plot_multi_shape_heatmap`. |
| `explorer.py` | `MinSatSweep` planes range + gate controls; `multi_shape` branch + CSV. |

## Core-purity plan

`CORE_PKGS={constellation,propagation,geometry,coverage}`, `ALLOWED_TOP={numpy,astropy,typing,
dataclasses,datetime,math,__future__}`. New `constellation/model.py` and `coverage/refine.py` are
**auto-scanned** by the existing `test_core_purity.py` and stay numpy-only (no `collections`,
`bisect`, `sgp4`, `skyfield`). **No new bespoke allowlist test** (the retracted non-core package
would have needed one and could drift). `pipeline.py`/`config.py`/`sweep.py`/`viz`/`explorer` are
non-core and unaffected.

## Divergences (verified)

- **Retracted:** the non-core `ngso_sls/continuity/` package + its deque port + a second purity
  test. Continuity stays in core; the shipped `continuity.py` is the base.
- Reference AoS `Satellite/OrbitElements` → **SoA** `ConstellationModel`.
- `plane_uid` from physical plane (not slot index).
- "Event-based continuity" → **grid-detected + sub-second endpoint refinement** with a Nyquist
  precondition. Full §6 event bracketing across all crossings deferred.
- k≥2 continuum verdict, worst **link margin** (→Slice B), population-weighted §8 aggregates
  (need `terminals/`), per-shell `min_elev` (single-threshold engine), and multi-epoch (common
  epoch assumed) are **deferred/noted**, not silently dropped.

## Open questions (proposed defaults — confirm or adjust)

1. `plane_uid` quantization `q` — default round `raan`/`inc` to 1e-3 rad (~0.057°), `a` to 0.1 km.
2. `n_refine_cells` default **64**, `max_grid_cells` default **256** (vs the 1600-sat anchor).
3. Nyquist precondition: **raise** (not warn-and-clamp) with a `step_s` floor.
4. `handover_rate` reported as the max-min-overlap path's (max, avg) — documented, not renamed.
5. §8 aggregates **area-weighted** now; population-weighted when `terminals/` exists.
6. All four generators are **in the Slice-A DoD** (per decision 2), exercised in the notebook.
