import pandas as pd
import numpy as np
from ngso_sls.io.csv_io import write_availability_csv


def test_write_availability_csv(tmp_path):
    res = {
        "lat": np.array([0.0, 1.0]),
        "lon": np.array([10.0, 11.0]),
        "availability": np.array([0.5, 1.0]),
        "min_elev_deg": 25.0,
    }
    path = tmp_path / "avail.csv"
    write_availability_csv(res, path, manifest={"seed": 0, "cell_layout": "UNSPEC"})
    df = pd.read_csv(path, comment="#")
    assert list(df.columns) == ["cell_id", "lat", "lon", "availability"]
    assert len(df) == 2
