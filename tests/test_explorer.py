import matplotlib
matplotlib.use("Agg")
from ngso_sls.explorer import CoverageExplorer


def test_explorer_builds_and_runs(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "cov.csv"))
    # widgets + tabbed results present
    assert ex.controls is not None and ex.results is not None
    assert len(ex.tabs.children) == 4
    # small/fast configuration
    ex.scenario.value = "~200 @48° (minimal)"
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    ex.run()
    assert ex.last_result is not None
    assert "availability" in ex.last_result and "sats_in_view_mean" in ex.last_result
    assert (tmp_path / "cov.csv").exists()
    # progress + status feedback wired
    assert ex.progress.value == ex.progress.max
    assert ex.progress.bar_style == "success"
    assert "done" in ex.status.value
    assert ex.run_btn.disabled is False and ex.run_btn.description == "Run simulation"


def test_custom_walker_via_explorer(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "c.csv"))
    ex.scenario.value = "Custom (Walker)"
    ex.planes1.value, ex.spp1.value = 12, 10   # -> 120 sats
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    cons = ex.build_constellation()
    assert sum(s.walker_T for s in cons.shells) == 120
