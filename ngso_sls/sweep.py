"""Minimum-satellite sweep: vary a Walker shell's size and measure AOR coverage, to find the
smallest constellation that meets a coverage grade — for one or more k-coverage levels (e.g.
k=1 single coverage vs k=2 handover-capable dual coverage). Pure geometry (reuses the engine).
"""
from datetime import datetime, timezone

from .config import Shell, Constellation, TimeGrid, SimConfig
from .pipeline import run_coverage_h3

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def min_sat_sweep(aor, planes, altitude_km, inclination_deg, sats_per_plane_values,
                  min_elev_deg=25.0, k_values=(1, 2), target_availability=0.99, area_grade=0.95,
                  cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1, use_sharding=True,
                  propagator=None, progress=None) -> dict:
    """Sweep a single Walker shell's sats/plane (-> total N = planes * sats/plane) and measure
    coverage over the AOR for each k in `k_values`, to find the minimum constellation size
    meeting a coverage grade.

    Per candidate & per k: per-cell availability = fraction of time with >= k sats in view;
    `pct_by_k[k]` = fraction of AOR cells with availability >= target_availability.
    `min_N_by_k[k]` = smallest N whose pct >= area_grade (None if not reached in the range).

    Returns {"sweep": [...], "min_N_by_k": {k: int|None}, "k_values": [...], ...params}. The full
    curve is always returned. `progress(done, total)` is optional. One coverage run per N covers
    all k (computed in a single pass), so adding k values is nearly free.
    """
    ks = list(k_values)
    spp_values = list(sats_per_plane_values)
    total = len(spp_values)
    sweep = []
    for i, spp in enumerate(spp_values):
        shell = Shell("sweep", planes * spp, planes, min(phasing, planes - 1),
                      altitude_km, inclination_deg, min_elev_user_deg=min_elev_deg)
        sim = SimConfig(Constellation((shell,)),
                        TimeGrid(_EPOCH, duration_s=duration_s, step_s=step_s), k_coverage=ks[0])
        res = run_coverage_h3(sim, aor, cell_res=cell_res,
                              shard_res=(1 if use_sharding else None), chunk_steps=10,
                              propagator=propagator, k_values=ks)
        abk = res["availability_by_k"]
        sweep.append({
            "N": planes * spp,
            "planes": planes,
            "sats_per_plane": spp,
            "mean_sats_in_view": float(res["sats_in_view_mean"].mean()),
            "pct_by_k": {k: float((abk[k] >= target_availability).mean()) for k in ks},
            "mean_avail_by_k": {k: float(abk[k].mean()) for k in ks},
        })
        if progress is not None:
            progress(i + 1, total)

    min_N_by_k = {}
    for k in ks:
        meeting = [r["N"] for r in sweep if r["pct_by_k"][k] >= area_grade]
        min_N_by_k[k] = (min(meeting) if meeting else None)

    return {
        "sweep": sweep,
        "min_N_by_k": min_N_by_k,
        "k_values": ks,
        "target_availability": target_availability,
        "area_grade": area_grade,
        "planes": planes,
        "altitude_km": altitude_km,
        "inclination_deg": inclination_deg,
    }
