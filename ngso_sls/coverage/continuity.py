"""Make-before-break (MBB) handover continuity for k=1 service.

Continuous single coverage is not enough for a live service: at every transition between
serving satellites the source and target must be *simultaneously* in view long enough to
execute a make-before-break handover. This module tests, per ground cell, whether a valid
serving path spans the whole evaluation window such that:

  * the first serving satellite is in view at t=0 (no initial gap);
  * each handover is between two DIFFERENT satellites that overlap in view for
    >= `min_overlap_steps` timesteps (the mandatory 2-sat window);
  * the last serving satellite is in view at the final timestep (no trailing gap).

Overlap is measured in whole timesteps, so the accuracy is +/- one `step_s`; set `step_s`
to order-seconds for second-scale handover windows. (Sub-step endpoint refinement is a
later enhancement per the Slice-A revisions design.)

Pure NumPy — safe for the dependency-light core (`tests/test_core_purity.py`).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Requirement:
    min_overlap_steps: int = 1          # shared samples required for a make-before-break window
    require_different_sat: bool = True
    require_different_plane: bool = False


def intervals_from_inview(inview: np.ndarray):
    """`inview` (n_time, n_sat) bool -> list of (sat, start, end_inclusive) usable intervals,
    the maximal runs of consecutive in-view timesteps for each satellite."""
    n_time, n_sat = inview.shape
    intervals = []
    for s in range(n_sat):
        col = inview[:, s]
        if not col.any():
            continue
        d = np.diff(col.astype(np.int8))
        starts = (np.where(d == 1)[0] + 1).tolist()
        ends = np.where(d == -1)[0].tolist()
        if col[0]:
            starts.insert(0, 0)
        if col[-1]:
            ends.append(n_time - 1)
        for st, en in zip(starts, ends):
            intervals.append((s, int(st), int(en)))
    return intervals


def mbb_continuity_cell(inview: np.ndarray, min_overlap_steps: int,
                        require_different_sat: bool = True) -> dict:
    """Make-before-break continuity verdict for ONE cell.

    Returns {feasible, worst_overlap_steps, n_handovers}:
      * feasible — a make-before-break serving path spans [0, n_time-1];
      * worst_overlap_steps — the largest *guaranteed* minimum handover overlap over all
        feasible paths (bottleneck); None when the best path needs no handover (a single
        satellite covers the whole window) or when infeasible;
      * n_handovers — handovers on that best path; None when infeasible.

    `min_overlap_steps` is floored at 1 so at least one shared timestep (a gapless MBB
    window) is always required.
    """
    n_time = int(inview.shape[0])
    thr = max(int(min_overlap_steps), 1)
    ivs = intervals_from_inview(inview)
    if not ivs:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None}

    ivs.sort(key=lambda x: (x[2], x[1]))          # by end, then start
    m = len(ivs)
    INF = n_time + 1                               # bottleneck sentinel for "no handover yet"
    best = [None] * m                             # max achievable bottleneck overlap to reach i
    hops = [0] * m
    for i, (_s, st, _en) in enumerate(ivs):
        if st <= 0:                               # in view at the start instant -> a source
            best[i] = INF

    # Edges go from earlier-ending to strictly later-ending intervals; sorted by end means a
    # single forward pass is a valid topological relaxation.
    for i in range(m):
        if best[i] is None:
            continue
        si, sti, eni = ivs[i]
        for j in range(i + 1, m):
            sj, stj, enj = ivs[j]
            if enj <= eni:                        # target must extend service
                continue
            if require_different_sat and sj == si:
                continue
            ov = min(eni, enj) - max(sti, stj) + 1   # shared timesteps (inclusive)
            if ov < thr:
                continue
            cand = best[i] if best[i] < ov else ov   # bottleneck = min overlap along path
            if best[j] is None or cand > best[j]:
                best[j] = cand
                hops[j] = hops[i] + 1

    goals = [i for i in range(m) if best[i] is not None and ivs[i][2] >= n_time - 1]
    if not goals:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None}
    gi = max(goals, key=lambda i: best[i])
    b = best[gi]
    return {
        "feasible": True,
        "worst_overlap_steps": (None if b >= INF else int(b)),
        "n_handovers": int(hops[gi]),
    }


def continuity_map(inview: np.ndarray, min_overlap_steps: int,
                   require_different_sat: bool = True,
                   plane_uid: np.ndarray | None = None,
                   requirement: Requirement | None = None) -> dict:
    """`inview` (n_cell, n_time, n_sat) bool -> per-cell MBB arrays.

    Returns {mbb_feasible (bool n_cell), worst_overlap_steps (int n_cell; -1 = n/a),
    n_handovers (int n_cell; -1 = n/a)}.

    When `plane_uid` and `requirement` are supplied the richer `mbb_continuity_cell_req`
    path is used and a `worst_gap_steps` array (int n_cell; -1 = n/a) is added to the
    output. The existing 3-argument call signature keeps working unchanged.
    """
    use_req = plane_uid is not None and requirement is not None
    n_cell = inview.shape[0]
    feasible = np.zeros(n_cell, dtype=bool)
    worst = np.full(n_cell, -1, dtype=np.int64)
    nhand = np.full(n_cell, -1, dtype=np.int64)
    worst_gap = np.full(n_cell, -1, dtype=np.int64) if use_req else None
    for c in range(n_cell):
        if use_req:
            r = mbb_continuity_cell_req(inview[c], plane_uid, requirement)
            feasible[c] = r["feasible"]
            if r["worst_overlap_steps"] is not None:
                worst[c] = r["worst_overlap_steps"]
            if r["n_handovers"] is not None:
                nhand[c] = r["n_handovers"]
            if r["worst_gap_steps"] is not None:
                worst_gap[c] = r["worst_gap_steps"]
        else:
            r = mbb_continuity_cell(inview[c], min_overlap_steps, require_different_sat)
            feasible[c] = r["feasible"]
            if r["worst_overlap_steps"] is not None:
                worst[c] = r["worst_overlap_steps"]
            if r["n_handovers"] is not None:
                nhand[c] = r["n_handovers"]
    out = {"mbb_feasible": feasible, "worst_overlap_steps": worst, "n_handovers": nhand}
    if use_req:
        out["worst_gap_steps"] = worst_gap
    return out


def _merged_worst_gap_steps(ivs, n_time):
    """Largest uncovered run over [0, n_time-1] from the union of all intervals (independent of
    whether a serving path exists), in timesteps."""
    covered = np.zeros(n_time, dtype=bool)
    for _s, st, en in ivs:
        covered[st:en + 1] = True
    if covered.all():
        return 0
    # longest run of False
    worst = cur = 0
    for v in covered:
        cur = 0 if v else cur + 1
        worst = max(worst, cur)
    return worst


def mbb_continuity_cell_req(inview: np.ndarray, plane_uid: np.ndarray,
                             req: Requirement) -> dict:
    """Full-requirement make-before-break verdict for one cell. Extends `mbb_continuity_cell`
    with the different-plane rule (via `plane_uid`, -1 = unknown -> conservatively reject) and a
    merged-interval worst-gap (reported even when infeasible)."""
    n_time = int(inview.shape[0])
    thr = max(int(req.min_overlap_steps), 1)
    ivs = intervals_from_inview(inview)
    worst_gap = _merged_worst_gap_steps(ivs, n_time) if ivs else n_time
    if not ivs:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None,
                "worst_gap_steps": worst_gap}
    ivs.sort(key=lambda x: (x[2], x[1]))
    m = len(ivs)
    INF = n_time + 1
    best = [None] * m
    hops = [0] * m
    for i, (_s, st, _en) in enumerate(ivs):
        if st <= 0:
            best[i] = INF
    for i in range(m):
        if best[i] is None:
            continue
        si, sti, eni = ivs[i]
        for j in range(i + 1, m):
            sj, stj, enj = ivs[j]
            if enj <= eni:
                continue
            if req.require_different_sat and sj == si:
                continue
            if req.require_different_plane:
                pi, pj = int(plane_uid[si]), int(plane_uid[sj])
                if pi < 0 or pj < 0 or pi == pj:          # unknown -> conservative reject
                    continue
            ov = min(eni, enj) - max(sti, stj) + 1
            if ov < thr:
                continue
            cand = best[i] if best[i] < ov else ov
            if best[j] is None or cand > best[j]:
                best[j] = cand
                hops[j] = hops[i] + 1
    goals = [i for i in range(m) if best[i] is not None and ivs[i][2] >= n_time - 1]
    if not goals:
        return {"feasible": False, "worst_overlap_steps": None, "n_handovers": None,
                "worst_gap_steps": worst_gap}
    gi = max(goals, key=lambda i: best[i])
    b = best[gi]
    return {"feasible": True, "worst_overlap_steps": (None if b >= INF else int(b)),
            "n_handovers": int(hops[gi]), "worst_gap_steps": 0}
