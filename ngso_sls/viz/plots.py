import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection
import h3
import plotly.graph_objects as go

from ..geodata import all_border_rings

_HEX_ALPHA = 0.80  # cell opacity default; lets country borders show through the coverage cells


def _draw_borders(ax):
    ax.add_collection(LineCollection(all_border_rings(), colors="0.25", linewidths=0.5, zorder=3))


def _hexmap(res, values, label, title, cmap, vmin=None, vmax=None, alpha=_HEX_ALPHA):
    """2D geographic map (matplotlib): H3 cells as translucent hexagons colored by `values`,
    over country borders. `alpha` (0-1) sets cell opacity so borders show through.
    Renders reliably in Colab/Jupyter (plain matplotlib, no JS/downloads)."""
    polys = []
    for c in res["cells"]:
        # h3 boundary is [(lat, lng), ...]; matplotlib wants (x=lon, y=lat)
        polys.append([(lng, lat) for (lat, lng) in h3.cell_to_boundary(c)])
    pc = PolyCollection(polys, array=np.asarray(values, dtype=float), cmap=cmap,
                        edgecolors="none", alpha=float(alpha), zorder=2)
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


def plot_coverage_hexmap(res: dict, title: str = "Coverage availability", alpha: float = _HEX_ALPHA):
    """Geographic map of per-cell coverage availability (fraction of time, 0-1)."""
    return _hexmap(res, res["availability"], "availability (fraction of time)", title,
                   cmap="RdYlGn", vmin=0.0, vmax=1.0, alpha=alpha)


def plot_sats_in_view_hexmap(res: dict, title: str = "Mean satellites in view (time-avg)",
                             alpha: float = _HEX_ALPHA):
    """Geographic map of the time-averaged number of satellites in view (>= min elev) per cell.
    (Instantaneously the count is an integer; this is its mean over the run's timesteps.)"""
    return _hexmap(res, res["sats_in_view_mean"], "mean satellites in view (time-avg)", title,
                   cmap="viridis", vmin=0.0, vmax=None, alpha=alpha)


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


def plot_min_sat_sweep(sweep: dict):
    """Coverage vs constellation size (matplotlib): % of AOR cells meeting the availability
    target vs total satellites N, one curve per k, with the area-grade line and per-k minimum-N
    markers (k=1 = single coverage, k=2 = handover-capable dual coverage)."""
    s = sweep["sweep"]
    N = [r["N"] for r in s]
    colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for k in sweep["k_values"]:
        c = colors.get(k, None)
        pct = [100.0 * r["pct_by_k"][k] for r in s]
        ax.plot(N, pct, "-o", ms=5, color=c, label=f"k={k}: % cells ≥ {sweep['target_availability']:.0%} avail")
        mn = sweep["min_N_by_k"].get(k)
        if mn is not None:
            ax.axvline(mn, ls=":", lw=1.6, color=c)
            ax.annotate(f"min N(k={k})={mn}", xy=(mn, 5), color=c, fontsize=8,
                        rotation=90, va="bottom", ha="right")
    ax.axhline(100.0 * sweep["area_grade"], ls="--", color="0.4", lw=1,
               label=f"area grade {sweep['area_grade']:.0%}")
    ax.set_xlabel("total satellites (N)")
    ax.set_ylabel(f"% of area with ≥ {sweep['target_availability']:.0%} availability")
    ax.set_ylim(0, 101)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title(f"Coverage vs constellation size "
                 f"({sweep['inclination_deg']:g}° @ {sweep['altitude_km']:g} km, {sweep['planes']} planes)")
    return fig


def plot_inclination_sweep(result: dict):
    """Minimum satellites N vs inclination, one line per k (gaps where the target is not reached
    within the swept range). Identifies the inclination that minimizes the constellation size."""
    incs = result["inclinations"]
    colors = {1: "tab:blue", 2: "tab:orange", 3: "tab:green", 4: "tab:red"}
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for k in result["k_values"]:
        y = [b["min_N_by_k"][k] for b in result["by_inclination"]]
        y = [np.nan if v is None else v for v in y]         # 'not reached' -> gap
        ax.plot(incs, y, "-o", ms=5, color=colors.get(k), label=f"k={k} min N")
    ax.set_xlabel("inclination (deg)")
    ax.set_ylabel("minimum satellites N")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title(f"Minimum N vs inclination ({result['planes']} planes @ {result['altitude_km']:g} km; "
                 f"{result['area_grade']:.0%} of area @ {result['target_availability']:.0%} avail)")
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
