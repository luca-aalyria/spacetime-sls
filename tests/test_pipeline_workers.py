# workers=N must be BIT-IDENTICAL to serial (same guarantee as sharded==monolithic).
import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import TimeGrid
from ngso_sls.grids.aor import AORS
from ngso_sls.pipeline import run_coverage_h3_elements
from ngso_sls.explorer import WalkerConstellationBuilder


def _run(workers):
    b = WalkerConstellationBuilder()
    b.scenario.value = "Custom (Walker)"
    b.planes1.value, b.spp1.value = 6, 8
    elems, pu, _ = b.elements()
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=1200.0, step_s=10.0)
    return run_coverage_h3_elements(elems, pu, 25.0, tg, AORS["India"], cell_res=3,
                                    shard_res=1, chunk_steps=10, k_values=[1, 2],
                                    continuity_overlap_s=20.0, workers=workers)


def test_parallel_workers_bit_identical_to_serial():
    a, b = _run(None), _run(4)
    for k in (1, 2):
        assert np.array_equal(a["availability_by_k"][k], b["availability_by_k"][k])
    assert np.array_equal(a["sats_in_view_mean"], b["sats_in_view_mean"])
    assert np.array_equal(a["mbb_feasible"], b["mbb_feasible"])
    assert np.array_equal(a["mbb_worst_gap_s"], b["mbb_worst_gap_s"])
