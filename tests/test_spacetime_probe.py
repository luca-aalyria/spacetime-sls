from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.config import SpacetimeEndpoint
from ngso_sls.spacetime.probe import probe_store, probe_endpoint, format_report


def _store():
    return MemoryEntityStore.from_fixture("mini_constellation.json")


def test_probe_store_stages_against_fixture():
    stages = probe_store(_store())
    by = {s["stage"].split(" ")[0]: s for s in stages}
    assert all(s["ok"] for s in stages)                       # every stage passes on the fixture
    assert "1 INSTALLED" in by["intents"]["detail"]
    assert "4 platform(s), 2 antenna(s)" in by["entities"]["detail"]
    # 2 keplerian served (plat-0, plat-1); plat-tle skipped; plat-ext external
    assert "2 keplerian served" in by["platform"]["detail"]
    assert "2 RK_CONTAINS" in by["relationships"]["detail"]


def test_probe_store_flags_all_tle_constellation():
    data = {"entities": [{"id": "t", "kind": 11, "platform": {"is_external_system": False,
             "motion": {"entry": [{"tle": {"line1": "1 ...", "line2": "2 ..."}}]}}}],
            "relationships": [], "intents": []}
    stages = probe_store(MemoryEntityStore.from_dict(data))
    motion = next(s for s in stages if s["stage"] == "platform motion")
    assert motion["ok"] is False                              # no usable Keplerian motion -> FAIL
    assert "0 keplerian served" in motion["detail"]


def test_probe_endpoint_degrades_offline():
    # in the sandbox spacetime-api is absent -> the live store can't be built; probe still reports
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_file="/x.key")
    report = probe_endpoint(ep)
    assert report["store_built"] is False
    assert report["capability_flags"]["HAS_MODEL"] is False
    assert "spacetime-api" in report.get("error", "")
    text = format_report(report)
    assert "capability flags" in text and "NOT built" in text
