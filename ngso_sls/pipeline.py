import numpy as np
from .config import SimConfig
from .constellation.walker import walker_elements
from .propagation.kepler_j2 import KeplerJ2Propagator
from .geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from .geometry.access import elevation_deg
from .grids.aor import latlon_grid, aor_bbox
from .grids.h3_grid import h3_cells_for_aor, cell_circumradius_deg
from .grids.shards import assign_shards
from .coverage.visibility import max_elev_and_count
from .coverage.availability import availability
from .coverage.prefilter import (
    ecef_to_subpoint_latlon,
    relevant_sat_mask,
    conservative_dilation_deg,
)


def run_coverage(sim: SimConfig, aor: dict, grid_step_deg: float, propagator=None) -> dict:
    """MVP coverage on a lat/lon grid (global, single in-memory pass). [Milestone 1]"""
    propagator = propagator or KeplerJ2Propagator()
    elems = np.vstack([walker_elements(s) for s in sim.constellation.shells])
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    times = sim.time_grid.times_s()
    r_eci = propagator.propagate(elems, times)
    gmst = gmst_rad(sim.time_grid.epoch_utc, times)
    r_ecef = eci_to_ecef(r_eci, gmst)
    b = aor_bbox(aor)
    lat, lon = latlon_grid(b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"], grid_step_deg)
    cell_ecef = geodetic_to_ecef(lat, lon)
    cell_up = enu_up(lat, lon)
    elev = elevation_deg(cell_ecef, cell_up, r_ecef)
    _, n_in_view = max_elev_and_count(elev, min_elev)
    avail = availability(n_in_view, k=sim.k_coverage)
    return {"lat": lat, "lon": lon, "availability": avail, "min_elev_deg": min_elev}


def run_coverage_h3(
    sim: SimConfig,
    aor: dict,
    cell_res: int,
    shard_res: int | None = None,
    chunk_steps: int | None = None,
    propagator=None,
    progress=None,
    k_values=None,
) -> dict:
    """Coverage on an H3 grid. [Milestone 3]

    `shard_res=None` -> global single-owner pass (monolithic). Otherwise cells are partitioned
    into single-owner shards via `cell_to_parent(shard_res)`, each shard pre-filters its
    relevant satellites (conservative cap geometry), and time is processed in chunks. Because
    the pre-filter only drops satellites that are never in view of the shard's cells and all
    reductions are integer counts, the sharded result is bit-identical to the monolithic one
    (the `sharded == monolithic` invariant)."""
    propagator = propagator or KeplerJ2Propagator()
    elems = np.vstack([walker_elements(s) for s in sim.constellation.shells])
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    max_alt = max(s.altitude_km for s in sim.constellation.shells)
    times = sim.time_grid.times_s()
    n_time = len(times)

    cells, lat, lon = h3_cells_for_aor(aor, cell_res)
    n_cell = len(cells)
    if n_cell == 0:
        raise ValueError(
            "AOR produced 0 H3 cells at this resolution — increase H3 resolution or check the AOR."
        )

    r_eci = propagator.propagate(elems, times)
    gmst = gmst_rad(sim.time_grid.epoch_utc, times)
    r_ecef = eci_to_ecef(r_eci, gmst)                       # (n_sat,n_time,3)
    cell_ecef = geodetic_to_ecef(lat, lon)
    cell_up = enu_up(lat, lon)

    if shard_res is None:
        shards = {None: np.arange(n_cell)}
        sub_lat = sub_lon = None
        dil = None
    else:
        groups, _ = assign_shards(cells, shard_res)
        shards = {s: np.array(idx) for s, idx in groups.items()}
        sub_lat, sub_lon = ecef_to_subpoint_latlon(r_ecef)
        dil = conservative_dilation_deg(
            max_alt, min_elev, cell_circumradius_deg(cell_res), sim.time_grid.step_s
        )

    chunk = chunk_steps or n_time
    bounds = [(i, min(i + chunk, n_time)) for i in range(0, n_time, chunk)]

    ks = sorted(set(k_values)) if k_values is not None else [sim.k_coverage]
    serviceable = {k: np.zeros(n_cell, dtype=np.int64) for k in ks}  # #timesteps with >=k in view
    sat_sum = np.zeros(n_cell, dtype=np.int64)          # sum over time of sats-in-view per cell
    total_shards = len(shards)
    done_shards = 0
    if progress is not None:
        progress(done_shards, total_shards)             # 0/total (optional UI callback)
    for cidx in shards.values():
        clat, clon = lat[cidx], lon[cidx]
        ce, cu = cell_ecef[cidx], cell_up[cidx]
        if shard_res is None:
            sat_idx = np.arange(elems.shape[0])
        else:
            mask = relevant_sat_mask(sub_lat, sub_lon, clat, clon, dil)
            sat_idx = np.nonzero(mask)[0]
        if sat_idx.size:
            for a, b in bounds:
                re_chunk = r_ecef[sat_idx][:, a:b, :]        # (n_sat_s, n_chunk, 3)
                elev = elevation_deg(ce, cu, re_chunk)       # (n_cellS, n_chunk, n_sat_s)
                nv = (elev >= min_elev).sum(axis=-1)         # (n_cellS, n_chunk)
                for k in ks:
                    serviceable[k][cidx] += (nv >= k).sum(axis=1)
                sat_sum[cidx] += nv.sum(axis=1)
        done_shards += 1
        if progress is not None:
            progress(done_shards, total_shards)

    availability_by_k = {k: serviceable[k] / n_time for k in ks}
    default_k = sim.k_coverage if sim.k_coverage in availability_by_k else ks[0]
    return {
        "cells": cells, "lat": lat, "lon": lon,
        "availability": availability_by_k[default_k],       # back-compat (single-k callers)
        "availability_by_k": availability_by_k,             # {k: per-cell availability}
        "sats_in_view_mean": sat_sum / n_time,
        "min_elev_deg": min_elev,
    }
