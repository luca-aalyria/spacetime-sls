import numpy as np
import h3
from ngso_sls.grids.h3_grid import h3_cells_for_bbox, cell_circumradius_deg
from ngso_sls.grids.aor import INDIA_AOR


def test_h3_cells_over_india():
    cells, lat, lon = h3_cells_for_bbox(**INDIA_AOR, res=3)
    assert len(cells) > 0
    assert len(cells) == len(set(cells))  # unique
    assert cells == sorted(cells)         # canonical order
    # centroids fall within the bbox (centroid-containment mode)
    assert lat.min() >= INDIA_AOR["lat_min"] and lat.max() <= INDIA_AOR["lat_max"]
    assert lon.min() >= INDIA_AOR["lon_min"] and lon.max() <= INDIA_AOR["lon_max"]
    # all are resolution-3 cells
    assert all(h3.get_resolution(c) == 3 for c in cells)


def test_circumradius_positive_and_shrinks_with_res():
    assert cell_circumradius_deg(3) > cell_circumradius_deg(5) > 0
