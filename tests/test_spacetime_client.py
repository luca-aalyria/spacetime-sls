# tests/test_spacetime_client.py
import base64
import os
import pytest
from ngso_sls.spacetime.client import GrpcEntityStore, _key_bytes, _materialize_key_file
from ngso_sls.spacetime.config import SpacetimeEndpoint
from ngso_sls.spacetime.store import StoreError


def _ep():
    return SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_file="/x.key")


def test_key_bytes_from_base64():
    raw = b"-----BEGIN KEY-----\nabc\n-----END KEY-----\n"
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u",
                           private_key_b64=base64.b64encode(raw).decode())
    assert _key_bytes(ep) == raw


def test_key_bytes_from_file(tmp_path):
    p = tmp_path / "k.pem"
    p.write_bytes(b"FILEKEY")
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_file=str(p))
    assert _key_bytes(ep) == b"FILEKEY"


def test_key_bytes_missing_raises():
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u")
    with pytest.raises(StoreError, match="no private key"):
        _key_bytes(ep)


def test_key_bytes_bad_base64_raises():
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_b64="A")
    with pytest.raises(StoreError, match="not valid base64"):
        _key_bytes(ep)


def test_materialize_key_file_is_0600_and_shredded():
    path, cleanup = _materialize_key_file(b"SECRETKEY")
    try:
        assert os.path.exists(path)
        assert (os.stat(path).st_mode & 0o777) == 0o600         # owner-only
        with open(path, "rb") as f:
            assert f.read() == b"SECRETKEY"
    finally:
        cleanup()
    assert not os.path.exists(path)                             # cleanup removed it
    cleanup()                                                    # idempotent (no raise)


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

    # NetOps facade double: ListEntities(type=INTENT) -> Entity records with an `intent` oneof.
    class _Intent:
        def __init__(self, state):
            self.state = state
    class _Entity:
        def __init__(self, intent):
            self._intent = intent
            self.intent = intent
        def HasField(self, name):
            return name == "intent" and self._intent is not None
    class _NetOps:
        def ListEntities(self, req):
            return type("R", (), {"entities": [_Entity(_Intent("INSTALLED"))]})()
    store._nbi = _NetOps()
    store._nbi_pb2 = type("M", (), {
        "ListEntitiesRequest": staticmethod(lambda **kw: object()),
        "EntityType": type("E", (), {"INTENT": 6}),
    })
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


def test_list_intents_with_real_vendored_stubs():
    # Upgrade of the hand-double test: with vendor/spacetime_api_stubs on sys.path the whole
    # request/response path uses REAL generated messages (proto2 oneof, real INTENT=6 enum).
    from ngso_sls.spacetime import _deps
    if not _deps.HAS_NBI:
        pytest.skip("vendored NBI stubs not on sys.path")
    pb = _deps.nbi_pb2

    captured = {}
    class _NetOps:
        def ListEntities(self, req):
            captured["req"] = req
            resp = pb.ListEntitiesResponse()
            e = resp.entities.add()
            e.id = "intent-001"
            e.intent.SetInParent()                    # real oneof arm
            resp.entities.add(id="not-an-intent")     # oneof unset -> filtered by HasField
            return resp

    store = GrpcEntityStore.__new__(GrpcEntityStore)  # bypass __init__ (no channel)
    store._model = None
    store._nbi = _NetOps()
    store._nbi_pb2 = pb
    intents = store.list_intents()
    assert isinstance(captured["req"], pb.ListEntitiesRequest)
    assert captured["req"].type == pb.EntityType.Value("INTENT") == 6
    assert len(intents) == 1                          # HasField filtering on the real proto
