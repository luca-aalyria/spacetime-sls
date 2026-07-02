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
