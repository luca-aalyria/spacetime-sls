import numpy as np


def availability(n_in_view: np.ndarray, k: int = 1) -> np.ndarray:
    """Fraction of timesteps with >= k sats in view, per cell.
    Integer-count form (deterministic, no float drift)."""
    serviceable = (n_in_view >= k)
    return serviceable.sum(axis=1) / n_in_view.shape[1]
