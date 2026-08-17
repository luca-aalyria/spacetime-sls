# CLAUDE.md — NGSO SLS Toolkit

Guidance for Claude Code (and any agent) working in this repository. Read this first,
every session, before touching code or docs.

## What This Is

A **system-level simulator (SLS) toolkit for non-geostationary (NGSO) satellite
constellations**, delivered as a pip-installable Python package (`ngso_sls`) plus
Jupyter/Colab notebooks. It covers constellation design, coverage and capacity
analysis, beam-hopping, frequency reuse, interference (GEO-arc), and RF/payload
planning, and (in later slices) connects to a live **Aalyria Spacetime / Minkowski**
instance to build and validate scenarios.

The authoritative system design document is
`references/spacetime_ngso_sls_toolkit_brainstorming.md` (archived locally; gitignored). The capability bar is
**NCAT** (Analysys Mason). Two anchor customers drive requirements:
- **Reliance Jio** — design-time constellation feasibility (greenfield 1,600-sat dual shell).
- **Telesat CCMS** — operations-time service feasibility & capacity planning (in-service Lightspeed).

## Program Decomposition (sub-projects, each its own spec → plan → build)

This is a program, not one project. Slices are built in order; each has its own design doc.

- **Slice A — SLS engine core (offline).** Constellation + propagation + geometry +
  coverage + CSV/2D viz. **← current focus.** See `docs/design-docs/slice-a-coverage-core.md`.
- **Slice B — Capacity, link budget & beam-hopping.**
- **Slice C — Optimization, interference & 3D Cesium viewer.**
- **Slice D — NMTS export** (reuse/extend `minkowski_ws3/scenarios/builder/py`).
- **Slice E — Live Spacetime/Minkowski NBI integration** (push scenarios / pull state & results).

## Environment & Sandbox Constraints — READ CAREFULLY

**Empirically (verified 2026-06-29):** pypi IS reachable from this sandbox and a local
venv with the full stack works — contrary to the initial "no-internet" assumption.

- **ONE unified uv-managed venv, shared sandbox↔host (since 2026-08-15).** Deps declared
  in `pyproject.toml` (extras `spacetime`/`oracle`, dependency-group `dev`), locked in the
  committed `uv.lock`. The venv is shareable because ALL its internal paths are
  `/workspace/...`-based:
  - Interpreter: uv-managed standalone CPython 3.12 at `/workspace/.uv-python/` (in the
    shared mount; glibc build — sandbox is Wolfi/glibc, host is Debian/glibc).
  - `.venv/pyvenv.cfg home`, script shebangs, symlinks → all `/workspace/...`.
  - **Host precondition (once):** `sudo ln -s ~/workspace_3 /workspace` so those paths
    resolve host-side too. Host and sandbox then use the same `.venv/bin/python`.
  - Vendored-stubs `.pth` uses a RELATIVE path (`../../../../vendor/spacetime_api_stubs`)
    — valid from both views.
  - Rebuild: `uv venv .venv --python /workspace/.uv-python/cpython-3.12*/bin/python3.12
    && uv sync --all-extras --active` + re-add the `.pth`. Never rebuild with a
    side-local interpreter (that's what broke sharing before). uv binary in the sandbox:
    `/tmp/bin/uv` (`pip install uv` if missing).
- **The system interpreter `/usr/bin/python3` has no stack** — always use `.venv`.
- **Google Colab remains the delivery target.** Notebooks under `notebooks/` must run
  unmodified in Colab; keep deps pip-installable and pure (no Bazel, no native build).
- **Faithful reporting still applies:** state plainly whether a result was run locally
  (in the venv) vs only in Colab vs not yet run. If the network ever becomes unavailable,
  fall back to the venv-already-installed packages.

## Always Do

0. **Adversarially verify every design decision.** For any non-trivial design point, fan out
   independent analysis agents, then run adversarial skeptic agents that try to *refute* the
   design (false-negatives, over-coupling, scope creep, correctness) before committing it.
   Synthesize the verified result into the design docs. The project owner requires this — it
   is what makes the design robust and scalable. (Use the Workflow tool: analyze → verify →
   synthesize.)
1. **Keep the docs in sync.** Any design change updates the relevant doc in
   `docs/design-docs/`. Any progress updates `docs/design-docs/progress.md` (with its
   `Last Updated` date and task checklist). Docs are living, not write-once.
2. **Write concise docs — essentials only.** Documentation must be terse and high-signal:
   decisions, contracts, key numbers, diagrams. No filler, no restating the obvious, no
   padding. If a table or bullet list says it, don't also say it in prose. Prefer the level
   of concision used in chat answers over long expository prose.
2. **Respect slice discipline.** Only build the current slice. Do not create modules,
   deps, or files belonging to a deferred slice. Their absence keeps scope honest.
3. **Design-before-code.** No implementation code until the relevant slice design is
   approved by the project owner. Brainstorming/spec writing is allowed; implementation is not.
4. **Reproducibility.** Everything is seeded and versioned. Same inputs → same outputs.
   Inputs are CSV (+ equivalent code objects); record the config used for any result.
5. **Honor the conventions** (below): units/frames, the propagator seam, CSV-in/CSV-out.
6. **Report outcomes faithfully.** Tests that fail, steps skipped, things run only in
   Colab — state them plainly. No hedging, no overclaiming.

## Conventions

- **Units & frames.** SI internally (km, s; radians in math, **degrees at the I/O
  boundary**). `propagation` emits ECI (GCRF-approx) position; conversion to
  ECEF/geodetic happens only inside `geometry` via Astropy-backed GMST/Earth rotation.
  Every module contract states its frame and units.
- **Propagator seam.** Propagation is behind a `Propagator` Protocol
  (`propagate(elements, times_s) -> (n_sat, n_time, 3) ECI`). Slice A ships
  `KeplerJ2Propagator`. Future engines (SGP4, Orekit, **Principia n-body**) implement
  the same interface and are selected by config. **Nothing downstream of `propagation`
  may depend on the propagator implementation.**
- **CSV in / CSV out.** Every input dataset imports from CSV; every output dataset
  exports to a tidy CSV. The schemas are part of the slice design.
- **Grids.** H3 hexagonal grid per AOR with a lat/lon global fallback.
- **Colab-first packaging.** Pure-pip installable, no native build steps on the
  critical path. No Bazel in this package (the monorepo uses Bazel; we stay decoupled
  until Slices D/E).
- **Configurable-first.** Analysis choices (time-step, availability target, k-coverage,
  metrics, thresholds) are simulation parameters with sensible defaults — not hardcoded.
  `step_s`/`quantum_width` are floats (default 10 s; support frame-aligned quanta, e.g. NR
  10.24 s). Always emit full curves even when a target is set. Track every requirement in
  `docs/design-docs/requirements.md`.

## Solver Alignment (core architectural directive)

Build the SLS core **as close as possible to the Spacetime Solver**, because the Slice-E
harness will eventually call the real Spacetime Solver to run simulation jobs. The offline
core and the live solver must be conceptually interchangeable and directly comparable.

Reference implementations in `minkowski_ws3` (mirror these, don't reinvent):
- **Satsolver** (`apps/satsolver_nmts`, `engdoc/.../solvers/satsolver.md`) — FSS-constellation
  solver. Quantum-based time model (`quantumWidth` ~10s); decomposes the global problem into
  subproblems: user-link assignment → feeder-link assignment → carrier assignment → routing →
  beam-hopping. Sharding via `enablingUserSharding` (default true) / `enablingFeederSharding`.
- **Netsolve** (`crates/netsolve-core`, `crates/netsolve-spacetime`, `apps/simplesolver`) — the
  architectural template: five phases **load → enumerate → select(MILP) → reconcile → write**,
  I/O-agnostic core + Spacetime adapter, composable MILP contributors.
- **Link Predictor** (`java/com/aalyria/spacetime/link/predictor/`, `java/com/google/googlex/
  minkowski/link/NetworkShard*.java`) — the spatial **sharding** + **appointer** machinery
  (BeamCandidateAppointer, PropagationVectorAppointer). Slice A's coverage/visibility layer
  corresponds to this layer (beam candidates + access + link reports).

Data shapes to align with: **NMTS** entities/relationships, **beam-candidate segments** (what a
spot beam sees toward a ground target), **link reports** (signal quality between two antennas),
and **intents** (Link/Radio/Path/Modem). Slice A's coverage tensor ≈ the precursor to
beam-candidate / access generation.

**Sharding dimensions** (satcom), primarily: **(a) user clustering** and **(b) regulatory
areas**; other partitionings (geographic tiles, beam/feeder) are also valid. Shards must be
**conservative** (never drop a satellite/UT that is actually relevant — no false negatives).
Where the offline SLS must deviate from the solver, document the divergence and why.

## Build & Test (intended; runner must be staged — see Environment)

```bash
# Local (requires a staged Python env with the stack — NOT the system 3.14 interpreter)
python -m pytest tests/ -q

# Delivery / heavy validation
# Open notebooks/01_slice_a_coverage.ipynb in Google Colab.
```

## Documentation Map

- `references/spacetime_ngso_sls_toolkit_brainstorming.md` — original full design, archived locally (gitignored). In-repo authoritative: `docs/design-docs/`.
- `docs/design-docs/README.md` — design-doc index.
- `docs/design-docs/design.md` — program-level architecture & slice decomposition.
- `docs/design-docs/brainstorming.md` — decisions log from the brainstorming sessions.
- `docs/design-docs/slice-a-coverage-core.md` — detailed Slice A design (current).
- `docs/design-docs/progress.md` — progress tracking + task checklist.

## Notebook Versioning

Every notebook carries `**Notebook version: vX.Y.Z**` in its first (title) markdown cell.
**Bump it whenever the notebook's behavior changes** — that includes edits to the `.ipynb`
AND behavior-affecting changes in the modules it surfaces (`ngso_sls.explorer`, pipeline,
spacetime client): the notebooks are thin shells, most changes land module-side.
`tools/bump_nb_version.py notebooks/<nb>.ipynb [patch|minor|major]` (patch=fix,
minor=feature, major=restructure). Generated notebooks (06 via `tools/build_nb06.py`)
keep the marker in the BUILDER's header — bump it there. Same commit as the change.
