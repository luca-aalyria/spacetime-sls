import matplotlib
matplotlib.use("Agg")
import numpy as np
import plotly.graph_objects as go
from ngso_sls.viz.plots import (
    plot_availability,
    plot_availability_map,
    plot_coverage_hexmap,
    plot_sats_in_view_hexmap,
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


def test_world_borders_bundled():
    from ngso_sls.geodata import all_border_rings, country_polygons
    assert len(all_border_rings()) > 100          # ~289 border rings bundled
    assert len(all_border_rings()[0][0]) == 2     # each point is [lon, lat]
    assert len(country_polygons("India")) >= 1     # India polygon present


def test_plotly_geo_map_returns_figure():
    fig = plot_availability_map(_res())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1  # one Scattergeo trace


def test_hexmap_returns_figure_with_polygons():
    import h3
    cells = [h3.latlng_to_cell(lat, 80.0, 3) for lat in (10.0, 20.0, 30.0)]
    res = {
        "cells": cells,
        "lat": np.array([10.0, 20.0, 30.0]),
        "lon": np.array([80.0, 80.0, 80.0]),
        "availability": np.array([0.2, 0.6, 1.0]),
        "sats_in_view_mean": np.array([3.0, 8.0, 15.0]),
        "min_elev_deg": 25.0,
    }
    assert len(plot_coverage_hexmap(res).axes[0].collections) >= 1  # availability hexes
    assert len(plot_sats_in_view_hexmap(res).axes[0].collections) >= 1  # sats-in-view hexes
    # configurable opacity is applied to the hex PolyCollection
    fig = plot_coverage_hexmap(res, alpha=0.3)
    assert any(abs((c.get_alpha() or 1.0) - 0.3) < 1e-9 for c in fig.axes[0].collections)


def test_sweep_plots_import_without_plotly(monkeypatch):
    import sys, importlib
    monkeypatch.setitem(sys.modules, "plotly", None)      # simulate plotly absent
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", None)
    import ngso_sls.viz.plots as p
    importlib.reload(p)
    from ngso_sls.viz.plots import plot_multi_shape_scatter, plot_multi_shape_heatmap
    sweep = {"candidates": [
                {"N": 16, "planes": 4, "sats_per_plane": 4, "pct_by_k": {1: 0.6},
                 "pct_mbb": 0.4, "mbb_pass": False, "is_pareto": False},
                {"N": 48, "planes": 6, "sats_per_plane": 8, "pct_by_k": {1: 0.95},
                 "pct_mbb": 0.9, "mbb_pass": True, "is_pareto": True}],
             "min_N_by_k": {1: 48}, "min_N_mbb": 48, "continuity_overlap_s": 30.0,
             "k_values": [1], "planes_values": [4, 6], "spp_values": [4, 8],
             "target_availability": 0.9, "area_grade": 0.8,
             "altitude_km": 650.0, "inclination_deg": 53.0}
    assert len(plot_multi_shape_scatter(sweep, k=1).axes) >= 1
    assert len(plot_multi_shape_heatmap(sweep, k=1).axes) >= 1
    importlib.reload(p)                                    # restore for other tests


def test_mbb_hexmap_and_sweep_overlay():
    import h3
    from ngso_sls.viz.plots import plot_mbb_feasible_hexmap, plot_min_sat_sweep
    cells = [h3.latlng_to_cell(lat, 80.0, 3) for lat in (10.0, 20.0, 30.0)]
    res = {
        "cells": cells, "lat": np.array([10.0, 20.0, 30.0]), "lon": np.array([80.0, 80.0, 80.0]),
        "min_elev_deg": 25.0, "continuity_overlap_s": 30.0,
        "mbb_feasible": np.array([False, True, True]),
    }
    assert len(plot_mbb_feasible_hexmap(res).axes[0].collections) >= 1
    # sweep plot with the MBB gate overlay (fail flag + min-N marker)
    sweep = {
        "sweep": [
            {"N": 240, "planes": 6, "sats_per_plane": 40, "mean_sats_in_view": 3.0,
             "pct_by_k": {1: 0.8}, "mean_avail_by_k": {1: 0.9}, "pct_mbb": 0.5, "mbb_pass": False},
            {"N": 480, "planes": 6, "sats_per_plane": 80, "mean_sats_in_view": 6.0,
             "pct_by_k": {1: 1.0}, "mean_avail_by_k": {1: 1.0}, "pct_mbb": 0.97, "mbb_pass": True},
        ],
        "min_N_by_k": {1: 240}, "min_N_mbb": 480, "continuity_overlap_s": 30.0, "k_values": [1],
        "target_availability": 0.95, "area_grade": 0.95,
        "planes": 6, "altitude_km": 650.0, "inclination_deg": 53.0,
    }
    assert len(plot_min_sat_sweep(sweep).axes) >= 1
