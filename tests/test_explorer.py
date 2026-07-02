import matplotlib
matplotlib.use("Agg")
from ngso_sls.explorer import CoverageExplorer


def test_explorer_builds_and_runs(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "cov.csv"))
    # widgets + run-history results present (no runs yet)
    assert ex.controls is not None and ex.results is not None
    assert len(ex.runs_tab.children) == 0
    # small/fast configuration
    ex.scenario.value = "~200 @48° (minimal)"
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    ex.run()
    assert ex.last_result is not None
    assert "availability" in ex.last_result and "sats_in_view_mean" in ex.last_result
    assert (tmp_path / "cov.csv").exists()
    # first run appended a panel whose inner tab has all 5 plot views
    assert len(ex.runs_tab.children) == 1
    inner = ex.runs_tab.children[0].children[1]
    assert len(inner.children) == 5
    # a second run KEEPS the first (history), appending another panel
    ex.run()
    assert len(ex.runs_tab.children) == 2
    # progress + status feedback wired
    assert ex.progress.value == ex.progress.max
    assert ex.progress.bar_style == "success"
    assert "done" in ex.status.value
    assert ex.run_btn.disabled is False and ex.run_btn.description == "Run simulation"


def test_explorer_close_run_and_per_run_csv(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "cov.csv"))
    ex.scenario.value = "~200 @48° (minimal)"
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    ex.run()
    ex.run()
    assert len(ex.runs_tab.children) == 2
    # each run persisted its own CSV (survives a tab close)
    assert (tmp_path / "cov_run1.csv").exists() and (tmp_path / "cov_run2.csv").exists()
    # closing the first run's tab removes it; the other stays
    first_panel = ex.runs_tab.children[0]
    ex._close_run(first_panel)
    assert len(ex.runs_tab.children) == 1
    assert (tmp_path / "cov_run1.csv").exists()          # data remains on disk after closing
    # titles reindexed, no crash selecting
    assert ex.runs_tab.selected_index == 0


def test_explorer_handover_gate_and_params(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "h.csv"))
    ex.scenario.value = "~200 @48° (minimal)"
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    ex.k_cov.value = 1
    ex.handover_gate.value = True
    ex.overlap_s.value = 30.0
    ex.run()
    assert "mbb_feasible" in ex.last_result and ex.last_result["continuity_overlap_s"] == 30.0
    # input parameters are saved into the output CSV manifest
    text = (tmp_path / "h.csv").read_text()
    assert "# min_overlap_s: 30.0" in text and "# handover_gate: True" in text
    assert "mbb_feasible" in text.splitlines()[-2] or "mbb_feasible" in text  # column present


def test_custom_walker_via_explorer(tmp_path):
    ex = CoverageExplorer(csv_path=str(tmp_path / "c.csv"))
    ex.scenario.value = "Custom (Walker)"
    ex.planes1.value, ex.spp1.value = 12, 10   # -> 120 sats
    ex.cell_res.value = 2
    ex.duration_min.value = 20.0
    cons = ex.build_constellation()
    assert sum(s.walker_T for s in cons.shells) == 120
