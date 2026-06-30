import matplotlib
matplotlib.use("Agg")
import numpy as np
from ngso_sls.viz.plots import plot_availability


def test_plot_returns_figure():
    res = {
        "lat": np.array([0.0, 1.0, 2.0]),
        "lon": np.array([0.0, 1.0, 2.0]),
        "availability": np.array([0.1, 0.5, 0.9]),
        "min_elev_deg": 25.0,
    }
    fig = plot_availability(res)
    assert fig is not None and len(fig.axes) >= 1
