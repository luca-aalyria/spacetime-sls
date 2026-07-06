# NTN Mobility CONOPS — Inter-Satellite Switching Procedures

## 1. Scope

This document defines the Concept of Operations (CONOPS) for NTN mobility caused by **satellite orbital motion** — the predictable, continuous movement of NGSO (LEO/MEO) satellites that forces periodic switching of the radio link between the UE and the serving satellite, and of the backhaul link between the satellite and the ground infrastructure.

It covers:
- **Service link (user link)** switching — the satellite-to-UE radio path changes
- **Feeder link** switching — the satellite-to-NTN-Gateway backhaul path changes
- **Inter-satellite handover** — UE context transfers from one satellite-gNB to another (regenerative only)

Across two payload architectures:
- **Transparent** (bent-pipe): gNB on ground, satellite is RF relay
- **Regenerative** (full gNB): gNB on-board satellite, NG interface over feeder link

And three cell-motion models:
- **Earth-Fixed Cells (EFC)**: beam steered to stay on fixed ground area
- **Quasi-Earth-Fixed Cells (QEFC)**: beam nominally fixed, periodically repositioned
- **Earth-Moving Cells (EMC)**: beam body-fixed to satellite, sweeps ground

Normative basis: TS 38.300 §16.14, TS 38.331 §5.5.4.17-19, TS 38.413, TS 23.501, TR 28.874, TR 23.700-29.

---

## 2. Terminology

| Term | Definition |
|------|------------|
| **Service link** | Radio path from satellite payload to UE (downlink) and UE to satellite (uplink). Also called "user link." |
| **Feeder link** | Backhaul path from satellite to NTN Gateway on the ground. Carries the NG interface (regenerative) or bent-pipe RF (transparent). |
| **NTN Gateway** | Ground station that terminates the feeder link. Houses the gNB (transparent) or connects to the satellite-gNB's NG interface (regenerative). |
| **EFC** | Earth-Fixed Cell — satellite steers beam to maintain fixed ground coverage. |
| **QEFC** | Quasi-Earth-Fixed Cell — beam fixed for a period, then repositioned at scheduled intervals. |
| **EMC** | Earth-Moving Cell — beam body-fixed to satellite, sweeps ground as satellite orbits. |
| **CHO** | Conditional Handover — handover prepared in advance, executed when a condition is met (D1/D2/T1 event). |
| **ISL** | Inter-Satellite Link — direct RF or optical link between satellites. Enables Xn interface for regenerative inter-satellite handover. |
| **Hard switchover** | Brief interruption during feeder link or service link change. |
| **Soft switchover** | Make-before-break switching using dual connectivity to old and new path. |
| **Mapped Cell ID** | Geographically fixed virtual cell identity reported to the CN, decoupled from satellite motion. See companion document `ntn-mapped-cell-id-reference.md`. |
| **Uu Cell ID** | Physical radio beam identity on the air interface. May change during satellite switching. |

---

## 3. Satellite Motion and Switchover Cadence

### 3.1 Orbital Parameters

| Orbit | Altitude | Velocity | Orbital Period | Visibility Window |
|-------|----------|----------|----------------|-------------------|
| LEO | 300-600 km | ~7.6 km/s | ~90 min | 5-10 min per pass |
| LEO | 1200 km | ~7.3 km/s | ~109 min | ~12 min per pass |
| MEO | 10,000 km | ~4.9 km/s | ~6 hr | ~2-4 hr per pass |
| GEO | 35,786 km | ~3.1 km/s (station-kept) | 24 hr | Continuous |

### 3.2 Switchover Rates

- **Service link switchover (LEO):** Every **5-10 minutes** — all UEs in a cell must transition to the next satellite's coverage
- **Feeder link switchover:** All UEs under the **entire satellite's footprint** switch gateway simultaneously — higher aggregate signaling cost than service link switchover
- **Constellation sizing:** LEO at ~1200 km typically requires 300-500 satellites for global coverage
- **GEO:** No orbit-driven switchover (station-kept). Switchovers occur only for maintenance, failure, or orbital slot changes.

### 3.3 Predictability

NTN switchovers are **deterministic** — satellite positions are known from ephemeris data broadcast in SIB19 (NTN-Config IE, TS 38.331). This enables:
- Pre-computed handover timing
- Conditional Handover (CHO) with distance-based or time-based triggers
- OAM pre-configuration of security associations and gateway bindings via `NTNTimeBasedConfig`

---

## 4. Scenario Matrix

The following matrix shows what changes at each layer for each combination of payload type and cell-motion model:

| | **EFC** | **QEFC** | **EMC** |
|---|---|---|---|
| **Transparent** | Service link switch: UE re-syncs to trailing satellite broadcasting same PCI/SIBs. No HO needed. Feeder link switch: TNL address change, UE unaware. **Mapped Cell ID: unchanged. Uu Cell ID: unchanged.** | Service link switch: UE re-syncs at reposition boundary. CHO prepared via D1/T1. Feeder link switch: TNL change + TA list update. **Mapped Cell ID: unchanged. Uu Cell ID: may change at reposition.** | Service link switch: beam sweeps, UE handed between Uu Cell IDs via CHO (D1/D2/T1). Feeder link switch: TNL change. **Mapped Cell ID: unchanged. Uu Cell ID: changes continuously.** |
| **Regenerative (full gNB)** | Inter-satellite HO: Xn-based (ISL) or NG-based. NCGI changes (new gNB-ID). Feeder link switch: NG re-homing to new gateway. **Mapped Cell ID: unchanged. Uu Cell ID: depends on cell definition.** | Inter-satellite HO at reposition boundary. CHO prepared, time-windowed. Feeder link switch: NG re-homing + TA update. **Mapped Cell ID: unchanged. Uu Cell ID: changes at reposition.** | Inter-satellite HO as beam sweeps. Frequent CHO via D2 (moving reference). Feeder link switch: NG re-homing. **Mapped Cell ID: unchanged. Uu Cell ID: changes continuously.** |

**Invariant across all scenarios:** The Mapped Cell ID reported to the CN does not change due to satellite motion. Only the Uu Cell ID and/or serving NCGI change.

---

## 5. Service Link Switchover (User Link)

The service link connects the UE to the satellite payload. When the serving satellite moves beyond coverage, the UE must transition to a trailing satellite.

### 5.1 Unchanged-PCI Satellite Switch with Re-Synchronization (EFC)

**Applicable to:** EFC with transparent payload.

**Concept:** Multiple satellites in a constellation are configured to broadcast the **same PCI, cell information, and SIBs** for the same earth-fixed ground area (TR 23.737 §6). When the serving satellite passes out of view and the trailing satellite takes over:

1. The UE experiences gradual signal degradation from the departing satellite and signal strengthening from the approaching satellite
2. No handover command is needed — the new satellite broadcasts identical cell identity
3. The UE re-synchronizes to the new satellite's timing (TA adjustment due to different propagation path)
4. The NTN Gateway on the ground manages the feeder link transition independently

**CN impact:** None. The Mapped Cell ID, Uu Cell ID, and NCGI all remain the same.

**UE impact:** TA re-synchronization only. GNSS-based TA pre-compensation (Rel-17) reduces the re-sync transient.

**Signaling:** No RRC reconfiguration. No NGAP messages to AMF. The gNB (on ground) adjusts the TA common offset.

**Key constraint:** Requires sufficient satellite density such that coverage handoff is seamless (overlap zone between departing and approaching satellite beams).

### 5.2 Conditional Handover via D1/D2/T1 Events

**Applicable to:** QEFC and EMC (both payload types). Also EFC when PCI continuity is not configured.

3GPP introduced NTN-specific measurement events in Rel-17 (TS 38.331 §5.5.4.17-19) and Conditional Handover (CHO) to make satellite-driven mobility deterministic:

#### Event D1 — Distance-Based (Fixed Reference)

- **Trigger:** Distance from UE to `referenceLocation1` exceeds `threshold1` **AND** distance to `referenceLocation2` is below `threshold2`
- **Use case:** UE moves away from the current cell's reference point toward the target cell's reference point. Works for EFC/QEFC where reference locations are fixed on the ground.
- **Input:** UE GNSS position + reference locations broadcast in SIB19 or provided via RRC reconfiguration

#### Event D2 — Distance-Based (Moving Reference)

- **Trigger:** Same structure as D1, but uses `movingReferenceLocation` derived from satellite ephemeris broadcast in SIB19
- **Use case:** EMC — both the serving and target beams are moving. The reference locations are computed from satellite orbital parameters and epoch time.
- **Input:** UE GNSS position + satellite ephemeris from SIB19 + epoch time

#### CondEvent T1 — Time-Based

- **Trigger:** Current time falls within a duration from a configured threshold time
- **Use case:** Predictable satellite pass timing — the handover fires at a pre-computed time regardless of UE position
- **Input:** UE system time + configured threshold time (derived from ephemeris-based pass schedule)

#### CHO Procedure Flow

```
                    gNB (source)                         gNB (target)
                        |                                     |
1. RRC Reconfiguration  |                                     |
   (CHO config with     |                                     |
   D1/D2/T1 condition)  |                                     |
         |               |                                     |
         v               |                                     |
   UE evaluates          |                                     |
   condition             |                                     |
   continuously          |                                     |
         |               |                                     |
   [condition met]       |                                     |
         |               |                                     |
2. UE executes HO  ─────────────────────────────────────>      |
   (access target cell)                                        |
         |                                                     |
3.       |               <── Path Switch Request ──────────    |
         |               ── Path Switch Ack ──────────>        |
         |                                                     |
   [HO complete]         [AMF updated with new serving cell]
```

**Key advantage over standard handover:** The CHO is prepared while the UE still has good signal from the source. Execution is autonomous at the UE — no real-time command from the network is needed at the trigger point. This is critical for NTN where the source cell may be losing coverage at exactly the moment a handover command would be needed.

**UE capability:** `condHandover-r16` — applies only to FDD-FR1 NTN bands (excludes TDD-FR1 and FR2).

### 5.3 Standard A3/B1 Handover (Fallback)

When CHO is not configured or the UE does not support it:

- **Event A3:** Neighbor becomes offset better than serving (RSRP/RSRQ). Standard terrestrial HO trigger.
- **Event B1:** Inter-RAT neighbor exceeds threshold. Used for NTN-to-TN handover.

**Limitation for NTN:** A3 assumes signal strength varies meaningfully between cells. In NTN with large cells and near-flat signal across the footprint, A3 may not trigger reliably. This is the primary motivation for D1/D2/T1 events.

### 5.4 RLF-Based Mobility (NB-IoT NTN)

NB-IoT NTN UEs (Rel-17) do not support CHO. Mobility relies on:
- Radio Link Failure (RLF) detection
- Cell reselection in idle mode
- RRC re-establishment on the target cell

This is inherently less efficient (service interruption during RLF + re-establishment), but acceptable for IoT traffic patterns with infrequent, delay-tolerant transmissions.

---

## 6. Feeder Link Switchover

The feeder link connects the satellite to the NTN Gateway on the ground. As an NGSO satellite moves, it must transition to a different NTN Gateway with a viable line-of-sight.

### 6.1 Transparent Payload

**What happens:** The ground-based gNB switches its RF path from the old gateway to the new gateway. The satellite is a passive relay — no on-board state changes.

**UE awareness:** None. The feeder link is transparent to the UE. The UE sees no PCI change, no RRC reconfiguration, no cell change.

**CN impact:** If the gNB's IP address changes (because the gateway change alters the transport path):
- **Path Switch Request** (gNB → AMF): updates the AMF's serving-cell view and switches the N3 (GTP-U) downlink path
- **PDU Session Resource Modify Indication** (gNB → AMF): alternative for session-level path update

If the gNB IP does not change (e.g., gateway diversity behind a common IP front-end), there is no CN signaling.

**OAM pre-configuration:** NTN Gateway locations provided to gNB via O&M. Security associations and IP configuration must be pre-established with the target gateway before switchover.

### 6.2 Regenerative Payload (Full gNB)

**What happens:** The on-board gNB's NG interface (N2/N3) re-homes from the old NTN Gateway to the new one. The N2 (control plane) and N3 (user plane) transport endpoints change.

**UE awareness:** None — the feeder link is below the NG interface abstraction.

**CN impact:**
- The gNB's IP address changes → Path Switch Request to AMF (per-UE) or TNL update
- AMF continuity assumed: TS 38.300 §16.14.4.2 — "for regenerative payload it is assumed that the UE's serving AMF is not changed due to feeder link switch over"
- If AMF *does* change (satellite crosses AMF service area boundary): TS 23.501 standard inter-AMF mobility applies. TR 23.700-29: the gNB may release UEs to IDLE before changing gateway, or trigger handover when it realizes it is about to leave a tracking area.

**Signaling cost:** All UEs under the entire satellite's coverage must have their N3 paths updated simultaneously — this is the highest-signaling-cost switchover type.

### 6.3 Pre-Configuration via NTNTimeBasedConfig

For both transparent and regenerative payloads, OAM can pre-configure feeder link switchovers using the `NTNTimeBasedConfig` IOC (TR 28.874):

- **Time windows** define when each gateway association is active
- **Security associations** (X.509 certificates, IPsec SAs) are pre-established with the target gateway
- **IP configuration** is pre-provisioned so the gNB can switch endpoints without runtime negotiation

TR 28.874 Use Case 5 ("Feeder link management"): security association and IP configuration pre-configuration with time-windowed lifecycle.

---

## 7. Inter-Satellite Handover (Regenerative)

When each satellite hosts a full gNB (Rel-19 regenerative), a satellite switch is an **inter-gNB handover**. The source gNB (departing satellite) transfers UE context to the target gNB (approaching satellite).

### 7.1 Xn-Based Handover (over ISL)

**Prerequisite:** Inter-Satellite Link (ISL) between source and target satellites, carrying the Xn interface.

**ISL technology options:**
- RF ISL: 22-24.75 GHz, 27-27.5 GHz, or 66-81 GHz (ITU WRC-19 allocations)
- Optical ISL: no spectrum coordination, higher bandwidth, but requires ATP (acquisition, tracking, pointing). Initial setup: up to 50 seconds; re-establishing existing connection: up to 20 seconds.

**Procedure:**

```
Source gNB (departing satellite)          Target gNB (approaching satellite)          AMF
         |                                           |                                |
1. [CHO prepared: D1/D2/T1]                         |                                |
         |                                           |                                |
2.       |──── Handover Request (Xn) ──────>         |                                |
         |<─── Handover Request Ack (Xn) ───         |                                |
         |                                           |                                |
3. RRC Reconfiguration ──> UE                        |                                |
         |                                           |                                |
4. [UE accesses target] ────────────────────>        |                                |
         |                                           |                                |
5.       |                                           |── Path Switch Request ────────> |
         |                                           |<─ Path Switch Request Ack ────  |
         |                                           |                                |
6.       |<─── UE Context Release (Xn) ─────         |                                |
         |                                           |                                |
   [source releases UE]                   [target is new serving gNB]    [AMF updated]
```

**Advantages:**
- Make-before-break: UE context transferred before the source loses coverage
- Standard Xn handover procedure — no NTN-specific modifications to the inter-gNB interface
- ISL carries Xn directly — Rel-19's full-gNB architecture enables this natively

**What changes at the CN:**
- Serving NCGI changes (new gNB-ID from the target satellite)
- Mapped Cell ID: **unchanged** (both satellites map to the same geographic area)
- ULI updated in Path Switch Request with the new serving NCGI (containing the Mapped Cell ID)
- N3 GTP-U tunnel switched to the target gNB's downlink endpoint

### 7.2 NG-Based Handover (No ISL)

**When used:** No ISL exists between source and target satellites, or Xn association not established.

**Procedure:** Standard NG handover via AMF:

```
Source gNB                    AMF                    Target gNB
    |                          |                          |
1.  |── Handover Required ──>  |                          |
    |                          |── Handover Request ────> |
    |                          |<─ Handover Request Ack ─ |
    |<── Handover Command ──── |                          |
    |                          |                          |
2. RRC Reconfiguration ──> UE                             |
    |                          |                          |
3. [UE accesses target] ──────────────────────────>       |
    |                          |                          |
4.  |                          |<── Handover Notify ────  |
    |                          |                          |
5.  |<── UE Context Release ── |                          |
```

**Trade-off:** Higher latency than Xn-based (signaling traverses ground via feeder links of both satellites). Acceptable for GEO or MEO with long visibility windows; potentially problematic for dense LEO with 5-10 minute windows.

### 7.3 Mapped Cell ID Continuity

Across all inter-satellite handover types:

- The **serving NCGI** (Uu Cell ID) changes — the target satellite has a different gNB-ID
- The **Mapped Cell ID** remains invariant — both satellites serve the same earth-fixed geographic area
- The **AMF updates only its serving-cell pointer** (and N3 path). It has no awareness of which physical satellite underlies a Mapped Cell ID, and needs none.
- TR 23.700-29 §8.1 (KI#1 conclusion): "AMF/MME can treat the Mapped Cell IDs as for Rel-17" — no regenerative-specific mapped-cell signalling.

### 7.4 CU-on-Ground Alternative

If the gNB-CU is placed on the ground and only the gNB-DU runs on the satellite:

- Satellite change = **intra-gNB inter-DU mobility** (F1 handover under one CU)
- The CU anchors the NG/N2 association → the AMF sees at most a TNL update, often nothing
- NCGI continuity depends on cell definition at the DU level
- **Primary advantage:** Collapses most satellite changes into AMF-invisible F1 mobility, eliminating the inter-gNB handover storm in dense LEO
- **Primary disadvantage:** F1 interface over the feeder link is more frequent/expensive than NG; store-and-forward and feeder link switchover require ISL or proprietary transport (not standardized). This is why Rel-19 chose full gNB.

---

## 8. CN Impact and Signaling Summary

| Scenario | AMF Sees | SMF/UPF Impact | Mapped Cell ID | Uu Cell ID |
|----------|----------|----------------|----------------|------------|
| **EFC transparent — service link switch (same PCI)** | Nothing | None | Unchanged | Unchanged |
| **EFC transparent — feeder link switch** | Path Switch Request (if gNB IP changes) | N3 tunnel endpoint update | Unchanged | Unchanged |
| **QEFC — reposition boundary** | RAN Config Update (TA list) + per-UE Path Switch on next event | N3 update if path changes | Unchanged | May change |
| **EMC transparent — beam sweep** | Nothing (Mapped Cell ID unchanged) | None | Unchanged | Changes (CHO) |
| **EMC transparent — feeder link switch** | Path Switch Request | N3 tunnel endpoint update | Unchanged | Current value |
| **Regenerative EFC — inter-satellite HO** | Path Switch Request (new NCGI) | N3 tunnel re-routed | Unchanged | New gNB's cell ID |
| **Regenerative EFC — feeder link switch** | Path Switch Request (gNB IP change) | N3 tunnel endpoint update | Unchanged | Unchanged |
| **Regenerative EMC — inter-satellite HO** | Path Switch Request (new NCGI) | N3 tunnel re-routed | Unchanged | Changes |
| **Regenerative — satellite crosses AMF boundary** | Inter-AMF HO or UE release to IDLE | Full session re-establishment | Unchanged | Changes |

---

## 9. OAM Pre-Configuration Requirements

Each switchover type requires specific pre-configuration via OAM:

### 9.1 Service Link Switchover

| Item | Provisioned To | Source Spec |
|------|---------------|-------------|
| Per-beam cell identifiers (NG + Uu) and reference locations | gNB | TS 38.300 Annex B.4 |
| Satellite ephemeris data | gNB + UE (via SIB19) | TS 38.331, TS 28.541 NTNFunction |
| CHO configuration (D1/D2/T1 thresholds, target cells) | UE (via RRC Reconfiguration) | TS 38.331 §5.5.4.17-19 |
| Mapped Cell ID ↔ area table | gNB + AMF/LMF | TS 28.541 mappedCellIdInfoList |
| NTN tracking area codes | NRCellDU | TS 28.541 nTNTAClist |
| Time-windowed cell-gateway schedule (QEFC) | gNB | TR 28.874 NTNTimeBasedConfig |

### 9.2 Feeder Link Switchover

| Item | Provisioned To | Source Spec |
|------|---------------|-------------|
| NTN Gateway locations | gNB | OAM (operator-specific) |
| Security associations (X.509, IPsec SAs) with target gateway | gNB + gateway | TR 28.874 Use Case 5 |
| IP configuration for target gateway | gNB | TR 28.874 Use Case 5 |
| Time-windowed gateway association schedule | gNB | TR 28.874 NTNTimeBasedConfig |
| AMF service area mapping | AMF | TS 23.501 |

### 9.3 Inter-Satellite Handover (Regenerative)

| Item | Provisioned To | Source Spec |
|------|---------------|-------------|
| Xn interface configuration (over ISL) | Both satellite gNBs | TS 38.420 |
| Neighbor cell relations | Both gNBs | TS 28.541 NRCellRelation |
| NTNgNBCapability (time-varying TAI support) | AMF | TR 28.874 |
| `isOnBoard` attribute | GNBCUCPFunction, AMFFunction | TR 28.874 |
| Satellite coverage info list | AMF | TS 28.541 AMFFunction |

---

## 10. Design Trade-Offs

### 10.1 Payload Architecture Selection

| Factor | Transparent | Regenerative (Full gNB) | CU-DU Split |
|--------|-------------|------------------------|-------------|
| Satellite complexity | Low (RF relay) | High (full protocol stack) | Medium (DU only) |
| Feeder link load | High (full Uu bandwidth) | Low (NG interface only) | Medium (F1 interface) |
| Inter-satellite HO | N/A (gNB on ground) | Xn over ISL (standardized) | Not standardized |
| AMF handover storm | None | Proportional to sat-switch rate | Minimal (F1 invisible) |
| Store-and-forward | At gateway (ground) | On-board (native) | Requires ISL (not std) |
| Rel-19 normative status | Baseline (Rel-17/18) | Selected architecture | Valid but not selected |

### 10.2 Handover Storm Mitigation

Dense LEO regenerative deployments face inter-gNB handovers every 5-10 minutes for every UE:

1. **CHO (D1/D2/T1):** Prepare handover in advance; UE executes autonomously at the trigger point. Eliminates real-time network-command dependency.
2. **Soft switchover:** Make-before-break using dual connectivity. Eliminates service interruption.
3. **CU-on-ground architecture:** Collapses inter-satellite to intra-gNB. Eliminates AMF-visible handovers at the cost of F1-over-feeder-link complexity.
4. **Constellation design:** Maximize beam overlap zones between consecutive satellites. Enable unchanged-PCI satellite switch (EFC).

### 10.3 EFC vs QEFC vs EMC Selection

| Factor | EFC | QEFC | EMC |
|--------|-----|------|-----|
| Satellite antenna | Steerable/phased array | Steerable, periodic repos | Body-fixed |
| Mapping complexity | Static table | Time-windowed table | Beam-motion model |
| OAM burden | Low | Medium (NTNTimeBasedConfig) | High (continuous model) |
| UE mobility triggers | None (same PCI) or D1 | D1/T1 at reposition | D2 (moving ref) continuous |
| Spectrum efficiency | Lower (beam steering loss) | Medium | Higher (simpler antenna) |
| Satellite cost | Higher (complex antenna) | Medium | Lower (fixed antenna) |

### 10.4 Service Continuity Targets

| Switchover Type | Target Interruption | Mechanism |
|-----------------|---------------------|-----------|
| EFC unchanged-PCI satellite switch | 0 ms (seamless) | Same PCI/SIB, TA re-sync only |
| CHO-prepared service link switch | < 50 ms | Pre-prepared target, autonomous execution |
| Standard A3 handover | 50-100 ms | Network-commanded, real-time signaling |
| RLF-based (NB-IoT) | 1-10 s | RLF detection + re-establishment |
| Feeder link hard switchover | < 100 ms | Gateway switch, UE unaware |
| Feeder link soft switchover | 0 ms | Dual connectivity |
| Regenerative inter-satellite (Xn) | < 50 ms | Make-before-break over ISL |
| Regenerative inter-satellite (NG) | 100-500 ms | Via AMF, depends on feeder link RTT |

---

## 11. Normative References

| Spec | Sections | Coverage |
|------|----------|----------|
| TS 38.300 | §16.14.2-4 | Service link/feeder link switchover procedures, cell types |
| TS 38.300 | §16.14.5 | NG-RAN signalling, Mapped Cell ID, two-identity model |
| TS 38.300 | Annex B.4 | Per-beam O&M data for EFC/QEFC/EMC |
| TS 38.331 | §5.5.4.17-19 | Measurement events D1, D2, CondEvent T1 |
| TS 38.331 | §5.2.2.46 | SIB19 (NTN-Config IE with ephemeris) |
| TS 38.413 | general | NGAP procedures (Path Switch, HO, ULI) |
| TS 38.420 | general | Xn interface general aspects (16 function categories) |
| TS 23.501 | §5.4.11.7 | Earth-fixed tracking areas, AMF continuity |
| TS 28.541 | §4.3.79, §4.3.83 | NTNFunction IOC, MappedCellIdInfo, mappedCellIdInfoList |
| TR 28.874 | UC 1-5 | NTNTimeBasedConfig, feeder link management, regenerative mode |
| TR 23.700-29 | §8.1 (KI#1) | Regenerative conclusion: standard Mapped Cell ID treatment |
| TR 23.737 | §6, §7 | Architecture study: earth-fixed TAs, rejection of virtual cells |
| TR 38.821 | §7.3.1.3.3 | RAN2 recommendation for fixed Tracking Areas |
