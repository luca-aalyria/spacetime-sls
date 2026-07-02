# Slice A — Patent-Shape Screening Post-Check (design stub)

**Status:** ⏸️ **DEFERRED / LOWER PRIORITY** (2026-07-02). Build **after** the base
generalized-constellation + handover-continuity revisions land. This stub captures scope so
it isn't lost; detailed detector thresholds are set at implementation time.

> **⚠️ Engineering flag, NOT a legal freedom-to-operate opinion.** Output flags geometries
> that *resemble* claimed constellation shapes, to trigger human review. It is not legal
> advice. Patents are territorial and claim-specific; live status, claims, continuations,
> national validations, and Indian national-phase entries must be verified in official
> registers. This disclaimer ships with every screening report.

## Goal

A **post-check** that runs on each simulated candidate shape (single sim or every point in a
sweep) and flags those that may fall within a patented constellation geometry, per
`references/constellation-shapes-patent-analyis/` (analysis + `constellation_patent_catalog.json`:
19 families — 11 RED, 7 YELLOW, 1 PRIOR_ART).

**Hard guardrail (from the guidance):** *"Do not constrain an ordinary Walker Delta sweep."*
The default single-inclined-Walker baseline must screen **clean**. Only the distinctive
geometries below are flagged.

## Architecture fit

Consumes the base design's `ConstellationModel` (explicit `(n_sat,6)` elements + per-sat
`shell_id`/`plane_id`/`slot_id` + derived `a,e,i,RAAN,M`) — exactly the descriptors these
detectors need. Pure-geometry, numpy-only → lives in the core-adjacent layer (screener module
importing only numpy; catalog is data). No new heavy deps.

- **Policy data:** distill machine-testable predicates from the catalog into a **package** data
  file `ngso_sls/data/patent_shapes.json` (family, priority, detector-id, numeric params,
  jurisdictions, urls, disclaimer). `references/` is gitignored; the shipped file is the
  distilled predicate set, not the raw analysis.
- **Entry point:** `screen_shape(model, config) -> list[Flag]`; the sweep attaches a
  `patent_flags` column per candidate; the heatmap gets an optional flag overlay (e.g. hatch /
  marker on flagged shapes), distinct from the handover red/green gate.
- **Configurable-first:** enable/disable, minimum priority (RED-only vs RED+YELLOW), per-family
  toggles, and numeric tolerances are all parameters with sane defaults.

## Two match tiers

The SLS models **geometry**, not operations (ISL routing, terminal tracking, active
station-keeping, deployment sequence, gateway/NOC topology). So:

- **GEOMETRIC** — fully testable from the element set → auto-flag with matched signatures.
- **PRECONDITION / REVIEW** — geometric preconditions detectable, but the distinguishing claim
  element is operational → flag as *"manual review"* only when the precondition holds.

## Family → detector mapping (RED first)

| # | Family (assignee) | Tier | Geometric signature to test |
|---|---|---|---|
| 1 | Latitude "Waves" (JHU, US12523778B2) | GEOMETRIC | even RAAN spacing **and** even in-plane anomaly **and** inter-plane phasing that synchronises neighbouring-plane equator crossings / keeps E-W neighbours at ~same latitude (distinct from ordinary Walker F) |
| 2 | Satellite "snakes" (SpaceX, US10843822B1/US11479372B2) | GEOMETRIC | ≈1 sat per distinct RAAN plane **and** adjacent-RAAN ordering forming a continuous string |
| 3 | RAAN–M traffic-lane lattice (Amazon, US12556266B1) | GEOMETRIC + review | regular (Ω,M) lattice with same-lane spacing < cross-lane spacing (the "actively maintained" element → review) |
| 4 | RGT + one-axis terminal tracking (SpinLaunch, US12345823B2) | REVIEW | RGT resonance detectable; terminal one-axis tracking not modelled (RGT generator itself deferred) |
| 5 | Common single RGT / repeating sky tracks (US11863289B2) | REVIEW | all sats on one common ground track detectable if RGT modelled; terminal ops not |
| 6 | Multi-incl **and** multi-alt LEO, common gateway (Blue Digs, US12199739B2/US11799542B2) | GEOMETRIC + review | ≥2 shells with **distinct inclinations and altitudes**, both in ~500–1500 km and ~30–60° (common gateway/NOC → review) |
| 7 | Polar + inclined LEO with cross-shell ISLs (US11362732B2) | PRECONDITION | a near-polar shell (i≈90°) **and** an inclined shell present (ISL capability → review) |
| 8 | Lower RF shell + higher optical trunk shell (US9391702B2) | PRECONDITION | two shells ~600–950 km and ~1100–1400 km (optical ISL → review) |
| 9 | Inclined GEO pair (US10889388B2) | GEOMETRIC | 2 sats, a≈42 164 km, e≈0, i 5–20°, ~same median longitude, RAANs ~90° apart |
| 10 | Single-launch differential-drift deployment (US11066190B2/EP3134322B1) | REVIEW-ONLY | deployment **method** — final Walker geometry may be safe; cannot be inferred from a static shape |
| 11 | Cross-plane ISL routing at plane crossings (Lynk, YELLOW) | REVIEW-ONLY | routing algorithm, not geometry |

YELLOW HEO families (circumpolar/teardrop) are GEOMETRIC (test e, period, i); Walker-maintenance
and GSO-interference-avoidance YELLOWs are REVIEW-ONLY (control method).

## Output

Per candidate: `[{family, priority, tier, matched_signatures, jurisdictions, urls}]` + the
disclaimer. Sweep CSV gains `patent_flag_count` / `patent_families`; the heatmap can overlay
flagged shapes. Empty for the safe baseline.

## Deferred / out of scope now

Downloading the actual patent PDFs (`references/.../patents/`, the downloader script) is ignored
per owner. Detector threshold tuning, the Waves co-phasing test, and jurisdiction filtering
(US/EP/GB/IN) are set at build time. No legal claim-charting is attempted.
