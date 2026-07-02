# ngso_sls/coverage/refine.py
"""Sub-second endpoint refinement for handover-continuity intervals (SA13).

The coarse `step_s` grid DETECTS which satellites are usable in which timesteps; this module only
SHARPENS the entry/exit instants of already-detected intervals by root-finding elevation(t) −
min_elev between the two adjacent coarse samples (guaranteed sign change). It does NOT find
passes/gaps shorter than `step_s` — that fidelity bound is enforced by the caller's Nyquist
precondition. Pure NumPy + math (no `bisect`), core-safe. `refine_crossing_s` takes an elevation
callable so it is unit-testable without the propagator; the pipeline supplies a callable that
propagates the specific (cell, satellite) at candidate times."""
import math


def n_bisect_iters(step_s: float, tol_s: float) -> int:
    """Fixed bisection iteration count to reach `tol_s` from a `step_s`-wide bracket."""
    return max(1, math.ceil(math.log2(max(step_s, tol_s) / tol_s)))


def refine_crossing_s(elev_at, lo_s: float, hi_s: float, min_elev_deg: float,
                      tol_s: float = 1e-3) -> float:
    """Return the time in [lo_s, hi_s] where elev_at(t) crosses `min_elev_deg`, by fixed-iteration
    bisection. Requires a sign change of (elev - min_elev) across the bracket."""
    f_lo = elev_at(lo_s) - min_elev_deg
    f_hi = elev_at(hi_s) - min_elev_deg
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError("no elevation-threshold sign change in the bracket")
    for _ in range(n_bisect_iters(hi_s - lo_s, tol_s)):
        mid = 0.5 * (lo_s + hi_s)
        f_mid = elev_at(mid) - min_elev_deg
        if (f_mid > 0) == (f_lo > 0):
            lo_s, f_lo = mid, f_mid
        else:
            hi_s = mid
    return 0.5 * (lo_s + hi_s)
