"""Canonical constellation representation + generators (Slice-A revisions SA12).

`ConstellationModel` is a Struct-of-Arrays: the (n_sat,6) `elems` array is THE compute contract
consumed by the propagator (kepler_j2.py); parallel metadata arrays carry per-satellite plane /
slot / shell identity used only by reporting and the handover different-plane rule. Generators
(Walker, explicit asymmetric planes, phase-slot/lattice) all emit this one type; propagation and
coverage never depend on which generator produced it. Pure NumPy — safe for the core."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
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
