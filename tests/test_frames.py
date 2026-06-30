import numpy as np
from datetime import datetime, timezone
from ngso_sls.geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from ngso_sls.constants import RE_EQ


def test_geodetic_equator_prime_meridian():
    p = geodetic_to_ecef(0.0, 0.0, 0.0)
    np.testing.assert_allclose(p, [RE_EQ, 0.0, 0.0], atol=1e-6)


def test_enu_up_unit_and_radial_at_equator():
    up = enu_up(0.0, 0.0)
    np.testing.assert_allclose(up, [1.0, 0.0, 0.0], atol=1e-12)


def test_eci_ecef_zero_gmst_identity():
    r = np.array([[[7000.0, 0.0, 0.0]]])
    out = eci_to_ecef(r, np.array([0.0]))
    np.testing.assert_allclose(out, r, atol=1e-9)


def test_gmst_runs_vectorized():
    g = gmst_rad(datetime(2026, 1, 1, tzinfo=timezone.utc), np.array([0.0, 3600.0]))
    assert g.shape == (2,) and np.all((g >= 0) & (g < 2 * np.pi))
