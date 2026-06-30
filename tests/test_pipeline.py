import numpy as np
from datetime import datetime, timezone
from ngso_sls.presets import jio_constellation
from ngso_sls.config import TimeGrid, SimConfig
from ngso_sls.pipeline import run_coverage
from ngso_sls.grids.aor import INDIA_AOR


def test_pipeline_jio_india_smoke():
    cons = jio_constellation()
    assert sum(s.walker_T for s in cons.shells) == 1600
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=600.0, step_s=60.0)
    sc = SimConfig(cons, tg)
    res = run_coverage(sc, aor=INDIA_AOR, grid_step_deg=4.0)
    assert res["availability"].shape == res["lat"].shape
    assert np.all((res["availability"] >= 0) & (res["availability"] <= 1))
    assert res["availability"].max() > 0.0
