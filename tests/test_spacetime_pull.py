from datetime import datetime, timezone
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.pull import pull_and_cover
from ngso_sls.grids.aor import AORS


def test_pull_and_cover_end_to_end_offline():
    store = MemoryEntityStore.from_fixture("mini_constellation.json")
    out = pull_and_cover(store, AORS["India"], cell_res=2, min_elev_user_deg=25.0,
                         duration_s=600.0, step_s=60.0,
                         epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert out["n_served"] == 2                      # 2 Keplerian non-external platforms
    assert out["coverage"]["availability"].shape[0] == len(out["coverage"]["cells"])
    assert "routes" in out and out["routes"]         # installed intent hop present
    assert "skipped" in out                          # external + TLE reported


def test_pull_and_cover_raises_on_zero_served():
    import pytest
    store = MemoryEntityStore.from_dict({"entities": [], "relationships": [], "intents": []})
    with pytest.raises(ValueError, match="no served Keplerian platforms"):
        pull_and_cover(store, AORS["India"])
