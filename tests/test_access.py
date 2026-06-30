import numpy as np
from ngso_sls.geometry.frames import geodetic_to_ecef, enu_up
from ngso_sls.geometry.access import elevation_deg
from ngso_sls.constants import RE_EQ


def test_elevation_overhead_and_horizon():
    cell = geodetic_to_ecef(0.0, 0.0, 0.0)[None, :]
    up = enu_up(0.0, 0.0)[None, :]
    overhead = np.array([[[RE_EQ + 650.0, 0.0, 0.0]]])
    el = elevation_deg(cell, up, overhead)
    np.testing.assert_allclose(el[0, 0, 0], 90.0, atol=1e-6)
    # true geometric horizon: satellite whose ECEF x-component equals the cell's
    # radius -> line-of-sight is perpendicular to local up -> elevation 0.
    h = 650.0
    y = np.sqrt((RE_EQ + h) ** 2 - RE_EQ**2)
    horizon = np.array([[[RE_EQ, y, 0.0]]])
    el2 = elevation_deg(cell, up, horizon)
    np.testing.assert_allclose(el2[0, 0, 0], 0.0, atol=1e-6)
    # a satellite a quarter-orbit away in longitude is well below the horizon
    far_y = np.array([[[0.0, RE_EQ + h, 0.0]]])
    el3 = elevation_deg(cell, up, far_y)
    assert el3[0, 0, 0] < -30.0
