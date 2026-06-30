# NGSO SLS Toolkit — Design Documentation

## Start Here

- **[design.md](design.md)** — Program-level architecture, slice decomposition, anchors.
- **[../../CLAUDE.md](../../CLAUDE.md)** — System guidance: environment, always-do rules, conventions.

## Authoritative Spec

- In-repo authoritative sources are the docs in this folder (design.md + the slice specs).
- The original full system design doc is archived locally at
  `references/spacetime_ngso_sls_toolkit_brainstorming.md` (gitignored / untracked — contains
  customer specifics, not for the tracked repo).

## Requirements

- [requirements.md](requirements.md) — tracked requirements (original spec + emergent), with slice + status.

## Slice Designs

- [slice-a-coverage-core.md](slice-a-coverage-core.md) — **Slice A: SLS engine core (offline)** — current focus.
- [slice-a-implementation-plan.md](slice-a-implementation-plan.md) — **Slice A implementation plan** (MVP-first, TDD; M1 done, M2–M8 roadmap).
- _Slice B (capacity/link-budget/beam-hopping), C (optimization/interference/3D viewer), D (NMTS export), E (Spacetime NBI integration) — written when reached._

## Process

- [brainstorming.md](brainstorming.md) — Decisions log from the brainstorming sessions (Q&A, rationale).
- [progress.md](progress.md) — Progress tracking, task checklist, current state.
