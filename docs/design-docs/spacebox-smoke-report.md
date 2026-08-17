# Spacebox integration smoke test — report (2026-08-17)

**Objective:** programmatically create ephemeral Spacetime instances (SpaceboxOperator
gRPC) for parameterized simulation runs. **Result: our entire client path works; blocked
by a platform-side fault in the deployed spacebox service.**

## Verified working (our side)
1. **Access:** ADC reaches the e2e-internal host cluster (`a5a-s7e-k8s-e2e-internal` /
   `cluster`, us-central1); `/tmp/bin/kctl-e2e` wrapper (fresh token per call).
2. **Service discovery:** `svc/spacebox` in `spacetime-system`, port 10002, healthy pod
   + endpoint; plaintext gRPC over port-forward.
3. **Stubs:** `spacebox/proto/operator.proto` vendored (bazel-free);
   `SpaceboxOperator.Create/Watch/Destroy` callable from Python.
4. **Contract exercised live:** `Create(id="luca-sls1", solver=SOLVER_SATSOLVER_NMTS,
   ttl=2h)` was ACCEPTED (idempotently re-sent after a first client timeout);
   `Watch(luca-sls1)` streamed `lifecycle: pending` — the operator queued our request.

## Blocker (platform side — needs the spacetime/SRE team)
The deployed spacebox pod cannot execute helm — every install/uninstall fails:
```
error: running /spacebox.runfiles/gazelle++go_deps+sh_helm_helm_v3/cmd/helm/helm_/helm
uninstall ... failed: fork/exec .../helm_/helm: no such file or directory
```
(seen repeatedly in `kubectl logs deploy/spacebox -n spacetime-system`, also against
pre-existing namespaces `telesat-feeder-links-cluster`, `telesat-user-links-cluster` —
NOT triggered by us). A bazel-runfiles/helm packaging fault in the currently deployed
image → `luca-sls1` stays `pending`; no namespace is ever created. Our 2h TTL entry will
be reaped (reaping itself may also fail until the image is fixed — flag both).

**Ask for the platform team:** roll/fix the spacebox deployment image on e2e-internal
(helm binary missing from runfiles); confirm `Create` processes again.

## Environment notes gathered en route
- Port-forwards to BOTH clusters flap under sustained use (SPDY error-stream timeouts;
  self-healing after quiet periods). Long-running work should prefer in-cluster execution.
- `netops-frontend` on fss01-demo is crash-looping (pre-existing, unrelated).

## Next steps (once the image is fixed — all client-side pieces are ready)
1. Re-run: Create → Watch to `ready` (script exists in session history; promote to
   `tools/spacebox_smoke.py`), verify namespace + storage svc, port-forward INTO the new
   instance, read empty Store, `Destroy`, verify reaped.
2. Version-pinned instance: read fss01-demo's deployed image digests → `app_versions` in
   Customization → legacy beam-hopping oracle instance.
3. Scenario population (write-path gate applies): pybuilder-generated NMTS for a Jio
   candidate; Store.Write restricted to spacebox namespaces.
