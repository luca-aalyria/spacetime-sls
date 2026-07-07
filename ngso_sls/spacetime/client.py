# ngso_sls/spacetime/client.py
"""Live gRPC EntityStore. The ONLY file that builds channels/stubs. All proto/grpc access is
lazy (via _deps), so importing this module is safe in the sandbox; only CONSTRUCTING
GrpcEntityStore requires spacetime-api. Read-only: no mutating RPC is ever wired."""
from . import _deps
from .store import StoreError


def _make_channel(ep):
    """Modern auth (decided): auth.Credentials(...).create_channel(url). Portable fallback via
    github/py Config/new_credentials when no Credentials class is present. The 256MB
    max_receive_message_length is REQUIRED on BOTH paths (full-constellation ListEntities
    responses are large). Never logs the key."""
    _deps.require("HAS_AUTH", "aalyria.spacetime.api.common.auth")
    auth = _deps.auth
    opts = [("grpc.max_receive_message_length", 256 << 20)]
    if hasattr(auth, "Credentials"):
        creds = auth.Credentials(key_id=ep.key_id, user_id=ep.user_id,
                                 private_key_file=ep.private_key_file)
        try:
            return creds.create_channel(ep.url, options=opts)     # 256MB limit (modern path)
        except TypeError:
            # older create_channel signature has no options kwarg; degrade within the modern
            # path (size limit best-effort — verify against the installed spacetime-api in Colab)
            return creds.create_channel(ep.url)
    # portable fallback: github/py Config/new_credentials -> secure_channel WITH the 256MB option
    grpc = _deps.grpc
    cfg = auth.Config(email=ep.user_id, private_key_id=ep.key_id,
                      private_key=open(ep.private_key_file, "rb"))
    call = auth.new_credentials(cfg)
    chan_creds = grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), call)
    target = ep.url.replace("https://", "")
    return grpc.secure_channel(target, chan_creds, opts)


class GrpcEntityStore:
    """EntityStore over a live Spacetime instance."""
    def __init__(self, endpoint):
        self._ep = endpoint
        _deps.require("HAS_MODEL", "aalyria.spacetime.api.model.v1 (Model service)")
        channel = _make_channel(endpoint)
        self._model = _deps.model_pb2_grpc.ModelStub(channel)
        self._nbi = _deps.nbi_pb2_grpc.NbiStub(channel) if _deps.HAS_NBI else None
        self._prov = (_deps.provisioning_pb2_grpc.ProvisioningStub(channel)
                      if _deps.HAS_PROVISIONING else None)
        self._model_pb2 = _deps.model_pb2
        self._nbi_pb2 = _deps.nbi_pb2

    # --- request factory (overridable in tests) ---
    def _req(self, name, **kw):
        return getattr(self._model_pb2, name)(**kw)

    # --- READ-ONLY surface ---
    def list_entities(self):
        try:
            return list(self._model.ListEntities(self._req("ListEntitiesRequest")).entities)
        except Exception as e:                       # normalize; never import grpc in callers
            raise StoreError.rpc(f"ListEntities failed: {type(e).__name__}")

    def list_relationships(self, cel: str | None = None):
        try:
            req = self._req("ListRelationshipsRequest", **({"filter": cel} if cel else {}))
            return list(self._model.ListRelationships(req).relationships)
        except Exception as e:
            raise StoreError.rpc(f"ListRelationships failed: {type(e).__name__}")

    def get_entity(self, entity_id: str):
        try:
            return self._model.GetEntity(self._req("GetEntityRequest", entity_id=entity_id))
        except Exception as e:
            raise StoreError.not_found(f"GetEntity({entity_id}) failed: {type(e).__name__}")

    def list_intents(self, states=None):
        if self._nbi is None:
            raise StoreError.rpc("Nbi service unavailable (HAS_NBI=False)")
        try:
            intents = list(self._nbi.ListIntents(self._nbi_pb2.ListIntentsRequest()).intents)
        except Exception as e:
            raise StoreError.rpc(f"ListIntents failed: {type(e).__name__}")
        if states is not None:
            sset = set(states)
            intents = [i for i in intents if getattr(i, "state", None) in sset]
        return intents
