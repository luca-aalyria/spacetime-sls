import numpy as np
import pytest
from datetime import datetime, timezone
from ngso_sls.presets import jio_constellation
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig, constellation_model
from ngso_sls.pipeline import run_coverage, run_coverage_h3, run_coverage_h3_elements
from ngso_sls.grids.aor import INDIA_AOR, AORS


def test_pipeline_jio_india_smoke():
    cons = jio_constellation()
    assert sum(s.walker_T for s in cons.shells) == 1600
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), duration_s=600.0, step_s=60.0)
    sc = SimConfig(cons, tg)
    res = run_coverage(sc, aor=INDIA_AOR, grid_step_deg=4.0)
    assert res["availability"].shape == res["lat"].shape
    assert np.all((res["availability"] >= 0) & (res["availability"] <= 1))
    assert res["availability"].max() > 0.0


def test_elements_seam_matches_shell_path():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1800.0, 60.0))
    viashell = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5)
    m = constellation_model(sim.constellation)
    viaelems = run_coverage_h3_elements(m.elems, m.plane_uid, 25.0, sim.time_grid,
                                        AORS["India"], cell_res=2, shard_res=1, chunk_steps=5)
    assert np.array_equal(viashell["availability_by_k"][2], viaelems["availability_by_k"][2])


def test_apoapsis_max_alt_used(monkeypatch):
    # an eccentric single shell: apoapsis alt = a(1+e)-RE_EQ must exceed a-RE_EQ
    from ngso_sls.constants import RE_EQ
    a = RE_EQ + 650.0
    elems = np.array([[a, 0.1, np.radians(53.0), 0.0, 0.0, 0.0]])
    captured = {}
    import ngso_sls.pipeline as pl
    real = pl.conservative_dilation_deg
    def spy(max_alt, *args, **kw):
        captured["max_alt"] = max_alt
        return real(max_alt, *args, **kw)
    monkeypatch.setattr(pl, "conservative_dilation_deg", spy)
    tg = TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 600.0, 60.0)
    run_coverage_h3_elements(elems, np.zeros(1, np.int64), 25.0, tg, AORS["India"],
                             cell_res=2, shard_res=1, chunk_steps=5)
    assert captured["max_alt"] > 650.0 + 1.0        # apoapsis, not a-RE_EQ (=650)


def test_nyquist_precondition_raises_when_step_too_coarse():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1200.0, 60.0))
    # tau=30s but step=60s violates step <= 0.5*tau -> must raise
    with pytest.raises(ValueError, match="step_s"):
        run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=5,
                        continuity_overlap_s=30.0)


def test_continuity_outputs_carry_resolution_metadata():
    sim = SimConfig(Constellation((Shell("s", 24, 6, 1, 650.0, 53.0, min_elev_user_deg=25.0),)),
                    TimeGrid(datetime(2026, 1, 1, tzinfo=timezone.utc), 1200.0, 5.0))
    res = run_coverage_h3(sim, AORS["India"], cell_res=2, shard_res=1, chunk_steps=20,
                          continuity_overlap_s=30.0)
    assert res["detection_step_s"] == 5.0 and "refine_tol_s" in res
    assert res["mbb_feasible"].shape == (len(res["cells"]),)
