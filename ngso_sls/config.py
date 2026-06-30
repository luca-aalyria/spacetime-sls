from dataclasses import dataclass
from datetime import datetime
import numpy as np


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
class Constellation:
    shells: tuple[Shell, ...]


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
    k_coverage: int = 1
    cell_layout: str = "UNSPEC"  # EFC|QEFC|EMC|UNSPEC — inert metadata (SA8)
