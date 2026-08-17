# Slice B — Capacity & Beam-Hopping (design stub)

**Status:** Outline only (owner-approved direction 2026-08-17); full spec to follow, then
adversarial pass, then implementation.

## Approved direction
- **Formulaic core first:** per-beam duty cycle `d = min(1, N_beams / N_cells_demanding)`
  per satellite; cell capacity ∝ spectral efficiency × bandwidth × duty cycle; swept over
  beam counts / revisit constraints / demand maps. Fast enough for design-time sweeps
  (thousands of candidates); NCAT-class deliverable.
- **Satsolver as oracle** (Slice-A pattern: analytic core + oracle + error budget): run
  selected scenarios through spacebox instances; calibration delta (SLS-predicted vs
  solver-achieved per beam/cell) is a first-class output.
- **Legacy-first oracle:** fss01-demo's beam-hopping solver (stable, less accurate) before
  master (unstable). Reproduce via spacebox `--spacetime-version`/`--app-version` pinned to
  fss01-demo's deployed image digests (read off the cluster); cherry-pick only if artifacts
  are purged. Three-way comparison: SLS vs legacy vs master.

## PIN — air-interface aspects (owner directive 2026-08-17; account for in the full design)
Beam-hopping capacity must later reflect waveform-specific constraints/capabilities, not
just geometric duty cycle. Placeholders to design against:

- **DVB-S2X / RCS2 (forward/return):**
  - S2X superframing (formats 4/5) quantizes dwell/illumination into the beam-hopping time
    grid; switching/guard times reduce effective duty cycle.
  - ACM modcod tables (spectral-efficiency vs SNR curves) replace a flat efficiency
    constant; rolloff choices; beam-hopping signalling overhead.
  - RCS2 return: MF-TDMA carrier/timeslot granularity, contention vs dedicated access.
- **5G NR NTN (Rel-17/18):**
  - Timing: K_offset / extended HARQ (or HARQ disabling) reduces effective throughput at
    GEO/LEO delays; scheduling round-trips constrain hopping cadence.
  - Beam management: SSB burst periodicity + PRACH occasions impose MINIMUM revisit /
    dwell per cell (a hopped beam must return often enough to keep UEs attached).
  - Capacity grid: PRB/MCS tables (TS 38.214) vs DVB curves; polarization/frequency reuse
    interplay with hopping pattern.
- **Model hook:** the formulaic core exposes `min_dwell_s`, `revisit_max_s`,
  `switch_overhead_s`, and a pluggable `spectral_efficiency(snr)` curve per air interface —
  waveform packs (S2X, NR-NTN) fill these in a later increment without changing the core.

## Open questions (for the full spec)
- Demand model: uniform vs population-weighted vs traffic hotspots (ties to M7 weighting).
- Where the oracle comparison lives: extend nb06 (live intents already parsed) vs new nb.
- Feeder-link capacity coupling (fss01 scenario doesn't intent-manage feeder links).

## Oracle protocol — Spacetime-as-simulator (owner discussion 2026-08-17)
Everything needed is read/written through the **Store**; no service-specific query APIs.
Link predictor and satsolver are REACTIVE: they watch the model in the Store and
continuously write outputs back. "Querying" them = writing inputs, reading outputs:
1. **Author** (pybuilder): UTs at H3 res-3/4 cell centers + demand map as
   SERVICE_REQUESTs (uniform first) + constellation shape → load into a version-pinned
   spacebox instance.
2. **Link predictor output** (read Store): BEAM_CANDIDATE_SEGMENT=52 +
   PROPAGATION_VECTOR_SEGMENT=63 → LoS/sats-in-view/availability per cell — the
   solver-side twin of nb01's coverage tensor (validates Slice A cell-by-cell).
3. **Satsolver output** (read Store): link/modem/cell intents + SCHEDULE=33 → per-cell
   dwell/revisit (beam-hopping duty cycle) + modcod (spectral efficiency) → capacity ≡
   the Slice B oracle. SBI is NOT needed (that's for real device agents; sim readout is
   the Store).
- fss01-demo dataset counts for beam-candidates/prop-vectors/schedules: UNVERIFIED (probe
  attempted 2026-08-17; port-forward dropped mid-probe — retry). Old instances may retain
  these only transiently (durationcache) — the diff/interval GetEntities time-specs are
  the fallback readout.
