import pandas as pd


def write_availability_csv(res: dict, path, manifest: dict):
    """Write per-cell coverage availability as a tidy CSV with a manifest header."""
    df = pd.DataFrame(
        {
            "cell_id": range(len(res["lat"])),
            "lat": res["lat"],
            "lon": res["lon"],
            "availability": res["availability"],
        }
    )
    with open(path, "w") as f:
        for k, v in manifest.items():
            f.write(f"# {k}: {v}\n")
        f.write(f"# min_elev_deg: {res['min_elev_deg']}\n")
        df.to_csv(f, index=False)
