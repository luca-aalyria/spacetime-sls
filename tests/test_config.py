import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig


def test_timegrid_times():
    tg = TimeGrid(epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=30.0, step_s=10.0)
    np.testing.assert_allclose(tg.times_s(), [0.0, 10.0, 20.0])


def test_simconfig_defaults():
    sh = Shell("p", 1200, 40, 1, 650.0, 48.0)
    sc = SimConfig(Constellation((sh,)), TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 30.0))
    assert sc.k_coverage == 2 and sc.target_availability is None and sc.cell_layout == "UNSPEC"
    assert sh.min_elev_user_deg == 25.0


# --- Task 4: GeneralizedShell + constellation_model() + continuity params ---
from ngso_sls.config import (GeneralizedShell, constellation_model)
from ngso_sls.constellation.model import OrbitTemplate, PlaneSpec
from ngso_sls.constants import RE_EQ


def test_constellation_model_from_walker_shell_matches_elems():
    shell = Shell("s", 24, 6, 1, 650.0, 53.0)
    m = constellation_model(Constellation((shell,)))
    from ngso_sls.constellation.walker import walker_elements
    assert np.array_equal(m.elems, walker_elements(shell))


def test_generalized_shell_and_multishell_concat():
    g = GeneralizedShell("g", "explicit_planes",
                         template=OrbitTemplate(a_km=RE_EQ + 600.0, inc_rad=np.radians(50.0)),
                         planes=(PlaneSpec(raan_rad=0.0, phase_rad=(0.0, 1.0)),
                                 PlaneSpec(raan_rad=1.0, phase_rad=(0.0, 1.0))))
    m = constellation_model(Constellation((Shell("w", 12, 3, 1, 650.0, 53.0), g)))
    assert m.n_sat == 12 + 4
    assert set(np.unique(m.shell_id).tolist()) == {0, 1}


def test_simconfig_continuity_defaults():
    sim = SimConfig(Constellation((Shell("s", 12, 3, 1, 650.0, 53.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0))
    assert sim.min_handover_overlap_s == 0.0 and sim.require_different_sat is True
    assert sim.make_before_break_gate is False and sim.max_handover_rate_hz == float("inf")
