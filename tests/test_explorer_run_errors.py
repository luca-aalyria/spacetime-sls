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


def test_builder_feeds_live_explorer_and_rerun_tracks_widgets(tmp_path, monkeypatch):
    # nb01's new two-cell flow: WalkerConstellationBuilder.elements (a callable) feeds the
    # SAME LiveCoverageExplorer used by nb07; every Run re-reads the builder's widgets.
    monkeypatch.chdir(tmp_path)
    from ngso_sls.explorer import WalkerConstellationBuilder
    b = WalkerConstellationBuilder()
    b.scenario.value = "Custom (Walker)"
    b.planes1.value, b.spp1.value = 4, 5
    ex = LiveCoverageExplorer(b.elements, csv_path="cov.csv")
    ex.duration_min.value = 10
    ex.run()
    assert ex.status.value.startswith("✅") and ex.last_result["_total_sats"] == 20
    b.planes1.value = 6                       # tweak constellation; NO explorer rebuild
    ex.run()
    assert ex.last_result["_total_sats"] == 30


def test_constellation_source_walker_and_spacetime_modes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from ngso_sls.explorer import ConstellationSource
    src = ConstellationSource()
    elems, pu, label = src.elements()                 # Walker default preset
    assert elems.shape[0] == 1600 and "1600" in label
    src.mode.value = "Spacetime (live NMTS)"
    try:                                              # live iff a forward is up; dump otherwise
        elems, pu, label = src.elements()
    except RuntimeError:
        pytest.skip("no live store and no dump in this environment")
    assert elems.shape[0] > 0 and ("live" in label or "dump" in label)
