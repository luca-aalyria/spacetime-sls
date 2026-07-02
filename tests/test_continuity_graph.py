import numpy as np
from ngso_sls.coverage.continuity import Requirement, mbb_continuity_cell_req


def _inview(n_time, spans):
    n_sat = max(spans) + 1
    iv = np.zeros((n_time, n_sat), dtype=bool)
    for s, runs in spans.items():
        for a, b in runs:
            iv[a:b + 1, s] = True
    return iv


def test_different_plane_rejects_same_plane_handover():
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})          # overlap 2, feasible if planes differ
    plane = np.array([7, 7], np.int64)                    # SAME physical plane
    req = Requirement(min_overlap_steps=1, require_different_plane=True)
    r = mbb_continuity_cell_req(iv, plane, req)
    assert not r["feasible"]                               # same-plane handover disallowed
    r2 = mbb_continuity_cell_req(iv, np.array([7, 8], np.int64), req)
    assert r2["feasible"]                                  # different planes -> OK


def test_unknown_plane_is_conservatively_rejected():
    iv = _inview(5, {0: [(0, 2)], 1: [(1, 4)]})
    plane = np.array([-1, 5], np.int64)                    # source plane unknown
    req = Requirement(min_overlap_steps=1, require_different_plane=True)
    assert not mbb_continuity_cell_req(iv, plane, req)["feasible"]


def test_worst_gap_reported_on_failing_cell():
    iv = _inview(6, {0: [(0, 1)], 1: [(4, 5)]})           # gap at t=2,3 -> infeasible
    req = Requirement(min_overlap_steps=1)
    r = mbb_continuity_cell_req(iv, np.array([0, 1], np.int64), req)
    assert not r["feasible"] and r["worst_gap_steps"] >= 2   # real gap from merged intervals
