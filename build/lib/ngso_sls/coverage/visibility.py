import numpy as np


def max_elev_and_count(elev_deg: np.ndarray, min_elev_deg: float):
    """elev_deg (n_cell,n_time,n_sat) ->
    (max_elev (n_cell,n_time), n_in_view (n_cell,n_time))."""
    max_elev = np.nanmax(elev_deg, axis=-1)
    n_in_view = np.sum(elev_deg >= min_elev_deg, axis=-1)
    return max_elev, n_in_view
