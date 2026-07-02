import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection
import h3
import plotly.graph_objects as go

from ..geodata import all_border_rings

_HEX_ALPHA = 0.55  # let country borders show through the coverage cells


def _draw_borders(ax):
    ax.add_collection(LineCollection(all_border_rings(), colors="0.25", linewidths=0.5, zorder=3))


def _hexmap(res, values, label, title, cmap, vmin=None, vmax=None):
    """2D geographic map (matplotlib): H3 cells as translucent hexagons colored by `values`,
    over country borders. Renders reliably in Colab/Jupyter (plain matplotlib, no JS/downloads)."""
    polys = []
    for c in res["cells"]:
        # h3 boundary is [(lat, lng), ...]; matplotlib wants (x=lon, y=lat)
        polys.append([(lng, lat) for (lat, lng) in h3.cell_to_boundary(c)])
    pc = PolyCollection(polys, array=np.asarray(values, dtype=float), cmap=cmap,
                        edgecolors="none", alpha=_HEX_ALPHA, zorder=2)
    pc.set_clim(vmin if vmin is not None else float(np.min(values)),
                vmax if vmax is not None else float(np.max(values)))
    fig, ax = plt.subplots(figsize=(8, 6))
    _draw_borders(ax)               # country outlines (drawn above the translucent hexes too)
    ax.add_collection(pc)
    # frame the Area of Responsibility (padded), so the service area fills the view
    lon, lat = np.asarray(res["lon"]), np.asarray(res["lat"])
    padx = max(2.0, 0.1 * (lon.max() - lon.min()))
    pady = max(2.0, 0.1 * (lat.max() - lat.min()))
    ax.set_xlim(lon.min() - padx, lon.max() + padx)
    ax.set_ylim(lat.min() - pady, lat.max() + pady)
    lat_mid = float(np.mean(lat))
    ax.set_aspect(1.0 / max(np.cos(np.radians(lat_mid)), 0.1))  # rough lon/lat distortion fix
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{title} (min elev {res['min_elev_deg']}°)")
    fig.colorbar(pc, ax=ax, label=label)
    return fig


def plot_coverage_hexmap(res: dict, title: str = "Coverage availability"):
    """Geographic map of per-cell coverage availability (fraction of time, 0-1)."""
    return _hexmap(res, res["availability"], "availability (fraction of time)", title,
                   cmap="RdYlGn", vmin=0.0, vmax=1.0)


def plot_sats_in_view_hexmap(res: dict, title: str = "Mean satellites in view (time-avg)"):
    """Geographic map of the time-averaged number of satellites in view (>= min elev) per cell.
    (Instantaneously the count is an integer; this is its mean over the run's timesteps.)"""
    return _hexmap(res, res["sats_in_view_mean"], "mean satellites in view (time-avg)", title,
                   cmap="viridis", vmin=0.0, vmax=None)


def plot_availability(res: dict):
    """Simple matplotlib scatter of per-cell coverage availability over the AOR."""
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(
        res["lon"], res["lat"], c=res["availability"], s=40, cmap="RdYlGn", vmin=0, vmax=1
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Coverage availability (min elev {res['min_elev_deg']}°)")
    fig.colorbar(sc, ax=ax, label="availability")
    return fig


def plot_availability_map(res: dict, title: str = "Coverage availability"):
    """Interactive 2D geographic map (Plotly) of per-cell availability over the service area,
    with coastlines + country borders, auto-zoomed to the AOR."""
    fig = go.Figure(
        go.Scattergeo(
            lon=res["lon"],
            lat=res["lat"],
            mode="markers",
            marker=dict(
                size=7,
                color=res["availability"],
                colorscale="RdYlGn",
                cmin=0.0,
                cmax=1.0,
                colorbar=dict(title="availability"),
                line=dict(width=0),
            ),
            text=[f"avail={a:.3f}" for a in res["availability"]],
            hovertemplate="%{lat:.2f}, %{lon:.2f}<br>%{text}<extra></extra>",
        )
    )
    fig.update_geos(
        showcoastlines=True,
        showcountries=True,
        showland=True,
        landcolor="rgb(243,243,243)",
        resolution=50,
        fitbounds="locations",
    )
    fig.update_layout(
        title=f"{title} (min elev {res['min_elev_deg']}°)",
        margin=dict(l=0, r=0, t=40, b=0),
        height=520,
    )
    return fig


def plot_sats_in_view_vs_latitude(res: dict, bin_deg: float = 1.0):
    """Mean satellites-in-view vs latitude (matplotlib), binned over the AOR cells."""
    lat = res["lat"]
    siv = res["sats_in_view_mean"]
    edges = np.arange(np.floor(lat.min()), np.ceil(lat.max()) + bin_deg, bin_deg)
    which = np.digitize(lat, edges)
    centers, means = [], []
    for b in range(1, len(edges)):
        m = which == b
        if m.any():
            centers.append(0.5 * (edges[b - 1] + edges[b]))
            means.append(siv[m].mean())
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(means, centers, "-o", ms=3, color="tab:blue")
    ax.set_xlabel("mean satellites in view (time-avg, ≥ min elev)")
    ax.set_ylabel("latitude (°)")
    ax.set_title("Satellites in view vs latitude")
    ax.grid(True, alpha=0.3)
    return fig


def plot_availability_hist(res: dict, bins: int = 20):
    """Distribution of per-cell coverage availability (matplotlib)."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(res["availability"], bins=bins, range=(0.0, 1.0), color="steelblue", edgecolor="white")
    ax.set_xlabel("coverage availability")
    ax.set_ylabel("number of cells")
    ax.set_title("Availability distribution across cells")
    ax.grid(True, alpha=0.3)
    return fig
