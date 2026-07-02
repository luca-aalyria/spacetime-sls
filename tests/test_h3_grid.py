import numpy as np
import h3
from ngso_sls.grids.h3_grid import h3_cells_for_bbox, cell_circumradius_deg
from ngso_sls.grids.aor import INDIA_AOR


def test_h3_cells_over_india():
    b = INDIA_AOR["bbox"]
    cells, lat, lon = h3_cells_for_bbox(**b, res=3)
    assert len(cells) > 0
    assert len(cells) == len(set(cells))  # unique
    assert cells == sorted(cells)         # canonical order
    # centroids fall within the bbox (centroid-containment mode)
    assert lat.min() >= b["lat_min"] and lat.max() <= b["lat_max"]
    assert lon.min() >= b["lon_min"] and lon.max() <= b["lon_max"]
    # all are resolution-3 cells
    assert all(h3.get_resolution(c) == 3 for c in cells)


def test_circumradius_positive_and_shrinks_with_res():
    assert cell_circumradius_deg(3) > cell_circumradius_deg(5) > 0


def test_global_bbox_fill_nonempty():
    from ngso_sls.grids.h3_grid import h3_cells_for_bbox
    from ngso_sls.grids.aor import GLOBAL_AOR
    b = GLOBAL_AOR["bbox"]
    cells, lat, lon = h3_cells_for_bbox(b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"], 2)
    assert len(cells) > 1000                       # full globe at res 2 (~5.8k cells)
    assert lon.min() < -150 and lon.max() > 150    # spans the antimeridian region


def test_country_shape_fill_is_subset_of_bbox():
    from ngso_sls.grids.h3_grid import h3_cells_for_aor, h3_cells_for_bbox
    cells, lat, lon = h3_cells_for_aor(INDIA_AOR, res=3)   # country-shape fill
    assert len(cells) > 0
    b = INDIA_AOR["bbox"]
    bbox_cells, _, _ = h3_cells_for_bbox(b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"], 3)
    # India's shape covers fewer cells than its bounding box (ocean/neighbors excluded)
    assert len(cells) < len(bbox_cells)
    # centers stay within (roughly) the India box
    assert lat.min() > 4 and lat.max() < 40 and lon.min() > 66 and lon.max() < 100
