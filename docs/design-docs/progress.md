# NGSO SLS Toolkit — Progress & Next Steps

## Last Updated: 2026-08-16 (notebooks 01+07 MERGED; shared analysis panel; explorer fixes)

### Coverage Explorer unification (owner-directed, 2026-08-16)
- `LiveCoverageExplorer` = nb01's GUI minus constellation section, elements-fed;
  `WalkerConstellationBuilder` + `ConstellationSource` (Walker presets/custom OR live
  Spacetime NMTS pull w/ dump fallback + model min-elev hint; lazy spacetime imports).
- **nb01 is now the single Coverage Explorer** (A1 source -> A2 shared analysis); nb07
  retired (analysis divergence eliminated). nb06 (intent analytics) unchanged.
- Fixes: ipywidgets Output-context exception swallow in run() (UnboundLocalError on
  compute failure), status bar now shows the real error; step slider min 10s -> 1s
  (MBB gate usability); notebooks 01/05/06 dual-env solid (local anchor + Colab clone).
- Env: ONE shared uv venv (/workspace-anchored, standalone cpython 3.12.14 in mount);
  host mirror of the port-forward = same sandbox_live_setup.sh script. 144 tests green.

---

## Last Updated: 2026-08-15 (live fss01-demo loop closed: dump + notebooks 05/06/07 executed live)

### Slice E — live-instance analytics (sandbox → fss01-demo via port-forward, read-only)
- Live loop VERIFIED end-to-end: `tools/sandbox_live_setup.sh` (kubectl+ADC+supervised
  forward) → `StorageEntityStore` → nb05 full pull (150 sats, India k=1 avail 0.996,
  2000 route hops, replay snapshot), nb06 intent analytics (gateway load 6x imbalance,
  UT handover timeline, OISL 144+144 lattice, RK_CONTAINS validation join → 100%),
  nb07 = notebook-01 Slice-A analysis on the LIVE constellation (10x15 @53°/1157 km;
  global res-2: 5862 cells, k=1 mean 0.923, 87.2% fully covered; Europe elev sweep).
- Real-proto compat fixes (found live, all unit-tested): _NmtsEntityView (ek_* oneof →
  int kind), _is_external (message-field truthiness), _kepler (oneof default-instance),
  intent state enum→name. 141 tests green. Dump tool → /workspace/<instance>-dump.
- HTML exports in `outputs/notebook-exports/` (gitignored); CSVs in `outputs/`.
- **Jio alignment (owner directive 2026-08-15):** notebooks must ultimately answer the
  original Reliance Jio questions (min-N/k sweep over India, availability targets,
  population-weighted coverage — M4–M7). nb07 proves engine-parity on a live
  constellation; the Jio path additionally needs Slice D (push the 1600-sat candidate
  INTO an instance) + solver-run + pull-back compare. See Current Focus.
- **nb07 v2 (2026-08-15):** nb01-style controls (AOR/res/duration/k, optional global) +
  service parameters FROM the model — min elevation derived from NMTS `ek_antenna`
  `field_of_regard` conic half-angles (UT 65° cone → 25° min elev; gateways 80° → 10°;
  sats 75° nadir). India res-3 sweep: k=1 mean avail 1.000/0.996/0.657 @ 10/25/40°.
- **Ephemeral instances (owner directive 2026-08-15):** exploration doc
  `slice-de-ephemeral-instances.md` — spacebox IS the mechanism (gRPC SpaceboxOperator
  Create/Destroy/Watch + TTL reaper on e2e-internal; parallel namespaces native; CLI
  `--scenario` loads checked-in scenarios post-create; pybuilder = parameterized NMTS
  generator). Gated on owner approval + adversarial pass (write-path policy change).

---

## Prior — Last Updated: 2026-08-14 (NBI stubs vendored; GFS wildcard mirror; raw-Store port-forward path)

### Slice E — raw Store access path (`StorageEntityStore`, no platform deploy needed)
- Engdoc-verified: all storage backends serve `minkowski.proto.Store` gRPC on port 9999;
  `kubectl port-forward svc/storage -n <ns> 9999:9999` + plaintext gRPC is the blessed
  dev pattern (`nbictl`/`storectl` do exactly this; storectl even supervises the forward).
- Vendored `proto_internal/storage/storage.proto` + 90-proto closure (regen script now
  computes closures dynamically: `tools/regen_spacetime_stubs.sh`, replaces regen_nbi_stubs).
  New `HAS_STORAGE` probe; side-effect: `HAS_NMTS` now also True offline (real nmts.proto
  in the closure).
- `StorageEntityStore` implements the read-only EntityStore protocol over `Store.Get/
  GetEntities` (INTENT/NMTS_ENTITY/NMTS_RELATIONSHIP; CEL rejected — internal filter only).
  Verified with an in-process gRPC Store server (real wire round-trip, 4 tests).
- Auth boundary = kubectl access (dev/ops path); intentfe facade remains the key-authed
  product path. Future: same surface reads SCHEDULE / BEAM_CANDIDATE_SEGMENT /
  PROPAGATION_VECTOR_SEGMENT for Slices B/C.
- Suite: **138 tests green** in the local venv.

### Slice E — NBI NetOps Python stubs (unblocks Colab intent queries without the pip rebuild)
- Generated `nbi_pb2`/`nbi_pb2_grpc` + 32-proto transitive closure from `minkowski`
  @ `nbi-intent-facade` via grpcio-tools → `vendor/spacetime_api_stubs/` (66 modules,
  git-tracked so Colab's clone gets them; regen: `tools/regen_spacetime_stubs.sh`).
- `_deps.py` NBI probe now tries pip root then bazel/vendored root (`api.nbi.v1alpha`);
  official pip package wins automatically once rebuilt. Verified `EntityType.INTENT=6`,
  `Entity.intent` oneof, real request/response round-trip through `list_intents`.
- `05_slice_e_pull.ipynb` install cell inserts the vendored root + reprobes.
- Still platform-env-blocked: bazel test/build, image push, deploy override,
  AuthorizationConfig, live smoke (see `slice-e-intent-facade.md`).

### Weather static ingestion (Options 1+2 executed; see `references/weather-static-ingestion-options.md`)
- **Option 2 shipped:** `tools/gfs-wildcard-mirror/mirror.py` — stdlib-only wildcard GFS
  mirror honoring the weather-server contract (idx GET→200; ranged GRIB GET→206; 404
  fallthrough); static-forever (wildcard pair) + bounded-interval (exact per-cycle trees
  win) modes; 8 contract tests. Runbook in the tool's README (fixture prep incl. wgrib2
  subsetting + idx regeneration, `--gfs` pointing, deployment notes).
- **Option 1 documented** in the same runbook (historical replay via AWS NODD archive —
  zero build). Option 3 (`StaticSource` in-tree) remains the durable follow-up, not started.
- Suite: **134 tests green** in the local venv.

### Slice E — key-authed intent ingest (intent facade)
- Root-caused: raw intents live only in the internal Store; no public key-authed endpoint serves
  them (modelfe=NMTS-only, provisioningfe=SR-TE inputs, grpcui=SRE-internal, nbi pod dead).
- Decision: revive legacy `nbi.proto` `service NetOps` **read-only** over `Store.GetEntities(INTENT)`,
  on the existing robot-reachable `nbi`/`nbi-v1alpha` subdomain. Design: `slice-e-intent-facade.md`.
- Scaffolded (minkowski_ws3 branch `nbi-intent-facade`): restored proto+BUILD, `nbi/intentfe/`
  (server + impl + test + BUILD ×2), `permissions` NetOps patterns. Read-only enforced 3 ways
  (no write RPCs; verb→READ/WRITE map; RO-robot `model/entity/*` READ ACL).
- SLS wired: `client.py list_intents` → `NetOps.ListEntities(type=INTENT)`; offline tests green (19/19).
- Pending (platform env): `bazel gazelle/test/build`, push experimental image, deploy override,
  rebuild api pip package (Python NetOps stub), populate AuthorizationConfig, live smoke.

---

## Prior — Last Updated: 2026-07-07 (Slice E Increment-1 offline complete; 113 tests)

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

M1 deferred to later milestones (per plan roadmap): H3+sharding+prefilter (M3 ✓ done), elevation
sweep (M4), terminals/UT (M5), in-view intervals (M6), population+min-N sweep (M7), cell_layout (M8).

**Milestone 3 (sharding) COMPLETE** (2026-06-30, 29/29 tests):
- [x] `grids/h3_grid.py` (H3 AOR cells + circumradius) · `grids/shards.py` (single-owner `cellToParent`)
- [x] `coverage/prefilter.py` (cap λ geometry, ECEF→subpoint, conservative `relevant_sat_mask`;
      conservativeness proven as superset of brute-force in-view; ~18× sat-axis pruning, 1600→~90/shard)
- [x] `pipeline.run_coverage_h3` (sharded + time-chunked) · **`sharded == monolithic` bit-identical CI test**
- Chunking+pre-filter lift the MVP memory ceiling; shards are embarrassingly parallel (multi-worker = future).

### Slices B–E — queued (designs not yet written)
- [ ] Slice B — capacity, link budget, demand, beam-hopping scheduler
- [ ] Slice C — optimization, interference, Cesium 3D viewer
- [ ] Slice D — NMTS export (reuse `scenarios/builder/py`)
- [x] Slice E — Increment-1 IMPLEMENTED (offline, subagent-driven, 113 tests): guarded ngso_sls/spacetime/ (EntityStore + MemoryStore/RecordedStore/GrpcEntityStore, NMTS adapter w/ epoch reconciliation, pull_and_cover reusing run_coverage_h3_elements), 05_slice_e_pull.ipynb; DEFERRED: Sgp4/TLE, legacy NetOps fallback, live @integration tests

---

## Current Focus

**Slice E Increment-1 COMPLETE (2026-07-07, 116 tests).** Guarded `ngso_sls/spacetime/` subpackage shipped: `_deps/config/store/memory_store/recording/nmts_adapter/client/pull` + `probe` (staged first-contact diagnostic + `python -m ngso_sls.spacetime.probe` CLI), elements CSV, packaging, Colab notebook `05_slice_e_pull.ipynb` (with a first-contact smoke-probe cell). All tests green. Enum values `ek_platform=11/ek_antenna=40/RK_CONTAINS=4` verified against `nmts.proto`. Next: push repo, then **live test run** in Colab against `fss01-demo` (smoke probe first), then Slice B or Slice E live @integration tests.

## Next Steps

00. **Slice A REVISIONS — IMPLEMENTED (2026-07-02, 92 tests).** SA12–SA14 complete.
    Modules: `constellation/model.py`, `coverage/refine.py`, `sweep.multi_shape_sweep`,
    `viz.plots` scatter/heatmap, `explorer` planes-range + multi_shape branch.
    - **SA12**: `ConstellationModel` SoA + generators (Walker byte-identical shim, explicit-planes,
      phase-slot/lattice, multi-shell concat); `config.GeneralizedShell` + `constellation_model()`;
      `run_coverage_h3_elements` seam + apoapsis `max_alt`.
    - **SA13** (◐ partial): LIVE end-to-end = grid-quantized detection + different-**sat** +
      different-**plane** gate + merged worst-gap (`mbb_worst_gap_s`) + Nyquist precondition +
      resolution metadata. `require_different_plane` kwarg wired in `run_coverage_h3` and
      Explorer. **Deferred**: sub-second refinement (`coverage/refine.py`); `SimConfig` knobs
      `max_buffered_gap_s`, `min_target_dwell_s`, `max_handover_rate_hz`, buffered-break (inert);
      §6 event bracketing, k≥2 continuum, link margin.
    - **SA14**: `multi_shape_sweep` 2D P×spp grid (cap, gate, Pareto/min-N); scatter + heatmap viz
      (lazy plotly); Explorer planes-range + multi_shape + CSV.
    (SA15 patent-shape screening: deferred/lower-priority; stub at `slice-a-patent-screening.md`)

0. **Slice E — Increment-1 IMPLEMENTED (2026-07-07, 113 tests).** Guarded `ngso_sls/spacetime/`: `_deps` (per-surface flags), `config` (SpacetimeEndpoint), `store` (EntityStore + StoreError), `memory_store`/`recording` (offline replay), `nmts_adapter` (Keplerian→elements + epoch reconciliation), `client` (GrpcEntityStore, lazy), `pull` (pull_and_cover orchestration). Elements CSV. `05_slice_e_pull.ipynb` (Colab: Increment-0 probe + connection form + pull→coverage→compare→record). DEFERRED: Sgp4/TLE, legacy NetOps fallback, live @integration tests.
1. (Owner) Push repo to a git remote so the notebook's `!git clone` works in Colab.
2. **M7 — min-N sweep** (the headline Jio answer: reduce N / raise k until coverage drops; now
   feasible at fine H3 grids thanks to M3) — or **M4** (elevation sweep) / **M5** (terminals/UT).
3. M2 oracle hardening (Skyfield ECI cross-check) can slot in anytime.
4. Wire multi-worker execution over shards (N7) when scale demands it.

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
