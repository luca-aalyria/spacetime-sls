import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go


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
    ax.set_xlabel("mean satellites in view (≥ min elev)")
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
