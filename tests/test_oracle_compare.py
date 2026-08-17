# Oracle compare: rebuild nb01 outputs from (synthetic) beam-candidate segments.
import numpy as np
import pytest
from ngso_sls.spacetime import _deps
from ngso_sls.spacetime.oracle import beam_candidates_to_coverage

pytestmark = pytest.mark.skipif(not _deps.HAS_STORAGE, reason="vendored storage stubs absent")


def _seg(bucket, antenna, lat, lon, acc, res_s=10, start=1000):
    pb = _deps.storage_pb2
    e = pb.Entity(id=f"T:{bucket}#{antenna}@{lat}/{lon}")
    s = e.beam_candidate_segment
    s.interval.start_time.seconds = start
    s.sampling_resolution.seconds = res_s
    s.accessibilities.extend(acc)
    return e

def test_aggregates_to_nb01_shape():
    ents = [
        _seg("b", "sat-1-platform-a0", 10.0, 70.0, [True, True, False]),
        _seg("b", "sat-2-platform-a0", 10.0, 70.0, [True, False, False]),
        _seg("b", "sat-1-platform-a1", 10.0, 70.0, [True, True, False]),  # same sat, 2nd antenna
        _seg("b", "sat-1-platform-a0", 20.0, 75.0, [False, False, False]),
    ]
    res = beam_candidates_to_coverage(ents, cell_res=3, k_values=(1, 2))
    i = list(zip(res["lat"], res["lon"])).index((10.0, 70.0))
    # t0: sats {1,2}; t1: {1} (antenna dedup!); t2: {}
    assert res["availability_by_k"][1][i] == pytest.approx(2 / 3)
    assert res["availability_by_k"][2][i] == pytest.approx(1 / 3)
    assert res["sats_in_view_mean"][i] == pytest.approx(1.0)
    j = 1 - i if len(res["lat"]) == 2 else None
    assert res["availability_by_k"][1][1 - i] == 0.0
    assert len(res["cells"]) == 2 and res["n_samples"] == 3

def test_live_smoke_if_forward_up():
    from ngso_sls.spacetime.oracle import read_beam_candidates
    import datetime
    prefix = "T:" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H")
    try:
        ents = read_beam_candidates(bucket_prefix=prefix, dump_timeout_s=120)
    except Exception:
        pytest.skip("no live store reachable")
    if not ents:
        pytest.skip("bucket empty")
    res = beam_candidates_to_coverage(ents, k_values=(1, 2))
    assert res["n_points"] > 0 and 0.0 <= res["availability"].mean() <= 1.0
    print(f"LIVE ORACLE: {res['n_points']} points, {res['n_samples']} samples, "
          f"k1 mean {res['availability_by_k'][1].mean():.3f}, "
          f"siv mean {res['sats_in_view_mean'].mean():.2f}")
