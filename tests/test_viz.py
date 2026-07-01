import matplotlib
matplotlib.use("Agg")
import numpy as np
import plotly.graph_objects as go
from ngso_sls.viz.plots import (
    plot_availability,
    plot_availability_map,
    plot_sats_in_view_vs_latitude,
    plot_availability_hist,
)


def _res():
    return {
        "cells": ["a", "b", "c"],
        "lat": np.array([6.0, 20.0, 34.0]),
        "lon": np.array([70.0, 80.0, 90.0]),
        "availability": np.array([0.1, 0.5, 0.9]),
        "sats_in_view_mean": np.array([2.0, 8.0, 12.0]),
        "min_elev_deg": 25.0,
    }


def test_matplotlib_plots_return_figures():
    r = _res()
    assert len(plot_availability(r).axes) >= 1
    assert len(plot_sats_in_view_vs_latitude(r).axes) >= 1
    assert len(plot_availability_hist(r).axes) >= 1


def test_plotly_geo_map_returns_figure():
    fig = plot_availability_map(_res())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1  # one Scattergeo trace
