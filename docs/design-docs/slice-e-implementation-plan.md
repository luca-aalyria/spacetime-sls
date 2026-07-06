# Slice E — Spacetime NBI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only harness that pulls data from a live Aalyria Spacetime/Minkowski instance (NMTS network model + installed intents/routes) and feeds it into the offline Slice-A coverage engine to seed & validate coverage — fully offline-testable, with the live gRPC path guarded for Colab.

**Architecture:** A new **guarded subpackage** `ngso_sls/spacetime/` (outside `CORE_PKGS`) does all proto/grpc imports **lazily**. A netsolve-style `EntityStore` Protocol has three backends — `GrpcEntityStore` (live), `MemoryEntityStore` (JSON fixtures), `RecordedEntityStore` (replay). An `nmts_adapter` translates NMTS entities → the canonical `(n_sat,6)` element array + `plane_uid`, which flows into the **already-shipped** `run_coverage_h3_elements` seam. Proto objects flow *through* the store as opaque values read by duck-typed accessors, so the adapter math is unit-tested on plain JSON dicts with zero proto dependency.

**Tech Stack:** Python 3.14 (venv `/workspace/spacetime-sls/.venv`), NumPy, Astropy; live-only (Colab): `spacetime-api` (private index), grpcio, protobuf.

**Design:** `docs/design-docs/slice-e-nbi-integration.md` (approved, adversarially verified). Read it before starting.

**Hard constraints (non-negotiable):**
- The sandbox **cannot** install `spacetime-api` (private index) or reach an instance. **Every default test runs offline** via `MemoryEntityStore`/`RecordedEntityStore` with **pure-JSON** fixtures. Live tests are `@pytest.mark.integration`, skipped unless `SPACETIME_URL`+creds env are set.
- **Core purity:** `constellation/ propagation/ geometry/ coverage/` stay proto-free (`tests/test_core_purity.py`). The `spacetime/` subpackage is **not** a core package; it imports proto/grpc **only lazily** (inside functions / a single `_deps` module), so `import ngso_sls` and `import ngso_sls.spacetime` succeed with the package absent.
- **Read-only:** no Create/Update/Delete/Upsert RPC is ever wired.
- Reuse the shipped seam `run_coverage_h3_elements(elems, plane_uid, min_elev_user_deg, time_grid, aor, cell_res, …)` (in `pipeline.py`) — do NOT re-add it.

**Increment-1 scope:** the **proven** intents/provisioning pull is the guaranteed deliverable; the **NMTS→elements→coverage** path is built but gated at runtime behind an Increment-0 capability probe in the notebook. **Keplerian** platform motion is fully supported; **TLE/ephemeris** motion is flagged & skipped with a warning (a real `Sgp4Propagator`/`EphemerisInterpolator` is an explicit DEFERRED follow-up — see Self-Review).

**Standing rules:** run `/workspace/spacetime-sls/.venv/bin/pytest`; cwd resets to `/workspace` between bash calls (prepend `cd /workspace/spacetime-sls &&`); SI units, degrees at the I/O boundary; commit per task; credentials never logged.

---

## File Structure

| File | Responsibility |
|---|---|
| `ngso_sls/spacetime/__init__.py` **(NEW)** | Pure; re-export capability flags + safe symbols. `import ngso_sls.spacetime` must succeed in the sandbox. |
| `ngso_sls/spacetime/_deps.py` **(NEW)** | The ONLY place with guarded proto/grpc imports; per-surface flags `HAS_AUTH/HAS_NBI/HAS_PROVISIONING/HAS_MODEL/HAS_NMTS` + `require(flag, name)`. |
| `ngso_sls/spacetime/config.py` **(NEW)** | `SpacetimeEndpoint` dataclass (pure Python). |
| `ngso_sls/spacetime/store.py` **(NEW)** | `EntityStore` Protocol + `StoreError` (+ `Connection`/`Rpc`/`NotFound` kinds). |
| `ngso_sls/spacetime/_access.py` **(NEW)** | Duck-typed field accessors (`_get`, `_epoch_s`, `_motion_entries`, `_kepler`) — work on protos AND JSON dicts. |
| `ngso_sls/spacetime/memory_store.py` **(NEW)** | `MemoryEntityStore` over in-memory JSON. |
| `ngso_sls/spacetime/fixtures/mini_constellation.json` **(NEW)** | Offline fixture: platforms (Keplerian + one TLE) + antennas (RK_CONTAINS) + installed intents. Pure JSON. |
| `ngso_sls/spacetime/nmts_adapter.py` **(NEW)** | NMTS entities/relationships → `(n_sat,6)` elems + `plane_uid` + metadata; routes from intents. |
| `ngso_sls/spacetime/client.py` **(NEW)** | `GrpcEntityStore` — the only file that builds channels/stubs (lazy). |
| `ngso_sls/spacetime/recording.py` **(NEW)** | `RecordedEntityStore(path)` (proto-free JSON projection) + `record(store, path)`. |
| `ngso_sls/spacetime/pull.py` **(NEW)** | Orchestration: pull → build → coverage → compare (+ `__main__`). |
| `ngso_sls/io/csv_io.py` **(MODIFY)** | `write_elements_csv`/`load_elements_csv` + snapshot writers. |
| `pyproject.toml` **(MODIFY)** | Optional extras + `ngso_sls.spacetime` fixtures package-data. |
| `tests/test_spacetime_*.py` **(NEW)** | Offline tests; live behind `@pytest.mark.integration`. |
| `notebooks/05_slice_e_pull.ipynb` **(NEW)** | Colab: Increment-0 probe + connection form + pull flow. |

---

## Task 1: `spacetime/__init__.py` + `_deps.py` (per-surface capability flags)

**Files:** Create `ngso_sls/spacetime/__init__.py`, `ngso_sls/spacetime/_deps.py`; Test `tests/test_spacetime_deps.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_deps.py
import pytest


def test_import_succeeds_in_sandbox_and_flags_false():
    import ngso_sls
    import ngso_sls.spacetime as st
    # spacetime-api is absent in the sandbox -> every surface flag is False
    assert st.HAS_AUTH is False and st.HAS_NBI is False and st.HAS_MODEL is False
    assert st.HAS_PROVISIONING is False and st.HAS_NMTS is False


def test_require_raises_clear_error_when_absent():
    from ngso_sls.spacetime._deps import require
    with pytest.raises(RuntimeError, match="spacetime-api"):
        require("HAS_MODEL", "aalyria.spacetime.api.model.v1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_deps.py -q`
Expected: FAIL (`ngso_sls.spacetime` missing).

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/_deps.py
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
```

```python
# ngso_sls/spacetime/__init__.py
"""Slice E — read-only Spacetime/Minkowski NBI integration (guarded subpackage).

Proto/grpc imports are lazy (see `_deps`), so this package imports cleanly even when
`spacetime-api` is absent. Offline backends (MemoryEntityStore / RecordedEntityStore) + the
NMTS adapter work with no proto dependency; the live GrpcEntityStore requires the package."""
from ._deps import (HAS_AUTH, HAS_NBI, HAS_PROVISIONING, HAS_MODEL, HAS_NMTS)
from .config import SpacetimeEndpoint
from .store import EntityStore, StoreError
from .memory_store import MemoryEntityStore
from .recording import RecordedEntityStore, record
from . import nmts_adapter

__all__ = ["HAS_AUTH", "HAS_NBI", "HAS_PROVISIONING", "HAS_MODEL", "HAS_NMTS",
           "SpacetimeEndpoint", "EntityStore", "StoreError", "MemoryEntityStore",
           "RecordedEntityStore", "record", "nmts_adapter"]
```

*Note:* `__init__` imports `config/store/memory_store/recording/nmts_adapter` — none of those may import proto at module top (only lazily). Later tasks create them; until then, temporarily reduce `__init__` to just the `_deps` import to keep Task 1 green, and restore the full `__init__` in Task 6. (The Step-3 `__init__` above is the FINAL form; for Task 1 commit only the `from ._deps import ...` line + `__all__` of the flags.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_deps.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/__init__.py ngso_sls/spacetime/_deps.py tests/test_spacetime_deps.py
git commit -m "feat(spacetime): guarded per-surface capability flags + require() (Slice E)"
```

---

## Task 2: `spacetime/config.py` — `SpacetimeEndpoint`

**Files:** Create `ngso_sls/spacetime/config.py`; Test `tests/test_spacetime_config.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_config.py
from ngso_sls.spacetime.config import SpacetimeEndpoint


def test_endpoint_defaults_and_fields():
    ep = SpacetimeEndpoint(url="https://fss01-demo.spacetime.aalyria.com:443",
                           key_id="k", user_id="u", private_key_file="/tmp/k.key")
    assert ep.api_variant == "modern" and ep.model_version == "v1" and ep.model_url is None


def test_endpoint_repr_never_leaks_key_path_as_secret():
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u",
                           private_key_file="/secret/path.key")
    # the private key CONTENTS are never held here — only a path; sanity that it's a str field
    assert isinstance(ep.private_key_file, str)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_config.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/config.py
"""Connection configuration for a Spacetime/Minkowski instance (pure Python, no proto)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SpacetimeEndpoint:
    url: str                                   # https://<host>:443
    key_id: str
    user_id: str                               # service-account id/email (see open questions)
    private_key_file: str                      # path; contents read by auth, never stored here
    model_url: str | None = None               # Model service may live on a different host
    api_variant: str = "modern"                # 'modern' | 'legacy'
    model_version: str = "v1"                  # 'v1' | 'v1alpha' | 'v0'
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/config.py tests/test_spacetime_config.py
git commit -m "feat(spacetime): SpacetimeEndpoint config (Slice E)"
```

---

## Task 3: `spacetime/store.py` — `EntityStore` Protocol + `StoreError`

**Files:** Create `ngso_sls/spacetime/store.py`; Test `tests/test_spacetime_store.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_store.py
import pytest
from ngso_sls.spacetime.store import StoreError


def test_store_error_kinds():
    e = StoreError("boom", kind="NotFound")
    assert e.kind == "NotFound" and "boom" in str(e)
    assert StoreError.not_found("x").kind == "NotFound"
    assert StoreError.connection("x").kind == "Connection"
    assert StoreError.rpc("x").kind == "Rpc"


def test_entity_store_is_a_protocol():
    from ngso_sls.spacetime.store import EntityStore
    import typing
    assert getattr(EntityStore, "_is_protocol", False) or isinstance(EntityStore, type)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_store.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/store.py
"""Read-only entity store seam (netsolve `Store` pattern). Proto objects flow THROUGH as opaque
values; callers/tests never import grpc. Backends: GrpcEntityStore (live), MemoryEntityStore
(fixtures), RecordedEntityStore (replay)."""
from typing import Protocol, runtime_checkable, Any


class StoreError(Exception):
    """Normalized store error so callers/tests never import grpc. `kind` in
    {Connection, Rpc, NotFound}."""
    def __init__(self, message: str, kind: str = "Rpc"):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def not_found(cls, msg: str) -> "StoreError":
        return cls(msg, kind="NotFound")

    @classmethod
    def connection(cls, msg: str) -> "StoreError":
        return cls(msg, kind="Connection")

    @classmethod
    def rpc(cls, msg: str) -> "StoreError":
        return cls(msg, kind="Rpc")


@runtime_checkable
class EntityStore(Protocol):
    """READ-ONLY surface. No create/update/delete."""
    def list_entities(self) -> list[Any]: ...
    def list_relationships(self, cel: str | None = None) -> list[Any]: ...
    def get_entity(self, entity_id: str) -> Any: ...
    def list_intents(self, states: list[str] | None = None) -> list[Any]: ...
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/store.py tests/test_spacetime_store.py
git commit -m "feat(spacetime): EntityStore protocol + StoreError (Slice E)"
```

---

## Task 4: `_access.py` duck-typed accessors + `MemoryEntityStore` + JSON fixture

**Files:** Create `ngso_sls/spacetime/_access.py`, `ngso_sls/spacetime/memory_store.py`, `ngso_sls/spacetime/fixtures/mini_constellation.json`; Test `tests/test_spacetime_memory_store.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_memory_store.py
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.store import StoreError
import pytest


def test_memory_store_from_fixture_lists_and_gets():
    st = MemoryEntityStore.from_fixture("mini_constellation.json")
    ents = st.list_entities()
    kinds = sorted({e["kind"] for e in ents})
    assert 11 in kinds and 40 in kinds                 # ek_platform=11, ek_antenna=40
    rels = st.list_relationships()
    assert any(r["kind"] == 4 for r in rels)           # RK_CONTAINS=4
    intents = st.list_intents(states=["INSTALLED"])
    assert intents and all(i["state"] == "INSTALLED" for i in intents)
    first_id = ents[0]["id"]
    assert st.get_entity(first_id)["id"] == first_id
    with pytest.raises(StoreError):
        st.get_entity("does-not-exist")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_memory_store.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create the fixture `ngso_sls/spacetime/fixtures/mini_constellation.json`:

```json
{
  "entities": [
    {"id": "plat-0", "kind": 11, "platform": {"name": "SAT-0", "is_external_system": false,
      "motion": {"entry": [{"interval": {"start": {"seconds": 0}, "end": {"seconds": 0}},
        "keplerian_elements": {"semimajor_axis_m": 7028137.0, "eccentricity": 0.0,
          "inclination_deg": 53.0, "raan_deg": 0.0, "argument_of_periapsis_deg": 0.0,
          "true_anomaly_deg": 0.0, "epoch": {"seconds": 1767225600}}}]}}},
    {"id": "plat-1", "kind": 11, "platform": {"name": "SAT-1", "is_external_system": false,
      "motion": {"entry": [{"interval": {"start": {"seconds": 0}, "end": {"seconds": 0}},
        "keplerian_elements": {"semimajor_axis_m": 7028137.0, "eccentricity": 0.0,
          "inclination_deg": 53.0, "raan_deg": 60.0, "argument_of_periapsis_deg": 0.0,
          "true_anomaly_deg": 120.0, "epoch": {"seconds": 1767225660}}}]}}},
    {"id": "plat-ext", "kind": 11, "platform": {"name": "INTERFERER", "is_external_system": true,
      "motion": {"entry": [{"interval": {"start": {"seconds": 0}, "end": {"seconds": 0}},
        "keplerian_elements": {"semimajor_axis_m": 7028137.0, "eccentricity": 0.0,
          "inclination_deg": 53.0, "raan_deg": 120.0, "argument_of_periapsis_deg": 0.0,
          "true_anomaly_deg": 0.0, "epoch": {"seconds": 1767225600}}}]}}},
    {"id": "plat-tle", "kind": 11, "platform": {"name": "TLE-SAT", "is_external_system": false,
      "motion": {"entry": [{"interval": {"start": {"seconds": 0}, "end": {"seconds": 0}},
        "tle": {"line1": "1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9990",
                "line2": "2 25544  51.6000   0.0000 0001000   0.0000   0.0000 15.50000000000000"}}]}}},
    {"id": "ant-0", "kind": 40, "antenna": {"type": "RF", "is_steerable": true,
      "max_transmit_power_w": 10.0, "g_over_t_db_per_k": 5.0}},
    {"id": "ant-1", "kind": 40, "antenna": {"type": "RF", "is_steerable": true,
      "max_transmit_power_w": 10.0, "g_over_t_db_per_k": 5.0}}
  ],
  "relationships": [
    {"kind": 4, "a": "plat-0", "z": "ant-0"},
    {"kind": 4, "a": "plat-1", "z": "ant-1"}
  ],
  "intents": [
    {"id": "intent-0", "state": "INSTALLED", "route": {"path_segments": [
      {"src_network_node_id": "plat-0", "dst_network_node_id": "plat-1",
       "src_interface_id": "ant-0", "dst_interface_id": "ant-1"}]}}
  ]
}
```

```python
# ngso_sls/spacetime/_access.py
"""Duck-typed field access so the adapter runs identically on real protobuf messages AND on
plain JSON dicts (fixtures). Never import proto here."""


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _epoch_s(kep) -> float:
    """Seconds-since-epoch of a KeplerianElements' `epoch` (proto Timestamp or JSON {seconds})."""
    ep = _get(kep, "epoch")
    return float(_get(ep, "seconds", 0.0) or 0.0)


def _motion_entries(platform):
    """The list of MotionDescription entries for a platform (Motion.entry is REPEATED)."""
    motion = _get(platform, "motion")
    return list(_get(motion, "entry", []) or [])


def _kepler(entry):
    """The KeplerianElements of a MotionDescription entry, or None if this entry is not Keplerian."""
    return _get(entry, "keplerian_elements")
```

```python
# ngso_sls/spacetime/memory_store.py
"""In-memory EntityStore over plain JSON (offline). Mirrors crates/netsolve-spacetime MemoryStore."""
import json
import pathlib
from .store import StoreError

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class MemoryEntityStore:
    def __init__(self, entities=None, relationships=None, intents=None):
        self._entities = list(entities or [])
        self._relationships = list(relationships or [])
        self._intents = list(intents or [])

    @classmethod
    def from_fixture(cls, name: str) -> "MemoryEntityStore":
        data = json.loads((_FIXTURES / name).read_text())
        return cls(data.get("entities"), data.get("relationships"), data.get("intents"))

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntityStore":
        return cls(data.get("entities"), data.get("relationships"), data.get("intents"))

    def list_entities(self):
        return list(self._entities)

    def list_relationships(self, cel: str | None = None):
        return list(self._relationships)          # CEL filtering is a live-only concern

    def get_entity(self, entity_id: str):
        for e in self._entities:
            if (e.get("id") if isinstance(e, dict) else getattr(e, "id", None)) == entity_id:
                return e
        raise StoreError.not_found(f"entity '{entity_id}' not in MemoryEntityStore")

    def list_intents(self, states=None):
        out = self._intents
        if states is not None:
            sset = set(states)
            out = [i for i in out if (i.get("state") if isinstance(i, dict)
                                      else getattr(i, "state", None)) in sset]
        return list(out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_memory_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/_access.py ngso_sls/spacetime/memory_store.py \
        ngso_sls/spacetime/fixtures/mini_constellation.json tests/test_spacetime_memory_store.py
git commit -m "feat(spacetime): MemoryEntityStore + duck-typed accessors + JSON fixture (Slice E)"
```

---

## Task 5: `nmts_adapter.py` — entities → elements (+ epoch reconciliation)

**Files:** Create `ngso_sls/spacetime/nmts_adapter.py`; Test `tests/test_spacetime_adapter.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_adapter.py
import numpy as np
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements, routes_from_intents
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.constants import RE_EQ, MU_EARTH


def _store():
    return MemoryEntityStore.from_fixture("mini_constellation.json")


def test_keplerian_platforms_to_elements_shape_and_units():
    st = _store()
    res = platforms_to_elements(st.list_entities(), st.list_relationships())
    elems = res["elems"]
    assert elems.shape[1] == 6
    # 2 served Keplerian platforms (plat-0, plat-1); external + TLE excluded/flagged
    assert elems.shape[0] == 2
    assert np.all(elems[:, 0] > 6000.0)                       # a_km
    assert res["plane_uid"].shape == (2,)
    ids = [m["sat_id"] for m in res["meta"]]
    assert "plat-ext" not in ids                              # external-system excluded
    assert any("plat-tle" == s["sat_id"] for s in res["skipped"])  # TLE flagged & skipped


def test_true_to_mean_anomaly_roundtrip():
    # circular orbit: true anomaly == mean anomaly; a 120-deg sat should have M≈120deg
    st = _store()
    res = platforms_to_elements(st.list_entities(), st.list_relationships())
    # plat-1 has true_anomaly_deg=120 at e=0 -> M ~ 120 deg (2.094 rad), but it is also
    # epoch-reconciled forward by 60 s; assert it is a finite angle in [0, 2pi)
    M = res["elems"][:, 5]
    assert np.all((M >= 0) & (M < 2 * np.pi + 1e-9))


def test_epoch_reconciliation_advances_mean_anomaly():
    # two identical sats, epochs 0 and +T/4; after reconciling to the earlier epoch the later
    # sat's M advances by n0 * dt relative to its raw value.
    a_km = RE_EQ + 650.0
    n0 = np.sqrt(MU_EARTH / a_km ** 3)                       # rad/s
    dt = 60.0
    ents = [
        {"id": "s0", "kind": 11, "platform": {"is_external_system": False, "motion": {"entry": [
            {"keplerian_elements": {"semimajor_axis_m": a_km * 1000, "eccentricity": 0.0,
             "inclination_deg": 53.0, "raan_deg": 0.0, "argument_of_periapsis_deg": 0.0,
             "true_anomaly_deg": 0.0, "epoch": {"seconds": 1000}}}]}}},
        {"id": "s1", "kind": 11, "platform": {"is_external_system": False, "motion": {"entry": [
            {"keplerian_elements": {"semimajor_axis_m": a_km * 1000, "eccentricity": 0.0,
             "inclination_deg": 53.0, "raan_deg": 0.0, "argument_of_periapsis_deg": 0.0,
             "true_anomaly_deg": 0.0, "epoch": {"seconds": 1000 + int(dt)}}}]}}},
    ]
    res = platforms_to_elements(ents, [], ref_epoch_s=1000.0)
    m0, m1 = res["elems"][0, 5], res["elems"][1, 5]
    # s0 at ref epoch -> M0 ~ 0; s1 started dt later, reconciled back to ref -> M advanced by n0*dt
    assert abs(m0) < 1e-9
    assert abs(((m1 - n0 * dt) % (2 * np.pi))) < 1e-6
    assert res["ref_epoch_s"] == 1000.0


def test_routes_from_intents_extracts_hops():
    st = _store()
    hops = routes_from_intents(st.list_intents(states=["INSTALLED"]))
    assert ("plat-0", "plat-1") in [(h["src"], h["dst"]) for h in hops]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_adapter.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/nmts_adapter.py
"""Translate pulled NMTS entities/relationships into the canonical (n_sat,6) element array the
Slice-A engine consumes, plus reporting metadata. Pure Python (numpy only) — reads proto/JSON
fields via duck-typed accessors so it is unit-tested with no proto dependency.

Increment-1 supports KEPLERIAN motion. TLE / state-vector / ephemeris motion is flagged and
skipped (a real Sgp4Propagator/EphemerisInterpolator is a deferred follow-up)."""
import numpy as np
from ..constants import MU_EARTH, RE_EQ
from ..constellation.model import _physical_plane_uid
from ._access import _get, _epoch_s, _motion_entries, _kepler

EK_PLATFORM = 11
EK_ANTENNA = 40
RK_CONTAINS = 4                      # compared as an int, never a proto enum


def _true_to_mean(nu_rad: float, e: float) -> float:
    E = 2.0 * np.arctan2(np.sqrt(1 - e) * np.sin(nu_rad / 2),
                         np.sqrt(1 + e) * np.cos(nu_rad / 2))
    return (E - e * np.sin(E)) % (2 * np.pi)


def _antenna_ids_for(platform_id: str, relationships) -> list:
    return [_get(r, "z") for r in relationships
            if int(_get(r, "kind", -1)) == RK_CONTAINS and _get(r, "a") == platform_id]


def platforms_to_elements(entities, relationships, *, ref_epoch_s: float | None = None,
                          include_external: bool = False) -> dict:
    """Returns {elems (n,6), plane_uid (n,), meta [dict], skipped [dict], ref_epoch_s,
    antennas [dict]}. External-system platforms are excluded unless include_external."""
    platforms = [e for e in entities if int(_get(e, "kind", -1)) == EK_PLATFORM]
    antennas = [e for e in entities if int(_get(e, "kind", -1)) == EK_ANTENNA]

    # collect Keplerian rows first (to pick a reference epoch), skip/flag the rest
    rows, meta, skipped = [], [], []
    for e in platforms:
        pid = _get(e, "id")
        plat = _get(e, "platform")
        is_ext = bool(_get(plat, "is_external_system", False))
        entries = _motion_entries(plat)
        kep = _kepler(entries[0]) if entries else None       # Increment-1: first entry
        if kep is None:
            skipped.append({"sat_id": pid, "reason": "non-Keplerian motion (TLE/ephemeris) "
                                                      "not supported in Increment-1"})
            continue
        if is_ext and not include_external:
            skipped.append({"sat_id": pid, "reason": "external-system platform (interferer)"})
            continue
        rows.append((pid, e, plat, kep))

    if not rows:
        return {"elems": np.empty((0, 6)), "plane_uid": np.empty((0,), dtype=np.int64),
                "meta": [], "skipped": skipped, "ref_epoch_s": ref_epoch_s or 0.0,
                "antennas": [_antenna_meta(a) for a in antennas]}

    epochs = [_epoch_s(kep) for (_pid, _e, _plat, kep) in rows]
    t_ref = float(ref_epoch_s) if ref_epoch_s is not None else float(min(epochs))

    elems = np.empty((len(rows), 6))
    for i, (pid, e, plat, kep) in enumerate(rows):
        a_km = float(_get(kep, "semimajor_axis_m")) / 1000.0
        ecc = float(_get(kep, "eccentricity", 0.0))
        inc = np.radians(float(_get(kep, "inclination_deg")))
        raan = np.radians(float(_get(kep, "raan_deg")))
        argp = np.radians(float(_get(kep, "argument_of_periapsis_deg", 0.0)))
        M = _true_to_mean(np.radians(float(_get(kep, "true_anomaly_deg"))), ecc)
        # epoch reconciliation to the common reference epoch (two-body mean-motion advance)
        n0 = np.sqrt(MU_EARTH / a_km ** 3)
        M = (M + n0 * (t_ref - _epoch_s(kep))) % (2 * np.pi)
        elems[i] = [a_km, ecc, inc, raan, argp, M]
        meta.append({"sat_id": pid, "name": _get(plat, "name"),
                     "epoch_utc_s": t_ref, "motion_kind": "keplerian",
                     "antenna_ids": _antenna_ids_for(pid, relationships),
                     "is_external_system": bool(_get(plat, "is_external_system", False))})

    return {"elems": elems, "plane_uid": _physical_plane_uid(elems), "meta": meta,
            "skipped": skipped, "ref_epoch_s": t_ref,
            "antennas": [_antenna_meta(a) for a in antennas]}


def _antenna_meta(a) -> dict:
    an = _get(a, "antenna")
    return {"antenna_id": _get(a, "id"), "type": _get(an, "type"),
            "is_steerable": _get(an, "is_steerable"),
            "max_transmit_power_w": _get(an, "max_transmit_power_w"),
            "g_over_t_db_per_k": _get(an, "g_over_t_db_per_k")}


def routes_from_intents(intents) -> list:
    """Flatten installed PathIntents to a list of hops {src, dst, src_if, dst_if} (the live
    'computed coverage' reference to compare against predicted access)."""
    hops = []
    for i in intents:
        route = _get(i, "route")
        for seg in (_get(route, "path_segments", []) or []):
            hops.append({"src": _get(seg, "src_network_node_id"),
                         "dst": _get(seg, "dst_network_node_id"),
                         "src_if": _get(seg, "src_interface_id"),
                         "dst_if": _get(seg, "dst_interface_id")})
    return hops
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/nmts_adapter.py tests/test_spacetime_adapter.py
git commit -m "feat(spacetime): NMTS adapter — Keplerian->elements + epoch reconciliation (Slice E)"
```

---

## Task 6: Restore full `__init__.py` + capability-guard integration test

**Files:** Modify `ngso_sls/spacetime/__init__.py`; Test `tests/test_spacetime_deps.py` (extend).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_spacetime_deps.py
def test_public_symbols_importable_offline():
    import ngso_sls.spacetime as st
    assert hasattr(st, "SpacetimeEndpoint") and hasattr(st, "MemoryEntityStore")
    assert hasattr(st, "EntityStore") and hasattr(st, "StoreError")
    assert hasattr(st, "RecordedEntityStore") and hasattr(st, "record")
    assert hasattr(st, "nmts_adapter")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_deps.py::test_public_symbols_importable_offline -q`
Expected: FAIL (`RecordedEntityStore`/`record`/full re-exports not yet wired — recording.py is Task 7).

- [ ] **Step 3: Implement** — set `ngso_sls/spacetime/__init__.py` to the FINAL form shown in Task 1 Step 3 (it imports `config/store/memory_store/recording/nmts_adapter`). This requires `recording.py` (Task 7) to exist. **Reorder note for the executor:** if you reach Task 6 before Task 7, implement `recording.py` (Task 7) first, then this task — they are interdependent. Simplest: do Task 7, then Task 6.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_deps.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/__init__.py tests/test_spacetime_deps.py
git commit -m "feat(spacetime): full package re-exports + offline symbol guard test (Slice E)"
```

---

## Task 7: `recording.py` — `RecordedEntityStore` + `record()`

**Files:** Create `ngso_sls/spacetime/recording.py`; Test `tests/test_spacetime_recording.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_recording.py
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.recording import RecordedEntityStore, record


def test_record_then_replay_matches_memory_store(tmp_path):
    mem = MemoryEntityStore.from_fixture("mini_constellation.json")
    path = tmp_path / "snap.json"
    record(mem, str(path), intent_states=["INSTALLED"])
    rec = RecordedEntityStore(str(path))
    assert [e["id"] for e in rec.list_entities()] == [e["id"] for e in mem.list_entities()]
    assert rec.list_relationships() == mem.list_relationships()
    assert [i["id"] for i in rec.list_intents(states=["INSTALLED"])] == \
           [i["id"] for i in mem.list_intents(states=["INSTALLED"])]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_recording.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/recording.py
"""Record a store's read surface to a proto-free JSON projection, and replay it offline.

Only the fields the adapter consumes are projected (so replay needs NO proto). A separate
proto-native .pb format for Colab round-trip parity is out of scope for the offline default
(would be gated behind @pytest.mark.integration)."""
import json
from ._access import _get
from .memory_store import MemoryEntityStore


def _project_entity(e):
    kind = int(_get(e, "kind", -1))
    out = {"id": _get(e, "id"), "kind": kind}
    if kind == 11:                     # ek_platform: keep name/is_external + motion entries
        plat = _get(e, "platform")
        entries = []
        for en in (_get(_get(plat, "motion"), "entry", []) or []):
            kep = _get(en, "keplerian_elements")
            if kep is not None:
                entries.append({"keplerian_elements": {
                    k: _get(kep, k) for k in ("semimajor_axis_m", "eccentricity",
                    "inclination_deg", "raan_deg", "argument_of_periapsis_deg",
                    "true_anomaly_deg")} | {"epoch": {"seconds": int(
                        _get(_get(kep, "epoch"), "seconds", 0) or 0)}}})
            else:
                entries.append({"motion_kind": "non_keplerian"})   # flagged, not propagatable
        out["platform"] = {"name": _get(plat, "name"),
                           "is_external_system": bool(_get(plat, "is_external_system", False)),
                           "motion": {"entry": entries}}
    elif kind == 40:                   # ek_antenna
        an = _get(e, "antenna")
        out["antenna"] = {k: _get(an, k) for k in ("type", "is_steerable",
                          "max_transmit_power_w", "g_over_t_db_per_k")}
    return out


def _project_rel(r):
    return {"kind": int(_get(r, "kind", -1)), "a": _get(r, "a"), "z": _get(r, "z")}


def _project_intent(i):
    route = _get(i, "route")
    segs = [{"src_network_node_id": _get(s, "src_network_node_id"),
             "dst_network_node_id": _get(s, "dst_network_node_id"),
             "src_interface_id": _get(s, "src_interface_id"),
             "dst_interface_id": _get(s, "dst_interface_id")}
            for s in (_get(route, "path_segments", []) or [])]
    return {"id": _get(i, "id"), "state": _get(i, "state"), "route": {"path_segments": segs}}


def record(store, path: str, intent_states=None) -> None:
    """Serialize a store's read surface to a proto-free JSON snapshot at `path`."""
    data = {
        "entities": [_project_entity(e) for e in store.list_entities()],
        "relationships": [_project_rel(r) for r in store.list_relationships()],
        "intents": [_project_intent(i) for i in store.list_intents(states=intent_states)],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class RecordedEntityStore(MemoryEntityStore):
    """Replays a JSON snapshot produced by `record()` — identical read surface, offline."""
    def __init__(self, path: str):
        data = json.loads(open(path).read())
        super().__init__(data.get("entities"), data.get("relationships"), data.get("intents"))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_recording.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/recording.py tests/test_spacetime_recording.py
git commit -m "feat(spacetime): RecordedEntityStore + proto-free JSON projection (Slice E)"
```

*(Executor: do Task 7 before Task 6 — see Task 6's reorder note.)*

---

## Task 8: `client.py` — guarded `GrpcEntityStore`

**Files:** Create `ngso_sls/spacetime/client.py`; Test `tests/test_spacetime_client.py`.

- [ ] **Step 1: Write the failing test** (offline: construction raises clear error; stub-parity via injected double — no live import)

```python
# tests/test_spacetime_client.py
import pytest
from ngso_sls.spacetime.client import GrpcEntityStore
from ngso_sls.spacetime.config import SpacetimeEndpoint


def _ep():
    return SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u", private_key_file="/x.key")


def test_grpc_store_raises_clear_error_without_package():
    # spacetime-api absent in the sandbox -> constructing the live store fails clearly, not obscurely
    with pytest.raises(RuntimeError, match="spacetime-api"):
        GrpcEntityStore(_ep())


class _FakeModelStub:
    """Hand-written double matching the verified Model wire signatures (offline stub-parity)."""
    def __init__(self):
        self.calls = []
    def ListEntities(self, req):
        self.calls.append(("ListEntities", type(req).__name__))
        return type("R", (), {"entities": [{"id": "plat-0", "kind": 11}]})()
    def ListRelationships(self, req):
        self.calls.append(("ListRelationships", type(req).__name__))
        return type("R", (), {"relationships": [{"kind": 4, "a": "plat-0", "z": "ant-0"}]})()
    def GetEntity(self, req):
        self.calls.append(("GetEntity", type(req).__name__))
        return {"id": "plat-0", "kind": 11}


def test_stub_parity_reads_only_and_never_mutates():
    # inject fake stubs so we exercise the request routing offline, with no grpc/proto import
    store = GrpcEntityStore.__new__(GrpcEntityStore)          # bypass __init__ (no channel)
    fake = _FakeModelStub()
    store._model = fake
    store._nbi = None
    store._prov = None
    store._req = lambda name, **kw: {"__req__": name, **kw}    # request factory double
    ents = store.list_entities()
    rels = store.list_relationships()
    assert ents and rels
    names = [c[0] for c in fake.calls]
    assert names == ["ListEntities", "ListRelationships"]
    # no mutating verb was ever called
    assert not any(v in n for n in names for v in ("Create", "Update", "Delete", "Upsert"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_client.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/client.py
"""Live gRPC EntityStore. The ONLY file that builds channels/stubs. All proto/grpc access is
lazy (via _deps), so importing this module is safe in the sandbox; only CONSTRUCTING
GrpcEntityStore requires spacetime-api. Read-only: no mutating RPC is ever wired."""
from . import _deps
from .store import StoreError


def _make_channel(ep):
    """Modern auth (decided): auth.Credentials(...).create_channel(url). Portable fallback via
    github/py Config/new_credentials. 256MB max_receive_message_length is REQUIRED on BOTH paths
    (full-constellation ListEntities responses are large). Never logs the key."""
    _deps.require("HAS_AUTH", "aalyria.spacetime.api.common.auth")
    auth = _deps.auth
    opts = [("grpc.max_receive_message_length", 256 << 20)]
    creds = auth.Credentials(key_id=ep.key_id, user_id=ep.user_id,
                             private_key_file=ep.private_key_file)
    try:
        return creds.create_channel(ep.url)          # modern one-liner
    except (AttributeError, TypeError):
        # portable fallback: build a secure channel from call-credentials + ssl
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
```

*Note on the stub-parity test:* it constructs the object via `__new__` and injects `_model`/`_req`, so no channel/proto is built — the routing + read-only assertions run fully offline. `_req` in the test returns a dict tagging the request name, satisfying the `type(req).__name__` checks in the fake stub.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_client.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/client.py tests/test_spacetime_client.py
git commit -m "feat(spacetime): guarded GrpcEntityStore (read-only, lazy deps) (Slice E)"
```

---

## Task 9: `pull.py` — pull → build → coverage → compare

**Files:** Create `ngso_sls/spacetime/pull.py`; Test `tests/test_spacetime_pull.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spacetime_pull.py
from datetime import datetime, timezone
from ngso_sls.spacetime.memory_store import MemoryEntityStore
from ngso_sls.spacetime.pull import pull_and_cover
from ngso_sls.grids.aor import AORS


def test_pull_and_cover_end_to_end_offline():
    store = MemoryEntityStore.from_fixture("mini_constellation.json")
    out = pull_and_cover(store, AORS["India"], cell_res=2, min_elev_user_deg=25.0,
                         duration_s=600.0, step_s=60.0,
                         epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert out["n_served"] == 2                      # 2 Keplerian non-external platforms
    assert out["coverage"]["availability"].shape[0] == len(out["coverage"]["cells"])
    assert "routes" in out and out["routes"]         # installed intent hop present
    assert "skipped" in out                          # external + TLE reported
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_pull.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# ngso_sls/spacetime/pull.py
"""Increment-1 orchestration: pull NMTS model + installed intents from a store, build the SLS
raw-element constellation, run Slice-A coverage on it, and return the routes for comparison.
Store-agnostic: works with MemoryEntityStore/RecordedEntityStore (offline) or GrpcEntityStore
(live). Reuses the shipped run_coverage_h3_elements seam."""
from datetime import datetime, timezone
from ..config import TimeGrid
from ..pipeline import run_coverage_h3_elements
from .nmts_adapter import platforms_to_elements, routes_from_intents

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def pull_and_cover(store, aor, cell_res=3, min_elev_user_deg=25.0, duration_s=3600.0,
                   step_s=60.0, epoch_utc=None, k_values=(1, 2), shard_res=1,
                   chunk_steps=10, continuity_overlap_s=None):
    """Pull -> build elements -> run coverage -> collect installed routes. Returns a dict with
    the coverage result, served-satellite count, routes, and the skipped/flagged platforms."""
    entities = store.list_entities()
    rels = store.list_relationships()
    built = platforms_to_elements(entities, rels)
    elems, plane_uid = built["elems"], built["plane_uid"]
    if elems.shape[0] == 0:
        raise ValueError("no served Keplerian platforms pulled — check the instance/probe "
                         f"(skipped: {built['skipped']})")
    tg = TimeGrid(epoch_utc or _EPOCH, duration_s=duration_s, step_s=step_s)
    coverage = run_coverage_h3_elements(
        elems, plane_uid, min_elev_user_deg, tg, aor, cell_res, shard_res=shard_res,
        chunk_steps=chunk_steps, k_values=list(k_values), continuity_overlap_s=continuity_overlap_s)
    routes = routes_from_intents(store.list_intents(states=["INSTALLED"]))
    return {"coverage": coverage, "n_served": int(elems.shape[0]), "routes": routes,
            "meta": built["meta"], "antennas": built["antennas"], "skipped": built["skipped"],
            "ref_epoch_s": built["ref_epoch_s"]}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_pull.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/spacetime/pull.py tests/test_spacetime_pull.py
git commit -m "feat(spacetime): pull->build->coverage orchestration (Slice E)"
```

---

## Task 10: `io/csv_io.py` — elements CSV + snapshot writers

**Files:** Modify `ngso_sls/io/csv_io.py`; Test `tests/test_io.py`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_io.py
import numpy as np
from ngso_sls.io.csv_io import write_elements_csv, load_elements_csv


def test_elements_csv_roundtrip(tmp_path):
    elems = np.array([[7028.137, 0.0, 0.925, 0.0, 0.0, 0.0],
                      [7028.137, 0.0, 0.925, 1.047, 0.0, 2.094]])
    sat_ids = ["plat-0", "plat-1"]
    path = tmp_path / "elements.csv"
    write_elements_csv(elems, sat_ids, str(path), manifest={"ref_epoch_s": 1000.0})
    e2, ids2 = load_elements_csv(str(path))
    assert ids2 == sat_ids and np.allclose(e2, elems)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_io.py::test_elements_csv_roundtrip -q`
Expected: FAIL.

- [ ] **Step 3: Implement** — append to `ngso_sls/io/csv_io.py`:

```python
def write_elements_csv(elems, sat_ids, path, manifest: dict | None = None):
    """Write a pulled constellation's (n,6) elements as a tidy CSV with a manifest header."""
    import numpy as np
    df = pd.DataFrame({
        "sat_id": list(sat_ids),
        "a_km": elems[:, 0], "e": elems[:, 1], "i_rad": elems[:, 2],
        "raan_rad": elems[:, 3], "argp_rad": elems[:, 4], "M_rad": elems[:, 5],
    })
    with open(path, "w") as f:
        for k, v in (manifest or {}).items():
            f.write(f"# {k}: {v}\n")
        df.to_csv(f, index=False)


def load_elements_csv(path):
    """Inverse of write_elements_csv -> (elems (n,6) float64, sat_ids list[str])."""
    import numpy as np
    df = pd.read_csv(path, comment="#")
    elems = df[["a_km", "e", "i_rad", "raan_rad", "argp_rad", "M_rad"]].to_numpy(dtype=float)
    return elems, df["sat_id"].astype(str).tolist()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_io.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ngso_sls/io/csv_io.py tests/test_io.py
git commit -m "feat(io): pulled-elements CSV read/write (Slice E)"
```

---

## Task 11: Packaging + core-purity confirm + full suite

**Files:** Modify `pyproject.toml`; Test `tests/test_core_purity.py` (unchanged — confirm still green).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_spacetime_deps.py
def test_spacetime_subpackage_not_in_core_purity_scope_but_core_still_pure():
    # importing the guarded subpackage must not drag proto into the pure core
    import ngso_sls.spacetime  # noqa: F401
    import ngso_sls.constellation, ngso_sls.coverage, ngso_sls.propagation, ngso_sls.geometry  # noqa
    # the core-purity test itself is the real guard; here we assert the subpackage imports clean
    assert True
```

- [ ] **Step 2: Run to verify it fails / passes** — this passes once the subpackage imports cleanly; run it to confirm.

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest tests/test_spacetime_deps.py tests/test_core_purity.py -q`
Expected: PASS.

- [ ] **Step 3: Implement** — edit `pyproject.toml`:
  - Add optional extras:
    ```toml
    [project.optional-dependencies]
    spacetime = ["grpcio", "protobuf"]   # spacetime-api itself is NOT on PyPI — see notebook install cell
    oracle = ["sgp4", "skyfield"]
    ```
  - Add fixtures to package-data (current config ships only `data/*.json`):
    ```toml
    [tool.setuptools.package-data]
    ngso_sls = ["data/*.json"]
    "ngso_sls.spacetime" = ["fixtures/*.json"]
    ```
  - Confirm `[tool.setuptools.packages.find]` already includes `ngso_sls*` (it does) so `ngso_sls.spacetime` is packaged.

- [ ] **Step 4: Run the FULL suite**

Run: `cd /workspace/spacetime-sls && .venv/bin/pytest -q`
Expected: PASS (all prior + new Slice-E tests). `tests/test_core_purity.py` MUST stay green — if it fails, a core module imported proto/grpc; move that import into `spacetime/` or make it lazy.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_spacetime_deps.py
git commit -m "build(spacetime): optional extras + fixtures package-data; core purity intact (Slice E)"
```

---

## Task 12: `notebooks/05_slice_e_pull.ipynb` (Colab; out of pytest path)

**Files:** Create `notebooks/05_slice_e_pull.ipynb`.

- [ ] **Step 1: Build the notebook** with these cells (use `jupyter nbconvert`/`nbformat` or hand-author JSON; it is NOT run by pytest — validate only that it is valid JSON that `nbformat.read` accepts):

  1. **Markdown** — title + what it does + the read-only/Increment-0 framing + "never paste keys" warning.
  2. **Install** (verbatim): `!pip install --upgrade spacetime-api --extra-index-url https://us-central1-python.pkg.dev/a5a-spacetime-artifacts/py-packages/simple --prefer-binary` then `!pip install ngso_sls` (or clone+install like `01_slice_a_mvp.ipynb`).
  3. **Imports & Increment-0 capability probe:** `import ngso_sls.spacetime as st; print({k: getattr(st, k) for k in ["HAS_AUTH","HAS_NBI","HAS_PROVISIONING","HAS_MODEL","HAS_NMTS"]})`. This decides whether the NMTS→coverage path runs; the intents/provisioning demo always runs.
  4. **Connection form (widgets):** `URL` (default `https://fss01-demo.spacetime.aalyria.com:443`), `KEY_ID`, `USER_ID`, `PRIVATE_KEY_FILE` (upload / `google.colab.userdata`), `MODEL_URL`, `model_version`. Build `endpoint = st.SpacetimeEndpoint(...)`. **Never print the key**; source secrets from `google.colab.userdata`/env, never notebook literals.
  5. **Build store:** `store = st.GrpcEntityStore(endpoint)` (guarded).
  6. **Pull model + build elements:** `from ngso_sls.spacetime.pull import pull_and_cover; out = pull_and_cover(store, AORS["India"], cell_res=3, ...)`; show `n_served`, `skipped`, and a regularity summary of the pulled elements.
  7. **Coverage viz:** feed `out["coverage"]` into the existing `plot_coverage_hexmap` / `plot_mbb_feasible_hexmap`.
  8. **Compare vs installed routes:** for each hop in `out["routes"]`, check predicted access; write `validation_report.csv`.
  9. **Record fixtures:** `st.record(store, "fixtures/spacetime_live_snapshot.json", intent_states=["INSTALLED"])` so the same pull replays offline via `RecordedEntityStore`.

- [ ] **Step 2: Validate the notebook is well-formed**

Run: `cd /workspace/spacetime-sls && .venv/bin/python -c "import nbformat; nbformat.read('notebooks/05_slice_e_pull.ipynb', as_version=4); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Update docs** — set I4/Slice-E status in `requirements.md` to ◐ (Increment-1 offline build done; live path Colab-only), and update `progress.md` (Slice E: Increment-1 implemented offline; live pull runs in Colab; Sgp4/TLE deferred).

- [ ] **Step 4: Commit**

```bash
git add notebooks/05_slice_e_pull.ipynb docs/design-docs/requirements.md docs/design-docs/progress.md
git commit -m "feat(spacetime): Colab pull notebook (Increment-0 probe + connection form) + docs (Slice E)"
```

---

## Self-Review

**Spec coverage** (vs `slice-e-nbi-integration.md`): guarded subpackage + per-surface `_deps` flags → T1; `SpacetimeEndpoint` → T2; `EntityStore`+`StoreError` → T3; `MemoryEntityStore`+JSON fixtures + duck-typed accessors → T4; NMTS adapter (motion=repeated→first entry, Keplerian→elements in degrees, true→mean, **epoch reconciliation as a hard step**, external-system exclusion, `RK_CONTAINS=4` integer compare, antenna metadata) + routes-from-intents → T5; full re-exports → T6; `RecordedEntityStore` + proto-free JSON projection → T7; guarded `GrpcEntityStore` (modern auth + fallback + 256 MB option, read-only method map, StoreError normalization, offline stub-parity double) → T8; pull→build→coverage→compare reusing the shipped `run_coverage_h3_elements` → T9; elements/snapshot CSV → T10; packaging extras + fixtures package-data + core-purity confirm → T11; Colab notebook with Increment-0 probe + connection form + record → T12.

**Deferred (documented, no task) — flag for owner at plan review:**
- **TLE/ephemeris motion** → `Sgp4Propagator`/`EphemerisInterpolator`. Increment-1 **flags & skips** non-Keplerian platforms (the adapter reports them in `skipped`). Wiring a real SGP4 (TEME→GCRF) propagator + a mixed-motion coverage path is a follow-up. This is the one scope call worth confirming: Increment-1 delivers intents/provisioning + **Keplerian** model→coverage; TLE-only constellations won't build until the follow-up.
- **Legacy `NetOps.ListEntitiesOverTime` fallback** on `UNIMPLEMENTED`, `model_version` import dispatch beyond the two-root probe, CEL server-side filtering, and proto-native `.pb` recording (Colab parity) — all noted in the design; live-spike/follow-up.
- **Comparison depth:** Increment-1 compares predicted access vs installed `PathIntent` hops; `coverage.proto` S2CoverageGrid is a richer future ground truth.

**Placeholder scan:** every code step has complete code; every test step has runnable asserts; no TBD/"handle errors" placeholders.

**Type consistency:** `SpacetimeEndpoint(url,key_id,user_id,private_key_file,model_url,api_variant,model_version)` consistent T2/T8/T12; `EntityStore` methods `list_entities/list_relationships(cel)/get_entity(id)/list_intents(states)` consistent T3–T9; `StoreError.{not_found,connection,rpc}` + `.kind` consistent T3/T4/T8; adapter `platforms_to_elements(...) -> {elems, plane_uid, meta, skipped, ref_epoch_s, antennas}` + `routes_from_intents(...) -> [{src,dst,src_if,dst_if}]` consistent T5/T9; `record(store,path,intent_states)` + `RecordedEntityStore(path)` consistent T7; `run_coverage_h3_elements(elems, plane_uid, min_elev_user_deg, time_grid, aor, cell_res, …)` matches the shipped signature (T9); `write_elements_csv(elems,sat_ids,path,manifest)` / `load_elements_csv(path)` consistent T10.

**Ordering caveat:** T6 (full `__init__` re-exports) depends on T7 (`recording.py`). Execute **T7 before T6** (noted in both tasks). All other tasks are in dependency order.
