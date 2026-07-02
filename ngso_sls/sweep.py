"""Minimum-satellite sweep: vary a Walker shell's size (and optionally inclination) and measure
AOR coverage, to find the smallest constellation that meets a coverage grade — for one or more
k-coverage levels (e.g. k=1 single coverage vs k=2 handover-capable dual coverage). Pure geometry.
"""
from datetime import datetime, timezone

from .config import Shell, Constellation, TimeGrid, SimConfig
from .pipeline import run_coverage_h3

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def incl_values(inc_min, inc_max, step_deg):
    """Inclination list from inc_min..inc_max at `step_deg` (min granularity 0.1°)."""
    step = max(float(step_deg), 0.1)
    if inc_max <= inc_min:
        return [round(float(inc_min), 1)]
    n = int(round((inc_max - inc_min) / step))
    return [round(inc_min + i * step, 1) for i in range(n + 1) if inc_min + i * step <= inc_max + 1e-9]


def min_sat_sweep(aor, planes, altitude_km, inclination_deg, sats_per_plane_values,
                  min_elev_deg=25.0, k_values=(1, 2), target_availability=0.99, area_grade=0.95,
                  cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1, use_sharding=True,
                  propagator=None, progress=None, continuity_overlap_s=None) -> dict:
    """Sweep a single Walker shell's sats/plane (-> total N = planes * sats/plane) and measure
    coverage over the AOR for each k in `k_values`, to find the minimum constellation size
    meeting a coverage grade.

    Per candidate & per k: per-cell availability = fraction of time with >= k sats in view;
    `pct_by_k[k]` = fraction of AOR cells with availability >= target_availability.
    `min_N_by_k[k]` = smallest N whose pct >= area_grade (None if not reached in the range).

    When `continuity_overlap_s` is set, an additional **make-before-break (k=1) gate** is
    computed: `pct_mbb` = fraction of cells that are continuously served by >=1 satellite with
    a >= `continuity_overlap_s` two-satellite overlap at every handover; `min_N_mbb` = smallest
    N with pct_mbb >= area_grade (a strictly stronger requirement than the k=1 availability
    grade, so failing shapes stay in the curve and are flagged in the UI).

    Returns {"sweep": [...], "min_N_by_k": {k: int|None}, "min_N_mbb": int|None, "k_values": [...],
    ...params}. The full curve is always returned. `progress(done, total)` is optional. One
    coverage run per N covers all k (computed in a single pass), so adding k values is nearly free.
    """
    ks = list(k_values)
    spp_values = list(sats_per_plane_values)
    total = len(spp_values)
    do_mbb = continuity_overlap_s is not None
    sweep = []
    for i, spp in enumerate(spp_values):
        shell = Shell("sweep", planes * spp, planes, min(phasing, planes - 1),
                      altitude_km, inclination_deg, min_elev_user_deg=min_elev_deg)
        sim = SimConfig(Constellation((shell,)),
                        TimeGrid(_EPOCH, duration_s=duration_s, step_s=step_s), k_coverage=ks[0])
        res = run_coverage_h3(sim, aor, cell_res=cell_res,
                              shard_res=(1 if use_sharding else None), chunk_steps=10,
                              propagator=propagator, k_values=ks,
                              continuity_overlap_s=continuity_overlap_s)
        abk = res["availability_by_k"]
        row = {
            "N": planes * spp,
            "planes": planes,
            "sats_per_plane": spp,
            "mean_sats_in_view": float(res["sats_in_view_mean"].mean()),
            "pct_by_k": {k: float((abk[k] >= target_availability).mean()) for k in ks},
            "mean_avail_by_k": {k: float(abk[k].mean()) for k in ks},
        }
        if do_mbb:
            row["pct_mbb"] = float(res["mbb_feasible"].mean())
            row["mbb_pass"] = bool(row["pct_mbb"] >= area_grade)
        sweep.append(row)
        if progress is not None:
            progress(i + 1, total)

    min_N_by_k = {}
    for k in ks:
        meeting = [r["N"] for r in sweep if r["pct_by_k"][k] >= area_grade]
        min_N_by_k[k] = (min(meeting) if meeting else None)
    min_N_mbb = None
    if do_mbb:
        meeting = [r["N"] for r in sweep if r["pct_mbb"] >= area_grade]
        min_N_mbb = (min(meeting) if meeting else None)

    return {
        "sweep": sweep,
        "min_N_by_k": min_N_by_k,
        "min_N_mbb": min_N_mbb,
        "continuity_overlap_s": continuity_overlap_s,
        "k_values": ks,
        "target_availability": target_availability,
        "area_grade": area_grade,
        "planes": planes,
        "altitude_km": altitude_km,
        "inclination_deg": inclination_deg,
    }


def multi_shape_sweep(aor, planes_values, spp_values, altitude_km, inclination_deg,
                      min_elev_deg=25.0, k_values=(1, 2), target_availability=0.99,
                      area_grade=0.95, cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1,
                      use_sharding=True, handover_gate=False, continuity_overlap_s=None,
                      max_grid_cells=256, propagator=None, progress=None) -> dict:
    """2D sweep over planes x sats/plane (N = planes*spp). Each candidate: pct_by_k, and (gate on)
    pct_mbb/mbb_pass. min_N_by_k + min_N_mbb; is_pareto by lexicographic order (constraints, then
    min N, then min planes). Full grid always returned; refuses grids over `max_grid_cells`."""
    Pv, Sv, ks = list(planes_values), list(spp_values), list(k_values)
    if len(Pv) * len(Sv) > max_grid_cells:
        raise ValueError(f"grid {len(Pv)}x{len(Sv)} exceeds max_grid_cells={max_grid_cells}; "
                         f"coarsen the ranges or raise the cap")
    overlap = continuity_overlap_s if handover_gate else None
    total, done = len(Pv) * len(Sv), 0
    cands = []
    for P in Pv:
        for spp in Sv:
            shell = Shell("sweep", P * spp, P, min(phasing, P - 1), altitude_km,
                          inclination_deg, min_elev_user_deg=min_elev_deg)
            sim = SimConfig(Constellation((shell,)),
                            TimeGrid(_EPOCH, duration_s=duration_s, step_s=step_s), k_coverage=ks[0])
            res = run_coverage_h3(sim, aor, cell_res=cell_res,
                                  shard_res=(1 if use_sharding else None), chunk_steps=10,
                                  propagator=propagator, k_values=ks, continuity_overlap_s=overlap)
            abk = res["availability_by_k"]
            c = {"N": P * spp, "planes": P, "sats_per_plane": spp,
                 "mean_sats_in_view": float(res["sats_in_view_mean"].mean()),
                 "pct_by_k": {k: float((abk[k] >= target_availability).mean()) for k in ks},
                 "is_pareto": False}
            if overlap is not None:
                c["pct_mbb"] = float(res["mbb_feasible"].mean())
                c["mbb_pass"] = bool(c["pct_mbb"] >= area_grade)
            cands.append(c)
            done += 1
            if progress is not None:
                progress(done, total)

    def passes(c):
        ok = all(c["pct_by_k"][k] >= area_grade for k in ks)
        return ok and (c.get("mbb_pass", True) if overlap is not None else ok)

    winners = [c for c in cands if passes(c)]
    winners.sort(key=lambda c: (c["N"], c["planes"]))          # lexicographic (ref §9)
    if winners:
        winners[0]["is_pareto"] = True
    min_N_by_k = {}
    for k in ks:
        m = [c["N"] for c in cands if c["pct_by_k"][k] >= area_grade]
        min_N_by_k[k] = min(m) if m else None
    min_N_mbb = (min([c["N"] for c in cands if c.get("mbb_pass")], default=None)
                 if overlap is not None else None)
    return {"candidates": cands, "min_N_by_k": min_N_by_k, "min_N_mbb": min_N_mbb,
            "continuity_overlap_s": overlap, "k_values": ks, "planes_values": Pv,
            "spp_values": Sv, "target_availability": target_availability, "area_grade": area_grade,
            "altitude_km": altitude_km, "inclination_deg": inclination_deg}


def inclination_sweep(aor, planes, altitude_km, inclination_values, sats_per_plane_values,
                      min_elev_deg=25.0, k_values=(1, 2), target_availability=0.99, area_grade=0.95,
                      cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1, use_sharding=True,
                      propagator=None, progress=None, continuity_overlap_s=None) -> dict:
    """For each inclination, run `min_sat_sweep` and record min-N per k, to compare inclinations.

    Returns {"by_inclination": [{"inclination", "min_N_by_k", "sweep"}...], "inclinations": [...],
    "k_values": [...], ...params}. `progress(done, total)` reports overall progress across the
    inclination x sats/plane grid.
    """
    incs = list(inclination_values)
    spp = list(sats_per_plane_values)
    total = len(incs) * len(spp)
    done = 0
    by_inclination = []
    for inc in incs:
        base = done

        def _p(d, t, base=base):
            if progress is not None:
                progress(base + d, total)

        r = min_sat_sweep(aor, planes, altitude_km, inc, spp, min_elev_deg=min_elev_deg,
                          k_values=k_values, target_availability=target_availability,
                          area_grade=area_grade, cell_res=cell_res, duration_s=duration_s,
                          step_s=step_s, phasing=phasing, use_sharding=use_sharding,
                          propagator=propagator, progress=_p,
                          continuity_overlap_s=continuity_overlap_s)
        done += len(spp)
        by_inclination.append({"inclination": inc, "min_N_by_k": r["min_N_by_k"],
                               "min_N_mbb": r["min_N_mbb"], "sweep": r["sweep"]})

    return {
        "by_inclination": by_inclination,
        "inclinations": incs,
        "k_values": list(k_values),
        "continuity_overlap_s": continuity_overlap_s,
        "target_availability": target_availability,
        "area_grade": area_grade,
        "planes": planes,
        "altitude_km": altitude_km,
    }
