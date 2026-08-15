# StorageEntityStore against a REAL in-process gRPC Store server built from the vendored
# proto_internal.storage stubs — full wire round-trip (serialize/deserialize), not doubles.
# This is the raw-Store access path (engdoc: storage service, port 9999, reached via
# kubectl port-forward; plaintext gRPC).
from concurrent import futures

import pytest

from ngso_sls.spacetime import _deps
from ngso_sls.spacetime.store import EntityStore, StoreError

pytestmark = pytest.mark.skipif(
    not (_deps.HAS_STORAGE and _deps.grpc is not None),
    reason="vendored storage stubs or grpcio not available")


def _servicer():
    spb = _deps.storage_pb2
    sgrpc = _deps.storage_pb2_grpc

    class FakeStore(sgrpc.StoreServicer):
        def __init__(self):
            self.requests = []

        def GetEntities(self, request, context):
            self.requests.append(request)
            if request.type == spb.EntityType.Value("INTENT"):
                e = spb.Entity(id="intent-001")
                e.intent.SetInParent()
                yield spb.GetEntitiesResponsePart(entity=e)
                bare = spb.Entity(id="no-value-arm")     # deletion/foreign arm -> filtered
                yield spb.GetEntitiesResponsePart(entity=bare)
            elif request.type == spb.EntityType.Value("NMTS_ENTITY"):
                e = spb.Entity(id="plat-0")
                e.nmts_entity.SetInParent()
                yield spb.GetEntitiesResponsePart(entity=e)
            elif request.type == spb.EntityType.Value("NMTS_RELATIONSHIP"):
                e = spb.Entity(id="rel-0")
                e.nmts_relationship.SetInParent()
                yield spb.GetEntitiesResponsePart(entity=e)

        def Get(self, request, context):
            self.requests.append(request)
            resp = spb.GetResponse()
            if request.id == "plat-0":
                resp.entity.id = "plat-0"
                resp.entity.nmts_entity.SetInParent()
            return resp

    return FakeStore()


@pytest.fixture()
def store_server():
    server = _deps.grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    servicer = _servicer()
    _deps.storage_pb2_grpc.add_StoreServicer_to_server(servicer, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    yield f"localhost:{port}", servicer
    server.stop(grace=None)


def test_list_intents_wire_roundtrip(store_server):
    from ngso_sls.spacetime.client import StorageEntityStore
    target, servicer = store_server
    with StorageEntityStore(target) as store:
        intents = store.list_intents()
    assert len(intents) == 1                          # oneof-unset entity filtered out
    req = servicer.requests[0]
    assert req.type == _deps.storage_pb2.EntityType.Value("INTENT") == 6
    assert req.WhichOneof("time_spec") == "current"   # snapshot query, not history


def test_nmts_and_get_entity_roundtrip(store_server):
    from ngso_sls.spacetime.client import StorageEntityStore
    target, _ = store_server
    with StorageEntityStore(target) as store:
        assert len(store.list_entities()) == 1
        assert len(store.list_relationships()) == 1
        assert store.get_entity("plat-0") is not None
        with pytest.raises(StoreError, match="no NMTS_ENTITY"):
            store.get_entity("missing")
        with pytest.raises(StoreError, match="CEL"):
            store.list_relationships(cel="a == b")    # raw Store has no CEL filter


def test_satisfies_entity_store_protocol(store_server):
    from ngso_sls.spacetime.client import StorageEntityStore
    target, _ = store_server
    with StorageEntityStore(target) as store:
        assert isinstance(store, EntityStore)


def test_connection_error_normalized_no_grpc_leak():
    from ngso_sls.spacetime.client import StorageEntityStore
    store = StorageEntityStore("localhost:1")         # nothing listens here
    with pytest.raises(StoreError):                   # normalized, not grpc.RpcError
        store.list_intents()
    store.close()


def test_entity_view_and_state_filter_adapter_compat(store_server):
    # The raw Store returns nmts.v1.Entity (ek_* oneof) and enum-int intent states; the
    # adapter expects Model-API shapes (int kind, .platform payload, state NAMES).
    from ngso_sls.spacetime.client import StorageEntityStore, _NmtsEntityView
    spb = _deps.storage_pb2

    e = spb.Entity(id="sat-1")
    e.nmts_entity.id = "sat-1"
    e.nmts_entity.ek_platform.name = "SAT-1"
    kep = e.nmts_entity.ek_platform.motion.entry.add().keplerian_elements
    kep.semimajor_axis_m = 7_000_000.0
    kep.inclination_deg = 53.0
    view = _NmtsEntityView(e.nmts_entity)
    assert view.kind == 11 and view.id == "sat-1"            # ek_platform field number
    assert view.platform.name == "SAT-1"                     # bare-name payload alias
    assert view.platform.motion.entry[0].keplerian_elements.inclination_deg == 53.0

    # adapter end-to-end on the view: one Keplerian platform -> one element row
    from ngso_sls.spacetime import nmts_adapter
    out = nmts_adapter.platforms_to_elements([view], [])
    assert out["elems"].shape == (1, 6)

    # intent state filter maps enum ints to names
    from api.nbi.v1alpha.resources import intent_pb2
    from ngso_sls.spacetime.client import _filter_intent_states
    i_inst = intent_pb2.Intent(state=intent_pb2.IntentState.Value("INSTALLED"))
    i_sched = intent_pb2.Intent(state=intent_pb2.IntentState.Value("SCHEDULED"))
    assert _filter_intent_states([i_inst, i_sched], ["INSTALLED"]) == [i_inst]


def test_geodetic_platforms_skipped_not_zero_kepler():
    # Proto pitfall: unset oneof message fields read back as DEFAULT instances. A gateway
    # (geodetic motion) must be SKIPPED, not parsed as an all-zero Keplerian orbit.
    from ngso_sls.spacetime.client import _NmtsEntityView
    from ngso_sls.spacetime import nmts_adapter
    spb = _deps.storage_pb2

    gw = spb.Entity(id="gw-1")
    gw.nmts_entity.id = "gw-1"
    gw.nmts_entity.ek_platform.name = "GW-1"
    geo = gw.nmts_entity.ek_platform.motion.entry.add().geodetic_wgs84
    geo.latitude_deg = -5.62

    sat = spb.Entity(id="sat-1")
    sat.nmts_entity.id = "sat-1"
    kep = sat.nmts_entity.ek_platform.motion.entry.add().keplerian_elements
    kep.semimajor_axis_m = 7_535_439.0
    kep.inclination_deg = 53.0

    out = nmts_adapter.platforms_to_elements(
        [_NmtsEntityView(gw.nmts_entity), _NmtsEntityView(sat.nmts_entity)], [])
    assert out["elems"].shape == (1, 6)                      # only the satellite
    assert [s["sat_id"] for s in out["skipped"]] == ["gw-1"]
