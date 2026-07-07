from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.store import StoreError
import pytest


def test_memory_store_from_fixture_lists_and_gets():
    st = MemoryEntityStore.from_fixture("mini_constellation.json")
    ents = st.list_entities()
    kinds = sorted({e["kind"] for e in ents})
    assert 11 in kinds and 40 in kinds                 # ek_platform=11, ek_antenna=40
    rels = st.list_relationships()
    assert any(r["kind"] == 4 for r in rels)           # RK_CONTAINS=4
    intents = st.list_intents(states=["INSTALLED"])
    assert intents and all(i["state"] == "INSTALLED" for i in intents)
    first_id = ents[0]["id"]
    assert st.get_entity(first_id)["id"] == first_id
    with pytest.raises(StoreError):
        st.get_entity("does-not-exist")
