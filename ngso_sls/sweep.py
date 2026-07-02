"""Minimum-satellite sweep: vary a Walker shell's size and measure AOR coverage, to find the
smallest constellation that meets a coverage grade. Pure geometry (reuses the coverage engine).
"""
from datetime import datetime, timezone

from .config import Shell, Constellation, TimeGrid, SimConfig
from .pipeline import run_coverage_h3

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def min_sat_sweep(aor, planes, altitude_km, inclination_deg, sats_per_plane_values,
                  min_elev_deg=25.0, k_coverage=1, target_availability=0.99, area_grade=0.95,
                  cell_res=3, duration_s=3600.0, step_s=60.0, phasing=1, use_sharding=True,
                  propagator=None, progress=None) -> dict:
    """Sweep a single Walker shell's sats/plane (-> total N = planes * sats/plane) and measure
    coverage over the AOR, to find the minimum constellation size meeting a coverage grade.

    Per candidate: per-cell availability = fraction of time with >= k_coverage sats in view;
    `pct_cells_meeting_target` = fraction of AOR cells with availability >= target_availability.
    `min_N` = smallest N whose pct-cells-meeting-target >= area_grade (None if none reach it).

    Returns {"sweep": [per-candidate dicts], "min_N": int|None, ...params}. The full curve is
    always returned regardless of whether a target is met. `progress(done, total)` is optional.
    """
    spp_values = list(sats_per_plane_values)
    total = len(spp_values)
    sweep = []
    for i, spp in enumerate(spp_values):
        shell = Shell("sweep", planes * spp, planes, min(phasing, planes - 1),
                      altitude_km, inclination_deg, min_elev_user_deg=min_elev_deg)
        sim = SimConfig(Constellation((shell,)),
                        TimeGrid(_EPOCH, duration_s=duration_s, step_s=step_s),
                        k_coverage=k_coverage)
        res = run_coverage_h3(sim, aor, cell_res=cell_res,
                              shard_res=(1 if use_sharding else None), chunk_steps=10,
                              propagator=propagator)
        avail = res["availability"]
        sweep.append({
            "N": planes * spp,
            "planes": planes,
            "sats_per_plane": spp,
            "mean_availability": float(avail.mean()),
            "pct_cells_meeting_target": float((avail >= target_availability).mean()),
            "mean_sats_in_view": float(res["sats_in_view_mean"].mean()),
        })
        if progress is not None:
            progress(i + 1, total)

    meeting = [r["N"] for r in sweep if r["pct_cells_meeting_target"] >= area_grade]
    return {
        "sweep": sweep,
        "min_N": (min(meeting) if meeting else None),
        "target_availability": target_availability,
        "area_grade": area_grade,
        "k_coverage": k_coverage,
        "planes": planes,
        "altitude_km": altitude_km,
        "inclination_deg": inclination_deg,
    }
