# tests/test_spacetime_client.py
import pytest
from ngso_sls.spacetime.client import GrpcEntityStore
from ngso_sls.spacetime.config import SpacetimeEndpoint


def _ep():
    return SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_file="/x.key")


def test_grpc_store_raises_clear_error_without_package():
    # spacetime-api absent in the sandbox -> constructing the live store fails clearly, not obscurely
    with pytest.raises(RuntimeError, match="spacetime-api"):
        GrpcEntityStore(_ep())


class _FakeModelStub:
    """Hand-written double matching the verified Model wire signatures (offline stub-parity)."""
    def __init__(self):
        self.calls = []
    def ListEntities(self, req):
        self.calls.append(("ListEntities", type(req).__name__))
        return type("R", (), {"entities": [{"id": "plat-0", "kind": 11}]})()
    def ListRelationships(self, req):
        self.calls.append(("ListRelationships", type(req).__name__))
        return type("R", (), {"relationships": [{"kind": 4, "a": "plat-0", "z": "ant-0"}]})()
    def GetEntity(self, req):
        self.calls.append(("GetEntity", type(req).__name__))
        return {"id": "plat-0", "kind": 11}


def test_model_absent_intents_work_entities_fail_clearly():
    # A build with HAS_NBI but HAS_MODEL=False must still allow the proven intents pull, and fail
    # the NMTS/Model path PER-OPERATION with a clear message (not at construction).
    from ngso_sls.spacetime.store import StoreError
    store = GrpcEntityStore.__new__(GrpcEntityStore)         # bypass __init__ (no channel)
    store._model = None                                      # Model surface absent
    class _Nbi:
        def ListIntents(self, req):
            return type("R", (), {"intents": [type("I", (), {"state": "INSTALLED"})()]})()
    store._nbi = _Nbi()
    store._nbi_pb2 = type("M", (), {"ListIntentsRequest": staticmethod(lambda: object())})
    assert len(store.list_intents(states=["INSTALLED"])) == 1     # proven surface works
    with pytest.raises(StoreError, match="Model service unavailable"):
        store.list_entities()
    with pytest.raises(StoreError, match="Model service unavailable"):
        store.list_relationships()


def test_stub_parity_reads_only_and_never_mutates():
    # inject fake stubs so we exercise the request routing offline, with no grpc/proto import
    store = GrpcEntityStore.__new__(GrpcEntityStore)          # bypass __init__ (no channel)
    fake = _FakeModelStub()
    store._model = fake
    store._nbi = None
    store._prov = None
    store._req = lambda name, **kw: {"__req__": name, **kw}    # request factory double
    ents = store.list_entities()
    rels = store.list_relationships()
    assert ents and rels
    names = [c[0] for c in fake.calls]
    assert names == ["ListEntities", "ListRelationships"]
    # no mutating verb was ever called
    assert not any(v in n for n in names for v in ("Create", "Update", "Delete", "Upsert"))
