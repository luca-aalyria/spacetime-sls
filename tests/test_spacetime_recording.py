from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.recording import RecordedEntityStore, record


def test_record_then_replay_matches_memory_store(tmp_path):
    mem = MemoryEntityStore.from_fixture("mini_constellation.json")
    path = tmp_path / "snap.json"
    record(mem, str(path), intent_states=["INSTALLED"])
    rec = RecordedEntityStore(str(path))
    assert [e["id"] for e in rec.list_entities()] == [e["id"] for e in mem.list_entities()]
    assert rec.list_relationships() == mem.list_relationships()
    assert [i["id"] for i in rec.list_intents(states=["INSTALLED"])] == \
           [i["id"] for i in mem.list_intents(states=["INSTALLED"])]
