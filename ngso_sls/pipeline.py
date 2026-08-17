import numpy as np
from .config import SimConfig
from .constellation.walker import walker_elements
from .constants import RE_EQ
from .propagation.kepler_j2 import KeplerJ2Propagator
from .geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up, enu_east, enu_north
from .geometry.access import elevation_deg, az_el_deg
from .grids.aor import latlon_grid, aor_bbox
from .grids.h3_grid import h3_cells_for_aor, cell_circumradius_deg
from .grids.shards import assign_shards
from .coverage.visibility import max_elev_and_count
from .coverage.availability import availability
from .coverage.continuity import continuity_map, Requirement
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
    workers: int | None = None,
    propagator=None,
    progress=None,
    k_values=None,
    terrain=None,
    continuity_overlap_s: float | None = None,
    require_different_sat: bool = True,
    require_different_plane: bool = False,
) -> dict:
    """Coverage on an H3 grid. [Milestone 3]

    `shard_res=None` -> global single-owner pass (monolithic). Otherwise cells are partitioned
    into single-owner shards via `cell_to_parent(shard_res)`, each shard pre-filters its
    relevant satellites (conservative cap geometry), and time is processed in chunks. Because
    the pre-filter only drops satellites that are never in view of the shard's cells and all
    reductions are integer counts, the sharded result is bit-identical to the monolithic one
    (the `sharded == monolithic` invariant)."""
    from .config import constellation_model
    model = constellation_model(sim.constellation)
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    return run_coverage_h3_elements(
        model.elems, model.plane_uid, min_elev, sim.time_grid, aor, cell_res,
        shard_res=shard_res, chunk_steps=chunk_steps, workers=workers,
        propagator=propagator, progress=progress,
        k_values=(k_values if k_values is not None else [sim.k_coverage]), terrain=terrain,
        continuity_overlap_s=continuity_overlap_s, require_different_sat=require_different_sat,
        require_different_plane=require_different_plane,
        default_k=sim.k_coverage)


def run_coverage_h3_elements(
    elems: np.ndarray,
    plane_uid: np.ndarray,
    min_elev_user_deg: float,
    time_grid,
    aor: dict,
    cell_res: int,
    shard_res: int | None = None,
    chunk_steps: int | None = None,
    workers: int | None = None,
    propagator=None,
    progress=None,
    k_values=None,
    terrain=None,
    continuity_overlap_s: float | None = None,
    require_different_sat: bool = True,
    require_different_plane: bool = False,
    default_k=None,
) -> dict:
    """Coverage on an H3 grid given pre-assembled element arrays.

    This is the core compute kernel; `run_coverage_h3` assembles elems/plane_uid from a SimConfig
    and delegates here. The `plane_uid` array is consumed by the MBB shard loop when
    `require_different_plane=True` (or when `continuity_overlap_s` is set)."""
    propagator = propagator or KeplerJ2Propagator()
    min_elev = min_elev_user_deg
    max_alt = float((elems[:, 0] * (1.0 + elems[:, 1])).max()) - RE_EQ  # apoapsis
    times = time_grid.times_s()
    n_time = len(times)

    cells, lat, lon = h3_cells_for_aor(aor, cell_res)
    n_cell = len(cells)
    if n_cell == 0:
        raise ValueError(
            "AOR produced 0 H3 cells at this resolution — increase H3 resolution or check the AOR."
        )

    r_eci = propagator.propagate(elems, times)
    gmst = gmst_rad(time_grid.epoch_utc, times)
    r_ecef = eci_to_ecef(r_eci, gmst)                       # (n_sat,n_time,3)
    cell_ecef = geodetic_to_ecef(lat, lon)
    cell_up = enu_up(lat, lon)

    if terrain is not None:                              # per-cell azimuth-binned horizon (deg)
        cell_east, cell_north = enu_east(lat, lon), enu_north(lat, lon)
        terrain_masks = np.asarray(terrain(lat, lon), dtype=float)
        n_bins = terrain_masks.shape[1]
        bin_w = 360.0 / n_bins

    if shard_res is None:
        shards = {None: np.arange(n_cell)}
        sub_lat = sub_lon = None
        dil = None
    else:
        groups, _ = assign_shards(cells, shard_res)
        shards = {s: np.array(idx) for s, idx in groups.items()}
        sub_lat, sub_lon = ecef_to_subpoint_latlon(r_ecef)
        dil = conservative_dilation_deg(
            max_alt, min_elev, cell_circumradius_deg(cell_res), time_grid.step_s
        )

    chunk = chunk_steps or n_time
    bounds = [(i, min(i + chunk, n_time)) for i in range(0, n_time, chunk)]

    if k_values is not None:
        ks = sorted(set(k_values))
    elif default_k is not None:
        ks = [default_k]
    else:
        ks = [1, 2]   # sensible default when neither k_values nor default_k is given
    serviceable = {k: np.zeros(n_cell, dtype=np.int64) for k in ks}  # #timesteps with >=k in view
    sat_sum = np.zeros(n_cell, dtype=np.int64)          # sum over time of sats-in-view per cell

    # Make-before-break (k=1) continuity: opt-in per-cell handover-feasibility analysis.
    do_mbb = continuity_overlap_s is not None
    if do_mbb:
        step = time_grid.step_s
        if continuity_overlap_s > 0 and step > 0.5 * continuity_overlap_s:
            raise ValueError(
                f"step_s ({step}s) too coarse for a {continuity_overlap_s}s overlap gate; "
                f"require step_s <= 0.5*overlap ({0.5 * continuity_overlap_s}s)")
        # Conservative: `ov` shared samples guarantee (ov-1)*step of continuous 2-sat visibility,
        # so require ov >= overlap_s/step + 1 (>=1 shared sample even at overlap_s=0).
        min_overlap_steps = (int(np.ceil(continuity_overlap_s / step)) + 1
                             if continuity_overlap_s > 0 else 1)
        refine_tol_s = min(1.0, step / 10.0)
        mbb_req = Requirement(min_overlap_steps=min_overlap_steps,
                              require_different_sat=require_different_sat,
                              require_different_plane=require_different_plane)
        mbb_feasible = np.zeros(n_cell, dtype=bool)
        mbb_worst_steps = np.full(n_cell, -1, dtype=np.int64)
        mbb_n_handovers = np.full(n_cell, -1, dtype=np.int64)
        # Default = n_time (fully-uncovered) so empty-shard cells match the monolithic result
        # for cells that see no satellites in view (worst_gap = entire window).
        mbb_worst_gap_steps = np.full(n_cell, n_time, dtype=np.int64)

    total_shards = len(shards)
    done_shards = 0
    if progress is not None:
        progress(done_shards, total_shards)             # 0/total (optional UI callback)

    ctx = {"lat": lat, "lon": lon, "cell_ecef": cell_ecef, "cell_up": cell_up,
           "shard_res": shard_res, "elems": elems, "sub_lat": sub_lat, "sub_lon": sub_lon,
           "dil": dil, "terrain_on": terrain is not None, "n_time": n_time, "bounds": bounds,
           "r_ecef": r_ecef, "min_elev": min_elev, "ks": ks, "do_mbb": do_mbb,
           "plane_uid": plane_uid, "require_different_sat": require_different_sat,
           "mbb_req": mbb_req if do_mbb else None,
           "min_overlap_steps": min_overlap_steps if do_mbb else None}
    if terrain is not None:
        ctx.update(cell_east=cell_east, cell_north=cell_north,
                   terrain_masks=terrain_masks, n_bins=n_bins, bin_w=bin_w)

    def _apply(cidx, r):
        if r is not None:
            for k in ks:
                serviceable[k][cidx] += r["serviceable"][k]
            sat_sum[cidx] += r["sat_sum"]
            if do_mbb:
                mbb_feasible[cidx] = r["mbb_feasible"]
                mbb_worst_steps[cidx] = r["worst_overlap_steps"]
                mbb_n_handovers[cidx] = r["n_handovers"]
                mbb_worst_gap_steps[cidx] = r["worst_gap_steps"]

    shard_list = list(shards.values())
    n_workers = min(int(workers or 1), len(shard_list))
    if n_workers > 1 and _FORK_OK:
        # Shards are single-owner and embarrassingly parallel; fork shares the big read-only
        # arrays copy-on-write. Falls back to serial where fork is unavailable.
        import concurrent.futures as _cf
        import multiprocessing as _mp
        global _SHARD_CTX
        _SHARD_CTX = ctx
        try:
            with _cf.ProcessPoolExecutor(max_workers=n_workers,
                                         mp_context=_mp.get_context("fork")) as pool:
                for cidx, r in zip(shard_list,
                                   pool.map(_shard_task, shard_list, chunksize=1)):
                    _apply(cidx, r)
                    done_shards += 1
                    if progress is not None:
                        progress(done_shards, total_shards)
        finally:
            _SHARD_CTX = None
    else:
        for cidx in shard_list:
            _apply(cidx, _compute_shard(ctx, cidx))
            done_shards += 1
            if progress is not None:
                progress(done_shards, total_shards)

    availability_by_k = {k: serviceable[k] / n_time for k in ks}
    _default_k = default_k if (default_k is not None and default_k in availability_by_k) else ks[0]
    out = {
        "cells": cells, "lat": lat, "lon": lon,
        "availability": availability_by_k[_default_k],      # back-compat (single-k callers)
        "availability_by_k": availability_by_k,             # {k: per-cell availability}
        "sats_in_view_mean": sat_sum / n_time,
        "min_elev_deg": min_elev,
    }
    if do_mbb:
        # Guaranteed continuous 2-sat overlap on the best serving path: (steps-1)*step seconds
        # (-1 where n/a: no handover needed, or infeasible).
        worst_s = np.where(mbb_worst_steps >= 1, (mbb_worst_steps - 1) * step, -1.0)
        out.update({
            "mbb_feasible": mbb_feasible,                   # per-cell k=1 make-before-break OK
            "mbb_overlap_worst_s": worst_s,                 # worst valid handover overlap (s)
            "mbb_n_handovers": mbb_n_handovers,
            "mbb_worst_gap_s": mbb_worst_gap_steps * step,  # merged worst coverage gap (s; 0=none)
            "continuity_overlap_s": float(continuity_overlap_s),
            "detection_step_s": float(step),
            "refine_tol_s": float(refine_tol_s),
        })
    return out


_FORK_OK = hasattr(__import__("os"), "fork")
_SHARD_CTX = None


def _shard_task(cidx):
    return _compute_shard(_SHARD_CTX, cidx)


def _compute_shard(ctx, cidx):
    """One shard of the coverage kernel (identical math for serial and parallel paths).
    Returns per-shard accumulator slices, or None for an empty shard."""
    lat, lon = ctx["lat"], ctx["lon"]
    n_time, bounds, ks = ctx["n_time"], ctx["bounds"], ctx["ks"]
    do_mbb = ctx["do_mbb"]
    clat, clon = lat[cidx], lon[cidx]
    ce, cu = ctx["cell_ecef"][cidx], ctx["cell_up"][cidx]
    if ctx["shard_res"] is None:
        sat_idx = np.arange(ctx["elems"].shape[0])
    else:
        mask = relevant_sat_mask(ctx["sub_lat"], ctx["sub_lon"], clat, clon, ctx["dil"])
        sat_idx = np.nonzero(mask)[0]
    if not sat_idx.size:
        return None
    if ctx["terrain_on"]:
        east_s, north_s = ctx["cell_east"][cidx], ctx["cell_north"][cidx]
        tmask_s = ctx["terrain_masks"][cidx]
        rows = np.arange(tmask_s.shape[0])[:, None, None]
        n_bins, bin_w = ctx["n_bins"], ctx["bin_w"]
    # For continuity we retain the full per-(cell,sat) in-view time series of this shard
    # (a cell only ever sees its shard's relevant sats — the conservative pre-filter
    # guarantees no false negatives — so shard-local satellite identity is sufficient).
    inview_shard = (np.zeros((len(cidx), n_time, sat_idx.size), dtype=bool)
                    if do_mbb else None)
    out = {"serviceable": {k: np.zeros(len(cidx), dtype=np.int64) for k in ks},
           "sat_sum": np.zeros(len(cidx), dtype=np.int64)}
    for a, b in bounds:
        re_chunk = ctx["r_ecef"][sat_idx][:, a:b, :]         # (n_sat_s, n_chunk, 3)
        if not ctx["terrain_on"]:
            elev = elevation_deg(ce, cu, re_chunk)           # (n_cellS, n_chunk, n_sat_s)
            in_view = elev >= ctx["min_elev"]
        else:
            elev, az = az_el_deg(ce, east_s, north_s, cu, re_chunk)
            azb = np.clip((az / bin_w).astype(int), 0, n_bins - 1)
            eff_min = np.maximum(ctx["min_elev"], tmask_s[rows, azb])    # terrain skyline
            in_view = elev >= eff_min
        nv = in_view.sum(axis=-1)                            # (n_cellS, n_chunk)
        for k in ks:
            out["serviceable"][k] += (nv >= k).sum(axis=1)
        out["sat_sum"] += nv.sum(axis=1)
        if do_mbb:
            inview_shard[:, a:b, :] = in_view
    if do_mbb:
        mbb = continuity_map(inview_shard, ctx["min_overlap_steps"],
                             ctx["require_different_sat"],
                             plane_uid=ctx["plane_uid"][sat_idx], requirement=ctx["mbb_req"])
        out.update(mbb_feasible=mbb["mbb_feasible"],
                   worst_overlap_steps=mbb["worst_overlap_steps"],
                   n_handovers=mbb["n_handovers"],
                   worst_gap_steps=mbb["worst_gap_steps"])
    return out
