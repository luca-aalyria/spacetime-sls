from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import numpy as np

from .constellation.model import (ConstellationModel, OrbitTemplate, PlaneSpec, PhaseSlot,
                                  walker_model, explicit_planes_model, phase_slot_model)


@dataclass(frozen=True)
class Shell:
    shell_id: str
    walker_T: int
    walker_P: int
    walker_F: int
    altitude_km: float
    inclination_deg: float
    raan0_deg: float = 0.0
    phase0_deg: float = 0.0
    ecc: float = 0.0
    arg_perigee_deg: float = 0.0
    min_elev_user_deg: float = 25.0
    min_elev_feeder_deg: float = 30.0


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


@dataclass(frozen=True)
class Constellation:
    shells: tuple  # tuple[Shell | GeneralizedShell, ...]


@dataclass(frozen=True)
class TimeGrid:
    epoch_utc: datetime
    duration_s: float
    step_s: float = 10.0
    quantum_width_s: float = 10.0

    def times_s(self) -> np.ndarray:
        return np.arange(0.0, self.duration_s, self.step_s)


@dataclass(frozen=True)
class SimConfig:
    constellation: Constellation
    time_grid: TimeGrid
    seed: int = 0
    target_availability: float | None = None
    k_coverage: int = 2  # default: >=2 sats in view (supports inter-satellite handover)
    cell_layout: str = "UNSPEC"  # EFC|QEFC|EMC|UNSPEC — inert metadata (SA8)
    # --- handover continuity (SA13); all off/permissive by default so existing callers are unaffected
    min_handover_overlap_s: float = 0.0
    max_buffered_gap_s: float = 0.0
    min_target_dwell_s: float = 0.0
    max_handover_rate_hz: float = float("inf")
    require_different_plane: bool = False
    require_different_sat: bool = True
    permit_buffered_break_before_make: bool = False
    make_before_break_gate: bool = False


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
