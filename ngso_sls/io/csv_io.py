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


def write_elements_csv(elems, sat_ids, path, manifest: dict | None = None):
    """Write a pulled constellation's (n,6) elements as a tidy CSV with a manifest header."""
    import numpy as np
    df = pd.DataFrame({
        "sat_id": list(sat_ids),
        "a_km": elems[:, 0], "e": elems[:, 1], "i_rad": elems[:, 2],
        "raan_rad": elems[:, 3], "argp_rad": elems[:, 4], "M_rad": elems[:, 5],
    })
    with open(path, "w") as f:
        for k, v in (manifest or {}).items():
            f.write(f"# {k}: {v}\n")
        df.to_csv(f, index=False)


def load_elements_csv(path):
    """Inverse of write_elements_csv -> (elems (n,6) float64, sat_ids list[str])."""
    import numpy as np
    df = pd.read_csv(path, comment="#")
    elems = df[["a_km", "e", "i_rad", "raan_rad", "argp_rad", "M_rad"]].to_numpy(dtype=float)
    return elems, df["sat_id"].astype(str).tolist()
