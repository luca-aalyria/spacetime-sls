# Slices D/E — Ephemeral Spacetime instances for parameterized simulation runs

**Status:** Exploration draft (owner directive 2026-08-15). NOT a committed design —
requires the adversarial-verification pass and owner approval before any implementation
(this also flips the deliberate read-only policy: population needs a write path).

## Requirement

Programmatically stand up an **empty** Spacetime/spacebox instance, populate it with a
customer-parameterized constellation (e.g. Jio 1600-sat dual-shell candidates), let the
real solver run, pull results (existing nb05/06/07 machinery), tear down. Two shapes:
single ephemeral instance reset per run, or N parallel instances for parameter sweeps.

## Findings (verified in minkowski_ws3 + engdoc, 2026-08-15)

- **Spacebox is exactly this mechanism.** Short-lived full Spacetime instances as k8s
  namespaces on the `e2e-internal` host cluster; created in 1–3 min; `spacebox-reaper`
  enforces TTLs. Parallel namespaces (`alice001`, `bob001`, `nightly001`) are the native
  operating mode — parallelism is free.
- **It is a gRPC service, not just a bazel CLI.** `spacebox/proto/operator.proto`:
  `SpaceboxOperator.Create(id, Customization) / Destroy(id) / Watch(id) -> stream
  LifecycleEvent{pending|created|ready|destroying|destroyed}`. `Customization` carries
  solver type, helm-values Struct, versions, **ttl**, observability. Proto closure = 4
  well-known imports -> trivially vendorable as Python stubs (same pattern as the Store).
  The bazel CLI (`bazel run //spacebox -- create --storage storage-sqlite --solver
  satsolver-nmts ...`) is a client; `--experimental` image builds are CLI-side extras.
- **Population paths** (empty instance -> customer model):
  1. `scenarios/pybuilder` (Python, in minkowski): fluent NMTS authoring —
     `SatelliteBuilder("sat-i").with_circular_orbit(altitude_m, inclination_deg)`,
     beams/carriers/routing. The natural Walker-params -> NMTS generator (Slice D reuse
     target per design.md).
  2. `storectl import` (bazel CLI): bulk-load textproto/sqlite dumps; also
     `delete --keep-scenario` for the "reset single instance" shape.
  3. `nbictl model-v1 rsync` over port-forwarded modelfe (engdoc-blessed).
  4. SLS-side `Store.Write` via the vendored storage stubs — smallest new code, but a
     **policy change**: our client wires no mutating RPC today. If adopted: a separate
     `WriteableStore` class, never default-constructed, targeting ONLY spacebox
     namespaces (guard: refuse if the target namespace lacks a spacebox marker/TTL).
- **Sim-run readback:** solver output appears as intents/schedules in the instance's
  Store — the nb05/06 pull pipeline applies unchanged (port-forward per namespace).

## Options

| | A: one reusable instance | B: ephemeral per run | C: pool of N (B × parallel) |
|---|---|---|---|
| Reset cost | storectl delete+import (~s–min) | create 1–3 min | amortized over sweep |
| Isolation between runs | weak (state bleed risk) | clean | clean |
| Sweep throughput | serial | serial + create overhead | N-way parallel |
| Quota/cost footprint | 1 namespace | 1 at a time | N namespaces (TTL-capped) |
| Fits | interactive iteration | CI / single what-if | Jio min-N / k sweeps |

**Leaning:** C with B's lifecycle per member (create with `ttl`, `Watch` until `ready`,
populate via pybuilder-generated model, solve, pull, `Destroy`), plus A as the
interactive dev loop. Instance id = deterministic hash of the parameter set
(reproducibility + idempotent retries).

## Gates before implementation

1. **Owner approval + adversarial workflow pass** on: write-path policy, orchestration
   shape (who drives the sweep — SLS notebook? a runner script?), and blast-radius
   guards (spacebox-namespace-only writes).
2. **Access verification (platform side):** e2e-internal cluster permissions for the
   operator's identity; where the SpaceboxOperator service listens (port-forward vs
   in-cluster only); image-pull and namespace quotas for N parallel instances.
3. **Solver-run semantics:** satsolver-nmts needs UTs/gateways/carriers, not just
   satellites — define the minimum viable scenario template (pybuilder) that produces
   meaningful intents for coverage/capacity questions.
4. Population tooling runs where bazel lives (pybuilder is in minkowski) OR pybuilder's
   generated fragments are exported once and replayed via storectl/Store.Write — decide.

## Open questions

- ~~Does `Customization.Scenario{filename}` load a scenario at create time?~~ Verified:
  the CLI's `--scenario` flag loads a `//scenarios` package target CLIENT-side after the
  instance is ready (`actions.LoadScenario`) — so create+populate in one invocation works
  for checked-in scenarios; parameterized customer models still need generate-then-load
  (pybuilder -> file -> LoadScenario/storectl).
- Namespace quota on e2e-internal for realistic sweep widths (N=10? 50?).
- 1600-sat Jio model scale on a storage-sqlite spacebox (fss01-demo runs 150 sats;
  satsolver sharding should handle 1600 but instance sizing needs a smoke run).
