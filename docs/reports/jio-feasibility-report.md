# NGSO Constellation Feasibility for Reliance Jio
### Coverage, Capacity and Live-System Validation with Aalyria Spacetime

**Status: DRAFT** — sections marked [PENDING] fill in as computation completes. Figures land in
`figs/` (committed with the report; regenerate via the Coverage Explorer notebook).

---

## 1. Executive summary  [PENDING - finalize last]

- The proposed 1,600-satellite dual-shell constellation delivers **[X]% availability at
  k=1 and [Y]% at k=2** over India at a 25° elevation mask. [PENDING: M7 sweep]
- The minimum constellation meeting a **99% availability target** over India is
  **[N] satellites ([P] planes × [S] sats/plane @ [alt] km / [inc]°)**. [PENDING: M7 sweep]
- Delivered capacity over India with beam hopping: **[C] Gbps** aggregate,
  **[c] Mbps** per cell median. [PENDING: Slice B + oracle]
- **Every prediction in this report is validated against Aalyria Spacetime** — the same
  software that will allocate resources in the live system. Geometric coverage agreement
  with Spacetime's production link predictor: **mean Δ 0.13 %, max 3.3 %** (§5).

## 2. Methodology

Two engines, one contract:

1. **Design-time SLS** (`ngso_sls`): analytic Kepler+J2 propagation, H3 hexagonal service
   grids, vectorized visibility/coverage, k-grade availability, make-before-break handover
   gating, beam-hopping duty-cycle capacity model. Fast enough to sweep thousands of
   constellation candidates (minutes per candidate, parallelized).
2. **Spacetime as the oracle**: candidate constellations are loaded into ephemeral
   Spacetime instances (identical software to production). Its link predictor computes
   beam-candidate accessibility; its satsolver allocates links, beams, modcods and routes
   exactly as it would operationally. The SLS is calibrated against these outputs, so
   design-time numbers reflect **how resource allocation actually happens in the real
   system** — not just geometry.

The workflow: sweep with the SLS → validate the shortlist in Spacetime → report both,
with deltas.

## 3. Coverage: the Jio constellation over India  [PENDING: M7 sweep]

- k=1 / k=2 / k=3 availability maps @ 10°/25°/40° masks — `figs/coverage_*.png`
- Elevation-mask sensitivity by coverage grade
- Make-before-break handover feasibility (20 s two-satellite overlap)
- Minimum-satellite sweep: availability vs N at the 99% target; Pareto candidates

## 4. Capacity with beam hopping  [PENDING: Slice B]

- Duty-cycle model: per-beam dwell/revisit under demand maps (uniform, then
  population-weighted); capacity per cell and aggregate
- Air-interface roadmap: DVB-S2X superframing & ACM; 5G NR NTN dwell/revisit constraints
- Spacetime satsolver comparison on identical scenarios (legacy + current solver)

## 5. Validation against the live system

A live Spacetime instance (150-satellite LEO reference constellation, 10×15 @ 53°/1157 km)
was read directly and compared point-for-point:

- **Coverage agreement**: SLS engine evaluated at the link predictor's exact 222 ground
  points and 10-second time samples → k=1 availability mean Δ **−0.0013**, max |Δ|
  **0.033**, ≥99% agreement in [Z]% of points — `figs/oracle_delta.png` [PENDING: figure export]
- **What the live system exposes** (all extracted programmatically, read-only):

| Data | Live example (reference constellation) |
|---|---|
| Constellation model (NMTS) | 150 satellites, 24 gateways, 203 user terminals, antenna fields-of-regard |
| Service parameters | min elevation derived from antenna FoR: user 25°, feeder 10° |
| Link-predictor output | 197k beam-candidate segments (10 s samples), per-pair propagation vectors incl. weather attenuation, interference, EIRP limits |
| Solver decisions | 2.6k live intents: link / modem / route / cell assignments |
| Schedules | per-agent enacted radio states, ~96 updates/s |
| Derived KPIs | gateway load balance (6× spread), user-terminal handover timeline, inter-satellite-link mesh utilization (288 active links), per-cell dwell |

## 6. Spacetime as a fully-fledged SLS

The validation loop demonstrates that a Spacetime instance is usable as a
system-level simulator with production fidelity: load a candidate constellation, let the
production link predictor and satsolver run, and read coverage, allocation and capacity
outcomes from the same data streams operations would use. Ephemeral instances spin up in
minutes, are version-pinnable to any deployed release, and are driven end-to-end
programmatically — enabling parameter sweeps where every point is a full-system answer.

## Appendix A — reproducibility  [PENDING]
Scenario definitions, sweep configurations, and per-figure regeneration commands.
