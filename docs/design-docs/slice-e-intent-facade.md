# Slice E — Revived read-only NBI intent facade (`intentfe`)

**Goal:** programmatic, **robot-key-authed** ingest of solver-written **intents** into the SLS.

## Alternative access path — raw Store over kubectl port-forward (works TODAY, no deploy)

Engdoc-documented ("Storage Services": every storage backend serves `minkowski.proto.Store`
gRPC on **port 9999**; `nbictl`/`storectl` use `kubectl port-forward` + plaintext gRPC —
the same pattern applies to `svc/storage` directly):

```
kubectl --context=<ctx> port-forward svc/storage -n <ns> 9999:9999
# then: StorageEntityStore("localhost:9999").list_intents()
```

SLS side is implemented: `StorageEntityStore` (`ngso_sls/spacetime/client.py`) over vendored
`proto_internal.storage` stubs (`HAS_STORAGE`); read-only (only `Get`/`GetEntities` wired);
4 in-process gRPC wire tests. Reads `INTENT=6`, `NMTS_ENTITY=17`, `NMTS_RELATIONSHIP=18` —
and can later read link reports / schedules / beam-candidate + propagation-vector segments
(Slice B/C inputs) with the full internal `EntityFilter` (intent time filters included).

**Trade-off vs the facade:** auth boundary is kubectl/cluster access, not robot keys — a
dev/ops path, fine for local Jupyter or a Colab runtime holding cluster creds, unusable for
key-only robots. The facade remains the product path; this unblocks intent ingest while the
facade's platform-env steps (below) are pending.

## Why a facade is required
Raw intents live only in the internal `Store` (`EntityType.INTENT=6`). No current public,
key-authed endpoint serves them:
- `modelfe` (`model-v1`) is hard-scoped to NMTS (`IsNMTSEntityKindSet`; only `NMTS_ENTITY`/`NMTS_RELATIONSHIP`).
- `provisioningfe` serves SR-TE *inputs*, not solver intents.
- `grpcui` is an **internal** subdomain (SRE-only IAP, not key) → unreachable by robots.
- `nbi`/`nbi-v1alpha` api subdomains are live routes but return *"no healthy upstream"* (pod gone).

The removed legacy `nbi.proto` `service NetOps` is exactly the missing facade: it reads Store
entities by type — including `INTENT` — and its `Entity.value` oneof carries
`resources.Intent intent = 9`, the **same generated type** the Store holds. We revive it,
**read-only**, on the existing (robot-reachable) `nbi` subdomain.

## Architecture
```
Store.GetEntities(type=INTENT)  ──►  intentfe (NetOps, read-only)  ──►  nbi-v1alpha api subdomain
   (internal gRPC, in-cluster)         permission middleware              (robot key / IAP)
                                                                              │
                                              SLS GrpcEntityStore.list_intents()  ◄── robot key
                                              → routes_from_intents() → coverage
```
`intentfe` mirrors `nbi/modelfe` exactly (same store-client dial, permission middleware,
reflection, 128 MiB max-recv). Translation is a direct oneof copy: `storage.Entity.intent`
and `nbi.Entity.intent` are the identical `resources.Intent` Go type.

## Read-only enforcement (three independent layers)
1. **No write RPCs implemented.** `Server` embeds `UnimplementedNetOpsServer`; only
   `GetEntity`/`ListEntities`/`ListEntitiesOverTime` are provided. `Create/Update/Delete` →
   `codes.Unimplemented`.
2. **Verb-derived permission map.** `RegisterNetOpsPatterns` maps `NetOps/{VERB}Entit(y|ies)`
   (+ a separate `{VERB}EntitiesOverTime` pattern — the anchored regex won't match the
   "OverTime" suffix otherwise) to `model/entity/*`. `Get`/`List` → READ; write verbs → WRITE.
   Unmatched methods are **default-denied** (fail-closed).
3. **Read-only authorization.** The ingest robot is granted only `PERMISSION_READ` on
   `model/entity/*` (and `model/entity/*/*`) in the singleton `AuthorizationConfig`.

`INTENT`-only scoping: non-INTENT reads return `Unimplemented` (use the Model API).

## Files
**minkowski_ws3** (branch `nbi-intent-facade`):
- `api/nbi/v1alpha/nbi.proto`, `api/nbi/v1alpha/BUILD` — restored verbatim from `2f5a397e60^`
  (all 13 imports still present → no drift; `nbi_go_grpc` importpath `aalyria.com/spacetime/api/nbi/v1alpha`).
- `nbi/intentfe/intentfe.go` — read-only NetOps impl over `storagepb.StoreClient`.
- `nbi/intentfe/intentfe_test.go` — e2e against `clienttest.NewMemoryStoreClient` (seed INTENT →
  ListEntities/GetEntity round-trip; non-INTENT → Unimplemented; write RPCs → Unimplemented).
- `nbi/intentfe/server/main.go`, `nbi/intentfe/{BUILD,server/BUILD}` — server + image
  (`a5a_oci_image` artifact `intent-frontend-server`), mirroring `modelfe`.
- `permissions/patterns.go` (+`permissions/BUILD`) — `RegisterNetOpsPatterns` + `extractNetOpsEntityResource`.

**spacetime-sls**:
- `ngso_sls/spacetime/client.py` — `_nbi` = `NetOpsStub`; `list_intents()` now calls
  `ListEntities(type=INTENT)` and reads `Entity.intent` (proto2 `HasField`). Adapter unchanged.
- `tests/test_spacetime_client.py` — NetOps double.

## Infra delta (spacetime-infra `environments/fss01-demo`)
Reuse the existing `nbi` app slot (its workload-identity SA `nbi` and the `nbi`/`nbi-v1alpha`
subdomain routing already exist; only the pod is missing). Store access is in-cluster mTLS via
that SA — no new GCP role. Add one override:
```hcl
# main.tf : locals.spacetime_overrides
nbi = {
  image = {
    repository = "us-central1-docker.pkg.dev/a5a-spacetime-artifacts/container-images-experimental/intent-frontend-server"
    tag        = "@sha256:<pushed-digest>"
  }
  # args wired by the nbi subchart: --store_uri, --permissions_endpoint, --audit_log_service_addr, --port
}
```
Precondition to verify in the umbrella chart: the `nbi` subchart still renders a Deployment +
Service and the Istio route `nbi-v1alpha.<domain>` → that Service. If the `nbi` subchart was
removed with the legacy server, add an `intent-frontend` chart (mirror `model-frontend`) +
VirtualService for `nbi-v1alpha` instead of the override.

**Robot (AuthZ), `AuthorizationConfig` singleton, `--permissions_strategy=file`:**
```textproto
authorizations { principal: "<ro-robot>@<proj>.iam.gserviceaccount.com" permissions: PERMISSION_READ resource: "model/entity/*" }
authorizations { principal: "<ro-robot>@<proj>.iam.gserviceaccount.com" permissions: PERMISSION_READ resource: "model/entity/*/*" }
```

## Verification (platform env — cannot run in the SLS sandbox: no Bazel/Go)
```
bazel run //:gazelle
bazel test //nbi/intentfe/... //permissions/... --@rules_go//go/config:race
bazel build //nbi/intentfe/server:image   # push to container-images-experimental
```
Then deploy the override, and smoke-test key-authed:
```
grpcurl -H "authorization: Bearer <robot-JWT>" nbi-v1alpha.fss01-demo.spacetime.aalyria.com:443 \
  aalyria.spacetime.api.nbi.v1alpha.NetOps/ListEntities   # {"type":"INTENT"}
```

## Open items / caveats
- **Rebase drift (found 2026-08-15, minkowski main pulled +326 commits):** upstream removed
  `resources.ComputedMotion` (motion_evaluation.proto) and the Store's
  `EntityType.COMPUTED_MOTION=13` / `Entity.computed_motion=16` (now reserved; replaced by
  internal `ComputedMotionSegment=76`). The branch's restored `nbi.proto` imports
  motion_evaluation.proto and carries a `computed_motion` oneof arm → **rebasing
  `nbi-intent-facade` onto main requires dropping that arm** (reserve its field number,
  mirroring upstream). No other facade file is affected. SLS read paths
  (INTENT=6 / NMTS_ENTITY=17 / NMTS_RELATIONSHIP=18, intent state/time fields,
  directional_link.platform_id/rx_platforms) verified unchanged on new main; vendored stubs
  left as-is (matched to the deployed fss01-demo version; 140 tests + live sanity green).
- **Python client dependency — RESOLVED (2026-08-14) via vendored stubs:** locally-generated
  `nbi_pb2`/`nbi_pb2_grpc` (+33-proto closure) live in `vendor/spacetime_api_stubs/`
  (bazel-layout root `api.nbi.v1alpha`; regen via `tools/regen_spacetime_stubs.sh`). `_deps.py`
  probes the pip root first, so the rebuilt official package supersedes them automatically.
  The official api pip rebuild is still wanted for the long term.
- **Bootstrap-mode fail-open:** if the instance's `AuthorizationConfig` is empty, the permission
  layer treats it as bootstrap and may permit all — exposing intents un-gated. Deploy precondition:
  run the permissions service with a populated `file` config (or `readonly`). The facade is no
  weaker than `modelfe` here, but it exposes a new data class, so the ACL must be populated first.
- **Every robot reaches the `nbi` subdomain** (IAP grants all robots on api subdomains). The
  per-principal ACL is the gate — grant READ to the ingest robot only.
- **Filter scope:** the legacy `EntityFilter` carries `references_service_request` only; intent
  time-filters (`intent_enact_before/withdraw_after`, `include_intent_type`) are not exposed —
  clients filter the returned `Intent` oneof. `field_masks` projection is not applied.
- **A `permissions/middleware_test.go` case for the NetOps patterns should be added** (not written
  here to avoid editing a large unrunnable test file).
