import numpy as np

INDIA_AOR = {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}


def latlon_grid(lat_min, lat_max, lon_min, lon_max, step_deg):
    """Flat (lat, lon) arrays for a regular lat/lon grid over a bbox."""
    lats = np.arange(lat_min, lat_max + 1e-9, step_deg)
    lons = np.arange(lon_min, lon_max + 1e-9, step_deg)
    lon_g, lat_g = np.meshgrid(lons, lats)
    return lat_g.ravel(), lon_g.ravel()
