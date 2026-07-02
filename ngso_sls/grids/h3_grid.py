import numpy as np
import h3
from ..geodata import country_polygons


def _centers(cells):
    centers = [h3.cell_to_latlng(c) for c in cells]
    lat = np.array([c[0] for c in centers], dtype=float)
    lon = np.array([c[1] for c in centers], dtype=float)
    return lat, lon


def h3_cells_for_bbox(lat_min, lat_max, lon_min, lon_max, res):
    """H3 cells whose centroid lies in the bbox, at resolution `res`.

    Returns (cells: list[str] sorted, lat: np.ndarray, lon: np.ndarray) — cell ids in a
    canonical (sorted) order plus their center latitudes/longitudes (deg)."""
    poly = h3.LatLngPoly(
        [(lat_min, lon_min), (lat_min, lon_max), (lat_max, lon_max), (lat_max, lon_min)]
    )
    cells = sorted(h3.h3shape_to_cells(poly, res))
    lat, lon = _centers(cells)
    return cells, lat, lon


def h3_cells_for_country(name, res, bbox=None):
    """H3 cells filling a country's shape (centroid-in-polygon), optionally clipped to a bbox.
    `bbox` (a {lat_min,...} dict) drops far-flung parts (e.g. Alaska/Hawaii for CONUS)."""
    cells = set()
    for poly in country_polygons(name):                 # poly = [exterior_ring, *holes]
        rings = [[(lat, lng) for (lng, lat) in ring] for ring in poly]  # h3 wants (lat,lng)
        shape = h3.LatLngPoly(rings[0], *rings[1:])
        cells.update(h3.h3shape_to_cells(shape, res))
    cells = sorted(cells)
    lat, lon = _centers(cells)
    if bbox is not None and cells:
        keep = ((lat >= bbox["lat_min"]) & (lat <= bbox["lat_max"])
                & (lon >= bbox["lon_min"]) & (lon <= bbox["lon_max"]))
        cells = [c for c, k in zip(cells, keep) if k]
        lat, lon = lat[keep], lon[keep]
    return cells, lat, lon


def h3_cells_for_aor(spec, res):
    """Resolve an AOR spec to H3 cells. Uses the country shape when `spec['country']` is set,
    otherwise fills the bounding box. Accepts a raw {lat_min,...} box for back-compat."""
    if isinstance(spec, dict) and "country" in spec:
        return h3_cells_for_country(spec["country"], res, spec.get("bbox"))
    b = spec["bbox"] if "bbox" in spec else spec
    return h3_cells_for_bbox(b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"], res)


def cell_circumradius_deg(res):
    """Approximate H3 cell circumradius in degrees of arc (edge length ~ circumradius)."""
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    return edge_km / 111.195  # km per degree of arc
