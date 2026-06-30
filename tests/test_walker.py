import numpy as np
import pytest
from ngso_sls.config import Shell
from ngso_sls.constellation.walker import walker_elements
from ngso_sls.constants import RE_EQ


def test_walker_shape_and_planes():
    el = walker_elements(Shell("p", 1200, 40, 1, 650.0, 48.0))
    assert el.shape == (1200, 6)
    raans = np.round(np.degrees(el[:, 3]), 6)
    assert len(np.unique(raans)) == 40
    np.testing.assert_allclose(el[:, 0], RE_EQ + 650.0)
    np.testing.assert_allclose(el[:, 2], np.radians(48.0))


def test_walker_divisibility_error():
    with pytest.raises(ValueError):
        walker_elements(Shell("p", 100, 7, 1, 650.0, 48.0))
