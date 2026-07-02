"""Bundled low-res (Natural Earth 110m) country geometry: polygons per country name.

Used to (a) draw country borders under coverage maps and (b) fill H3 cells to a country's
shape. Offline, no downloads. Not part of the numerical core."""
import json
from importlib.resources import files

_COUNTRIES = None
_BORDER_RINGS = None


def _load():
    global _COUNTRIES
    if _COUNTRIES is None:
        with files("ngso_sls.data").joinpath("countries.json").open("r") as f:
            _COUNTRIES = json.load(f)["countries"]
    return _COUNTRIES


def country_polygons(name):
    """Return a country's polygons: list[polygon], polygon = list[ring], ring = [[lon,lat],...]
    (ring 0 is the exterior, any others are holes)."""
    data = _load()
    if name not in data:
        raise KeyError(f"country '{name}' not in bundled data (have {len(data)} countries)")
    return data[name]


def all_border_rings():
    """All country border rings ([[lon,lat],...]) for drawing context outlines."""
    global _BORDER_RINGS
    if _BORDER_RINGS is None:
        rings = []
        for polys in _load().values():
            for poly in polys:
                rings.extend(poly)
        _BORDER_RINGS = rings
    return _BORDER_RINGS
