import pandas as pd
import numpy as np
from ngso_sls.io.csv_io import write_availability_csv, write_elements_csv, load_elements_csv


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


def test_elements_csv_roundtrip(tmp_path):
    elems = np.array([[7028.137, 0.0, 0.925, 0.0, 0.0, 0.0],
                      [7028.137, 0.0, 0.925, 1.047, 0.0, 2.094]])
    sat_ids = ["plat-0", "plat-1"]
    path = tmp_path / "elements.csv"
    write_elements_csv(elems, sat_ids, str(path), manifest={"ref_epoch_s": 1000.0})
    e2, ids2 = load_elements_csv(str(path))
    assert ids2 == sat_ids and np.allclose(e2, elems)
