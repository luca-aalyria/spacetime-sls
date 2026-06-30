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


def test_chunking_alone_is_identical():
    sim = _sim()
    one = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=None, chunk_steps=None)
    many = run_coverage_h3(sim, INDIA_AOR, cell_res=3, shard_res=None, chunk_steps=3)
    np.testing.assert_array_equal(one["availability"], many["availability"])
