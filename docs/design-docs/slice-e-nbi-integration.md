# Slice E — Live Spacetime/Minkowski NBI Integration (design)

**Status:** design (adversarially verified — 7-agent workflow `wi2lk7ugy`, 3 skeptic lenses).
**Scope of this doc:** Increment-1 = **read-only pull**. No Create/Update/Delete is ever wired.

## Goal

Connect the offline SLS to a live Aalyria **Spacetime/Minkowski** instance, pull data
read-only, and use it to **seed and validate** the Slice-A coverage engine. Endpoint is
configurable (owner live / Spacebox / custom) via a notebook form. The core numerical
engine (`constellation/ propagation/ geometry/ coverage/`) is **not touched** and stays
proto-free (`tests/test_core_purity.py` green).

## Two orthogonal pull capabilities

| Capability | Service / RPC (verified) | Yields | Certainty |
|---|---|---|---|
| **Intents / routes** | `NbiStub.ListIntents()` (modern pip) → `Intent` (oneof `route`=6 → `PathIntent.path_segments`); `ProvisioningStub.ListP2pSrTePolicies()` | live "computed coverage" reference (node adjacency) | **PROVEN** in Rivada notebook |
| **NMTS network model** | `ModelStub.ListEntities()` → `nmts.v1.Entity`; `ListRelationships(filter=CEL)` → `Relationship(kind,a,z)`; `GetEntity(id)` | Platforms (motion) + Antennas via `RK_CONTAINS` → SLS raw elements | **UNPROVEN on pip surface** (see probe) |

The NMTS-model→elements→coverage path is the user's stated first use-case, but it is
**not demonstrated** on the decided `spacetime-api` pip package by any reference notebook
(they only import `nbi`/`provisioning`; the Model client sample is bazel `github/py`). So
the notebook **leads with an Increment-0 capability probe** (below) and gates the
element-building path on it. The PROVEN intents/provisioning pull is the guaranteed
deliverable.

## Architecture

New guarded subpackage `ngso_sls/spacetime/` (outside `CORE_PKGS`; may import proto/grpc —
but **only lazily**). Two seams:

1. **`EntityStore` seam** (netsolve `Store` pattern) — abstract Protocol; `GrpcEntityStore`
   (live), `MemoryEntityStore` (fixtures), `RecordedEntityStore` (replay). Proto objects
   flow *through* it as opaque values; callers/tests never `import grpc`.
2. **Raw-elements coverage seam** — real constellations are **not** Walker grids, so the
   adapter feeds a raw `(n_sat,6)` `[a_km,e,i_rad,raan_rad,argp_rad,M_rad]` array (the exact
   contract `KeplerJ2Propagator.propagate` consumes, `kepler_j2.py:28`) into a new
   `run_coverage_h3_elements(...)`. `constellation/walker.py` and the core are untouched.

### Package layout

```
ngso_sls/spacetime/
  __init__.py        # pure; exposes capability flags + safe re-exports. import must succeed in sandbox.
  _deps.py           # per-surface guarded imports (see below) + require(flag)
  config.py          # SpacetimeEndpoint dataclass (pure Python)
  store.py           # EntityStore Protocol + StoreError(Connection/Rpc/NotFound)
  client.py          # GrpcEntityStore — the only file that builds channels/stubs
  memory_store.py    # MemoryEntityStore(entities, relationships, intents) — offline
  recording.py       # RecordedEntityStore(path) + record() wrapper
  nmts_adapter.py    # NMTS Entity/Relationship -> (n_sat,6) elements + metadata
  pull.py            # orchestration: pull -> build -> coverage -> compare (+ __main__)
  fixtures/*.json    # offline fixtures (pure JSON, no proto)
ngso_sls/pipeline.py # + run_coverage_h3_elements(...)  (NOT in CORE_PKGS)
ngso_sls/io/csv_io.py# + write/load_elements_csv + snapshot writers
tests/test_spacetime_adapter.py  # offline; live tests behind @pytest.mark.integration
notebooks/05_slice_e_pull.ipynb  # Colab (private-index install; out of pytest path)
```

## Client & auth

`SpacetimeEndpoint(url, key_id, user_id, private_key_file, model_url=None,
api_variant='modern'|'legacy', model_version='v1'|'v1alpha'|'v0')`. Defaults target the
owner instance; Spacebox/custom = different url/creds. URL form `https://<host>:443`.

**Auth (modern, decided):** `auth.Credentials(key_id, user_id, private_key_file)
.create_channel(url)`. **Portable fallback** (verified `github/py/authentication/auth.py`,
which has *no* `Credentials`/`create_channel` — only `Config`/`new_credentials` returning
**call**-creds): `grpc.secure_channel(target, composite_channel_credentials(
ssl_channel_credentials(), new_credentials(Config(email=user_id, private_key_id=key_id,
private_key=…))), [("grpc.max_receive_message_length", 256<<20)])`. **The 256 MB option is
REQUIRED on BOTH paths** — full-constellation `ListEntities` responses exceed the default.
Credentials are never logged; the key path is passed straight to auth, contents never enter
error strings.

Read-only method map (`EntityStore` → RPC): `list_entities → ModelStub.ListEntities().entities`;
`list_relationships(cel) → ModelStub.ListRelationships(filter=cel)`; `get_entity(id) →
ModelStub.GetEntity`; `list_intents(states) → NbiStub.ListIntents().intents` (filter by
state client-side) with **legacy fallback** `NetOpsStub.ListEntitiesOverTime(type='INTENT',
filter=EntityFilter(include_intent_states=[INSTALLED]))` on `UNIMPLEMENTED`.

## NMTS adapter contract

- **Motion is `repeated MotionDescription entry`** (`motion.proto:168-174`), each a oneof
  `{keplerian_elements, tle, state_vector, ecef_fixed, …}`. Iterate entries; **select the
  entry whose interval contains the reference epoch**, error if a bounded set has none.
- **Keplerian → elements** (angles in **degrees**, `orbital.proto:78-106`):
  `a_km=semimajor_axis_m/1000`, `e`, `i/raan/argp = radians(...)`, `M` from true anomaly via
  `E=2·atan2(√(1−e)·sin(ν/2), √(1+e)·cos(ν/2)); M=E−e·sinE`.
- **Epoch reconciliation (hard prerequisite, not optional):** `KeplerianElements.epoch` is
  per-satellite; the propagator applies J2 secular rates from `t=0` assuming one common
  `TimeGrid.epoch_utc`. The adapter **pre-propagates each satellite from its own epoch to a
  single reference epoch** (`M += n₀·(t_ref−t_epoch)`, advance raan/argp secularly) before
  emitting the array, and sets `TimeGrid.epoch_utc = t_ref`. Round-trip tested with two
  satellites at different epochs.
- **TLE / ephemeris motion** (`tle`, `state_vector`, `ccsds…`, `ecef_interpolation`,
  `cartographic_waypoints`) is **not** forced through KeplerJ2. It routes to a **raw-positions
  propagator** behind the existing `Propagator` Protocol: `Sgp4Propagator` (SGP4 TEME →
  GCRF via astropy/skyfield, then the existing `eci_to_ecef`) and `EphemerisInterpolator`.
  These live in `ngso_sls/spacetime/` (NOT `propagation/`, which is a CORE_PKG whose
  `ALLOWED_TOP` excludes `sgp4`/`skyfield`) or lazy-import. The "osculating→J2-mean shortcut"
  is dropped (frame + mean-vs-osculating error).
- **Antennas** (via `RK_CONTAINS`, compared as **integer `4`**, never `nmts_pb2.RK.…`, to keep
  the adapter proto-free): type, is_steerable, max_transmit_power_w, antenna_pattern, G/T,
  field_of_regard, sun-angle, geo-arc — **persisted as metadata only** (`antennas.csv`); seed
  Slices B/C. Slice-A coverage stays min-elevation based.
- **Output:** `(n_sat,6)` float array + parallel metadata (sat_id, name, epoch_utc,
  motion_kind, antenna_ids, is_external_system). **External-system platforms are tagged and
  excluded** from the served constellation (interferers, not assets).
- **Duck-typed field access** (`_motion_entries`, `_kepler`, …) so the same adapter runs on
  real protos **and** on plain fixture dataclasses — no proto import to unit-test the math.

## Coverage seam (`pipeline.py`, back-compatible)

Lift the three lines `elems=np.vstack([walker_elements…])` / `min_elev=min(…)` /
`max_alt=max(…)` out of `run_coverage_h3`; add
`run_coverage_h3_elements(elems, min_elev_user_deg, time_grid, aor, cell_res, shard_res=None,
chunk_steps=None, propagator=None, progress=None, k_values=None, terrain=None)`.
`run_coverage_h3(sim, aor, …)` computes those three from the `Constellation` and delegates.
**`max_alt = max(a·(1+e)) − RE_EQ` (apoapsis)**, not `a − RE_EQ`, so the conservative shard
dilation never under-estimates reach (preserves the `sharded == monolithic` invariant).

## `_deps.py` — per-surface capability flags (blocker fix)

The pip namespace (`aalyria.spacetime.api.*`) and bazel namespace (`api.model.v1`,
`nmts.v1.proto`) **never coexist**; one shared try-block is a guaranteed false-negative.
Split into independent probes, each its own try/except and flag:
`HAS_AUTH, HAS_NBI, HAS_PROVISIONING, HAS_MODEL, HAS_NMTS`. For Model/NMTS, **try both roots**
(`aalyria.spacetime.api.model.v1` then bazel `api.model.v1`) and record which resolved.
`model_version` **drives the import** (dispatch on it), not just a dataclass field; on
`UNIMPLEMENTED unknown service …model.v1.Model`, auto-retry the other versions and report
which the instance serves (Telesat tickets prove v1/v1alpha drift across instances).
`require(flag)` raises a clear `RuntimeError` naming the missing dist.

## Offline test strategy

All default tests run **offline** (no grpc, no network):
- **Capability guard:** `import ngso_sls` and `import ngso_sls.spacetime` succeed with the
  package absent; `HAS_* is False`; `GrpcEntityStore(...)` raises a clear error; MemoryStore +
  adapter work.
- **Adapter math:** fixture dataclasses mimicking `nmts.v1`; assert shape `(n,6)`, `a_km>6000`,
  true→mean round-trip, **two-epoch reconciliation** round-trip.
- **MemoryStore e2e:** full pull→build→coverage; intent fixtures are **`Intent`-shaped**
  (`{id, state, route:{path_segments:[{src/dst_network_node_id, src/dst_interface_id}]}}`),
  not top-level PathIntent; assert an installed hop is corroborated by predicted access.
- **Stub-parity (offline, unconditional):** a hand-written stub double matching verified wire
  signatures asserts `GrpcEntityStore` sends the right request types and **never calls a
  mutating RPC** (do not gate this on the package being importable).
- **RecordedStore:** two formats — proto-native `.pb` (Colab parity, `@integration`, skipped
  in sandbox) and a **proto-free JSON projection** (only adapter-consumed fields) that replays
  offline.
- **Packaging:** add `[tool.setuptools.package-data] ngso_sls.spacetime = ["fixtures/*.json"]`
  (current config ships only `data/*.json`). Sandbox fixtures are **pure JSON**, never textproto.
- Live tests `@pytest.mark.integration`, skipped unless `SPACETIME_URL`+creds env set.

## Colab notebook (`05_slice_e_pull.ipynb`)

1. Install (private index, verbatim): `!pip install --upgrade spacetime-api --extra-index-url
   https://us-central1-python.pkg.dev/a5a-spacetime-artifacts/py-packages/simple
   --prefer-binary`, then `ngso_sls`.
2. **Increment-0 probe** (blocker fix): print `HAS_*` flags; call `ModelStub.ListEntities` and
   count entities with `kind==ek_platform` and populated `.motion`. This decides whether the
   NMTS→coverage path runs; the intents/provisioning demo always runs.
3. **Connection form** (widget): URL (default `https://fss01-demo.spacetime.aalyria.com:443`),
   KEY_ID, USER_ID, PRIVATE_KEY_FILE (upload / Colab secret), MODEL_URL, model_version — all
   configurable for live/Spacebox/custom. **Never print the key**; source from
   `google.colab.userdata`/env, never notebook literals.
4. Build store → pull model → build raw elements (+ regularity summary) → pull installed
   intents → `run_coverage_h3_elements` → compare (route-vs-predicted-access, `validation_report.csv`)
   → record fixtures for offline replay.

## Divergences from the maps / CLAUDE.md (verified)

- Motion is **repeated**, not a single oneof (maps wrong).
- Three distinct service lineages, not one: **modern** `Nbi`/`Provisioning` (pip) · **legacy**
  `NetOps.ListEntitiesOverTime` (bazel) · **Model** NMTS service. All behind one `EntityStore`.
- `Nbi.ListIntents` and legacy auth are grounded **only** in the pip stub + one notebook —
  **not** in the in-repo `api/nbi` protos; treated as probe-at-runtime, not assumed.
- `model_pb2.ListEntitiesRequest` has **no type/filter field** — filter `Entity.kind`
  client-side (the `type='INTENT'` string is the *legacy* NetOps request, not Model).
- Phantom citation dropped: there is **no Python `SpacetimeCallCredentials`** (Java only);
  legacy path grounds on `NetOpsStub`.
- Real constellations aren't Walker → **raw-elements coverage path** (documented divergence
  from the Walker-only builder; core unchanged).

## Open questions (for the live spike, not blocking offline build)

Model version on the owner instance/Spacebox; whether the pip pkg ships Model/NMTS stubs;
whether the instance populates `ek_platform.motion`; `user_id` vs `email` in modern auth;
authoritative comparison product (PathIntents now; `coverage.proto` S2CoverageGrid later).
The Increment-0 probe answers the first three at runtime.
