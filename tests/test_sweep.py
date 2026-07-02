import matplotlib
matplotlib.use("Agg")
from ngso_sls.sweep import min_sat_sweep
from ngso_sls.grids.aor import AORS


def test_min_sat_sweep_engine():
    calls = []
    res = min_sat_sweep(AORS["India"], planes=20, altitude_km=650.0, inclination_deg=53.0,
                        sats_per_plane_values=[2, 10], min_elev_deg=25.0, k_coverage=1,
                        target_availability=0.9, area_grade=0.9, cell_res=2,
                        duration_s=300.0, step_s=60.0, progress=lambda d, t: calls.append((d, t)))
    assert [r["N"] for r in res["sweep"]] == [40, 200]
    # more satellites -> at least as much coverage
    assert res["sweep"][1]["pct_cells_meeting_target"] >= res["sweep"][0]["pct_cells_meeting_target"]
    assert calls[-1] == (2, 2)              # progress reported to completion
    assert res["min_N"] in (40, 200, None)


def test_min_sat_sweep_plot():
    from ngso_sls.viz.plots import plot_min_sat_sweep
    sweep = {
        "sweep": [
            {"N": 40, "sats_per_plane": 2, "mean_availability": 0.3, "pct_cells_meeting_target": 0.2, "mean_sats_in_view": 2.0},
            {"N": 200, "sats_per_plane": 10, "mean_availability": 0.9, "pct_cells_meeting_target": 0.96, "mean_sats_in_view": 8.0},
        ],
        "min_N": 200, "target_availability": 0.9, "area_grade": 0.95, "k_coverage": 1,
        "planes": 20, "altitude_km": 650.0, "inclination_deg": 53.0,
    }
    fig = plot_min_sat_sweep(sweep)
    assert len(fig.axes) >= 1


def test_min_sat_sweep_ui(tmp_path):
    from ngso_sls.explorer import MinSatSweep
    ui = MinSatSweep(csv_path=str(tmp_path / "s.csv"))
    ui.planes.value = 20
    ui.spp_min.value, ui.spp_max.value, ui.spp_step.value = 2, 10, 8   # -> [2, 10]
    ui.cell_res.value = 2
    ui.duration_min.value = 5.0
    ui.run()
    assert ui.last_result is not None and len(ui.last_result["sweep"]) == 2
    assert (tmp_path / "s.csv").exists()
    assert ui.run_btn.disabled is False and ui.progress.bar_style in ("success", "info")
