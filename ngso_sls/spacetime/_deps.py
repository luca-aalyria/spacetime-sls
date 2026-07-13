"""Single home for OPTIONAL proto/grpc imports, probed PER SURFACE.

The modern pip package (`aalyria.spacetime.api.*`) and the bazel layout (`api.model.v1`,
`nmts.v1.proto`) never coexist, so a single shared try-block would be a guaranteed
false-negative. Each surface gets its own guarded probe + flag. Nothing here imports proto at
module import time beyond these guarded try blocks, so `import ngso_sls.spacetime` always
succeeds — even in this sandbox where `spacetime-api` is not installed.

The probes run at import AND are re-runnable via `reprobe()` — important on Colab, where the
package is often pip-installed AFTER this module was first imported; Python does not cache failed
imports, so a re-probe picks up a newly-installed package without a kernel restart."""

HAS_AUTH = HAS_NBI = HAS_PROVISIONING = HAS_MODEL = HAS_NMTS = False
auth = nbi_pb2 = nbi_pb2_grpc = provisioning_pb2 = provisioning_pb2_grpc = None
model_pb2 = model_pb2_grpc = nmts_pb2 = grpc = None
MODEL_ROOT = None                       # which import root resolved for Model, if any
NMTS_ROOT = None                        # which import root resolved for NMTS, if any
_FLAGS = {}

# Model service: pip then bazel roots, across v1 / v1alpha / v0 (packages & instances drift —
# e.g. a build may ship only model.v1alpha). Prefer newest stable first; record which resolved.
_MODEL_ROOTS = tuple(f"{_base}.model.{_ver}"
                     for _ver in ("v1", "v1alpha", "v0")
                     for _base in ("aalyria.spacetime.api", "api"))
_NMTS_ROOTS = ("aalyria.spacetime.api.nmts.v1.proto", "aalyria.spacetime.nmts.v1.proto",
               "nmts.v1.proto", "aalyria.spacetime.api.nmts.v2alpha.proto", "nmts.v2alpha.proto")


def _probe():
    """(Re)attempt all optional imports and (re)set the capability flags. Safe to call repeatedly."""
    global HAS_AUTH, HAS_NBI, HAS_PROVISIONING, HAS_MODEL, HAS_NMTS
    global auth, nbi_pb2, nbi_pb2_grpc, provisioning_pb2, provisioning_pb2_grpc
    global model_pb2, model_pb2_grpc, nmts_pb2, grpc, MODEL_ROOT, NMTS_ROOT, _FLAGS

    try:
        from aalyria.spacetime.api.common import auth as _auth
        auth, HAS_AUTH = _auth, True
    except Exception:
        auth, HAS_AUTH = None, False

    try:
        from aalyria.spacetime.api.nbi.v1alpha import nbi_pb2 as _n, nbi_pb2_grpc as _ng
        nbi_pb2, nbi_pb2_grpc, HAS_NBI = _n, _ng, True
    except Exception:
        nbi_pb2, nbi_pb2_grpc, HAS_NBI = None, None, False

    try:
        from aalyria.spacetime.api.provisioning.v1alpha import (
            provisioning_pb2 as _p, provisioning_pb2_grpc as _pg)
        provisioning_pb2, provisioning_pb2_grpc, HAS_PROVISIONING = _p, _pg, True
    except Exception:
        provisioning_pb2, provisioning_pb2_grpc, HAS_PROVISIONING = None, None, False

    model_pb2 = model_pb2_grpc = None
    MODEL_ROOT, HAS_MODEL = None, False
    for _root in _MODEL_ROOTS:
        try:
            _m = __import__(_root + ".model_pb2", fromlist=["model_pb2"])
            _mg = __import__(_root + ".model_pb2_grpc", fromlist=["model_pb2_grpc"])
            model_pb2, model_pb2_grpc, MODEL_ROOT, HAS_MODEL = _m, _mg, _root, True
            break
        except Exception:
            continue

    nmts_pb2 = None
    NMTS_ROOT, HAS_NMTS = None, False
    for _root in _NMTS_ROOTS:
        try:
            nmts_pb2 = __import__(_root + ".nmts_pb2", fromlist=["nmts_pb2"])
            NMTS_ROOT, HAS_NMTS = _root, True
            break
        except Exception:
            continue

    try:
        import grpc as _grpc
        grpc = _grpc
    except Exception:
        grpc = None

    _FLAGS = {"HAS_AUTH": HAS_AUTH, "HAS_NBI": HAS_NBI, "HAS_PROVISIONING": HAS_PROVISIONING,
              "HAS_MODEL": HAS_MODEL, "HAS_NMTS": HAS_NMTS}
    return dict(_FLAGS)


_probe()


def reprobe() -> dict:
    """Re-run the capability probes (e.g. after installing spacetime-api in a running Colab kernel,
    so a restart isn't needed) and return the fresh flags dict."""
    return _probe()


def require(flag: str, dist_name: str):
    """Raise a clear error naming the missing dependency unless `flag` is satisfied. Re-probes once
    first, so it recovers if spacetime-api was installed after this module was imported."""
    if not _FLAGS.get(flag, False):
        _probe()                        # maybe installed after import (Colab: no restart needed)
    if not _FLAGS.get(flag, False):
        raise RuntimeError(
            f"spacetime-api surface '{dist_name}' is unavailable ({flag}=False). Run the Colab "
            f"install cell (private index) — then re-run; or use MemoryEntityStore / "
            f"RecordedEntityStore offline.")
