import numpy as np
import h3


def h3_cells_for_bbox(lat_min, lat_max, lon_min, lon_max, res):
    """H3 cells whose centroid lies in the bbox, at resolution `res`.

    Returns (cells: list[str] sorted, lat: np.ndarray, lon: np.ndarray) — cell ids in a
    canonical (sorted) order plus their center latitudes/longitudes (deg)."""
    poly = h3.LatLngPoly(
        [(lat_min, lon_min), (lat_min, lon_max), (lat_max, lon_max), (lat_max, lon_min)]
    )
    cells = sorted(h3.h3shape_to_cells(poly, res))
    centers = [h3.cell_to_latlng(c) for c in cells]
    lat = np.array([c[0] for c in centers], dtype=float)
    lon = np.array([c[1] for c in centers], dtype=float)
    return cells, lat, lon


def cell_circumradius_deg(res):
    """Approximate H3 cell circumradius in degrees of arc (edge length ~ circumradius)."""
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    return edge_km / 111.195  # km per degree of arc
