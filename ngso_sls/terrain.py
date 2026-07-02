"""Coarse terrain masking (M9 Tier-2): per-cell azimuth-dependent horizon (skyline) from a DEM.

Mountains raise the local horizon, so a satellite is only usable if its elevation exceeds the
terrain skyline in its azimuth direction. This module computes, for each ground cell, a horizon
mask angle per azimuth bin from a digital elevation model (DEM). The coverage engine then requires
`satellite_elevation >= max(min_elev, terrain_mask[cell, azimuth_bin])`.

A DEM here is (lat_1d[M] ascending, lon_1d[L] ascending in -180..180, elev_2d[M,L] in metres).
Get one via `synthetic_ridge_dem` (demo), a loader (`dem_from_xyz_csv`, `dem_from_geotiff`), or a
runtime fetch (`fetch_dem_erddap` — NOAA ERDDAP ETOPO, no API key, subset to a bounding box).

Public DEM sources (all usable at Colab runtime):
- NOAA ERDDAP ETOPO (no key): griddap CSV/NetCDF, bbox subset, ~1 arc-min. See `fetch_dem_erddap`.
- OpenTopography Global DEM API (free key): demtype SRTMGL3/COP90/ETOPO1, bbox, AAIGrid/GTiff.
  https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south=&north=&west=&east=&outputFormat=AAIGrid&API_Key=KEY
- Copernicus DEM GLO-90 on AWS Open Data (no key): 1°x1° COG tiles, bucket copernicus-dem-90m
  (needs rasterio; best resolution).
"""
import numpy as np

_RE_M = 6371000.0  # mean Earth radius (m) for the curvature drop term


def dem_from_xyz_csv(text):
    """Parse a (latitude, longitude, elevation) CSV into (lat_1d, lon_1d, elev_2d). Skips a
    header row and an optional units row; tolerates ERDDAP griddap CSV. Longitudes >180 are
    wrapped to -180..180."""
    import pandas as pd
    import io
    rows = []
    for line in text.splitlines():
        p = line.split(",")
        if len(p) < 3:
            continue
        try:
            rows.append((float(p[0]), float(p[1]), float(p[2])))
        except ValueError:
            continue  # header / units row
    df = pd.DataFrame(rows, columns=["lat", "lon", "elev"])
    df["lon"] = ((df["lon"] + 180.0) % 360.0) - 180.0
    grid = df.pivot_table(index="lat", columns="lon", values="elev")
    return grid.index.to_numpy(float), grid.columns.to_numpy(float), grid.to_numpy(float)


def dem_from_geotiff(path):
    """Load a single-band GeoTIFF DEM -> (lat_1d ascending, lon_1d ascending -180..180, elev_2d).
    Requires rasterio (`pip install rasterio`)."""
    import rasterio
    with rasterio.open(path) as ds:
        elev = ds.read(1).astype(float)
        h, w = elev.shape
        xs = ds.xy(np.zeros(w), np.arange(w))[0]
        ys = ds.xy(np.arange(h), np.zeros(h))[1]
    lon = ((np.asarray(xs) + 180.0) % 360.0) - 180.0
    lat = np.asarray(ys)
    if lat[0] > lat[-1]:                      # north-up raster -> flip to ascending lat
        lat, elev = lat[::-1], elev[::-1, :]
    order = np.argsort(lon)
    return lat, lon[order], elev[:, order]


_ERDDAP_SERVERS = ["https://coastwatch.pfeg.noaa.gov/erddap",
                   "https://upwell.pfeg.noaa.gov/erddap"]


def fetch_dem_erddap(bbox, servers=None, dataset="etopo180", variable="altitude",
                     pad_deg=1.0, timeout=60):
    """Fetch a DEM for `bbox` from a NOAA ERDDAP griddap dataset (no API key). Returns
    (lat_1d, lon_1d, elev_2d) in metres. `etopo180` is ~1 arc-min global relief on -180..180.
    Tries mirror servers and both latitude orderings; raises if all fail (callers may fall back
    to a synthetic DEM)."""
    import urllib.request
    servers = servers or _ERDDAP_SERVERS
    lo0, lo1 = bbox["lon_min"] - pad_deg, bbox["lon_max"] + pad_deg
    la0, la1 = bbox["lat_min"] - pad_deg, bbox["lat_max"] + pad_deg
    last = None
    for server in servers:
        for a, b in ((la0, la1), (la1, la0)):        # dataset may store lat asc or desc
            url = (f"{server}/griddap/{dataset}.csv?"
                   f"{variable}%5B({a}):({b})%5D%5B({lo0}):({lo1})%5D")
            try:
                with urllib.request.urlopen(url, timeout=timeout) as r:
                    text = r.read().decode("utf-8", "replace")
                lat, lon, elev = dem_from_xyz_csv(text)
                if lat.size and lon.size:
                    return lat, lon, elev
            except Exception as e:  # network / HTTP / parse — try the next combination
                last = e
    raise RuntimeError(f"ETOPO fetch failed from {servers}: {last}")


def fetch_dem_selftest(bbox=None):
    """Quick verification of the ETOPO runtime fetch (run in Colab). Fetches a small tile and
    returns a summary dict; the default bbox (Everest region) should show a high max elevation."""
    b = bbox or {"lat_min": 27.0, "lat_max": 29.0, "lon_min": 85.0, "lon_max": 87.0}
    lat, lon, elev = fetch_dem_erddap(b)
    return {"shape": tuple(elev.shape),
            "lat_range": (float(lat.min()), float(lat.max())),
            "lon_range": (float(lon.min()), float(lon.max())),
            "elev_min_m": float(np.nanmin(elev)), "elev_max_m": float(np.nanmax(elev))}


def synthetic_ridge_dem(bbox, ridge_lat, height_m=5000.0, width_deg=1.5, res_deg=0.25):
    """A demo DEM: a Gaussian mountain ridge along `ridge_lat` over (a padded) `bbox`.
    Returns (lat_1d, lon_1d, elev_2d[m])."""
    lat = np.arange(bbox["lat_min"] - 3, bbox["lat_max"] + 3 + 1e-9, res_deg)
    lon = np.arange(bbox["lon_min"] - 3, bbox["lon_max"] + 3 + 1e-9, res_deg)
    elev = height_m * np.exp(-((lat[:, None] - ridge_lat) / width_deg) ** 2)
    elev = np.repeat(elev, lon.size, axis=1)               # (M, L), ridge runs east-west
    return lat, lon, elev


def horizon_mask_from_dem(dem_lat, dem_lon, dem_elev, cell_lat, cell_lon,
                          n_bins=36, radius_km=400.0):
    """Per-cell azimuth-binned horizon mask (deg), shape (n_cell, n_bins).

    For each cell, look at DEM points within `radius_km`; the terrain elevation angle to a point
    at ground distance d and height Δh (above the cell) is atan((Δh - d²/2R) / d) — the
    d²/2R term is the Earth-curvature drop. The mask for an azimuth bin is the max such angle
    (>= 0). Azimuth bins are clockwise from north; bin b spans [b, b+1) * 360/n_bins degrees.
    """
    dem_lat = np.asarray(dem_lat, float)
    dem_lon = np.asarray(dem_lon, float)
    dem_elev = np.asarray(dem_elev, float)
    cell_lat = np.asarray(cell_lat, float)
    cell_lon = np.asarray(cell_lon, float)
    n_cell = cell_lat.size
    masks = np.zeros((n_cell, n_bins), dtype=float)
    bin_w = 360.0 / n_bins

    dlat = radius_km / 111.0
    for c in range(n_cell):
        clat, clon = cell_lat[c], cell_lon[c]
        dlon = radius_km / max(111.0 * np.cos(np.radians(clat)), 1e-6)
        i0, i1 = np.searchsorted(dem_lat, [clat - dlat, clat + dlat])
        j0, j1 = np.searchsorted(dem_lon, [clon - dlon, clon + dlon])
        if i1 <= i0 or j1 <= j0:
            continue
        plat = dem_lat[i0:i1]
        plon = dem_lon[j0:j1]
        PLON, PLAT = np.meshgrid(plon, plat)              # (h, w)
        pelev = dem_elev[i0:i1, j0:j1]
        # cell's own reference elevation (nearest DEM sample)
        ci = int(np.clip(np.searchsorted(dem_lat, clat), 0, dem_lat.size - 1))
        cj = int(np.clip(np.searchsorted(dem_lon, clon), 0, dem_lon.size - 1))
        cell_elev = dem_elev[ci, cj]
        # great-circle distance (haversine) and bearing from cell to each point
        phi1, lam1 = np.radians(clat), np.radians(clon)
        phi2, lam2 = np.radians(PLAT), np.radians(PLON)
        dphi, dlam = phi2 - phi1, lam2 - lam1
        a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
        d_m = 2 * _RE_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        within = (d_m > 1.0) & (d_m <= radius_km * 1000.0)
        if not within.any():
            continue
        d = d_m[within]
        dh = pelev[within] - cell_elev
        ang = np.degrees(np.arctan2(dh - d * d / (2 * _RE_M), d))   # curvature-corrected
        y = np.sin(dlam) * np.cos(phi2)
        x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlam)
        az = (np.degrees(np.arctan2(y, x)) % 360.0)[within]
        b = np.clip((az / bin_w).astype(int), 0, n_bins - 1)
        pos = ang > 0
        np.maximum.at(masks[c], b[pos], ang[pos])
    return masks


def cell_horizon_masks(cell_lat, cell_lon, aor_bbox, dem=None, ridge_lat=None,
                       n_bins=36, radius_km=400.0):
    """Convenience: build per-cell horizon masks. If `dem` (lat,lon,elev) is given, use it;
    otherwise generate a demonstration Himalaya-like ridge north of the AOR."""
    if dem is None:
        rl = ridge_lat if ridge_lat is not None else (aor_bbox["lat_max"] - 1.0)
        dem = synthetic_ridge_dem(aor_bbox, ridge_lat=rl)
    dlat, dlon, delev = dem
    return horizon_mask_from_dem(dlat, dlon, delev, cell_lat, cell_lon,
                                 n_bins=n_bins, radius_km=radius_km)
