from typing import Protocol, runtime_checkable
import numpy as np


@runtime_checkable
class Propagator(Protocol):
    def propagate(self, elements: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        """elements (n_sat,6) [a,e,i,raan,argp,M0]; times_s (n_time,)
        -> (n_sat,n_time,3) ECI position, km."""
        ...
