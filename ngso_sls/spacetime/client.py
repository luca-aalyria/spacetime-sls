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
        self._nbi = _deps.nbi_pb2_grpc.NbiStub(channel) if _deps.HAS_NBI else None
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
