# NGSO SLS Toolkit — Brainstorming Decisions Log

## Last Updated: 2026-06-27

Chronological record of decisions made during brainstorming, with rationale, so future
sessions don't re-litigate settled choices.

## Session 1 (2026-06-26 → 2026-06-27)

### Context explored
- Original spec `references/spacetime_ngso_sls_toolkit_brainstorming.md` (archived locally; full program design, 11 modules,
  NCAT benchmark, two anchors, 5-phase roadmap).
- Rivada Colab notebooks (two live-NBI client patterns; utilization/SR-fulfilment examples).
- `7-8-9_Rivada_Spacetime_Simulation_and_Analysis.md` (end-state: emulate system → drive live
  Spacetime → analyze loading/beam-hopping/routing/bandwidth/EPFD).
- `minkowski_ws3`: `scenarios/builder/py` (NMTS builder SDK w/ Walker-Delta gen), `api/` proto
  tree, `nmts/` + `nmtscli`.
- `warpfield` used as the reference for documentation structure.

### Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Program is decomposed into 5 slices (A–E)**, each its own spec→plan→build cycle | Whole spec (5 phases / 11 modules / 2 anchors / 3D viewer / NBI) is far too large for one spec; single-spec attempt would be shallow and wrong in the load-bearing details. |
| D2 | **Build Slice A (SLS engine core) first** | Foundation everything else builds on; answers the Jio min-satellite question; offline so no external-dependency risk. |
| D3 | **Standalone package now, monorepo-aware later** | Colab-first, loosest coupling; but structured so Slices D/E can import `minkowski_ws3` builder/protos at the boundary. No Bazel in this package. |
| D4 | **Slice A "done" = all four outputs**: sats-in-view vs latitude, global visibility heatmap, coverage availability per cell/AOR, min-satellite subset answer | Owner selected all four; coherent Phase-1 scope that directly answers the Jio question. |
| D5 | **Both grids**: H3 per-AOR + lat/lon global fallback | Global/latitudinal outputs suit lat/lon; AOR outputs suit H3 hex (NCAT-style). |
| D6 | **Propagation: analytic Kepler + J2 only** for Slice A; SGP4/TLE deferred | Jio is greenfield (no TLEs); orbital drift fidelity doesn't change initial coverage/capacity conclusions. |
| D7 | **Propagator is a pluggable interface (seam)** | Owner: "we can incorporate better propagators later including exotic n-body engines like Principia." Coverage/geometry/outputs must not depend on the impl. |
| D8 | **Compute core = Approach 3 (hybrid)**: Astropy for time/frame correctness; vectorized NumPy for the hot path (propagation→ECI, geometry, visibility tensor) | Only approach that meets the NFR (~1,600 sats × 24h × few-min step on Colab) while keeping a unit-testable numerical core; Skyfield/sgp4 kept as test oracles. |
| D9 | **Maintain living docs** (design-docs/, progress.md w/ checklist, CLAUDE.md guidance) modeled on `warpfield`, from the start | Owner request before approving the design. |
| D10 | **Mirror the Spacetime Solver** (Satsolver/Netsolve/Link-Predictor); core interchangeable with live Solver | Slice-E harness will call the real Solver; verified vs minkowski source. |
| D11 | **Compute shard = H3 cellToParent single-owner**; user-cluster + regulatory-area = reporting overlays (not shard keys) | Adversarial review: solver H3 shard is a CP-SAT/CIR construct; `GeographicRegion` is provisioning CRUD. Avoids cross-shard max() undercount. |
| D12 | **Conservative cap pre-filter** (dilate cell-footprint union by λ=9.674° + circumradius + ½-step halo); SLS-original geometry, not the solver k-ring | Guarantees no false negatives; adversarial review corrected the k-ring/λ conflation. |
| D13 | **Comparability = set-containment** (LP-accessible ⊆ SLS-in-view) + measured error budget; NOT value equality | SLS in-view is a geometric upper-bound envelope; real accessibility adds FOV+gain. |
| D14 | **Configurable-first** params (step_s/quantum floats default 10 s, NR-frame-aligned 10.24 s ok; target_availability; k_coverage; both %cells+%users); curves always emitted | Owner answers. Retires the "multiple-of-10s" idea. |
| D15 | **Add a requirements.md**; ingest public population datasets; reserve user-type + 3GPP-NTN population-band taxonomy (future) | Owner request. |

### Environment facts established
- Sandbox declared **no internet** by owner (probe to pypi returned 200, but honor the
  declaration). System **Python 3.14.5**, no `pip`, scientific stack **absent**.
- **Google Colab is the real run/validation target.** Local sandbox is for authoring + light
  pure-Python checks; numerical validation runs in Colab or a staged offline venv.

### Still open (for later slices)
- Slice E: pull-only vs round-trip; which NBI client pattern (raw grpc vs `spacetime-api`).
- Slice D: reuse depth of `scenarios/builder/py`.
- Slice A acceptance threshold for "acceptable coverage grade" (being finalized in Section 4 of slice-a design).
