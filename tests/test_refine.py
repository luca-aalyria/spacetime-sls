# tests/test_refine.py
import numpy as np
from ngso_sls.coverage.refine import refine_crossing_s, n_bisect_iters


def test_n_bisect_iters_covers_tolerance():
    assert n_bisect_iters(step_s=60.0, tol_s=1.0) >= 6          # 60/2^6 < 1
    assert 2.0 ** -n_bisect_iters(60.0, 1.0) * 60.0 <= 1.0


def test_refine_crossing_bisects_monotone_bracket():
    # elevation model: linear in t, crossing min_elev=10 at t*=57.0 within [0,60]
    # elev(t) = -5 + 0.5*(t-27); solving elev(t)=10 gives t=57
    def elev(t):
        return -5.0 + 0.5 * (t - 27.0)          # = min_elev(10) at t=57
    t = refine_crossing_s(elev, lo_s=0.0, hi_s=60.0, min_elev_deg=10.0, tol_s=1e-3)
    assert abs(t - 57.0) < 1e-2


def test_refine_requires_sign_change_bracket():
    def elev(t):
        return 20.0                              # never crosses
    import pytest
    with pytest.raises(ValueError):
        refine_crossing_s(elev, 0.0, 60.0, min_elev_deg=10.0)
