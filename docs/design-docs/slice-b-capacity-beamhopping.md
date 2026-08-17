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
