# NGSO SLS Toolkit — Progress & Next Steps

## Last Updated: 2026-06-27 (post solver-alignment + adversarial review)

---

## Overall Status

**Phase:** Brainstorming → design (Slice A). No implementation code yet (design-before-code gate).

- Program decomposed into Slices A–E (see `design.md`).
- Slice A design in progress: Sections 1–2 approved by owner; Sections 3–6 pending.
- Living documentation scaffolding established (this file, `design.md`, `brainstorming.md`,
  `slice-a-coverage-core.md`, `README.md`, root `CLAUDE.md`).

---

## Task Checklist

### Documentation & process
- [x] Explore project context (spec, notebooks, Rivada doc, minkowski, warpfield)
- [x] Set up living docs scaffolding (CLAUDE.md, design-docs/)
- [x] Record program decomposition (design.md) and decisions log (brainstorming.md)
- [x] Create requirements.md (tracked requirements, original + emergent)
- [x] Finalize Slice A design (§1–§6) via solver-alignment + adversarial review
- [x] Owner reviews Slice A spec — approved; moving to implementation (MVP-first, working version ASAP)
- [x] Produce Slice A implementation plan (writing-plans) → `slice-a-implementation-plan.md`
- [x] Verify local venv: `.venv` runs the full stack (numpy/astropy/pandas/matplotlib/pytest/h3/sgp4/skyfield)
- [ ] Execute M1 (MVP walking skeleton) ← NEXT

### Slice A — SLS engine core (NOT STARTED — blocked on design approval)
Design sections (verified via 2 adversarial workflows against minkowski source):
- [x] §1 Package layout & module boundaries — approved
- [x] §2 Data model & pluggable propagator seam — approved
- [x] §3 Compute pipeline & sharding — approved (single-owner cellToParent shard; conservative
      cap pre-filter; max_elev primitive; user-cluster/regulatory = reporting overlays)
- [x] §4 Outputs — approved; acceptance rule + temporal policy resolved as configurable sim
      parameters (step_s float default 10s / NR-frame-aligned; target_availability; k_coverage;
      both %cells + population-weighted %users; curves always emitted). + in-view-interval family
      (SA7) and cell/beam-layout resolved (SA8: layout-independent geometry; cell_layout inert
      metadata; beam_layout→Slice B; no WarpField CellMode semantics) via `ntn-cell-beam-layout`
      adversarial workflow (3 workflows total now inform Slice A)
- [x] §5 CSV schemas (v1)
- [x] §6 Validation & comparability (oracle error budget; sharded==monolithic test;
      set-containment comparability vs solver)

Implementation — **Milestone 1 (MVP) COMPLETE** (2026-06-30, 20/20 tests passing in `.venv`):
- [x] Local venv runs full stack (numpy/astropy/pandas/matplotlib/pytest/h3/sgp4/skyfield)
- [x] `config.py` + `constellation/walker.py` (Walker T/P/F expansion)
- [x] `propagation/` (Propagator Protocol + vectorized KeplerJ2; oracle tests: two-body, SSO regression)
- [x] `geometry/` (frames GMST/ECEF/geodetic/ENU-up; topocentric elevation)
- [x] `grids/aor.py` (lat/lon grid + India AOR)  ·  [x] `coverage/` (max_elev, n_in_view, availability)
- [x] `presets.py` (Jio) + `pipeline.py` (run_coverage) + `io/csv_io.py` + `viz/plots.py`
- [x] `notebooks/01_slice_a_mvp.ipynb` (git-clone mode; runs in Colab + local Jupyter)
- **Validated result:** Jio 1600-sat over India @ ≥25° → 6–21 sats in view (mean 11.6), max-elev mean
  66.8°, availability=1.000 @ k=1 (correct: full constellation continuously covers India). ~10 s / 272
  cells (2° grid, 1 h @ 60 s). MVP is unchunked (memory ∝ cells×sats×times) → chunking is M3.

M1 deferred to later milestones (per plan roadmap): H3+sharding+prefilter (M3), elevation sweep (M4),
terminals/UT (M5), in-view intervals (M6), population+min-N sweep (M7), cell_layout metadata+guard (M8).

### Slices B–E — queued (designs not yet written)
- [ ] Slice B — capacity, link budget, demand, beam-hopping scheduler
- [ ] Slice C — optimization, interference, Cesium 3D viewer
- [ ] Slice D — NMTS export (reuse `scenarios/builder/py`)
- [ ] Slice E — live Spacetime/Minkowski NBI integration

---

## Current Focus

Slice A **Milestone 1 (MVP) is complete and tested**. Primary deliverable:
`notebooks/01_slice_a_mvp.ipynb` (set `REPO_URL` to a git remote for Colab).

## Next Steps

1. (Owner) Push repo to a git remote so the notebook's `!git clone` works in Colab.
2. M2 — oracle hardening (Skyfield/SGP4 ECI cross-check + error budget).
3. M3 — H3 grid + single-owner shards + conservative cap pre-filter + `sharded==monolithic` CI test
   (also lifts the MVP memory ceiling → enables fine grids / 24 h runs).
4. M4–M8 per the implementation-plan roadmap.

---

## Notes / Risks

- **Engine runs locally** in `.venv` (pypi reachable; full stack installed) and in Colab. Report
  faithfully whether a result was run locally vs Colab vs not yet.
- **Customer/reference material + the original 3.3 MB spec live under `references/` (gitignored).**
  In-repo authoritative docs are `docs/design-docs/`.
- **Git history was reset to a single clean commit (2026-06-30)** to remove customer-confidential
  files (Telesat CCMS/Lightspeed, Rivada) that the initial `git add -A` had committed. The tracked
  tree + history are now clean → **safe to push to a remote** (set the notebook's `REPO_URL` to it).
- **Disk caveat:** `/dev/sda1` (shared with the large monorepos) runs ~100% full; a low-space write
  truncated `README.md` once (rebuilt). If writes fail with ENOSPC, free space before retrying.
