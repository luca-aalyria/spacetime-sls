from ngso_sls.presets import JIO_SCENARIOS, jio_constellation
from ngso_sls.constellation.walker import walker_elements


def test_jio_full_is_1600_dual_shell():
    cons = jio_constellation()
    assert sum(s.walker_T for s in cons.shells) == 1600
    assert len(cons.shells) == 2


def test_all_scenarios_valid_walker():
    for name, cons in JIO_SCENARIOS.items():
        assert len(cons.shells) >= 1, name
        for s in cons.shells:
            assert s.walker_T % s.walker_P == 0, f"{name}: {s.walker_T}/{s.walker_P} not divisible"
            el = walker_elements(s)                 # must expand without error
            assert el.shape == (s.walker_T, 6), name
