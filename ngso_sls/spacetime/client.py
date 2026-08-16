# ngso_sls/spacetime/client.py
"""Live gRPC EntityStore. The ONLY file that builds channels/stubs. All proto/grpc access is
lazy (via _deps), so importing this module is safe in the sandbox; only CONSTRUCTING
GrpcEntityStore requires spacetime-api. Read-only: no mutating RPC is ever wired."""
import atexit
import base64
import io
import os
import tempfile

from . import _deps
from .store import StoreError


def _key_bytes(ep) -> bytes:
    """Private key bytes from `private_key_b64` (base64 content; preferred) or `private_key_file`
    (path). The key material is never placed in error strings."""
    if ep.private_key_b64:
        try:
            return base64.b64decode(ep.private_key_b64.strip())    # tolerant of wrapped base64
        except Exception:
            raise StoreError.rpc("private_key_b64 is not valid base64 (expected `base64 -w0 key.pem`)")
    if ep.private_key_file:
        with open(ep.private_key_file, "rb") as f:
            return f.read()
    raise StoreError.rpc("no private key provided: set private_key_b64 (base64 of the key, e.g. "
                         "from a Colab secret) or private_key_file")


def _materialize_key_file(data: bytes):
    """Write key bytes to a 0600 temp file, RAM-backed (/dev/shm) when available so the key never
    touches persistent disk. Returns (path, cleanup); cleanup overwrites then unlinks the file."""
    tmpdir = "/dev/shm" if os.path.isdir("/dev/shm") else None      # tmpfs (RAM) on Linux/Colab
    fd, path = tempfile.mkstemp(prefix=".stkey_", dir=tmpdir)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)

    def _cleanup(p=path):
        try:                                                       # best-effort shred
            with open(p, "r+b") as f:
                n = f.seek(0, 2)
                f.seek(0)
                f.write(b"\x00" * n)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            pass
        try:
            os.unlink(p)
        except Exception:
            pass

    return path, _cleanup


def _make_channel(ep):
    """Build an authenticated channel and return (channel, cleanup). The 256MB
    max_receive_message_length is set on BOTH auth paths (full-constellation ListEntities
    responses are large). The key is taken from `private_key_pem` (content) or `private_key_file`
    (path); pem content never lands on persistent disk — the fallback path uses the bytes
    directly, and the modern path materializes a RAM-backed 0600 temp file that `cleanup` shreds.
    Never logs the key."""
    _deps.require("HAS_AUTH", "aalyria.spacetime.api.common.auth")
    auth = _deps.auth
    opts = [("grpc.max_receive_message_length", 256 << 20)]
    data = _key_bytes(ep)
    if hasattr(auth, "Credentials"):
        # modern path needs a FILE path -> materialize to a RAM-backed 0600 temp file, kept for
        # the store's lifetime (JWTs may be signed per-RPC) and shredded on cleanup.
        key_path, cleanup = _materialize_key_file(data)
        try:
            creds = auth.Credentials(key_id=ep.key_id, user_id=ep.user_id,
                                     private_key_file=key_path)
            try:
                return creds.create_channel(ep.url, options=opts), cleanup   # 256MB (modern)
            except TypeError:
                # older create_channel signature has no options kwarg (limit best-effort)
                return creds.create_channel(ep.url), cleanup
        except Exception:
            cleanup()
            raise
    # portable fallback: Config accepts key CONTENT directly -> no temp file at all
    grpc = _deps.grpc
    cfg = auth.Config(email=ep.user_id, private_key_id=ep.key_id, private_key=io.BytesIO(data))
    call = auth.new_credentials(cfg)
    chan_creds = grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), call)
    target = ep.url.replace("https://", "")
    return grpc.secure_channel(target, chan_creds, opts), (lambda: None)


class GrpcEntityStore:
    """EntityStore over a live Spacetime instance."""
    def __init__(self, endpoint):
        self._ep = endpoint
        # Construction requires only HAS_AUTH (to build the channel). Model / Nbi / Provisioning
        # stubs are built only if their surface is present; a missing surface fails PER-OPERATION,
        # so the proven intents/provisioning pull still works on a build that ships no Model.
        channel, self._key_cleanup = _make_channel(endpoint)     # requires HAS_AUTH
        atexit.register(self._key_cleanup)                       # shred temp key on interpreter exit
        self._model = _deps.model_pb2_grpc.ModelStub(channel) if _deps.HAS_MODEL else None
        # Revived read-only NBI intent facade: service NetOps (ListEntities/ListEntitiesOverTime).
        self._nbi = _deps.nbi_pb2_grpc.NetOpsStub(channel) if _deps.HAS_NBI else None
        self._prov = (_deps.provisioning_pb2_grpc.ProvisioningStub(channel)
                      if _deps.HAS_PROVISIONING else None)
        self._model_pb2 = _deps.model_pb2
        self._nbi_pb2 = _deps.nbi_pb2

    def close(self):
        """Shred any RAM-backed temp key file. Safe to call multiple times."""
        cleanup = getattr(self, "_key_cleanup", None)
        if cleanup is not None:
            cleanup()
            self._key_cleanup = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _model_or_raise(self):
        if self._model is None:
            raise StoreError.rpc(
                "Model service unavailable (HAS_MODEL=False) — this spacetime-api build ships no "
                "NMTS Model service, so the entity/relationship (NMTS→coverage) path can't run. "
                "The NBI intents/provisioning surface is still usable (store.list_intents).")
        return self._model

    # --- request factory (overridable in tests) ---
    def _req(self, name, **kw):
        return getattr(self._model_pb2, name)(**kw)

    # --- READ-ONLY surface ---
    def list_entities(self):
        model = self._model_or_raise()
        try:
            return list(model.ListEntities(self._req("ListEntitiesRequest")).entities)
        except StoreError:
            raise
        except Exception as e:                       # normalize; never import grpc in callers
            raise StoreError.rpc(f"ListEntities failed: {type(e).__name__}")

    def list_relationships(self, cel: str | None = None):
        model = self._model_or_raise()
        try:
            req = self._req("ListRelationshipsRequest", **({"filter": cel} if cel else {}))
            return list(model.ListRelationships(req).relationships)
        except StoreError:
            raise
        except Exception as e:
            raise StoreError.rpc(f"ListRelationships failed: {type(e).__name__}")

    def get_entity(self, entity_id: str):
        model = self._model_or_raise()
        try:
            return model.GetEntity(self._req("GetEntityRequest", entity_id=entity_id))
        except StoreError:
            raise
        except Exception as e:
            raise StoreError.not_found(f"GetEntity({entity_id}) failed: {type(e).__name__}")

    def list_intents(self, states=None):
        """Current installed intents via the revived read-only NetOps facade:
        ListEntities(type=INTENT) returns Entity records whose `intent` oneof arm carries the
        resources.Intent. Intent is the same generated message the adapter already consumes."""
        if self._nbi is None:
            raise StoreError.rpc("NBI NetOps intent facade unavailable (HAS_NBI=False)")
        pb = self._nbi_pb2
        try:
            req = pb.ListEntitiesRequest(type=pb.EntityType.INTENT)
            entities = self._nbi.ListEntities(req).entities
        except Exception as e:                       # normalize; never import grpc in callers
            raise StoreError.rpc(f"NetOps.ListEntities(INTENT) failed: {type(e).__name__}")
        intents = [e.intent for e in entities if e.HasField("intent")]
        return _filter_intent_states(intents, states)


def _intent_state_name(intent):
    """Intent state as its enum NAME ('INSTALLED', ...). Real protos store an enum int; the
    enum descriptor maps it back to the name. Fixture dicts/doubles may already hold the
    name — returned as-is."""
    s = intent.get("state") if isinstance(intent, dict) else getattr(intent, "state", None)
    if isinstance(s, int):
        try:
            return intent.DESCRIPTOR.fields_by_name["state"].enum_type.values_by_number[s].name
        except Exception:
            return s
    return s


def _filter_intent_states(intents, states):
    if states is None:
        return intents
    sset = set(states)
    return [i for i in intents if _intent_state_name(i) in sset]


def _grpc_detail(e) -> str:
    """Compact diagnostic for a normalized gRPC failure. UNAVAILABLE almost always means
    nothing is listening on the target — i.e. the kubectl port-forward is not running on
    THIS machine (each machine needs its own; a sandbox/host forward is not shared)."""
    try:
        code = e.code().name           # grpc.RpcError
    except Exception:
        return type(e).__name__
    hint = " (no listener on target — is the port-forward running on this machine?)" \
        if code == "UNAVAILABLE" else ""
    return f"{type(e).__name__}[{code}]{hint}"


class _NmtsEntityView:
    """Adapter-compatible view of a raw nmts.v1.Entity. The adapter (built for the Model API
    shape) expects `kind` as an int and the payload under a bare name (`.platform`); the raw
    proto has an ek_* oneof whose FIELD NUMBER is that kind int (ek_platform=11,
    ek_antenna=40). Everything else passes through to the wrapped proto."""
    def __init__(self, proto):
        self.proto = proto
        self._arm = proto.WhichOneof("kind")
        self.id = proto.id
        self.kind = proto.DESCRIPTOR.fields_by_name[self._arm].number if self._arm else -1

    def __getattr__(self, name):                     # only called for names not set above
        arm = self.__dict__["_arm"]
        proto = self.__dict__["proto"]
        if arm is not None and name == arm[3:]:      # 'platform' -> proto.ek_platform
            return getattr(proto, arm)
        return getattr(proto, name)


class StorageEntityStore:
    """READ-ONLY EntityStore over the raw internal Store (`minkowski.proto.Store`, port 9999).

    Access path (engdoc "Storage Services"): the storage backend serves plaintext gRPC
    in-cluster; reach it with `kubectl port-forward svc/<storage-svc> -n <ns> 9999:9999`
    (or storectl's supervised forward) and point this store at localhost:9999. The security
    boundary is cluster access (kubectl credentials), NOT this channel — there is no key auth
    on the raw Store, which is why this is a dev/ops path; the key-authed product path stays
    the NetOps intent facade.

    Compared to the facade this reads EVERY dataset (intents, NMTS, link reports, schedules,
    beam-candidate/propagation-vector segments) with the full EntityFilter — but requires
    kubectl access wherever the notebook runs (local Jupyter yes; Colab only with cluster
    creds in the runtime). Read-only: only Get/GetEntities are wired; Write/Listen are not.
    """
    def __init__(self, target: str = "localhost:9999"):
        _deps.require("HAS_STORAGE", "proto_internal.storage (vendored stubs)")
        if _deps.grpc is None:
            raise StoreError.connection("grpcio is not installed")
        self._pb = _deps.storage_pb2
        # plaintext by design: the transport is the kubectl port-forward tunnel
        self._channel = _deps.grpc.insecure_channel(
            target, options=[("grpc.max_receive_message_length", 256 << 20)])
        self._store = _deps.storage_pb2_grpc.StoreStub(self._channel)

    def close(self):
        self._channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get_entities(self, type_name: str):
        """Stream Store.GetEntities(type, current) and return the storage Entity wrappers."""
        pb = self._pb
        req = pb.GetEntitiesRequest(type=pb.EntityType.Value(type_name))
        req.current.SetInParent()                 # time_spec: current state
        try:
            return [part.entity for part in self._store.GetEntities(req)]
        except Exception as e:                    # normalize; never import grpc in callers
            raise StoreError.rpc(f"Store.GetEntities({type_name}) failed: {_grpc_detail(e)}")

    # --- EntityStore protocol (read-only) ---
    def list_entities(self):
        return [_NmtsEntityView(e.nmts_entity) for e in self._get_entities("NMTS_ENTITY")
                if e.HasField("nmts_entity")]

    def list_relationships(self, cel: str | None = None):
        if cel is not None:
            raise StoreError.rpc("raw Store has no CEL filter; filter client-side or use the "
                                 "Model API (list_relationships(cel=...) on GrpcEntityStore)")
        return [e.nmts_relationship for e in self._get_entities("NMTS_RELATIONSHIP")
                if e.HasField("nmts_relationship")]

    def get_entity(self, entity_id: str):
        pb = self._pb
        try:
            resp = self._store.Get(pb.GetRequest(id=entity_id,
                                                 type=pb.EntityType.Value("NMTS_ENTITY")))
        except Exception as e:
            raise StoreError.rpc(f"Store.Get({entity_id}) failed: {_grpc_detail(e)}")
        if not resp.HasField("entity"):
            raise StoreError.not_found(f"no NMTS_ENTITY with id {entity_id!r}")
        return _NmtsEntityView(resp.entity.nmts_entity)

    def list_intents(self, states=None):
        intents = [e.intent for e in self._get_entities("INTENT") if e.HasField("intent")]
        return _filter_intent_states(intents, states)
