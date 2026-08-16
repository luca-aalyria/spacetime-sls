# Regression: ipywidgets' Output.__exit__ SWALLOWS exceptions raised inside `with out_log:`,
# which let CoverageExplorer.run() fall through to panel code with `res` unbound
# (UnboundLocalError) when compute() failed (e.g. MBB overlap gate vs too-coarse step).
import os
import numpy as np
import pytest

pytest.importorskip("ipywidgets")
from ngso_sls.explorer import CoverageExplorer, LiveCoverageExplorer


def test_run_surfaces_compute_error_in_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ex = CoverageExplorer()
    ex.handover_gate.value = True
    ex.overlap_s.value = 10.0
    ex.step_s.value = 60.0            # engine precondition: step <= overlap/2 -> ValueError
    ex.run()                          # must not raise / not UnboundLocalError
    assert ex.status.value.startswith("❌ ValueError")
    assert "step_s" in ex.status.value          # actionable message, not generic
    assert not ex.run_btn.disabled               # button re-enabled after failure


def test_live_explorer_run_good_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    elems = np.array([[7535.4, 0.0, np.radians(53), 0.0, 0.0, 0.0]])
    lx = LiveCoverageExplorer(elems, np.array([0]), label="t", min_elev_deg=25.0)
    lx.duration_min.value = 10
    lx.run()
    assert lx.status.value.startswith("✅")
    assert os.path.exists("live_coverage_availability_run1.csv")
