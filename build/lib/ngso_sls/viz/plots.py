import matplotlib.pyplot as plt


def plot_availability(res: dict):
    """Scatter map of per-cell coverage availability over the AOR."""
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(
        res["lon"], res["lat"], c=res["availability"], s=40, cmap="RdYlGn", vmin=0, vmax=1
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Coverage availability (min elev {res['min_elev_deg']}°)")
    fig.colorbar(sc, ax=ax, label="availability")
    return fig
