import pandas as pd


def write_availability_csv(res: dict, path, manifest: dict):
    """Write per-cell coverage availability as a tidy CSV with a manifest header.

    The manifest (the run's input parameters) is written as `# key: value` comment lines so
    every output file is self-describing/reproducible. Make-before-break columns are included
    when the run computed them."""
    cols = {
        "cell_id": range(len(res["lat"])),
        "lat": res["lat"],
        "lon": res["lon"],
        "availability": res["availability"],
    }
    if "mbb_feasible" in res:
        cols["mbb_feasible"] = res["mbb_feasible"].astype(int)
        cols["mbb_overlap_worst_s"] = res["mbb_overlap_worst_s"]
        cols["mbb_n_handovers"] = res["mbb_n_handovers"]
    df = pd.DataFrame(cols)
    with open(path, "w") as f:
        for k, v in manifest.items():
            f.write(f"# {k}: {v}\n")
        f.write(f"# min_elev_deg: {res['min_elev_deg']}\n")
        df.to_csv(f, index=False)
