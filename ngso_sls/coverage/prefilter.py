import numpy as np
from ..constants import MU_EARTH, RE_EQ
from ..grids.h3_grid import cell_circumradius_deg

# Geocentric-vs-geodetic latitude differs by up to ~0.19deg; absorb it (plus rounding) here.
_SAFETY_DEG = 0.30


def cap_half_angle_deg(alt_km: float, min_elev_deg: float) -> float:
    """Earth-central half-angle lambda of the coverage cap for a satellite at altitude
    `alt_km` and ground min-elevation `min_elev_deg`:
        sin(eta) = (Re/(Re+h)) cos(eps);  lambda = 90 - eps - eta."""
    eps = np.radians(min_elev_deg)
    eta = np.arcsin((RE_EQ / (RE_EQ + alt_km)) * np.cos(eps))
    return 90.0 - min_elev_deg - np.degrees(eta)


def ground_speed_kms(alt_km: float) -> float:
    """Sub-satellite ground-track speed (km/s) for a circular orbit at `alt_km`."""
    a = RE_EQ + alt_km
    v = np.sqrt(MU_EARTH / a)            # orbital speed
    return v * RE_EQ / a                 # projected onto the ground


def conservative_dilation_deg(alt_km, min_elev_deg, cell_res, step_s) -> float:
    """Dilation radius (deg of arc) that makes the pre-filter a guaranteed superset of true
    visibility: cap half-angle + cell circumradius + half-step motion halo + safety."""
    lam = cap_half_angle_deg(alt_km, min_elev_deg)
    r_cell = cell_circumradius_deg(cell_res)
    halo = (ground_speed_kms(alt_km) * step_s / 2.0) / 111.195
    return lam + r_cell + halo + _SAFETY_DEG


def ecef_to_subpoint_latlon(r_ecef: np.ndarray):
    """ECEF (...,3) -> sub-satellite (lat_deg, lon_deg) (geocentric)."""
    x, y, z = r_ecef[..., 0], r_ecef[..., 1], r_ecef[..., 2]
    rad = np.sqrt(x * x + y * y + z * z)
    lat = np.degrees(np.arcsin(np.clip(z / rad, -1.0, 1.0)))
    lon = np.degrees(np.arctan2(y, x))
    return lat, lon


def relevant_sat_mask(sub_lat, sub_lon, cell_lat, cell_lon, dilation_deg) -> np.ndarray:
    """Conservative satellite relevance mask for a shard.

    sub_lat/sub_lon: (n_sat, n_time) sub-satellite tracks.
    cell_lat/cell_lon: (n_cell,) shard cell centers.
    Keep sat iff its sub-point is within `dilation_deg` (great-circle) of some shard cell at
    some time. Returns bool (n_sat,). Every test is a relaxation of true visibility -> the
    kept set is a superset of all genuinely in-view satellites (no false negatives)."""
    phis = np.radians(sub_lat)[:, :, None]      # (n_sat,n_time,1)
    lams = np.radians(sub_lon)[:, :, None]
    phic = np.radians(cell_lat)[None, None, :]  # (1,1,n_cell)
    lamc = np.radians(cell_lon)[None, None, :]
    cosd = np.sin(phis) * np.sin(phic) + np.cos(phis) * np.cos(phic) * np.cos(lams - lamc)
    ang = np.degrees(np.arccos(np.clip(cosd, -1.0, 1.0)))   # (n_sat,n_time,n_cell)
    return (ang <= dilation_deg).any(axis=(1, 2))
