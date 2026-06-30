import numpy as np
from ngso_sls.propagation.base import Propagator
from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator
from ngso_sls.constants import MU_EARTH, RE_EQ


def _circular_elem(alt_km, inc_deg, raan=0.0, M0=0.0):
    return np.array([[RE_EQ + alt_km, 0.0, np.radians(inc_deg), raan, 0.0, M0]])


def test_protocol_runtime():
    assert isinstance(KeplerJ2Propagator(), Propagator)


def test_circular_two_body_radius_constant():
    prop = KeplerJ2Propagator(j2=0.0)
    el = _circular_elem(650.0, 48.0)
    a = el[0, 0]
    n = np.sqrt(MU_EARTH / a**3)
    period = 2 * np.pi / n
    t = np.linspace(0, period, 50)
    r = prop.propagate(el, t)
    rad = np.linalg.norm(r, axis=-1)[0]
    np.testing.assert_allclose(rad, a, rtol=1e-9)
    np.testing.assert_allclose(r[0, 0], r[0, -1], atol=1e-3)


def test_sso_nodal_regression():
    # ~700 km sun-sync (inc ~98.19 deg) -> RAAN drift ~ +0.9856 deg/day
    prop = KeplerJ2Propagator()
    el = _circular_elem(700.0, 98.19)
    raan_dot_deg_day = np.degrees(prop.raan_dot(el)[0]) * 86400.0
    assert 0.95 < raan_dot_deg_day < 1.02
