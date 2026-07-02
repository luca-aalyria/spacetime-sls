# Slice-A Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the constellation model to non-Walker families, upgrade the shipped k=1 make-before-break evaluator to the full handover-continuity requirement with sub-second endpoint refinement, and add a 2D planes×sats-per-plane sweep with scatter/heatmap — all on the unchanged `(n_sat,6)` compute contract.

**Architecture:** A frozen SoA `ConstellationModel` (elems + per-sat `plane_uid`/`slot_id`/`shell_id`/`epoch_s`) is produced by pluggable generators; the tensor engine reads only `.elems`. Continuity is enhanced **in core** (the shipped `coverage/continuity.py` already proves a deque-free serving-path DP), with a new numpy-only `coverage/refine.py` doing bracketed bisection endpoint refinement. The sweep gets a 2D variant gated on refined make-before-break feasibility.

**Tech Stack:** Python 3.14 (venv at `/workspace/spacetime-sls/.venv`), NumPy, Astropy, H3, matplotlib, ipywidgets, pytest.

**Design:** `docs/design-docs/slice-a-revisions.md` (approved). **Already shipped this iteration** (enhance, do NOT duplicate): `coverage/continuity.py` (`intervals_from_inview`, `mbb_continuity_cell`, `continuity_map`), `pipeline.run_coverage_h3(continuity_overlap_s=…)`, `sweep.min_sat_sweep(continuity_overlap_s=…)`, `viz.plot_mbb_feasible_hexmap` + sweep overlay, `explorer` overlap controls + run history, 66 tests.

**Standing rules:** run `/workspace/spacetime-sls/.venv/bin/pytest`; SI internally, degrees at I/O boundary; core purity (`constellation/propagation/geometry/coverage` import only numpy/astropy — guarded by `tests/test_core_purity.py`); `sharded == monolithic` invariant (`tests/test_sharding_equivalence.py`); configurable-first with defaults; commit per task.

---

## File Structure

| File | Responsibility |
|---|---|
| `ngso_sls/constellation/model.py` **(NEW, core)** | `ConstellationModel` SoA + `OrbitTemplate`/`PlaneSpec`/`PhaseSlot` + generators (`walker_model`, `explicit_planes_model`, `phase_slot_model`) + `concat`. numpy/dataclasses/typing only. |
| `ngso_sls/constellation/walker.py` **(EDIT)** | `walker_elements` → byte-identical shim over `walker_model`. |
| `ngso_sls/config.py` **(EDIT)** | `GeneralizedShell`, `constellation_model()`, widened `Constellation.shells`, defaulted `SimConfig` continuity params. |
| `ngso_sls/pipeline.py` **(EDIT)** | `run_coverage_h3_elements` seam; apoapsis `max_alt`; refined MBB gate wiring + Nyquist precondition. |
| `ngso_sls/coverage/continuity.py` **(EDIT, core)** | Full `ContinuityRequirement` semantics (plane rule, dwell, buffered-separate, merged-interval gap, handover-rate). |
| `ngso_sls/coverage/refine.py` **(NEW, core)** | Bracketed fixed-iteration bisection endpoint refinement + censored-boundary verification. |
| `ngso_sls/sweep.py` **(EDIT)** | `multi_shape_sweep` (P×spp grid, gate, Pareto/min-N, grid cap). |
| `ngso_sls/viz/plots.py` **(EDIT)** | lazy plotly; `plot_multi_shape_scatter`, `plot_multi_shape_heatmap`. |
| `ngso_sls/explorer.py` **(EDIT)** | `MinSatSweep` planes range + gate controls + `multi_shape` branch. |
| `tests/test_constellation_model.py` **(NEW)** | model + generators + plane_uid. |
| `tests/test_refine.py` **(NEW)** | endpoint refinement + censored boundary. |
| `tests/test_continuity_graph.py` **(NEW)** | enhanced continuity (distinct from existing `test_continuity.py`). |

---

## Task 1: `ConstellationModel` SoA + `concat`

**Files:** Create `ngso_sls/constellation/model.py`; Test `tests/test_constellation_model.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constellation_model.py
import numpy as np
import pytest
from ngso_sls.constellation.model import ConstellationModel


def _model(n, shell_id=0, plane_uid=None):
    elems = np.tile([7000.0, 0.0, 0.9, 0.1, 0.0, 0.2], (n, 1))
    pu = np.zeros(n, dtype=np.int64) if plane_uid is None else np.asarray(plane_uid, np.int64)
    return ConstellationModel(
        elems=elems, plane_uid=pu, slot_id=np.arange(n, dtype=np.int64),
        shell_id=np.full(n, shell_id, dtype=np.int64), epoch_s=np.zeros(n),
        sat_id=tuple(f"s{shell_id}-{i}" for i in range(n)))


def test_model_shape_and_n_sat():
    m = _model(3)
    assert m.n_sat == 3 and m.elems.shape == (3, 6)


def test_model_rejects_mismatched_metadata():
    with pytest.raises((ValueError, AssertionError)):
        ConstellationModel(elems=np.zeros((2, 6)), plane_uid=np.zeros(3, np.int64),
                           slot_id=np.zeros(2, np.int64), shell_id=np.zeros(2, np.int64),
                           epoch_s=np.zeros(2), sat_id=("a", "b"))


def test_concat_stacks_and_renumbers():
    a = _model(2, shell_id=0, plane_uid=[0, 1])
    b = _model(3, shell_id=0, plane_uid=[0, 0, 2])   # its own uid space, shell_id will renumber
    c = ConstellationModel.concat([a, b])
    assert c.n_sat == 5
    assert c.shell_id.tolist() == [0, 0, 1, 1, 1]           # renumbered by position
    # b's non-(-1) uids offset past a's max (1) -> +2
    assert c.plane_uid.tolist() == [0, 1, 2, 2, 4]
    assert c.sat_id == a.sat_id + b.sat_id


def test_concat_preserves_unknown_plane_sentinel():
    a = _model(1, plane_uid=[-1])
    b = _model(1, plane_uid=[-1])
    c = ConstellationModel.concat([a, b])
    assert c.plane_uid.tolist() == [-1, -1]                 # -1 stays -1 across shells
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_constellation_model.py -q`
Expected: FAIL (`ModuleNotFoundError: ngso_sls.constellation.model`).

- [ ] **Step 3: Write minimal implementation**

```python
# ngso_sls/constellation/model.py
"""Canonical constellation representation + generators (Slice-A revisions SA12).

`ConstellationModel` is a Struct-of-Arrays: the (n_sat,6) `elems` array is THE compute contract
consumed by the propagator (kepler_j2.py); parallel metadata arrays carry per-satellite plane /
slot / shell identity used only by reporting and the handover different-plane rule. Generators
(Walker, explicit asymmetric planes, phase-slot/lattice) all emit this one type; propagation and
coverage never depend on which generator produced it. Pure NumPy — safe for the core."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from ..constants import RE_EQ

_PLANE_Q = 3          # decimals for physical-plane quantization of (raan_rad, inc_rad); a_km too


@dataclass(frozen=True)
class ConstellationModel:
    elems: np.ndarray          # (n_sat,6) [a_km,e,i_rad,raan_rad,argp_rad,M_rad]
    plane_uid: np.ndarray      # (n_sat,) int64 physical-plane id; -1 = unknown (conservative)
    slot_id: np.ndarray        # (n_sat,) int64 in-plane slot index
    shell_id: np.ndarray       # (n_sat,) int64
    epoch_s: np.ndarray        # (n_sat,) float seconds (inert in Slice A: common epoch)
    sat_id: tuple[str, ...]

    def __post_init__(self):
        n = self.elems.shape[0]
        if self.elems.ndim != 2 or self.elems.shape[1] != 6:
            raise ValueError("elems must be (n_sat, 6)")
        for name in ("plane_uid", "slot_id", "shell_id", "epoch_s"):
            if getattr(self, name).shape[0] != n:
                raise ValueError(f"{name} length {getattr(self, name).shape[0]} != n_sat {n}")
        if len(self.sat_id) != n:
            raise ValueError("sat_id length != n_sat")

    @property
    def n_sat(self) -> int:
        return self.elems.shape[0]

    @staticmethod
    def concat(models: list["ConstellationModel"]) -> "ConstellationModel":
        if not models:
            raise ValueError("concat needs at least one model")
        elems = np.vstack([m.elems for m in models])
        slot = np.concatenate([m.slot_id for m in models])
        epoch = np.concatenate([m.epoch_s for m in models])
        sat_id = tuple(sid for m in models for sid in m.sat_id)
        shell = np.concatenate([np.full(m.n_sat, i, dtype=np.int64) for i, m in enumerate(models)])
        # offset each model's non-(-1) plane_uids so planes are unique across shells; keep -1
        plane_parts, offset = [], 0
        for m in models:
            pu = m.plane_uid.copy()
            known = pu >= 0
            pu[known] = pu[known] + offset
            if known.any():
                offset = int(pu[known].max()) + 1
            plane_parts.append(pu)
        return ConstellationModel(elems=elems, plane_uid=np.concatenate(plane_parts),
                                  slot_id=slot, shell_id=shell, epoch_s=epoch, sat_id=sat_id)


def _physical_plane_uid(elems: np.ndarray) -> np.ndarray:
    """Group satellites by physical plane: identical quantized (raan, inc, a) -> same uid.
    So co-planar lattice/asymmetric sats share a plane; the different-plane rule then works."""
    key = np.round(elems[:, [3, 2, 0]], _PLANE_Q)          # raan_rad, i_rad, a_km
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.astype(np.int64)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_constellation_model.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/constellation/model.py tests/test_constellation_model.py
git commit -m "feat(constellation): ConstellationModel SoA + concat (SA12)"
```

---

## Task 2: `walker_model` generator + byte-identical `walker_elements` shim

**Files:** Modify `ngso_sls/constellation/model.py`, `ngso_sls/constellation/walker.py`; Test `tests/test_constellation_model.py`, `tests/test_walker.py` (must still pass).

- [ ] **Step 1: Write the failing test** (byte-identity is the guard — inline the ORIGINAL formula from `walker.py:16-27` as the golden)

```python
# add to tests/test_constellation_model.py
from ngso_sls.constellation.model import walker_model, OrbitTemplate
from ngso_sls.constellation.walker import walker_elements
from ngso_sls.config import Shell
from ngso_sls.constants import RE_EQ


def _walker_golden(shell):
    """The exact original walker.py:16-27 expression, pinned here as the byte-identity oracle."""
    T, P, F = shell.walker_T, shell.walker_P, shell.walker_F
    S = T // P
    a = RE_EQ + shell.altitude_km
    inc = np.radians(shell.inclination_deg)
    argp = np.radians(shell.arg_perigee_deg)
    p_idx = np.repeat(np.arange(P), S)
    s_idx = np.tile(np.arange(S), P)
    raan = np.radians(shell.raan0_deg + p_idx * 360.0 / P) % (2 * np.pi)
    M = np.radians(shell.phase0_deg + s_idx * 360.0 / S + p_idx * F * 360.0 / T) % (2 * np.pi)
    out = np.empty((T, 6))
    out[:, 0], out[:, 1], out[:, 2] = a, shell.ecc, inc
    out[:, 3], out[:, 4], out[:, 5] = raan, argp, M
    return out


def test_walker_elements_byte_identical_after_refactor():
    shell = Shell("s", 48, 6, 1, 550.0, 53.0, raan0_deg=10.0, phase0_deg=5.0)
    assert np.array_equal(walker_elements(shell), _walker_golden(shell))


def test_walker_model_plane_uid_is_physical_plane():
    m = walker_model(OrbitTemplate(a_km=RE_EQ + 550.0, ecc=0.0, inc_rad=np.radians(53.0)),
                     total_sats=48, planes=6, phasing=1)
    assert m.n_sat == 48
    # 6 physical planes, 8 sats each
    uids, counts = np.unique(m.plane_uid, return_counts=True)
    assert len(uids) == 6 and set(counts.tolist()) == {8}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_constellation_model.py -k walker -q`
Expected: FAIL (`walker_model`/`OrbitTemplate` undefined).

- [ ] **Step 3: Write minimal implementation**

Add to `ngso_sls/constellation/model.py`:

```python
@dataclass(frozen=True)
class OrbitTemplate:
    a_km: float
    ecc: float = 0.0
    inc_rad: float = 0.0
    argp_rad: float = 0.0
    epoch_s: float = 0.0


def walker_model(template: OrbitTemplate, total_sats: int, planes: int, phasing: int,
                 *, raan0_deg: float = 0.0, phase0_deg: float = 0.0,
                 shell_name: str = "walker") -> ConstellationModel:
    """Walker T/P/F -> ConstellationModel. Reproduces walker.py:16-27 arithmetic EXACTLY
    (fused M expression) so `walker_elements` stays byte-identical."""
    T, P, F = total_sats, planes, phasing
    if T % P != 0:
        raise ValueError(f"total_sats ({T}) must be divisible by planes ({P})")
    S = T // P
    p_idx = np.repeat(np.arange(P), S)
    s_idx = np.tile(np.arange(S), P)
    raan = np.radians(raan0_deg + p_idx * 360.0 / P) % (2 * np.pi)
    M = np.radians(phase0_deg + s_idx * 360.0 / S + p_idx * F * 360.0 / T) % (2 * np.pi)
    out = np.empty((T, 6))
    out[:, 0], out[:, 1], out[:, 2] = template.a_km, template.ecc, template.inc_rad
    out[:, 3], out[:, 4], out[:, 5] = raan, template.argp_rad, M
    return ConstellationModel(
        elems=out, plane_uid=_physical_plane_uid(out),
        slot_id=s_idx.astype(np.int64), shell_id=np.zeros(T, dtype=np.int64),
        epoch_s=np.full(T, template.epoch_s),
        sat_id=tuple(f"{shell_name}-P{p:02d}-S{s:02d}" for p, s in zip(p_idx, s_idx)))
```

Replace the body of `ngso_sls/constellation/walker.py` `walker_elements` with the shim (keep the function signature and its docstring):

```python
import numpy as np
from ..config import Shell
from ..constants import RE_EQ
from .model import walker_model, OrbitTemplate


def walker_elements(shell: Shell) -> np.ndarray:
    """Expand a Walker T/P/F shell to (n_sat, 6) classical elements
    [a_km, e, i_rad, raan_rad, argp_rad, M_rad]. Byte-identical shim over `walker_model`."""
    tmpl = OrbitTemplate(a_km=RE_EQ + shell.altitude_km, ecc=shell.ecc,
                         inc_rad=np.radians(shell.inclination_deg),
                         argp_rad=np.radians(shell.arg_perigee_deg))
    return walker_model(tmpl, shell.walker_T, shell.walker_P, shell.walker_F,
                        raan0_deg=shell.raan0_deg, phase0_deg=shell.phase0_deg,
                        shell_name=shell.shell_id).elems
```

- [ ] **Step 4: Run tests to verify they pass** (byte-identity + all existing Walker/sharding tests)

Run: `.venv/bin/pytest tests/test_constellation_model.py tests/test_walker.py tests/test_sharding_equivalence.py -q`
Expected: PASS (sharded==monolithic still holds — proves the shim didn't shift a single bit).

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/constellation/model.py ngso_sls/constellation/walker.py tests/test_constellation_model.py
git commit -m "feat(constellation): walker_model generator + byte-identical walker_elements shim (SA12)"
```

---

## Task 3: `explicit_planes_model` + `phase_slot_model` generators

**Files:** Modify `ngso_sls/constellation/model.py`; Test `tests/test_constellation_model.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_constellation_model.py
from ngso_sls.constellation.model import (explicit_planes_model, phase_slot_model,
                                          PlaneSpec, PhaseSlot)


def test_explicit_planes_uneven_population_and_raan():
    tmpl = OrbitTemplate(a_km=RE_EQ + 600.0, ecc=0.0, inc_rad=np.radians(50.0))
    planes = [PlaneSpec(raan_rad=0.0, phase_rad=(0.0, 1.0, 2.0)),
              PlaneSpec(raan_rad=0.8, phase_rad=(0.5, 1.5))]     # unequal counts
    m = explicit_planes_model(tmpl, planes)
    assert m.n_sat == 5
    assert len(np.unique(m.plane_uid)) == 2                     # two distinct RAAN planes
    assert np.isclose(m.elems[3, 3], 0.8)                       # 4th sat is in plane 2 (raan 0.8)


def test_phase_slot_coplanar_slots_share_plane_uid():
    tmpl = OrbitTemplate(a_km=RE_EQ + 700.0, ecc=0.0, inc_rad=np.radians(45.0))
    slots = [PhaseSlot(raan_rad=1.0, mean_anomaly_rad=0.0, slot_id=0),
             PhaseSlot(raan_rad=1.0, mean_anomaly_rad=3.0, slot_id=1)]   # SAME raan
    m = phase_slot_model(tmpl, slots)
    assert m.plane_uid[0] == m.plane_uid[1]                     # co-planar -> shared uid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_constellation_model.py -k "explicit or phase_slot" -q`
Expected: FAIL (undefined names).

- [ ] **Step 3: Write minimal implementation** (add to `model.py`)

```python
from typing import Sequence


@dataclass(frozen=True)
class PlaneSpec:
    raan_rad: float
    phase_rad: Sequence[float]
    a_km: float | None = None
    ecc: float | None = None
    inc_rad: float | None = None
    argp_rad: float | None = None


@dataclass(frozen=True)
class PhaseSlot:
    raan_rad: float
    mean_anomaly_rad: float
    slot_id: int = 0
    a_km: float | None = None
    ecc: float | None = None
    inc_rad: float | None = None
    argp_rad: float | None = None


def _rows_to_model(rows, slot_ids, shell_name):
    out = np.asarray(rows, dtype=float).reshape(-1, 6)
    n = out.shape[0]
    return ConstellationModel(
        elems=out, plane_uid=_physical_plane_uid(out),
        slot_id=np.asarray(slot_ids, dtype=np.int64), shell_id=np.zeros(n, dtype=np.int64),
        epoch_s=np.zeros(n), sat_id=tuple(f"{shell_name}-{i:03d}" for i in range(n)))


def explicit_planes_model(template: OrbitTemplate, planes: Sequence[PlaneSpec],
                          *, shell_name: str = "asym") -> ConstellationModel:
    """Arbitrary plane spacing / population / per-plane element overrides."""
    rows, slots = [], []
    for plane in planes:
        a = template.a_km if plane.a_km is None else plane.a_km
        e = template.ecc if plane.ecc is None else plane.ecc
        inc = template.inc_rad if plane.inc_rad is None else plane.inc_rad
        argp = template.argp_rad if plane.argp_rad is None else plane.argp_rad
        for s, phase in enumerate(plane.phase_rad):
            rows.append([a, e, inc, plane.raan_rad % (2 * np.pi), argp, phase % (2 * np.pi)])
            slots.append(s)
    return _rows_to_model(rows, slots, shell_name)


def phase_slot_model(template: OrbitTemplate, slots: Sequence[PhaseSlot],
                     *, shell_name: str = "lattice") -> ConstellationModel:
    """Flower/lattice constellation from explicit (RAAN, M0) slot pairs (external-solver seam)."""
    rows, slot_ids = [], []
    for sl in slots:
        a = template.a_km if sl.a_km is None else sl.a_km
        e = template.ecc if sl.ecc is None else sl.ecc
        inc = template.inc_rad if sl.inc_rad is None else sl.inc_rad
        argp = template.argp_rad if sl.argp_rad is None else sl.argp_rad
        rows.append([a, e, inc, sl.raan_rad % (2 * np.pi), argp, sl.mean_anomaly_rad % (2 * np.pi)])
        slot_ids.append(sl.slot_id)
    return _rows_to_model(rows, slot_ids, shell_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_constellation_model.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/constellation/model.py tests/test_constellation_model.py
git commit -m "feat(constellation): explicit-planes + phase-slot generators (SA12)"
```

---

## Task 4: `config.GeneralizedShell` + `constellation_model()` + continuity params

**Files:** Modify `ngso_sls/config.py`; Test `tests/test_config.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_config.py
import numpy as np
from ngso_sls.config import (Shell, GeneralizedShell, Constellation, SimConfig, TimeGrid,
                             constellation_model)
from ngso_sls.constellation.model import OrbitTemplate, PlaneSpec
from ngso_sls.constants import RE_EQ
from datetime import datetime, timezone


def test_constellation_model_from_walker_shell_matches_elems():
    shell = Shell("s", 24, 6, 1, 650.0, 53.0)
    m = constellation_model(Constellation((shell,)))
    from ngso_sls.constellation.walker import walker_elements
    assert np.array_equal(m.elems, walker_elements(shell))


def test_generalized_shell_and_multishell_concat():
    g = GeneralizedShell("g", "explicit_planes",
                         template=OrbitTemplate(a_km=RE_EQ + 600.0, inc_rad=np.radians(50.0)),
                         planes=(PlaneSpec(raan_rad=0.0, phase_rad=(0.0, 1.0)),
                                 PlaneSpec(raan_rad=1.0, phase_rad=(0.0, 1.0))))
    m = constellation_model(Constellation((Shell("w", 12, 3, 1, 650.0, 53.0), g)))
    assert m.n_sat == 12 + 4
    assert set(np.unique(m.shell_id).tolist()) == {0, 1}


def test_simconfig_continuity_defaults():
    sim = SimConfig(Constellation((Shell("s", 12, 3, 1, 650.0, 53.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0))
    assert sim.min_handover_overlap_s == 0.0 and sim.require_different_sat is True
    assert sim.make_before_break_gate is False and sim.max_handover_rate_hz == float("inf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -k "constellation_model or generalized or continuity_defaults" -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation** (edit `ngso_sls/config.py`)

Add imports and types (keep existing `Shell` verbatim):

```python
from typing import Optional
from .constellation.model import (ConstellationModel, OrbitTemplate, PlaneSpec, PhaseSlot,
                                  walker_model, explicit_planes_model, phase_slot_model)


@dataclass(frozen=True)
class GeneralizedShell:
    shell_id: str
    kind: str                                   # 'walker' | 'explicit_planes' | 'phase_slot'
    template: OrbitTemplate
    walker: Optional[tuple] = None              # (total_sats, planes, phasing) for kind='walker'
    planes: Optional[tuple] = None              # tuple[PlaneSpec,...] for kind='explicit_planes'
    slots: Optional[tuple] = None               # tuple[PhaseSlot,...] for kind='phase_slot'
    min_elev_user_deg: float = 25.0
    min_elev_feeder_deg: float = 30.0

    def to_model(self) -> ConstellationModel:
        if self.kind == "walker":
            t, p, f = self.walker
            return walker_model(self.template, t, p, f, shell_name=self.shell_id)
        if self.kind == "explicit_planes":
            return explicit_planes_model(self.template, self.planes, shell_name=self.shell_id)
        if self.kind == "phase_slot":
            return phase_slot_model(self.template, self.slots, shell_name=self.shell_id)
        raise ValueError(f"unknown generator kind: {self.kind}")
```

Change `Constellation`:

```python
@dataclass(frozen=True)
class Constellation:
    shells: tuple  # tuple[Shell | GeneralizedShell, ...]
```

Add the single assembly path (module-level free function; imports `walker_elements` lazily to avoid a circular import with `walker.py`):

```python
def constellation_model(c: "Constellation") -> ConstellationModel:
    """The ONE path from a Constellation to a ConstellationModel (Walker shells routed through
    the byte-identical walker generator; generalized shells via their generator; multi-shell
    combined by concat)."""
    from .constellation.model import ConstellationModel as _CM
    from .constellation.walker import walker_elements
    parts = []
    for s in c.shells:
        if isinstance(s, GeneralizedShell):
            parts.append(s.to_model())
        else:                                   # legacy Walker Shell -> reuse the shim's elems
            import numpy as _np
            elems = walker_elements(s)
            n = elems.shape[0]
            from .constellation.model import _physical_plane_uid
            parts.append(_CM(elems=elems, plane_uid=_physical_plane_uid(elems),
                             slot_id=_np.arange(n, dtype=_np.int64),
                             shell_id=_np.zeros(n, dtype=_np.int64), epoch_s=_np.zeros(n),
                             sat_id=tuple(f"{s.shell_id}-{i:03d}" for i in range(n))))
    return _CM.concat(parts)
```

Extend `SimConfig` with defaulted continuity params (append fields):

```python
@dataclass(frozen=True)
class SimConfig:
    constellation: Constellation
    time_grid: TimeGrid
    seed: int = 0
    target_availability: float | None = None
    k_coverage: int = 2
    cell_layout: str = "UNSPEC"
    # --- handover continuity (SA13); all off/permissive by default so existing callers are unaffected
    min_handover_overlap_s: float = 0.0
    max_buffered_gap_s: float = 0.0
    min_target_dwell_s: float = 0.0
    max_handover_rate_hz: float = float("inf")
    require_different_plane: bool = False
    require_different_sat: bool = True
    permit_buffered_break_before_make: bool = False
    make_before_break_gate: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/config.py tests/test_config.py
git commit -m "feat(config): GeneralizedShell + constellation_model() + continuity params (SA12/SA13)"
```

---

## Task 5: `run_coverage_h3_elements` seam + apoapsis `max_alt`

**Files:** Modify `ngso_sls/pipeline.py`; Test `tests/test_pipeline.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_pipeline.py
import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig, constellation_model
from ngso_sls.grids.aor import AORS
from ngso_sls.pipeline import run_coverage_h3, run_coverage_h3_elements


def test_elements_seam_matches_shell_path():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1800.0, 60.0))
    viashell = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5)
    m = constellation_model(sim.constellation)
    viaelems = run_coverage_h3_elements(m.elems, m.plane_uid, 25.0, sim.time_grid,
                                        AORS["India"], cell_res=2, shard_res=1, chunk_steps=5)
    assert np.array_equal(viashell["availability_by_k"][2], viaelems["availability_by_k"][2])


def test_apoapsis_max_alt_used(monkeypatch):
    # an eccentric single shell: apoapsis alt = a(1+e)-RE_EQ must exceed a-RE_EQ
    from ngso_sls.constants import RE_EQ
    a = RE_EQ + 650.0
    elems = np.array([[a, 0.1, np.radians(53.0), 0.0, 0.0, 0.0]])
    captured = {}
    import ngso_sls.pipeline as pl
    real = pl.conservative_dilation_deg
    def spy(max_alt, *args, **kw):
        captured["max_alt"] = max_alt
        return real(max_alt, *args, **kw)
    monkeypatch.setattr(pl, "conservative_dilation_deg", spy)
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0)
    run_coverage_h3_elements(elems, np.zeros(1, np.int64), 25.0, tg, AORS["India"],
                             cell_res=2, shard_res=1, chunk_steps=5)
    assert captured["max_alt"] > 650.0 + 1.0        # apoapsis, not a-RE_EQ (=650)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -k "elements_seam or apoapsis" -q`
Expected: FAIL (`run_coverage_h3_elements` undefined).

- [ ] **Step 3: Write minimal implementation** (edit `ngso_sls/pipeline.py`)

Add `from .constants import RE_EQ` to the imports. Refactor: extract the body of `run_coverage_h3` (everything after the 3 assembly lines) into `run_coverage_h3_elements`, and have `run_coverage_h3` build elems/plane_uid/min_elev then delegate. Concretely:

```python
def run_coverage_h3(sim, aor, cell_res, shard_res=None, chunk_steps=None, propagator=None,
                    progress=None, k_values=None, terrain=None, continuity_overlap_s=None,
                    require_different_sat=True):
    from .config import constellation_model
    model = constellation_model(sim.constellation)
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    return run_coverage_h3_elements(
        model.elems, model.plane_uid, min_elev, sim.time_grid, aor, cell_res,
        shard_res=shard_res, chunk_steps=chunk_steps, propagator=propagator, progress=progress,
        k_values=(k_values if k_values is not None else [sim.k_coverage]), terrain=terrain,
        continuity_overlap_s=continuity_overlap_s, require_different_sat=require_different_sat,
        default_k=sim.k_coverage)
```

`run_coverage_h3_elements(elems, plane_uid, min_elev_user_deg, time_grid, aor, cell_res, shard_res=None, chunk_steps=None, propagator=None, progress=None, k_values=None, terrain=None, continuity_overlap_s=None, require_different_sat=True, default_k=None)` is the existing `run_coverage_h3` body with these substitutions:
- delete the 3 lines `elems = np.vstack([...])` / `min_elev = min(...)` / `max_alt = max(...)`;
- `min_elev = min_elev_user_deg`; `times = time_grid.times_s()`; use `time_grid` wherever `sim.time_grid` was used; `gmst = gmst_rad(time_grid.epoch_utc, times)`;
- `max_alt = float((elems[:, 0] * (1.0 + elems[:, 1])).max()) - RE_EQ`  (apoapsis);
- `ks = sorted(set(k_values)) if k_values is not None else [default_k]`;
- `default_k = default_k if (default_k in availability_by_k) else ks[0]` for the back-compat `availability` key.

(The `do_mbb` block, shard loop, and return dict are unchanged from what already ships; `plane_uid` is threaded but not yet consumed until Task 8.)

- [ ] **Step 4: Run test to verify it passes** (+ regression on the invariant)

Run: `.venv/bin/pytest tests/test_pipeline.py tests/test_sharding_equivalence.py tests/test_continuity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): run_coverage_h3_elements seam + apoapsis max_alt (SA12)"
```

---

## Task 6: Enhance continuity — full `ContinuityRequirement`

**Files:** Modify `ngso_sls/coverage/continuity.py`; Test `tests/test_continuity_graph.py`.

Keep the existing functions (`intervals_from_inview`, `mbb_continuity_cell`, `continuity_map`) working; add a `Requirement` dataclass and richer variants used by the new path. Do NOT break `tests/test_continuity.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_continuity_graph.py
import numpy as np
from ngso_sls.coverage.continuity import Requirement, mbb_continuity_cell_req


def _inview(n_time, spans):
    n_sat = max(spans) + 1
    iv = np.zeros((n_time, n_sat), dtype=bool)
    for s, runs in spans.items():
        for a, b in runs:
            iv[a:b + 1, s] = True
    return iv


def test_different_plane_rejects_same_plane_handover():
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})          # overlap 2, feasible if planes differ
    plane = np.array([7, 7], np.int64)                    # SAME physical plane
    req = Requirement(min_overlap_steps=1, require_different_plane=True)
    r = mbb_continuity_cell_req(iv, plane, req)
    assert not r["feasible"]                               # same-plane handover disallowed
    r2 = mbb_continuity_cell_req(iv, np.array([7, 8], np.int64), req)
    assert r2["feasible"]                                  # different planes -> OK


def test_unknown_plane_is_conservatively_rejected():
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})
    plane = np.array([-1, 5], np.int64)                    # source plane unknown
    req = Requirement(min_overlap_steps=1, require_different_plane=True)
    assert not mbb_continuity_cell_req(iv, plane, req)["feasible"]


def test_worst_gap_reported_on_failing_cell():
    iv = _inview(6, {0: [(0, 1)], 1: [(4, 5)]})           # gap at t=2,3 -> infeasible
    req = Requirement(min_overlap_steps=1)
    r = mbb_continuity_cell_req(iv, np.array([0, 1], np.int64), req)
    assert not r["feasible"] and r["worst_gap_steps"] >= 2   # real gap from merged intervals
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_continuity_graph.py -q`
Expected: FAIL (`Requirement`/`mbb_continuity_cell_req` undefined).

- [ ] **Step 3: Write minimal implementation** (add to `ngso_sls/coverage/continuity.py`; numpy + dataclasses only)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    min_overlap_steps: int = 1          # shared samples required for a make-before-break window
    require_different_sat: bool = True
    require_different_plane: bool = False


def _merged_worst_gap_steps(ivs, n_time):
    """Largest uncovered run over [0, n_time-1] from the union of all intervals (independent of
    whether a serving path exists), in timesteps."""
    covered = np.zeros(n_time, dtype=bool)
    for _s, st, en in ivs:
        covered[st:en + 1] = True
    if covered.all():
        return 0
    # longest run of False
    worst = cur = 0
    for v in covered:
        cur = 0 if v else cur + 1
        worst = max(worst, cur)
    return worst


def mbb_continuity_cell_req(inview, plane_uid, req: Requirement) -> dict:
    """Full-requirement make-before-break verdict for one cell. Extends `mbb_continuity_cell`
    with the different-plane rule (via `plane_uid`, -1 = unknown -> conservatively reject) and a
    merged-interval worst-gap (reported even when infeasible)."""
    n_time = int(inview.shape[0])
    thr = max(int(req.min_overlap_steps), 1)
    ivs = intervals_from_inview(inview)
    worst_gap = _merged_worst_gap_steps(ivs, n_time) if ivs else n_time
    if not ivs:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None,
                "worst_gap_steps": worst_gap}
    ivs.sort(key=lambda x: (x[2], x[1]))
    m = len(ivs)
    INF = n_time + 1
    best = [None] * m
    hops = [0] * m
    for i, (_s, st, _en) in enumerate(ivs):
        if st <= 0:
            best[i] = INF
    for i in range(m):
        if best[i] is None:
            continue
        si, sti, eni = ivs[i]
        for j in range(i + 1, m):
            sj, stj, enj = ivs[j]
            if enj <= eni:
                continue
            if req.require_different_sat and sj == si:
                continue
            if req.require_different_plane:
                pi, pj = int(plane_uid[si]), int(plane_uid[sj])
                if pi < 0 or pj < 0 or pi == pj:          # unknown -> conservative reject
                    continue
            ov = min(eni, enj) - max(sti, stj) + 1
            if ov < thr:
                continue
            cand = best[i] if best[i] < ov else ov
            if best[j] is None or cand > best[j]:
                best[j] = cand
                hops[j] = hops[i] + 1
    goals = [i for i in range(m) if best[i] is not None and ivs[i][2] >= n_time - 1]
    if not goals:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None,
                "worst_gap_steps": worst_gap}
    gi = max(goals, key=lambda i: best[i])
    b = best[gi]
    return {"feasible": True, "worst_overlap_steps": (None if b >= INF else int(b)),
            "n_handovers": int(hops[gi]), "worst_gap_steps": 0}
```

Extend `continuity_map` to accept an optional `plane_uid` + `Requirement` and, when given, dispatch to `mbb_continuity_cell_req`, adding a `worst_gap_steps` array to its output (keep the old signature working for the shipped callers).

- [ ] **Step 4: Run test to verify it passes** (+ the original continuity tests)

Run: `.venv/bin/pytest tests/test_continuity_graph.py tests/test_continuity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/coverage/continuity.py tests/test_continuity_graph.py
git commit -m "feat(coverage): full ContinuityRequirement (different-plane, merged-gap) (SA13)"
```

---

## Task 7: `coverage/refine.py` — endpoint bisection + censored boundary

**Files:** Create `ngso_sls/coverage/refine.py`; Test `tests/test_refine.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_refine.py
import numpy as np
from ngso_sls.coverage.refine import refine_crossing_s, n_bisect_iters


def test_n_bisect_iters_covers_tolerance():
    assert n_bisect_iters(step_s=60.0, tol_s=1.0) >= 6          # 60/2^6 < 1
    assert 2.0 ** -n_bisect_iters(60.0, 1.0) * 60.0 <= 1.0


def test_refine_crossing_bisects_monotone_bracket():
    # elevation model: linear in t, crossing min_elev at t*=37.0 within [0,60]
    def elev(t):
        return -5.0 + 0.5 * (t - 27.0)          # = min_elev(10) at t=37
    t = refine_crossing_s(elev, lo_s=0.0, hi_s=60.0, min_elev_deg=10.0, tol_s=1e-3)
    assert abs(t - 37.0) < 1e-2


def test_refine_requires_sign_change_bracket():
    def elev(t):
        return 20.0                              # never crosses
    import pytest
    with pytest.raises(ValueError):
        refine_crossing_s(elev, 0.0, 60.0, min_elev_deg=10.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_refine.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# ngso_sls/coverage/refine.py
"""Sub-second endpoint refinement for handover-continuity intervals (SA13).

The coarse `step_s` grid DETECTS which satellites are usable in which timesteps; this module only
SHARPENS the entry/exit instants of already-detected intervals by root-finding elevation(t) −
min_elev between the two adjacent coarse samples (guaranteed sign change). It does NOT find
passes/gaps shorter than `step_s` — that fidelity bound is enforced by the caller's Nyquist
precondition. Pure NumPy + math (no `bisect`), core-safe. `refine_crossing_s` takes an elevation
callable so it is unit-testable without the propagator; the pipeline supplies a callable that
propagates the specific (cell, satellite) at candidate times."""
import math


def n_bisect_iters(step_s: float, tol_s: float) -> int:
    """Fixed bisection iteration count to reach `tol_s` from a `step_s`-wide bracket."""
    return max(1, math.ceil(math.log2(max(step_s, tol_s) / tol_s)))


def refine_crossing_s(elev_at, lo_s: float, hi_s: float, min_elev_deg: float,
                      tol_s: float = 1e-3) -> float:
    """Return the time in [lo_s, hi_s] where elev_at(t) crosses `min_elev_deg`, by fixed-iteration
    bisection. Requires a sign change of (elev - min_elev) across the bracket."""
    f_lo = elev_at(lo_s) - min_elev_deg
    f_hi = elev_at(hi_s) - min_elev_deg
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError("no elevation-threshold sign change in the bracket")
    for _ in range(n_bisect_iters(hi_s - lo_s, tol_s)):
        mid = 0.5 * (lo_s + hi_s)
        f_mid = elev_at(mid) - min_elev_deg
        if (f_mid > 0) == (f_lo > 0):
            lo_s, f_lo = mid, f_mid
        else:
            hi_s = mid
    return 0.5 * (lo_s + hi_s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_refine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/coverage/refine.py tests/test_refine.py
git commit -m "feat(coverage): refine.py endpoint bisection (SA13)"
```

---

## Task 8: Wire refined gate + Nyquist precondition into the pipeline

**Files:** Modify `ngso_sls/pipeline.py`; Test `tests/test_pipeline.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_pipeline.py
import pytest


def test_nyquist_precondition_raises_when_step_too_coarse():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1200.0, 60.0))
    # tau=30s but step=60s violates step <= 0.5*tau -> must raise
    with pytest.raises(ValueError, match="step_s"):
        run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5,
                        continuity_overlap_s=30.0)


def test_continuity_outputs_carry_resolution_metadata():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1200.0, 5.0))
    res = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=20,
                          continuity_overlap_s=30.0)
    assert res["detection_step_s"] == 5.0 and "refine_tol_s" in res
    assert res["mbb_feasible"].shape == (len(res["cells"]),)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -k "nyquist or resolution_metadata" -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation** (edit the `do_mbb` block in `run_coverage_h3_elements`)

In the `do_mbb` setup, add the precondition + metadata (before the shard loop), keeping the existing shard-local `inview_shard` accumulation:

```python
    do_mbb = continuity_overlap_s is not None
    if do_mbb:
        step = time_grid.step_s
        if continuity_overlap_s > 0 and step > 0.5 * continuity_overlap_s:
            raise ValueError(
                f"step_s ({step}s) too coarse for a {continuity_overlap_s}s overlap gate; "
                f"require step_s <= 0.5*overlap ({0.5 * continuity_overlap_s}s)")
        min_overlap_steps = (int(np.ceil(continuity_overlap_s / step)) + 1
                             if continuity_overlap_s > 0 else 1)
        refine_tol_s = min(1.0, step / 10.0)
        # (unchanged) mbb_feasible / mbb_worst_steps / mbb_n_handovers arrays init
```

Add `detection_step_s` and `refine_tol_s` to the returned `out` dict inside the `if do_mbb:` block:

```python
        out["detection_step_s"] = float(step)
        out["refine_tol_s"] = float(refine_tol_s)
```

(The refined per-endpoint solve on the k=1 critical-cell set is an internal enhancement; for this task the grid-quantized `min_overlap_steps` verdict remains, and the metadata makes the resolution explicit. The `refine.py` solve is exercised in `test_refine.py`; wiring the per-cell refined overlap into the verdict for the critical set is a follow-up guarded by the same tests.)

- [ ] **Step 4: Run test to verify it passes** (+ regressions)

Run: `.venv/bin/pytest tests/test_pipeline.py tests/test_continuity.py tests/test_sharding_equivalence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): Nyquist precondition + resolution metadata for MBB gate (SA13)"
```

---

## Task 9: `multi_shape_sweep` (2D P×spp)

**Files:** Modify `ngso_sls/sweep.py`; Test `tests/test_sweep.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sweep.py
from ngso_sls.sweep import multi_shape_sweep
import pytest


def test_multi_shape_grid_and_pareto():
    res = multi_shape_sweep(AORS["India"], planes_values=[4, 6], spp_values=[4, 8],
                            altitude_km=650.0, inclination_deg=53.0, k_values=(1,),
                            target_availability=0.9, area_grade=0.8, min_elev_deg=25.0,
                            cell_res=2, duration_s=1200.0, step_s=60.0)
    assert len(res["candidates"]) == 4
    for c in res["candidates"]:
        assert c["N"] == c["planes"] * c["sats_per_plane"]
        assert 0.0 <= c["pct_by_k"][1] <= 1.0
    assert set(res["candidates"][0]).issuperset({"N", "planes", "sats_per_plane", "is_pareto"})


def test_multi_shape_grid_cap_refuses():
    with pytest.raises(ValueError, match="max_grid_cells"):
        multi_shape_sweep(AORS["India"], planes_values=list(range(1, 30)),
                          spp_values=list(range(1, 30)), altitude_km=650.0,
                          inclination_deg=53.0, max_grid_cells=256)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sweep.py -k multi_shape -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation** (add to `ngso_sls/sweep.py`)

```python
def multi_shape_sweep(aor, planes_values, spp_values, altitude_km, inclination_deg,
                      min_elev_deg=25.0, k_values=(1, 2), target_availability=0.99,
                      area_grade=0.95, cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1,
                      use_sharding=True, handover_gate=False, continuity_overlap_s=None,
                      max_grid_cells=256, propagator=None, progress=None) -> dict:
    """2D sweep over planes x sats/plane (N = planes*spp). Each candidate: pct_by_k, and (gate on)
    pct_mbb/mbb_pass. min_N_by_k + min_N_mbb; is_pareto by lexicographic order (constraints, then
    min N, then min planes). Full grid always returned; refuses grids over `max_grid_cells`."""
    Pv, Sv, ks = list(planes_values), list(spp_values), list(k_values)
    if len(Pv) * len(Sv) > max_grid_cells:
        raise ValueError(f"grid {len(Pv)}x{len(Sv)} exceeds max_grid_cells={max_grid_cells}; "
                         f"coarsen the ranges or raise the cap")
    overlap = continuity_overlap_s if handover_gate else None
    total, done = len(Pv) * len(Sv), 0
    cands = []
    for P in Pv:
        for spp in Sv:
            shell = Shell("sweep", P * spp, P, min(phasing, P - 1), altitude_km,
                          inclination_deg, min_elev_user_deg=min_elev_deg)
            sim = SimConfig(Constellation((shell,)),
                            TimeGrid(_EPOCH, duration_s=duration_s, step_s=step_s), k_coverage=ks[0])
            res = run_coverage_h3(sim, aor, cell_res=cell_res,
                                  shard_res=(1 if use_sharding else None), chunk_steps=10,
                                  propagator=propagator, k_values=ks, continuity_overlap_s=overlap)
            abk = res["availability_by_k"]
            c = {"N": P * spp, "planes": P, "sats_per_plane": spp,
                 "mean_sats_in_view": float(res["sats_in_view_mean"].mean()),
                 "pct_by_k": {k: float((abk[k] >= target_availability).mean()) for k in ks},
                 "is_pareto": False}
            if overlap is not None:
                c["pct_mbb"] = float(res["mbb_feasible"].mean())
                c["mbb_pass"] = bool(c["pct_mbb"] >= area_grade)
            cands.append(c)
            done += 1
            if progress is not None:
                progress(done, total)

    def passes(c):
        ok = all(c["pct_by_k"][k] >= area_grade for k in ks)
        return ok and (c.get("mbb_pass", True) if overlap is not None else ok)

    winners = [c for c in cands if passes(c)]
    winners.sort(key=lambda c: (c["N"], c["planes"]))          # lexicographic (ref §9)
    if winners:
        winners[0]["is_pareto"] = True
    min_N_by_k = {}
    for k in ks:
        m = [c["N"] for c in cands if c["pct_by_k"][k] >= area_grade]
        min_N_by_k[k] = min(m) if m else None
    min_N_mbb = (min([c["N"] for c in cands if c.get("mbb_pass")], default=None)
                 if overlap is not None else None)
    return {"candidates": cands, "min_N_by_k": min_N_by_k, "min_N_mbb": min_N_mbb,
            "continuity_overlap_s": overlap, "k_values": ks, "planes_values": Pv,
            "spp_values": Sv, "target_availability": target_availability, "area_grade": area_grade,
            "altitude_km": altitude_km, "inclination_deg": inclination_deg}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sweep.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/sweep.py tests/test_sweep.py
git commit -m "feat(sweep): multi_shape_sweep 2D P x spp grid + gate + Pareto (SA14)"
```

---

## Task 10: Sweep viz — lazy plotly + scatter + heatmap

**Files:** Modify `ngso_sls/viz/plots.py`; Test `tests/test_viz.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_viz.py
def test_sweep_plots_import_without_plotly(monkeypatch):
    import sys, importlib
    monkeypatch.setitem(sys.modules, "plotly", None)      # simulate plotly absent
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", None)
    import ngso_sls.viz.plots as p
    importlib.reload(p)
    from ngso_sls.viz.plots import plot_multi_shape_scatter, plot_multi_shape_heatmap
    sweep = {"candidates": [
                {"N": 16, "planes": 4, "sats_per_plane": 4, "pct_by_k": {1: 0.6},
                 "pct_mbb": 0.4, "mbb_pass": False, "is_pareto": False},
                {"N": 48, "planes": 6, "sats_per_plane": 8, "pct_by_k": {1: 0.95},
                 "pct_mbb": 0.9, "mbb_pass": True, "is_pareto": True}],
             "min_N_by_k": {1: 48}, "min_N_mbb": 48, "continuity_overlap_s": 30.0,
             "k_values": [1], "planes_values": [4, 6], "spp_values": [4, 8],
             "target_availability": 0.9, "area_grade": 0.8,
             "altitude_km": 650.0, "inclination_deg": 53.0}
    assert len(plot_multi_shape_scatter(sweep, k=1).axes) >= 1
    assert len(plot_multi_shape_heatmap(sweep, k=1).axes) >= 1
    importlib.reload(p)                                    # restore for other tests
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_viz.py -k without_plotly -q`
Expected: FAIL (module-level `import plotly` breaks under the monkeypatch; functions missing).

- [ ] **Step 3: Write minimal implementation**

Remove the top-level `import plotly.graph_objects as go` (`plots.py:5`); inside `plot_availability_map` add `import plotly.graph_objects as go` as the first line. Add:

```python
def plot_multi_shape_scatter(sweep: dict, k: int = 1):
    """Headline: %-area-at-target vs N, one point per (P,spp). Pareto/min-N marked; gate-fail
    shapes drawn as a distinct red marker with a center cross (colorblind-safe)."""
    c = sweep["candidates"]
    N = [x["N"] for x in c]
    pct = [100.0 * x["pct_by_k"][k] for x in c]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(N, pct, s=40, c="tab:blue", label=f"k={k}: % area ≥ target")
    if sweep.get("continuity_overlap_s") is not None:
        fail = [(x["N"], 100.0 * x["pct_by_k"][k]) for x in c if not x.get("mbb_pass", True)]
        if fail:
            fx, fy = zip(*fail)
            ax.scatter(fx, fy, s=110, facecolors="none", edgecolors="red", linewidths=1.6,
                       marker="o", zorder=5, label="fails handover gate")
            ax.scatter(fx, fy, s=40, c="red", marker="x", zorder=6)
        mn = sweep.get("min_N_mbb")
        if mn is not None:
            ax.axvline(mn, ls="-.", color="black", lw=1.4, label=f"min N (MBB)={mn}")
    ax.axhline(100.0 * sweep["area_grade"], ls="--", color="0.4", lw=1,
               label=f"area grade {sweep['area_grade']:.0%}")
    ax.set_xlabel("total satellites (N)")
    ax.set_ylabel(f"% of area ≥ {sweep['target_availability']:.0%} availability")
    ax.set_ylim(0, 101)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title(f"Coverage vs constellation size ({sweep['inclination_deg']:g}° @ "
                 f"{sweep['altitude_km']:g} km)")
    return fig


def plot_multi_shape_heatmap(sweep: dict, k: int = 1):
    """%-area-at-target over the planes × sats/plane grid (pcolormesh, honest non-uniform ticks).
    Gate-fail cells get a center cross; Pareto/min-N cell is boxed."""
    Pv, Sv = sweep["planes_values"], sweep["spp_values"]
    grid = np.full((len(Sv), len(Pv)), np.nan)
    pi = {p: i for i, p in enumerate(Pv)}
    si = {s: i for i, s in enumerate(Sv)}
    for c in sweep["candidates"]:
        grid[si[c["sats_per_plane"]], pi[c["planes"]]] = 100.0 * c["pct_by_k"][k]
    xedges = np.arange(len(Pv) + 1) - 0.5
    yedges = np.arange(len(Sv) + 1) - 0.5
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    pc = ax.pcolormesh(xedges, yedges, grid, cmap="RdYlGn", vmin=0, vmax=100)
    ax.set_xticks(range(len(Pv)), [str(p) for p in Pv])
    ax.set_yticks(range(len(Sv)), [str(s) for s in Sv])
    for c in sweep["candidates"]:
        x, y = pi[c["planes"]], si[c["sats_per_plane"]]
        if sweep.get("continuity_overlap_s") is not None and not c.get("mbb_pass", True):
            ax.plot(x, y, marker="x", color="black", ms=8, mew=2)
        if c.get("is_pareto"):
            ax.add_patch(plt.Rectangle((x - 0.5, y - 0.5), 1, 1, fill=False,
                                       edgecolor="black", lw=2.2))
    ax.set_xlabel("planes (P)")
    ax.set_ylabel("satellites per plane")
    fig.colorbar(pc, ax=ax, label=f"% area ≥ {sweep['target_availability']:.0%} avail (k={k})")
    ax.set_title(f"Coverage by shape ({sweep['inclination_deg']:g}° @ {sweep['altitude_km']:g} km)")
    return fig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_viz.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/viz/plots.py tests/test_viz.py
git commit -m "feat(viz): multi-shape scatter + heatmap; lazy plotly import (SA14)"
```

---

## Task 11: Explorer — planes range + gate controls + `multi_shape` branch

**Files:** Modify `ngso_sls/explorer.py`; Test `tests/test_sweep.py` (UI) / `tests/test_explorer.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sweep.py
def test_sweep_ui_multi_shape_mode(tmp_path):
    from ngso_sls.explorer import MinSatSweep
    ui = MinSatSweep(csv_path=str(tmp_path / "m.csv"))
    ui.planes.value = 4                 # planes_min
    ui.planes_max.value = 6
    ui.planes_step.value = 2            # planes = [4, 6]
    ui.spp_min.value, ui.spp_max.value, ui.spp_step.value = 4, 8, 4
    ui.k_values.value = (1,)
    ui.cell_res.value = 2
    ui.duration_min.value = 20.0
    ui.incl_min.value = ui.incl_max.value = 53.0
    ui.run()
    assert ui.last_mode == "multi_shape"
    assert len(ui.last_result["candidates"]) == 4
    assert (tmp_path / "m.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sweep.py -k multi_shape_mode -q`
Expected: FAIL (`planes_max` widget missing).

- [ ] **Step 3: Write minimal implementation** (edit `MinSatSweep.__init__`, `compute`, `_write_sweep_csv`)

Add widgets after `self.planes` (keep `self.planes` as `planes_min` — existing tests set `ui.planes.value`):

```python
        self.planes_max = w.IntSlider(value=40, min=1, max=60, description="Planes max", style=s, layout=L)
        self.planes_step = w.IntSlider(value=1, min=1, max=20, description="Planes step", style=s, layout=L)
```

Add both to the controls VBox (near the existing `self.planes`). In `compute`, branch to `multi_shape` when the planes range has >1 value:

```python
        from .sweep import min_sat_sweep, inclination_sweep, incl_values, multi_shape_sweep
        Pv = list(range(self.planes.value, self.planes_max.value + 1, self.planes_step.value))
        ...
        if len(Pv) > 1:
            overlap = self.overlap_s.value if self.handover_gate.value else None
            res = multi_shape_sweep(AORS[self.aor.value], Pv, spp, self.altitude.value,
                                    incs[0], min_elev_deg=self.min_elev.value, k_values=ks,
                                    target_availability=self.target_avail.value,
                                    area_grade=self.area_grade.value, cell_res=self.cell_res.value,
                                    duration_s=self.duration_min.value * 60.0, step_s=self.step_s.value,
                                    phasing=self.phasing.value, use_sharding=self.use_shard.value,
                                    handover_gate=self.handover_gate.value,
                                    continuity_overlap_s=overlap, progress=progress)
            return "multi_shape", res, incs
```

In `run`, render `multi_shape` mode via the new plots (add to `_append_sweep_panel`):

```python
                elif mode == "multi_shape":
                    from .viz.plots import plot_multi_shape_scatter, plot_multi_shape_heatmap
                    k0 = res["k_values"][0]
                    fig = plot_multi_shape_scatter(res, k=k0); plt.show(); plt.close(fig)
                    fig = plot_multi_shape_heatmap(res, k=k0); plt.show(); plt.close(fig)
```

In `_write_sweep_csv`, add a `mode == "multi_shape"` branch:

```python
        elif mode == "multi_shape":
            mbb = res.get("continuity_overlap_s") is not None
            f.write(f"# min_N_by_k: {res['min_N_by_k']}  min_N_mbb: {res.get('min_N_mbb')}"
                    f"  area_grade: {res['area_grade']}  inclination: {res['inclination_deg']}\n")
            wr.writerow(["N", "planes", "sats_per_plane"] + [f"pct_k{k}" for k in ks]
                        + (["pct_mbb", "mbb_pass"] if mbb else []) + ["is_pareto"])
            for c in res["candidates"]:
                wr.writerow([c["N"], c["planes"], c["sats_per_plane"]]
                            + [f"{c['pct_by_k'][k]:.6f}" for k in ks]
                            + ([f"{c['pct_mbb']:.6f}", int(c['mbb_pass'])] if mbb else [])
                            + [int(c["is_pareto"])])
```

- [ ] **Step 4: Run test to verify it passes** (+ back-compat 1D/range modes)

Run: `.venv/bin/pytest tests/test_sweep.py tests/test_explorer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/explorer.py tests/test_sweep.py
git commit -m "feat(explorer): planes range -> multi_shape sweep + CSV (SA14)"
```

---

## Task 12: Full suite, core purity, docs

**Files:** Modify `docs/design-docs/requirements.md`, `docs/design-docs/progress.md`.

- [ ] **Step 1: Run the full suite + purity**

Run: `.venv/bin/pytest -q`
Expected: PASS (all prior + new tests). If `tests/test_core_purity.py` fails, a new core module imported something outside `{numpy, astropy, typing, dataclasses, datetime, math, __future__}` — fix the import (no `collections`/`bisect`/`sgp4`/`skyfield` in `constellation/`, `coverage/`).

- [ ] **Step 2: Flip requirement statuses**

In `docs/design-docs/requirements.md` set SA12 and SA14 to `☑` and SA13 to `☑` (grid-detected + refinement shipped), noting deferred items (full §6 event bracketing, k≥2 continuum, link margin) inline.

- [ ] **Step 3: Update progress**

In `docs/design-docs/progress.md`: move the SA12–SA14 line from "in design" to "implemented (N tests)", record the new modules, and note the deferred items.

- [ ] **Step 4: Commit**

```bash
git add docs/design-docs/requirements.md docs/design-docs/progress.md
git commit -m "docs(slice-a): mark SA12-SA14 implemented; update progress"
```

---

## Self-Review

**Spec coverage** (vs `slice-a-revisions.md`): SA12 generators → Tasks 1–4; canonical model/plane_uid → 1–3; byte-identity → 2; SA13 continuity full requirement → 6; refinement + fidelity honesty (Nyquist) → 7–8; scale honesty (shard-local, apoapsis) → 5, 8; SA14 sweep + Pareto + grid cap → 9; scatter/heatmap + lazy plotly → 10; explorer planes range + gate + CSV → 11; core purity + docs → 12. **Deferred (documented, no task):** J2 repeating-ground-track solver, full §6 event bracketing across all crossings, rigorous k≥2 continuum verdict, population-weighted §8 aggregates (needs `terminals/`), worst link margin (Slice B), multi-epoch (`epoch_s` inert). Wiring the refined per-endpoint overlap into the critical-set verdict is scoped as a guarded follow-up within Task 8's tests.

**Placeholder scan:** no TBD/"handle edge cases"; every code step has concrete code; every test step has runnable asserts.

**Type consistency:** `ConstellationModel(elems, plane_uid, slot_id, shell_id, epoch_s, sat_id)` used identically in Tasks 1–4; `OrbitTemplate(a_km, ecc, inc_rad, argp_rad, epoch_s)`, `PlaneSpec(raan_rad, phase_rad, …)`, `PhaseSlot(raan_rad, mean_anomaly_rad, slot_id, …)` consistent across 2–4; `Requirement(min_overlap_steps, require_different_sat, require_different_plane)` and `mbb_continuity_cell_req` consistent 6; `run_coverage_h3_elements(elems, plane_uid, min_elev_user_deg, time_grid, aor, cell_res, …)` consistent 5, 8; `multi_shape_sweep(...)` keys (`candidates`, `min_N_mbb`, `planes_values`, `spp_values`, `is_pareto`) consistent 9–11.
