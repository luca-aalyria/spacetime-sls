import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig


def test_timegrid_times():
    tg = TimeGrid(epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=30.0, step_s=10.0)
    np.testing.assert_allclose(tg.times_s(), [0.0, 10.0, 20.0])


def test_simconfig_defaults():
    sh = Shell("p", 1200, 40, 1, 650.0, 48.0)
    sc = SimConfig(Constellation((sh,)), TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 30.0))
    assert sc.k_coverage == 1 and sc.target_availability is None and sc.cell_layout == "UNSPEC"
    assert sh.min_elev_user_deg == 25.0
