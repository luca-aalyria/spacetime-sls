from ngso_sls import constants as c


def test_constants_present_and_sane():
    assert abs(c.MU_EARTH - 398600.4418) < 1e-6
    assert abs(c.RE_EQ - 6378.137) < 1e-6
    assert 1.0e-3 < c.J2 < 1.1e-3
    assert 0.0 < c.WGS84_E2 < 0.01
