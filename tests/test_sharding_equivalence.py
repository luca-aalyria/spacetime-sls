import numpy as np
from datetime import datetime, timezone
from ngso_sls.presets import jio_constellation
from ngso_sls.config import TimeGrid, SimConfig
from ngso_sls.pipeline import run_coverage_h3
from ngso_sls.grids.aor import INDIA_AOR


def _sim():
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=600.0, step_s=60.0)
    return SimConfig(jio_constellation(), tg)


def test_sharded_equals_monolithic_bit_identical():
    sim = _sim()
    glob = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=None)
    shard = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=1, chunk_steps=4)
    # same cells, same order
    assert glob["cells"] == shard["cells"]
    # the invariant: bit-identical availability regardless of sharding/chunking
    np.testing.assert_array_equal(glob["availability"], shard["availability"])
    # and the same for mean sats-in-view (also an integer-count reduction)
    np.testing.assert_array_equal(glob["sats_in_view_mean"], shard["sats_in_view_mean"])


def test_progress_callback_reports_all_shards():
    calls = []
    run_coverage_h3(_sim(), INDIA_AOR, cell_res=3, shard_res=1, chunk_steps=4,
                    progress=lambda done, total: calls.append((done, total)))
    assert calls[0][0] == 0                 # starts at 0/total
    assert calls[-1][0] == calls[-1][1] >= 1  # ends at done == total


def test_chunking_alone_is_identical():
    sim = _sim()
    one = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=None, chunk_steps=None)
    many = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=None, chunk_steps=3)
    np.testing.assert_array_equal(one["availability"], many["availability"])
