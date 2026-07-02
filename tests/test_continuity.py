from datetime import datetime, timezone
import numpy as np
from ngso_sls.coverage.continuity import (
    intervals_from_inview,
    mbb_continuity_cell,
    continuity_map,
)
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig
from ngso_sls.grids.aor import AORS
from ngso_sls.pipeline import run_coverage_h3


def _inview(n_time, spans):
    """spans: {sat: [(start, end_inclusive), ...]} -> (n_time, n_sat) bool."""
    n_sat = max(spans) + 1
    iv = np.zeros((n_time, n_sat), dtype=bool)
    for s, runs in spans.items():
        for a, b in runs:
            iv[a : b + 1, s] = True
    return iv


def test_intervals_extraction():
    iv = _inview(6, {0: [(0, 2)], 1: [(1, 1), (4, 5)]})
    got = sorted(intervals_from_inview(iv))
    assert got == [(0, 0, 2), (1, 1, 1), (1, 4, 5)]


def test_single_sat_covers_window_no_handover():
    iv = _inview(5, {0: [(0, 4)]})
    r = mbb_continuity_cell(iv, min_overlap_steps=2)
    assert r["feasible"] and r["n_handovers"] == 0 and r["worst_overlap_steps"] is None


def test_two_sat_make_before_break_feasible():
    # sat0 [0,2], sat1 [1,4] -> overlap = 2 timesteps
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})
    r = mbb_continuity_cell(iv, min_overlap_steps=2)
    assert r["feasible"] and r["n_handovers"] == 1 and r["worst_overlap_steps"] == 2


def test_overlap_too_short_infeasible():
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})   # overlap only 2 steps
    r = mbb_continuity_cell(iv, min_overlap_steps=3)
    assert not r["feasible"]


def test_uncovered_gap_infeasible():
    iv = _inview(5, {0: [(0, 1)], 1: [(3, 4)]})   # nothing in view at t=2
    r = mbb_continuity_cell(iv, min_overlap_steps=1)
    assert not r["feasible"]


def test_no_coverage_at_start_infeasible():
    iv = _inview(5, {0: [(1, 4)]})                # gap at t=0
    r = mbb_continuity_cell(iv, min_overlap_steps=1)
    assert not r["feasible"]


def test_three_sat_chain():
    iv = _inview(9, {0: [(0, 2)], 1: [(2, 5)], 2: [(5, 8)]})
    r = mbb_continuity_cell(iv, min_overlap_steps=1)
    assert r["feasible"] and r["n_handovers"] == 2 and r["worst_overlap_steps"] == 1


def test_adjacent_no_simultaneous_window_infeasible():
    # sat0 [0,2], sat1 [3,5]: coverage is technically gapless in TIME but there is NO shared
    # timestep, so there is no make-before-break window -> must fail the MBB gate.
    iv = _inview(6, {0: [(0, 2)], 1: [(3, 5)]})
    r = mbb_continuity_cell(iv, min_overlap_steps=1)
    assert not r["feasible"]


def test_continuity_map_shapes():
    iv = np.stack([
        _inview(5, {0: [(0, 4)], 1: []}),          # feasible, 0 handovers
        _inview(5, {0: [(0, 2)], 1: [(1, 4)]}),    # feasible, 1 handover, overlap 2
    ])
    m = continuity_map(iv, min_overlap_steps=2)
    assert m["mbb_feasible"].tolist() == [True, True]
    assert m["worst_overlap_steps"].tolist() == [-1, 2]   # -1 = n/a (no handover)
    assert m["n_handovers"].tolist() == [0, 1]


def _small_sim():
    shell = Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0)
    return SimConfig(Constellation((shell,)),
                     TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1800.0, 10.0))


def test_pipeline_continuity_outputs():
    sim = _small_sim()
    res = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5,
                          continuity_overlap_s=30.0)
    n = len(res["cells"])
    assert res["mbb_feasible"].shape == (n,) and res["mbb_feasible"].dtype == bool
    assert res["mbb_overlap_worst_s"].shape == (n,)
    assert res["continuity_overlap_s"] == 30.0
    # feasible cells with a handover must report a non-negative worst overlap
    hov = res["mbb_n_handovers"] > 0
    assert np.all(res["mbb_overlap_worst_s"][hov] >= 0.0)


def test_pipeline_continuity_sharded_equals_monolithic():
    sim = _small_sim()
    mono = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=None,
                           continuity_overlap_s=30.0)
    shard = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=4,
                            continuity_overlap_s=30.0)
    assert np.array_equal(mono["mbb_feasible"], shard["mbb_feasible"])
    assert np.array_equal(mono["mbb_n_handovers"], shard["mbb_n_handovers"])
    assert np.array_equal(mono["mbb_overlap_worst_s"], shard["mbb_overlap_worst_s"])


def test_pipeline_different_plane_is_stricter_and_reports_gap():
    sim = _small_sim()
    base = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5,
                           continuity_overlap_s=30.0)
    dp = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5,
                         continuity_overlap_s=30.0, require_different_plane=True)
    # different-plane is at least as strict: dp-feasible implies base-feasible (bool <=)
    assert np.all(dp["mbb_feasible"] <= base["mbb_feasible"])
    # worst-gap is now always reported (seconds); >=0 everywhere
    assert "mbb_worst_gap_s" in dp and dp["mbb_worst_gap_s"].shape == (len(dp["cells"]),)
    assert np.all(dp["mbb_worst_gap_s"] >= 0.0)


def test_pipeline_different_plane_sharded_equals_monolithic():
    sim = _small_sim()
    mono = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=None,
                           continuity_overlap_s=30.0, require_different_plane=True)
    shard = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=4,
                            continuity_overlap_s=30.0, require_different_plane=True)
    assert np.array_equal(mono["mbb_feasible"], shard["mbb_feasible"])
    assert np.array_equal(mono["mbb_worst_gap_s"], shard["mbb_worst_gap_s"])
