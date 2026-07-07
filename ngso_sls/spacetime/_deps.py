"""Single home for OPTIONAL proto/grpc imports, probed PER SURFACE.

The modern pip package (`aalyria.spacetime.api.*`) and the bazel layout (`api.model.v1`,
`nmts.v1.proto`) never coexist, so a single shared try-block would be a guaranteed
false-negative. Each surface gets its own guarded probe + flag. Nothing here imports proto at
module import time beyond these guarded try blocks, so `import ngso_sls.spacetime` always
succeeds — even in this sandbox where `spacetime-api` is not installed."""

HAS_AUTH = HAS_NBI = HAS_PROVISIONING = HAS_MODEL = HAS_NMTS = False
auth = nbi_pb2 = nbi_pb2_grpc = provisioning_pb2 = provisioning_pb2_grpc = None
model_pb2 = model_pb2_grpc = nmts_pb2 = grpc = None
MODEL_ROOT = None                       # which import root resolved for Model, if any

try:
    from aalyria.spacetime.api.common import auth as _auth
    auth = _auth
    HAS_AUTH = True
except Exception:
    pass

try:
    from aalyria.spacetime.api.nbi.v1alpha import nbi_pb2 as _n, nbi_pb2_grpc as _ng
    nbi_pb2, nbi_pb2_grpc = _n, _ng
    HAS_NBI = True
except Exception:
    pass

try:
    from aalyria.spacetime.api.provisioning.v1alpha import (
        provisioning_pb2 as _p, provisioning_pb2_grpc as _pg)
    provisioning_pb2, provisioning_pb2_grpc = _p, _pg
    HAS_PROVISIONING = True
except Exception:
    pass

for _root in ("aalyria.spacetime.api.model.v1", "api.model.v1"):   # try pip then bazel
    try:
        _m = __import__(_root + ".model_pb2", fromlist=["model_pb2"])
        _mg = __import__(_root + ".model_pb2_grpc", fromlist=["model_pb2_grpc"])
        model_pb2, model_pb2_grpc, MODEL_ROOT, HAS_MODEL = _m, _mg, _root, True
        break
    except Exception:
        continue

for _root in ("aalyria.spacetime.api.nmts.v1.proto", "nmts.v1.proto"):
    try:
        nmts_pb2 = __import__(_root + ".nmts_pb2", fromlist=["nmts_pb2"])
        HAS_NMTS = True
        break
    except Exception:
        continue

try:
    import grpc as _grpc
    grpc = _grpc
except Exception:
    pass

_FLAGS = {"HAS_AUTH": HAS_AUTH, "HAS_NBI": HAS_NBI, "HAS_PROVISIONING": HAS_PROVISIONING,
          "HAS_MODEL": HAS_MODEL, "HAS_NMTS": HAS_NMTS}


def require(flag: str, dist_name: str):
    """Raise a clear error naming the missing dependency unless `flag` is satisfied."""
    if not _FLAGS.get(flag, False):
        raise RuntimeError(
            f"spacetime-api surface '{dist_name}' is unavailable ({flag}=False). Install via the "
            f"Colab private-index cell, or use MemoryEntityStore/RecordedEntityStore offline.")
