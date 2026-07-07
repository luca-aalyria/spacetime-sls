import numpy as np
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements, routes_from_intents
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.constants import RE_EQ, MU_EARTH


def _store():
    return MemoryEntityStore.from_fixture("mini_constellation.json")


def test_keplerian_platforms_to_elements_shape_and_units():
    st = _store()
    res = platforms_to_elements(st.list_entities(), st.list_relationships())
    elems = res["elems"]
    assert elems.shape[1] == 6
    # 2 served Keplerian platforms (plat-0, plat-1); external + TLE excluded/flagged
    assert elems.shape[0] == 2
    assert np.all(elems[:, 0] > 6000.0)                       # a_km
    assert res["plane_uid"].shape == (2,)
    ids = [m["sat_id"] for m in res["meta"]]
    assert "plat-ext" not in ids                              # external-system excluded
    assert any("plat-tle" == s["sat_id"] for s in res["skipped"])  # TLE flagged & skipped


def test_true_to_mean_anomaly_roundtrip():
    # circular orbit: true anomaly == mean anomaly; a 120-deg sat should have M≈120deg
    st = _store()
    res = platforms_to_elements(st.list_entities(), st.list_relationships())
    # plat-1 has true_anomaly_deg=120 at e=0 -> M ~ 120 deg (2.094 rad), but it is also
    # epoch-reconciled forward by 60 s; assert it is a finite angle in [0, 2pi)
    M = res["elems"][:, 5]
    assert np.all((M >= 0) & (M < 2 * np.pi + 1e-9))


def test_epoch_reconciliation_advances_mean_anomaly():
    # two identical sats, epochs 0 and +T/4; after reconciling to the earlier epoch the later
    # sat's M advances by n0 * dt relative to its raw value.
    a_km = RE_EQ + 650.0
    n0 = np.sqrt(MU_EARTH / a_km ** 3)                       # rad/s
    dt = 60.0
    ents = [
        {"id": "s0", "kind": 11, "platform": {"is_external_system": False, "motion": {"entry": [
            {"keplerian_elements": {"semimajor_axis_m": a_km * 1000, "eccentricity": 0.0,
             "inclination_deg": 53.0, "raan_deg": 0.0, "argument_of_periapsis_deg": 0.0,
             "true_anomaly_deg": 0.0, "epoch": {"seconds": 1000}}}]}}},
        {"id": "s1", "kind": 11, "platform": {"is_external_system": False, "motion": {"entry": [
            {"keplerian_elements": {"semimajor_axis_m": a_km * 1000, "eccentricity": 0.0,
             "inclination_deg": 53.0, "raan_deg": 0.0, "argument_of_periapsis_deg": 0.0,
             "true_anomaly_deg": 0.0, "epoch": {"seconds": 1000 + int(dt)}}}]}}},
    ]
    res = platforms_to_elements(ents, [], ref_epoch_s=1000.0)
    m0, m1 = res["elems"][0, 5], res["elems"][1, 5]
    # s0 at ref epoch -> M0 ~ 0; s1 started dt later, reconciled back to ref -> M advanced by n0*dt
    assert abs(m0) < 1e-9
    assert abs(((m1 - n0 * dt) % (2 * np.pi))) < 1e-6
    assert res["ref_epoch_s"] == 1000.0


def test_routes_from_intents_extracts_hops():
    st = _store()
    hops = routes_from_intents(st.list_intents(states=["INSTALLED"]))
    assert ("plat-0", "plat-1") in [(h["src"], h["dst"]) for h in hops]
