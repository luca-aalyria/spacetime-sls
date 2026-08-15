# Vendored Spacetime Python stubs (NBI NetOps + raw Store)

Locally-generated `*_pb2.py` / `*_pb2_grpc.py` for two gRPC surfaces:

1. **NBI intent facade** — `aalyria.spacetime.api.nbi.v1alpha.NetOps` (read-only, key-authed;
   see `docs/design-docs/slice-e-intent-facade.md`). Root: `api.nbi.v1alpha`.
2. **Raw internal Store** — `minkowski.proto.Store` (engdoc "Storage Services": all storage
   backends serve this on **port 9999**; reach it with `kubectl port-forward` + plaintext
   gRPC, same pattern as `nbictl`/`storectl`). Root: `proto_internal.storage`. Used by
   `StorageEntityStore` — reads intents, NMTS entities/relationships, and (future) link
   reports / schedules / beam-candidate segments without any platform deploy.

**Why vendored:** the published `spacetime-api` pip package ships neither surface today
(NetOps returns only after the api-package rebuild; the raw Store proto is internal and never
will ship). These stubs make `HAS_NBI` / `HAS_STORAGE` / `HAS_NMTS` true wherever the repo is
cloned — sandbox venv and Colab alike.

- **Source:** `minkowski` @ branch `nbi-intent-facade` — `api/nbi/v1alpha/nbi.proto` +
  `proto_internal/storage/storage.proto` and their 91-proto transitive closure (computed
  dynamically at generation time). Apache-2.0 headers on the api/ protos.
- **Precedence:** `ngso_sls/spacetime/_deps.py` probes pip roots first, then these bazel-layout
  roots — a rebuilt official package supersedes the NBI stubs automatically.
- **Wiring:** put this directory on `sys.path`.
  - venv (RELATIVE path — survives the sandbox/host mount-path difference):
    `echo "../../../../vendor/spacetime_api_stubs" > .venv/lib/python3.*/site-packages/spacetime_api_stubs.pth`
  - Colab/notebook: `sys.path.insert(0, f"{REPO_DIR}/vendor/spacetime_api_stubs")` before
    importing `ngso_sls.spacetime` (or call `ngso_sls.spacetime.reprobe()` after).
- **Regenerate:** `tools/regen_spacetime_stubs.sh [minkowski_root]` (needs `grpcio-tools`,
  `googleapis-common-protos`).
- **Caveat:** top-level package names `api`, `nmts`, `proto_internal`, `connectivitycontract`
  are generic; insert this root only in contexts that need it.
