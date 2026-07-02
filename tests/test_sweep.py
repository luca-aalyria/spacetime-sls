import matplotlib
matplotlib.use("Agg")
import numpy as np
from datetime import datetime, timezone
from ngso_sls.sweep import min_sat_sweep
from ngso_sls.grids.aor import AORS
from ngso_sls.presets import jio_constellation
from ngso_sls.config import TimeGrid, SimConfig
from ngso_sls.pipeline import run_coverage_h3


def test_run_coverage_multi_k():
    sim = SimConfig(jio_constellation(), TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0))
    res = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=4, k_values=[1, 2])
    abk = res["availability_by_k"]
    assert set(abk) == {1, 2}
    # dual coverage (k=2) is never easier than single coverage (k=1), cell by cell
    assert np.all(abk[2] <= abk[1] + 1e-12)


def test_min_sat_sweep_k1_vs_k2():
    calls = []
    res = min_sat_sweep(AORS["India"], planes=40, altitude_km=650.0, inclination_deg=48.0,
                        sats_per_plane_values=[10, 20, 30], k_values=(1, 2),
                        target_availability=0.95, area_grade=0.95, min_elev_deg=25.0,
                        cell_res=2, duration_s=600.0, step_s=60.0,
                        progress=lambda d, t: calls.append((d, t)))
    assert [r["N"] for r in res["sweep"]] == [400, 800, 1200]
    for r in res["sweep"]:                                  # single >= dual coverage everywhere
        assert r["pct_by_k"][1] >= r["pct_by_k"][2] - 1e-9
    assert calls[-1] == (3, 3)
    m1, m2 = res["min_N_by_k"][1], res["min_N_by_k"][2]
    if m1 is not None and m2 is not None:                   # dual coverage needs at least as many
        assert m2 >= m1


def test_min_sat_sweep_plot():
    from ngso_sls.viz.plots import plot_min_sat_sweep
    sweep = {
        "sweep": [
            {"N": 400, "planes": 40, "sats_per_plane": 10, "mean_sats_in_view": 3.0,
             "pct_by_k": {1: 0.7, 2: 0.3}, "mean_avail_by_k": {1: 0.9, 2: 0.6}},
            {"N": 800, "planes": 40, "sats_per_plane": 20, "mean_sats_in_view": 6.0,
             "pct_by_k": {1: 1.0, 2: 0.96}, "mean_avail_by_k": {1: 1.0, 2: 0.98}},
        ],
        "min_N_by_k": {1: 400, 2: 800}, "k_values": [1, 2],
        "target_availability": 0.95, "area_grade": 0.95,
        "planes": 40, "altitude_km": 650.0, "inclination_deg": 48.0,
    }
    assert len(plot_min_sat_sweep(sweep).axes) >= 1


def test_inclination_sweep_engine():
    from ngso_sls.sweep import inclination_sweep, incl_values
    incs = incl_values(48.0, 53.0, 5.0)
    assert incs == [48.0, 53.0]
    calls = []
    res = inclination_sweep(AORS["India"], planes=40, altitude_km=650.0,
                            inclination_values=incs, sats_per_plane_values=[10, 20],
                            k_values=(1, 2), target_availability=0.9, area_grade=0.9,
                            cell_res=2, duration_s=300.0, step_s=60.0,
                            progress=lambda d, t: calls.append((d, t)))
    assert [b["inclination"] for b in res["by_inclination"]] == [48.0, 53.0]
    assert all(set(b["min_N_by_k"]) == {1, 2} for b in res["by_inclination"])
    assert calls[-1] == (4, 4)                      # 2 inclinations x 2 sizes


def test_incl_values_granularity():
    from ngso_sls.sweep import incl_values
    assert incl_values(50.0, 50.5, 0.1) == [50.0, 50.1, 50.2, 50.3, 50.4, 50.5]
    assert incl_values(48.0, 48.0, 5.0) == [48.0]   # single inclination


def test_sweep_ui_single_and_range(tmp_path):
    from ngso_sls.explorer import MinSatSweep
    # single inclination -> coverage_vs_N mode
    ui = MinSatSweep(csv_path=str(tmp_path / "s.csv"))
    ui.planes.value = 40
    ui.spp_min.value, ui.spp_max.value, ui.spp_step.value = 10, 20, 10
    ui.k_values.value = (1, 2)
    ui.cell_res.value = 2
    ui.duration_min.value = 5.0
    ui.incl_min.value = ui.incl_max.value = 48.0
    ui.run()
    assert ui.last_mode == "coverage_vs_N"
    assert set(ui.last_result["min_N_by_k"]) == {1, 2}
    assert (tmp_path / "s.csv").exists() and ui.run_btn.disabled is False
    # inclination range -> min_N_vs_incl mode
    ui.incl_min.value, ui.incl_max.value, ui.incl_step.value = 48.0, 53.0, 5.0
    ui.run()
    assert ui.last_mode == "min_N_vs_incl"
    assert [b["inclination"] for b in ui.last_result["by_inclination"]] == [48.0, 53.0]
