# NR NTN Handover Execution Time — LEO-600 Baseline

Derived from normative requirements in **TS 38.133 §6.1C.2–3** (Rel-18/19) and the study analysis in **TR 38.821 §7.3.2**. Covers both the CHO (Conditional Handover) path and the Unchanged-PCI Satellite Switch path, the two primary NTN service-link mobility mechanisms.

## Scenario Assumptions (LEO-600 FR1-NTN baseline)

| Parameter | Value | Source |
|-----------|-------|--------|
| Altitude | 600 km | TR 38.821 Set-3 |
| One-way propagation delay | 4–12.9 ms | TR 23.737 |
| RTT (radio, min–max) | 8–25.77 ms | TR 23.737 |
| SSB periodicity (Trs) | 5 ms (default if no SMTC configured) | TS 38.133 §6.1C.2.2.4 |
| SSB bandwidth | 20 PRB | Baseline |
| SCS | 15 kHz | FR1-NTN baseline |
| Cell dwell time (50 km beam) | ~6.6 s | TR 38.821 §7.3.2.1.4 |
| Cell dwell time (1000 km beam) | ~132 s | TR 38.821 §7.3.2.1.4 |

---

## Path 1: Conditional Handover (CHO) — Different PCI

This is the inter-cell handover path (TS 38.133 §6.1C.2). The total CHO delay is:

**D_CHO = T_RRC + T_Event_DU + T_interrupt + T_CHO_execution**

### Phase-by-phase breakdown

#### 1. Measurement phase (background, not gating)

For CHO, the UE is already measuring neighbours in connected mode. With NTN-specific SMTC, for FR1-NTN intra-frequency without gaps (§9.2C.5):

- PSS/SSS sync: `max(600 ms, 5 × SMTC period)` = **600 ms** (with 5 ms SMTC)
- SSB measurement period: `max(200 ms, 5 × SMTC period)` = **200 ms**
- Total cell identification: **~800 ms** for an unknown cell

**This runs continuously in the background** — it is NOT part of the handover execution latency. By the time CHO executes, the target cell is already known.

#### 2. Preparation phase (T_RRC)

- RRC procedure delay for processing `ConditionalReconfiguration`: **15 ms** (TS 38.331 clause 12, typical for RRC reconfiguration processing)
- This is UE-side processing of the stored CHO command. Network-side preparation (HO Request/ACK between gNBs) happens **before** CHO is configured and is not on the execution critical path.

#### 3. Trigger evaluation (T_Event_DU)

- For **T1 (time-based)**: deterministic — the UE counts down to the configured threshold time. T_Event_DU ≈ 0 (negligible uncertainty).
- For **D1/D2 (distance-based)**: depends on UE GNSS position update rate. With typical 1 Hz GNSS, worst-case uncertainty ≈ **1 second** (one GNSS fix interval). With 10 Hz GNSS, ≈ **100 ms**.
- **Best case (T1 trigger): ~0 ms additional uncertainty.**

#### 4. CHO execution (T_CHO_execution)

- TS 38.133 §6.1C.2.2.3: **T_CHO_execution ≤ 10 ms**

#### 5. Interruption time (T_interrupt)

TS 38.133 §6.1C.2.2.4:

- **T_processing ≤ 20 ms** (security key derivation + cell config application — higher than the 10 ms for unchanged-PCI SatSwitch because CHO requires KgNB* derivation)
- **T_IU** = SSB-to-PRACH association period + 10 ms. With typical NTN PRACH config, SSB-to-PRACH period ≈ 5–10 ms → **T_IU ≈ 15–20 ms**
- **T_Δ** = Trs = 5 ms (20 PRB SSB BW, fine time tracking)
- **T_margin ≤ 2 ms**
- If target cell is **known** (already measured): T_search = 0
- If target cell is **unknown** intra-freq: T_search = Trs = 5 ms
- If target cell is **unknown** inter-freq: T_search = 3 × Trs = 15 ms

**T_interrupt (known target, intra-freq) = 20 + 15 + 5 + 2 = ~42 ms**

**T_interrupt (unknown target, inter-freq) = 20 + 20 + 15 + 5 + 2 = ~62 ms**

### CHO Total — Minimum (best case, T1 trigger, known intra-freq target)

| Phase | Duration | Notes |
|-------|----------|-------|
| Measurement | 0 (background) | Already done before trigger |
| RRC processing | 15 ms | ConditionalReconfiguration stored |
| Trigger uncertainty | ~0 ms | T1 time-based trigger |
| Interruption | ~42 ms | T_processing + T_IU + T_Δ + T_margin |
| CHO execution | ≤ 10 ms | TS 38.133 §6.1C.2.2.3 |
| **Total** | **~67 ms** | **Minimum CHO execution** |

### CHO Total — Typical (D1 trigger, unknown intra-freq target)

| Phase | Duration |
|-------|----------|
| Measurement | 0 (background) |
| RRC processing | 15 ms |
| Trigger uncertainty | ~100 ms (10 Hz GNSS) |
| Interruption | ~47 ms |
| CHO execution | ≤ 10 ms |
| **Total** | **~172 ms** |

---

## Path 2: Unchanged-PCI Satellite Switch with Re-sync (SatSwitch)

This is the transparent-payload / QEFC path where the PCI stays the same (TS 38.133 §6.1C.3). No CN update, no security key derivation.

### Hard switch (break-before-make)

**T_interrupt = T_search + T_processing + T_Δ + T_margin**

- **T_search = T_first_SSB**: time to end of first complete SSB burst of target satellite. With 5 ms SSB periodicity, worst case ≈ **5 ms**, typical ~2–3 ms.
- **T_processing ≤ 10 ms** (no key derivation needed — same cell)
- **T_Δ = Trs = 5 ms** (20 PRB SSB BW)
- **T_margin ≤ 2 ms**

**T_interrupt (hard) = 5 + 10 + 5 + 2 = ~22 ms**

### Soft switch (make-before-break)

**T_soft_switch = max(t_service − t_serviceStart, T_search + T_Δ + T_margin) + T_processing**

If the overlap window (t_service − t_serviceStart) exceeds T_search + T_Δ + T_margin (= ~12 ms), the UE pre-acquires the target satellite before the break point. The visible interruption is then only **T_processing ≤ 10 ms** — essentially **zero perceptible service interruption** if the overlap window is well-planned.

---

## Path comparison summary (FR1-NTN, LEO-600)

| Mechanism | Visible Interruption | E2E Delay | When to use |
|-----------|---------------------|-----------|-------------|
| SatSwitch hard (unchanged PCI) | **~22 ms** | ~22 ms | Transparent + EFC/QEFC |
| SatSwitch soft (unchanged PCI) | **~10 ms** (or near-zero) | ~10 ms | Transparent + QEFC with overlap |
| CHO (T1 trigger, known cell) | **~42 ms** | ~67 ms | Any architecture, predictable timing |
| CHO (D1 trigger, unknown cell) | **~47–62 ms** | ~170 ms | Regenerative, EMC, inter-cell |
| Legacy HO (A3 measurement-based) | **2× RTT ≈ 16–52 ms** (UE interrupt) + network RTT | Up to ~78 ms | Fallback, not recommended for NTN |

---

## FR2-NTN Additions

For FR2-NTN (Ka-band VSAT), an additional **T_sat_beam** component is added for antenna steering to the target satellite (TS 38.133 §6.1C.3.3):

- **Electronic steering (phased array)**: T_sat_beam = 3 × T_SSB (SSB periodicity of source satellite). With 5 ms SSB periodicity → **15 ms**.
- **Mechanical steering (dish)**: T_sat_beam = O_angle / 22.5 seconds, where O_angle is the angular offset in degrees between serving and target satellites as seen from the UE. For a typical 30° offset → **~1.3 seconds**.

Mechanical VSAT UEs are **not expected** to support soft satellite switching.

---

## Does 3GPP provide a numerical end-to-end study?

**TR 38.821 §7.3.2.1.1** provides the only normative numerical analysis of HO interruption. It calculates:

- **GEO DL interruption (standard HO, no CHO)**: 2 × RTT ≈ **1080 ms**
- **GEO UL interruption**: 1.5 × RTT ≈ **810 ms**

These are for **legacy measurement-report-command-execute** handover, which is precisely why CHO was introduced for NTN.

For LEO-600 with CHO, 3GPP did **not** publish a single unified timing study with all phases summed. The numbers in this document are derived from the normative component-level requirements in TS 38.133 §6.1C.2–3, which is the authoritative source. No 3GPP TDoc or TR provides a pre-computed "total minimum handover time for LEO-600" figure — the spec defines the component budgets and leaves the system-level sum to implementation/deployment analysis.

The **TR 37.911 IMT-2020 satellite evaluation** states **"Mobility interruption: 0 ms (beam mobility)"** — but that refers to intra-cell beam switching (beam hopping), not inter-cell/inter-satellite handover.

---

## Key Design Insights

- **CHO is fundamentally different from legacy HO in NTN**: the preparation and measurement are decoupled from execution. The network pre-loads the target config; the UE autonomously triggers based on geometry (D1/D2) or time (T1). This eliminates the 1–2× RTT penalty of measurement-report-command round-trips that makes legacy HO unusable for GEO and marginal for LEO.

- **The 20 ms vs 10 ms T_processing difference** between CHO and SatSwitch reflects security key derivation: CHO changes the cell (new KgNB* from NH/NCC), while SatSwitch keeps the same cell and reuses the existing security context.

- **The real bottleneck for NTN mobility is not the handover itself but the RACH**: T_IU (SSB-to-PRACH association + 10 ms) often dominates the interruption time. RACH-less CHO (using configured grants) can eliminate this entirely, but requires careful target cell resource pre-provisioning.

---

## Spec References

| Spec | Section | Content |
|------|---------|---------|
| TS 38.133 | §6.1C.2 | CHO delay requirements (NTN) |
| TS 38.133 | §6.1C.2.2.3 | CHO execution time (≤ 10 ms) |
| TS 38.133 | §6.1C.2.2.4 | CHO interruption time formula |
| TS 38.133 | §6.1C.3 | Satellite switch with re-sync |
| TS 38.133 | §6.1C.3.2.2 | Hard switch interruption time |
| TS 38.133 | §6.1C.3.2.3 | Soft switch delay |
| TS 38.133 | §6.1C.3.3 | FR2-NTN satellite switch (T_sat_beam) |
| TS 38.133 | §9.2C.5–7 | NTN intra-frequency measurement periods |
| TS 38.133 | §9.3C.4–8 | NTN inter-frequency measurement periods |
| TS 38.331 | §5.5.4.17–19 | Events D1, D2, CondEvent T1 |
| TR 38.821 | §7.3.2.1.1 | Latency associated with mobility signalling |
| TR 38.821 | §7.3.2.1.4 | Frequent and unavoidable handover (cell dwell time) |
| TR 38.821 | §7.3.2.2.2 | Conditional Handover enhancements |
| TR 23.737 | Propagation delay tables | LEO/GEO RTT reference values |
| TR 37.911 | IMT-2020 evaluation | Mobility interruption = 0 ms (beam mobility) |
