import numpy as np
from astropy.time import Time
from astropy.utils import iers
import astropy.units as u
from ..constants import RE_EQ, WGS84_E2

# Use bundled IERS data (sub-arcsec UT1/polar-motion effects are negligible for
# coverage geometry); avoids a network fetch so it runs offline and fast.
iers.conf.auto_download = False


def gmst_rad(epoch_utc, times_s) -> np.ndarray:
    """Greenwich Mean Sidereal Time (rad) at epoch + times_s (vectorized)."""
    t = Time(epoch_utc, scale="utc") + np.asarray(times_s) * u.s
    return np.asarray(t.sidereal_time("mean", "greenwich").to_value(u.rad)) % (2 * np.pi)


def eci_to_ecef(r_eci: np.ndarray, gmst: np.ndarray) -> np.ndarray:
    """Rotate ECI->ECEF about z by GMST. r_eci (...,n_time,3), gmst (n_time,)."""
    cg = np.cos(gmst)
    sg = np.sin(gmst)
    x, y, z = r_eci[..., 0], r_eci[..., 1], r_eci[..., 2]
    xe = cg * x + sg * y
    ye = -sg * x + cg * y
    return np.stack([xe, ye, z], axis=-1)


def geodetic_to_ecef(lat_deg, lon_deg, h_m=0.0) -> np.ndarray:
    """WGS84 geodetic -> ECEF (km). Returns (...,3)."""
    lat = np.radians(np.asarray(lat_deg, float))
    lon = np.radians(np.asarray(lon_deg, float))
    h = np.asarray(h_m, float) / 1000.0
    N = RE_EQ / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    x = (N + h) * np.cos(lat) * np.cos(lon)
    y = (N + h) * np.cos(lat) * np.sin(lon)
    z = (N * (1 - WGS84_E2) + h) * np.sin(lat)
    return np.stack([x, y, z], axis=-1)


def enu_up(lat_deg, lon_deg) -> np.ndarray:
    """Local geodetic up (ellipsoid normal) unit vector in ECEF. Returns (...,3)."""
    lat = np.radians(np.asarray(lat_deg, float))
    lon = np.radians(np.asarray(lon_deg, float))
    return np.stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=-1
    )


def enu_east(lat_deg, lon_deg) -> np.ndarray:
    """Local east unit vector in ECEF. Returns (...,3)."""
    lon = np.radians(np.asarray(lon_deg, float))
    z = np.zeros_like(lon)
    return np.stack([-np.sin(lon), np.cos(lon), z], axis=-1)


def enu_north(lat_deg, lon_deg) -> np.ndarray:
    """Local north unit vector in ECEF. Returns (...,3)."""
    lat = np.radians(np.asarray(lat_deg, float))
    lon = np.radians(np.asarray(lon_deg, float))
    return np.stack(
        [-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)], axis=-1
    )
