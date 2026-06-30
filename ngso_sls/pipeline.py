import numpy as np
from .config import SimConfig
from .constellation.walker import walker_elements
from .propagation.kepler_j2 import KeplerJ2Propagator
from .geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from .geometry.access import elevation_deg
from .grids.aor import latlon_grid
from .coverage.visibility import max_elev_and_count
from .coverage.availability import availability


def run_coverage(sim: SimConfig, aor: dict, grid_step_deg: float, propagator=None) -> dict:
    """End-to-end Slice-A MVP coverage run (global, sharding off).

    Returns dict with lat, lon, availability (per cell), and min_elev_deg.
    """
    propagator = propagator or KeplerJ2Propagator()
    elems = np.vstack([walker_elements(s) for s in sim.constellation.shells])
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    times = sim.time_grid.times_s()
    r_eci = propagator.propagate(elems, times)              # (n_sat,n_time,3)
    gmst = gmst_rad(sim.time_grid.epoch_utc, times)         # (n_time,)
    r_ecef = eci_to_ecef(r_eci, gmst)
    lat, lon = latlon_grid(aor["lat_min"], aor["lat_max"], aor["lon_min"], aor["lon_max"], grid_step_deg)
    cell_ecef = geodetic_to_ecef(lat, lon)                  # (n_cell,3)
    cell_up = enu_up(lat, lon)
    elev = elevation_deg(cell_ecef, cell_up, r_ecef)        # (n_cell,n_time,n_sat)
    _, n_in_view = max_elev_and_count(elev, min_elev)
    avail = availability(n_in_view, k=sim.k_coverage)
    return {"lat": lat, "lon": lon, "availability": avail, "min_elev_deg": min_elev}
