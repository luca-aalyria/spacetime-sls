import numpy as np

# An AOR spec has a bounding box, and optionally a `country` name — when a country is given,
# H3 cells are filled to the country's shape (not the box); the box just bounds/clips it.
INDIA_AOR = {"country": "India",
             "bbox": {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}}
CONUS_AOR = {"country": "United States of America",
             "bbox": {"lat_min": 24.0, "lat_max": 50.0, "lon_min": -125.0, "lon_max": -66.0}}
EUROPE_AOR = {"bbox": {"lat_min": 35.0, "lat_max": 60.0, "lon_min": -11.0, "lon_max": 30.0}}
GLOBAL_AOR = {"bbox": {"lat_min": -85.0, "lat_max": 85.0, "lon_min": -180.0, "lon_max": 180.0}}

# Named registry for UI dropdowns.
AORS = {"India": INDIA_AOR, "CONUS": CONUS_AOR, "Europe": EUROPE_AOR, "Global": GLOBAL_AOR}


def aor_bbox(spec: dict) -> dict:
    """Return the bounding-box dict for an AOR spec (spec['bbox'], or spec itself if it is a
    raw {lat_min,...} box)."""
    return spec["bbox"] if "bbox" in spec else spec


def latlon_grid(lat_min, lat_max, lon_min, lon_max, step_deg):
    """Flat (lat, lon) arrays for a regular lat/lon grid over a bbox."""
    lats = np.arange(lat_min, lat_max + 1e-9, step_deg)
    lons = np.arange(lon_min, lon_max + 1e-9, step_deg)
    lon_g, lat_g = np.meshgrid(lons, lats)
    return lat_g.ravel(), lon_g.ravel()
