import numpy as np
from ngso_sls.grids.aor import latlon_grid, INDIA_AOR


def test_latlon_grid_counts_and_bounds():
    lat, lon = latlon_grid(0.0, 2.0, 0.0, 2.0, 1.0)
    assert lat.shape == lon.shape == (9,)  # 3x3
    assert lat.min() == 0.0 and lat.max() == 2.0


def test_india_aor_keys():
    assert set(INDIA_AOR) == {"lat_min", "lat_max", "lon_min", "lon_max"}
