import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import Shell, Constellation, TimeGrid
from ngso_sls.constellation.walker import walker_elements
from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator
from ngso_sls.geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from ngso_sls.geometry.access import elevation_deg
from ngso_sls.grids.h3_grid import h3_cells_for_bbox, cell_circumradius_deg
from ngso_sls.coverage.prefilter import (
    cap_half_angle_deg,
    ecef_to_subpoint_latlon,
    relevant_sat_mask,
    conservative_dilation_deg,
)


def test_cap_half_angle_known_value():
    # 650 km, 25 deg user elevation -> lambda ~ 9.674 deg
    assert abs(cap_half_angle_deg(650.0, 25.0) - 9.674) < 0.02


def test_subpoint_equator():
    r = np.array([[[7000.0, 0.0, 0.0]]])  # over (0N, 0E)
    lat, lon = ecef_to_subpoint_latlon(r)
    assert abs(lat[0, 0]) < 1e-9 and abs(lon[0, 0]) < 1e-9


def test_prefilter_is_conservative_superset_of_true_visibility():
    """The kept set must include every satellite ever genuinely in view of a shard cell."""
    shell = Shell("p", 120, 12, 1, 650.0, 53.0)
    el = walker_elements(shell)
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=600.0, step_s=60.0)
    times = tg.times_s()
    prop = KeplerJ2Propagator()
    r_eci = prop.propagate(el, times)
    gm = gmst_rad(tg.epoch_utc, times)
    r_ecef = eci_to_ecef(r_eci, gm)

    # a small shard: a handful of H3 cells over central India
    cells, clat, clon = h3_cells_for_bbox(18.0, 26.0, 76.0, 84.0, res=3)
    cell_ecef = geodetic_to_ecef(clat, clon)
    cell_up = enu_up(clat, clon)

    # ground truth: satellites in view (>=25 deg) of ANY shard cell at ANY time
    elev = elevation_deg(cell_ecef, cell_up, r_ecef)   # (n_cell,n_time,n_sat)
    truly_in_view = (elev >= 25.0).any(axis=(0, 1))    # (n_sat,)

    # pre-filter mask
    sub_lat, sub_lon = ecef_to_subpoint_latlon(r_ecef)
    dil = conservative_dilation_deg(650.0, 25.0, cell_circumradius_deg(3), step_s=60.0)
    mask = relevant_sat_mask(sub_lat, sub_lon, clat, clon, dil)

    # CONSERVATIVE: every truly-in-view sat is kept (no false negatives)
    assert np.all(mask[truly_in_view]), "pre-filter dropped a genuinely in-view satellite"
    # and it actually prunes something (not trivially keeping all)
    assert mask.sum() < el.shape[0]
