import numpy as np
from ngso_sls.coverage.visibility import max_elev_and_count
from ngso_sls.coverage.availability import availability


def test_max_and_count():
    # (n_cell=1, n_time=2, n_sat=3)
    el = np.array([[[10.0, 40.0, -5.0], [-1.0, -2.0, 30.0]]])
    mx, cnt = max_elev_and_count(el, min_elev_deg=25.0)
    np.testing.assert_allclose(mx, [[40.0, 30.0]])
    np.testing.assert_array_equal(cnt, [[1, 1]])


def test_availability_integer_fraction():
    cnt = np.array([[1, 0, 1, 1]])  # 3 of 4 timesteps serviceable
    np.testing.assert_allclose(availability(cnt, k=1), [0.75])
