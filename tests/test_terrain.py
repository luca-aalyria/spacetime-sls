import matplotlib
matplotlib.use("Agg")
import numpy as np
from datetime import datetime, timezone
from ngso_sls.geometry.frames import geodetic_to_ecef, enu_up, enu_east, enu_north
from ngso_sls.geometry.access import az_el_deg
from ngso_sls.terrain import synthetic_ridge_dem, horizon_mask_from_dem
from ngso_sls.constants import RE_EQ


def test_az_el_overhead_and_due_east_horizon():
    cell = geodetic_to_ecef(0.0, 0.0)[None, :]
    up, e, n = enu_up(0, 0)[None, :], enu_east(0, 0)[None, :], enu_north(0, 0)[None, :]
    el, az = az_el_deg(cell, e, n, up, np.array([[[RE_EQ + 650, 0.0, 0.0]]]))  # straight up
    assert abs(el[0, 0, 0] - 90.0) < 1e-6
    y = np.sqrt((RE_EQ + 650.0) ** 2 - RE_EQ ** 2)                    # on the horizon, due east
    el2, az2 = az_el_deg(cell, e, n, up, np.array([[[RE_EQ, y, 0.0]]]))
    assert abs(el2[0, 0, 0]) < 1e-6 and abs(az2[0, 0, 0] - 90.0) < 1e-3


def test_horizon_mask_is_directional():
    bbox = {"lat_min": 27, "lat_max": 30, "lon_min": 78, "lon_max": 82}
    dem = synthetic_ridge_dem(bbox, ridge_lat=29.0, height_m=5000.0, width_deg=0.2, res_deg=0.25)
    # a cell ~0.5° (~55 km) south of the ridge, looking north into it
    masks = horizon_mask_from_dem(*dem, np.array([28.5]), np.array([80.0]), n_bins=8, radius_km=200)
    north, south = masks[0, 0], masks[0, 4]      # bin 0 ~ due north, bin 4 ~ due south
    assert north > 3.0                            # nearby ridge raises the northern horizon
    assert north > south + 2.0                    # and it is directional (south ~ clear)


def _india_sim():
    from ngso_sls.presets import jio_constellation
    from ngso_sls.config import TimeGrid, SimConfig
    return SimConfig(jio_constellation(),
                     TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0), k_coverage=1)


def test_terrain_masking_integration_reduces_visibility():
    """A uniform 30° horizon mask (> the 25° min-elev) must remove low-elevation satellites."""
    from ngso_sls.pipeline import run_coverage_h3
    aor = {"bbox": {"lat_min": 26, "lat_max": 30, "lon_min": 78, "lon_max": 82}}
    sim = _india_sim()
    base = run_coverage_h3(sim, aor, cell_res=3, shard_res=1, chunk_steps=10)
    terr = run_coverage_h3(sim, aor, cell_res=3, shard_res=1, chunk_steps=10,
                           terrain=lambda clat, clon: np.full((clat.size, 12), 30.0))
    assert base["cells"] == terr["cells"]
    assert np.all(terr["sats_in_view_mean"] <= base["sats_in_view_mean"] + 1e-9)
    assert terr["sats_in_view_mean"].mean() < base["sats_in_view_mean"].mean()  # 30° cutoff drops sats


def test_dem_terrain_path_never_adds_satellites():
    """The DEM skyline path runs and can only raise the horizon (never increases visibility)."""
    from ngso_sls.pipeline import run_coverage_h3
    aor = {"bbox": {"lat_min": 26, "lat_max": 30, "lon_min": 78, "lon_max": 82}}
    sim = _india_sim()
    base = run_coverage_h3(sim, aor, cell_res=3, shard_res=1, chunk_steps=10)
    dem = synthetic_ridge_dem(aor["bbox"], ridge_lat=30.0, height_m=6000.0, width_deg=0.3, res_deg=0.25)
    terr = run_coverage_h3(sim, aor, cell_res=3, shard_res=1, chunk_steps=10,
                           terrain=lambda clat, clon: horizon_mask_from_dem(*dem, clat, clon, n_bins=36, radius_km=250))
    assert np.all(terr["sats_in_view_mean"] <= base["sats_in_view_mean"] + 1e-9)
