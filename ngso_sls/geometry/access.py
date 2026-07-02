import numpy as np


def elevation_deg(cell_ecef: np.ndarray, cell_up: np.ndarray, sat_ecef: np.ndarray) -> np.ndarray:
    """cell_ecef (n_cell,3), cell_up (n_cell,3), sat_ecef (n_sat,n_time,3)
    -> elevation in degrees, shape (n_cell, n_time, n_sat)."""
    rho = sat_ecef[None, :, :, :] - cell_ecef[:, None, None, :]  # (n_cell,n_sat,n_time,3)
    rng = np.linalg.norm(rho, axis=-1)                            # (n_cell,n_sat,n_time)
    dot = np.sum(rho * cell_up[:, None, None, :], axis=-1)        # (n_cell,n_sat,n_time)
    el = np.degrees(np.arcsin(np.clip(dot / rng, -1.0, 1.0)))
    return np.moveaxis(el, 1, 2)                                  # (n_cell,n_time,n_sat)


def az_el_deg(cell_ecef, cell_east, cell_north, cell_up, sat_ecef):
    """Topocentric (elevation, azimuth) in degrees, each (n_cell, n_time, n_sat). Azimuth is
    clockwise from north in [0,360). Needs the cell's local ENU basis (east/north/up)."""
    rho = sat_ecef[None, :, :, :] - cell_ecef[:, None, None, :]
    e = np.sum(rho * cell_east[:, None, None, :], axis=-1)
    n = np.sum(rho * cell_north[:, None, None, :], axis=-1)
    u = np.sum(rho * cell_up[:, None, None, :], axis=-1)
    el = np.degrees(np.arctan2(u, np.hypot(e, n)))
    az = np.degrees(np.arctan2(e, n)) % 360.0
    return np.moveaxis(el, 1, 2), np.moveaxis(az, 1, 2)
