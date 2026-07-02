# Slice A — Coverage Core — Implementation Plan (MVP-first)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A first working offline NGSO coverage engine that, for the Reliance-Jio 1600-sat dual shell, computes satellites-in-view and coverage availability over an India lat/lon grid and writes a CSV + a plot — runnable locally (`.venv`) and in Colab.

**Architecture:** Pure-NumPy vectorized core behind a `Propagator` seam (analytic Kepler+J2). Pipeline `load → enumerate(access) → aggregate → write`. Sharding/H3/terminals/sweeps are deferred to later milestones; MVP runs global (sharding off) on a lat/lon grid.

**Tech Stack:** Python 3.14, numpy, astropy (GMST/frames), pandas (CSV), matplotlib (plot), pytest; skyfield/sgp4 available as oracles. Local venv: `/workspace/spacetime-sls/.venv`.

**Design source:** `docs/design-docs/slice-a-coverage-core.md` (+ `requirements.md`). **Conventions:** SI internally (km, s, radians; degrees at I/O); core modules import only numpy (+astropy in geometry); seeded/reproducible.

**Run/test commands (local):**
- Tests: `.venv/bin/pytest -q`
- One test: `.venv/bin/pytest tests/test_x.py::test_y -v`

---

## Milestone 1 — MVP walking skeleton

File map (created in M1):
```
spacetime-sls/
  pyproject.toml
  ngso_sls/__init__.py
  ngso_sls/constants.py          # physical constants
  ngso_sls/config.py             # Shell, Constellation, TimeGrid, SimConfig
  ngso_sls/constellation/__init__.py
  ngso_sls/constellation/walker.py   # walker_elements()
  ngso_sls/propagation/__init__.py
  ngso_sls/propagation/base.py       # Propagator Protocol
  ngso_sls/propagation/kepler_j2.py  # KeplerJ2Propagator
  ngso_sls/geometry/__init__.py
  ngso_sls/geometry/frames.py        # gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
  ngso_sls/geometry/access.py        # elevation_deg
  ngso_sls/grids/__init__.py
  ngso_sls/grids/aor.py              # latlon_grid, INDIA_AOR
  ngso_sls/coverage/__init__.py
  ngso_sls/coverage/visibility.py    # max_elev_and_count
  ngso_sls/coverage/availability.py  # availability
  ngso_sls/presets.py                # jio_constellation()
  ngso_sls/pipeline.py               # run_coverage()
  ngso_sls/io/__init__.py
  ngso_sls/io/csv_io.py              # write_availability_csv, write_manifest
  ngso_sls/viz/__init__.py
  ngso_sls/viz/plots.py              # plot_availability
  notebooks/01_slice_a_mvp.ipynb
  tests/...
```

### Task 0: Repo + package scaffold

**Files:** Create `pyproject.toml`, `ngso_sls/__init__.py`, `tests/__init__.py`, `.gitignore`.

- [ ] **Step 1: git init + .gitignore**

```bash
cd /workspace/spacetime-sls
git init -q
printf '.venv/\n__pycache__/\n*.pyc\n*.egg-info/\n.pytest_cache/\noutputs/\n' > .gitignore
```

- [ ] **Step 2: pyproject.toml**

```toml
[project]
name = "ngso_sls"
version = "0.0.1"
description = "NGSO constellation coverage/availability simulator (Slice A)"
requires-python = ">=3.12"
dependencies = ["numpy", "astropy", "pandas", "matplotlib"]

[project.optional-dependencies]
oracle = ["skyfield", "sgp4"]
dev = ["pytest"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["ngso_sls*"]
```

- [ ] **Step 3: package init files**

`ngso_sls/__init__.py`:
```python
"""NGSO SLS — Slice A coverage core."""
__version__ = "0.0.1"
```
`tests/__init__.py`: empty file.

- [ ] **Step 4: editable install into the venv + verify pytest runs**

Run: `cd /workspace/spacetime-sls && .venv/bin/pip install -e ".[dev,oracle]" -q && .venv/bin/pytest -q`
Expected: pytest runs, "no tests ran" (exit 5) or 0 tests collected — no import errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "chore: scaffold ngso_sls package (Slice A MVP)"
```

### Task 1: constants

**Files:** Create `ngso_sls/constants.py`; Test `tests/test_constants.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constants.py
from ngso_sls import constants as c

def test_constants_present_and_sane():
    assert abs(c.MU_EARTH - 398600.4418) < 1e-6
    assert abs(c.RE_EQ - 6378.137) < 1e-6
    assert 1.0e-3 < c.J2 < 1.1e-3
    assert 0.0 < c.WGS84_E2 < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_constants.py -q`
Expected: FAIL (ModuleNotFoundError: ngso_sls.constants).

- [ ] **Step 3: Implement**

```python
# ngso_sls/constants.py
"""Physical constants (SI-ish: km, s, radians)."""
MU_EARTH = 398600.4418      # km^3/s^2
RE_EQ = 6378.137            # km, WGS84 equatorial radius
J2 = 1.08262668e-3          # Earth oblateness
WGS84_E2 = 6.69437999014e-3 # first eccentricity squared
```

- [ ] **Step 4: Run test to verify it passes** — `.venv/bin/pytest tests/test_constants.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -q -m "feat: physical constants"`

### Task 2: config dataclasses

**Files:** Create `ngso_sls/config.py`; Test `tests/test_config.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import numpy as np
from datetime import datetime, timezone
from ngso_sls.config import Shell, Constellation, TimeGrid, SimConfig

def test_timegrid_times():
    tg = TimeGrid(epoch_utc=datetime(2026,1,1,tzinfo=timezone.utc), duration_s=30.0, step_s=10.0)
    np.testing.assert_allclose(tg.times_s(), [0.0, 10.0, 20.0])

def test_simconfig_defaults():
    sh = Shell("p", 1200, 40, 1, 650.0, 48.0)
    sc = SimConfig(Constellation((sh,)), TimeGrid(datetime(2026,1,1,tzinfo=timezone.utc), 30.0))
    assert sc.k_coverage == 1 and sc.target_availability is None and sc.cell_layout == "UNSPEC"
    assert sh.min_elev_user_deg == 25.0
```

- [ ] **Step 2: Run → FAIL** (`.venv/bin/pytest tests/test_config.py -q`).

- [ ] **Step 3: Implement**

```python
# ngso_sls/config.py
from dataclasses import dataclass
from datetime import datetime
import numpy as np

@dataclass(frozen=True)
class Shell:
    shell_id: str
    walker_T: int
    walker_P: int
    walker_F: int
    altitude_km: float
    inclination_deg: float
    raan0_deg: float = 0.0
    phase0_deg: float = 0.0
    ecc: float = 0.0
    arg_perigee_deg: float = 0.0
    min_elev_user_deg: float = 25.0
    min_elev_feeder_deg: float = 30.0

@dataclass(frozen=True)
class Constellation:
    shells: tuple[Shell, ...]

@dataclass(frozen=True)
class TimeGrid:
    epoch_utc: datetime
    duration_s: float
    step_s: float = 10.0
    quantum_width_s: float = 10.0
    def times_s(self) -> np.ndarray:
        return np.arange(0.0, self.duration_s, self.step_s)

@dataclass(frozen=True)
class SimConfig:
    constellation: Constellation
    time_grid: TimeGrid
    seed: int = 0
    target_availability: float | None = None
    k_coverage: int = 1
    cell_layout: str = "UNSPEC"   # EFC|QEFC|EMC|UNSPEC — inert metadata (SA8)
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat: config dataclasses"`

### Task 3: Walker constellation expansion

**Files:** Create `ngso_sls/constellation/__init__.py` (empty), `ngso_sls/constellation/walker.py`; Test `tests/test_walker.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_walker.py
import numpy as np
from ngso_sls.config import Shell
from ngso_sls.constellation.walker import walker_elements
from ngso_sls.constants import RE_EQ

def test_walker_shape_and_planes():
    el = walker_elements(Shell("p", 1200, 40, 1, 650.0, 48.0))
    assert el.shape == (1200, 6)
    # 40 distinct RAANs, 30 sats per plane
    raans = np.round(np.degrees(el[:,3]), 6)
    assert len(np.unique(raans)) == 40
    # semi-major axis = Re + alt; inclination preserved
    np.testing.assert_allclose(el[:,0], RE_EQ + 650.0)
    np.testing.assert_allclose(el[:,2], np.radians(48.0))

def test_walker_divisibility_error():
    import pytest
    with pytest.raises(ValueError):
        walker_elements(Shell("p", 100, 7, 1, 650.0, 48.0))
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# ngso_sls/constellation/walker.py
import numpy as np
from ..config import Shell
from ..constants import RE_EQ

def walker_elements(shell: Shell) -> np.ndarray:
    """Expand a Walker T/P/F shell to (n_sat, 6) classical elements
    [a_km, e, i_rad, raan_rad, argp_rad, M_rad]."""
    T, P, F = shell.walker_T, shell.walker_P, shell.walker_F
    if T % P != 0:
        raise ValueError(f"walker_T ({T}) must be divisible by walker_P ({P})")
    S = T // P
    a = RE_EQ + shell.altitude_km
    inc = np.radians(shell.inclination_deg)
    argp = np.radians(shell.arg_perigee_deg)
    e = shell.ecc
    p_idx = np.repeat(np.arange(P), S)          # plane index per sat
    s_idx = np.tile(np.arange(S), P)            # in-plane index per sat
    raan = np.radians(shell.raan0_deg + p_idx * 360.0 / P) % (2*np.pi)
    M = np.radians(shell.phase0_deg + s_idx * 360.0 / S + p_idx * F * 360.0 / T) % (2*np.pi)
    out = np.empty((T, 6))
    out[:,0] = a; out[:,1] = e; out[:,2] = inc
    out[:,3] = raan; out[:,4] = argp; out[:,5] = M
    return out
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat: Walker T/P/F expansion"`

### Task 4: Propagator seam + Kepler+J2

**Files:** Create `ngso_sls/propagation/__init__.py` (empty), `base.py`, `kepler_j2.py`; Test `tests/test_kepler_j2.py`.

- [ ] **Step 1: Write the failing tests (oracle: two-body conservation + SSO nodal regression)**

```python
# tests/test_kepler_j2.py
import numpy as np
from ngso_sls.propagation.base import Propagator
from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator
from ngso_sls.constants import MU_EARTH, RE_EQ

def _circular_elem(alt_km, inc_deg, raan=0.0, M0=0.0):
    return np.array([[RE_EQ+alt_km, 0.0, np.radians(inc_deg), raan, 0.0, M0]])

def test_protocol_runtime():
    assert isinstance(KeplerJ2Propagator(), Propagator)

def test_circular_two_body_radius_constant():
    prop = KeplerJ2Propagator(j2=0.0)
    el = _circular_elem(650.0, 48.0)
    a = el[0,0]
    n = np.sqrt(MU_EARTH/a**3); period = 2*np.pi/n
    t = np.linspace(0, period, 50)
    r = prop.propagate(el, t)               # (1,50,3)
    rad = np.linalg.norm(r, axis=-1)[0]
    np.testing.assert_allclose(rad, a, rtol=1e-9)
    # returns to start after one period (J2=0)
    np.testing.assert_allclose(r[0,0], r[0,-1], atol=1e-3)

def test_sso_nodal_regression():
    # 700 km sun-sync ~ inc 98.19 deg -> RAAN drift ~ +0.9856 deg/day
    prop = KeplerJ2Propagator()
    el = _circular_elem(700.0, 98.19)
    day = 86400.0
    r0 = prop.propagate(el, np.array([0.0]))
    # measure RAAN drift via internal rate: propagate 1 day, compare orbit-plane normal longitude
    # Use the analytic raan_dot exposed for testability:
    raan_dot_deg_day = np.degrees(prop.raan_dot(el)[0]) * day
    assert 0.95 < raan_dot_deg_day < 1.02
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement base.py**

```python
# ngso_sls/propagation/base.py
from typing import Protocol, runtime_checkable
import numpy as np

@runtime_checkable
class Propagator(Protocol):
    def propagate(self, elements: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        """elements (n_sat,6) [a,e,i,raan,argp,M0]; times_s (n_time,) -> (n_sat,n_time,3) ECI km."""
        ...
```

- [ ] **Step 4: Implement kepler_j2.py**

```python
# ngso_sls/propagation/kepler_j2.py
import numpy as np
from ..constants import MU_EARTH, RE_EQ, J2

class KeplerJ2Propagator:
    def __init__(self, mu: float = MU_EARTH, re: float = RE_EQ, j2: float = J2):
        self.mu, self.re, self.j2 = mu, re, j2

    def _rates(self, elements):
        a = elements[:,0]; e = elements[:,1]; inc = elements[:,2]
        n0 = np.sqrt(self.mu / a**3)
        p = a * (1 - e**2)
        f = (self.re / p)**2
        cosi = np.cos(inc); sin2i = np.sin(inc)**2
        raan_dot = -1.5 * n0 * self.j2 * f * cosi
        argp_dot = 0.75 * n0 * self.j2 * f * (5*cosi**2 - 1)
        m_dot = n0 * (1 + 1.5*self.j2*f*np.sqrt(1-e**2)*(1 - 1.5*sin2i))
        return raan_dot, argp_dot, m_dot

    def raan_dot(self, elements):   # exposed for tests
        return self._rates(elements)[0]

    def propagate(self, elements: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        a = elements[:,0][:,None]; e = elements[:,1][:,None]; inc = elements[:,2][:,None]
        raan0 = elements[:,3][:,None]; argp0 = elements[:,4][:,None]; M0 = elements[:,5][:,None]
        raan_dot, argp_dot, m_dot = (r[:,None] for r in self._rates(elements))
        t = times_s[None,:]
        raan = raan0 + raan_dot*t
        argp = argp0 + argp_dot*t
        M = M0 + m_dot*t
        E = _kepler_E(M, e)
        nu = 2*np.arctan2(np.sqrt(1+e)*np.sin(E/2), np.sqrt(1-e)*np.cos(E/2))
        r = a*(1 - e*np.cos(E))
        xp = r*np.cos(nu); yp = r*np.sin(nu)
        cO, sO = np.cos(raan), np.sin(raan)
        ci, si = np.cos(inc), np.sin(inc)
        cw, sw = np.cos(argp), np.sin(argp)
        x = (cO*cw - sO*sw*ci)*xp + (-cO*sw - sO*cw*ci)*yp
        y = (sO*cw + cO*sw*ci)*xp + (-sO*sw + cO*cw*ci)*yp
        z = (sw*si)*xp + (cw*si)*yp
        return np.stack([x, y, z], axis=-1)

def _kepler_E(M, e, tol=1e-12, itmax=60):
    E = np.array(M, dtype=float)
    for _ in range(itmax):
        dE = (E - e*np.sin(E) - M) / (1 - e*np.cos(E))
        E -= dE
        if np.max(np.abs(dE)) < tol:
            break
    return E
```

- [ ] **Step 5: Run → PASS.** `git commit -am "feat: Propagator seam + vectorized Kepler+J2"`

### Task 5: geometry/frames

**Files:** Create `ngso_sls/geometry/__init__.py` (empty), `frames.py`; Test `tests/test_frames.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frames.py
import numpy as np
from datetime import datetime, timezone
from ngso_sls.geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from ngso_sls.constants import RE_EQ

def test_geodetic_equator_prime_meridian():
    p = geodetic_to_ecef(0.0, 0.0, 0.0)
    np.testing.assert_allclose(p, [RE_EQ, 0.0, 0.0], atol=1e-6)

def test_enu_up_unit_and_radial_at_equator():
    up = enu_up(0.0, 0.0)
    np.testing.assert_allclose(up, [1.0, 0.0, 0.0], atol=1e-12)

def test_eci_ecef_zero_gmst_identity():
    r = np.array([[[7000.0, 0.0, 0.0]]])   # (1,1,3)
    out = eci_to_ecef(r, np.array([0.0]))
    np.testing.assert_allclose(out, r, atol=1e-9)

def test_gmst_runs_vectorized():
    g = gmst_rad(datetime(2026,1,1,tzinfo=timezone.utc), np.array([0.0, 3600.0]))
    assert g.shape == (2,) and np.all((g >= 0) & (g < 2*np.pi))
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# ngso_sls/geometry/frames.py
import numpy as np
from astropy.time import Time
import astropy.units as u
from ..constants import RE_EQ, WGS84_E2

def gmst_rad(epoch_utc, times_s) -> np.ndarray:
    t = Time(epoch_utc, scale="utc") + np.asarray(times_s) * u.s
    return np.asarray(t.sidereal_time("mean", "greenwich").to_value(u.rad)) % (2*np.pi)

def eci_to_ecef(r_eci: np.ndarray, gmst: np.ndarray) -> np.ndarray:
    cg = np.cos(gmst); sg = np.sin(gmst)           # (n_time,)
    x, y, z = r_eci[...,0], r_eci[...,1], r_eci[...,2]
    xe = cg*x + sg*y
    ye = -sg*x + cg*y
    return np.stack([xe, ye, z], axis=-1)

def geodetic_to_ecef(lat_deg, lon_deg, h_m=0.0) -> np.ndarray:
    lat = np.radians(np.asarray(lat_deg, float)); lon = np.radians(np.asarray(lon_deg, float))
    h = np.asarray(h_m, float) / 1000.0
    N = RE_EQ / np.sqrt(1 - WGS84_E2*np.sin(lat)**2)
    x = (N+h)*np.cos(lat)*np.cos(lon)
    y = (N+h)*np.cos(lat)*np.sin(lon)
    z = (N*(1-WGS84_E2)+h)*np.sin(lat)
    return np.stack([x, y, z], axis=-1)

def enu_up(lat_deg, lon_deg) -> np.ndarray:
    lat = np.radians(np.asarray(lat_deg, float)); lon = np.radians(np.asarray(lon_deg, float))
    return np.stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)], axis=-1)
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat: geometry frames (GMST, ECI/ECEF, geodetic, ENU up)"`

### Task 6: geometry/access (elevation)

**Files:** Create `ngso_sls/geometry/access.py`; Test `tests/test_access.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_access.py
import numpy as np
from ngso_sls.geometry.frames import geodetic_to_ecef, enu_up
from ngso_sls.geometry.access import elevation_deg
from ngso_sls.constants import RE_EQ

def test_elevation_overhead_and_horizon():
    cell = geodetic_to_ecef(0.0, 0.0, 0.0)[None,:]      # (1,3)
    up = enu_up(0.0, 0.0)[None,:]                         # (1,3)
    overhead = np.array([[[RE_EQ+650.0, 0.0, 0.0]]])      # (1,1,3) straight up
    el = elevation_deg(cell, up, overhead)               # (1,1,1)
    np.testing.assert_allclose(el[0,0,0], 90.0, atol=1e-6)
    # true geometric horizon: sat whose ECEF x == cell radius -> LOS perpendicular to up -> 0 deg
    y = np.sqrt((RE_EQ+650.0)**2 - RE_EQ**2)
    horizon = np.array([[[RE_EQ, y, 0.0]]])
    np.testing.assert_allclose(elevation_deg(cell, up, horizon)[0,0,0], 0.0, atol=1e-6)
    # a quarter-orbit away in longitude is well below the horizon
    far_y = np.array([[[0.0, RE_EQ+650.0, 0.0]]])
    assert elevation_deg(cell, up, far_y)[0,0,0] < -30.0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# ngso_sls/geometry/access.py
import numpy as np

def elevation_deg(cell_ecef: np.ndarray, cell_up: np.ndarray, sat_ecef: np.ndarray) -> np.ndarray:
    """cell_ecef (n_cell,3), cell_up (n_cell,3), sat_ecef (n_sat,n_time,3)
    -> elevation in degrees, shape (n_cell, n_time, n_sat)."""
    rho = sat_ecef[None,:,:,:] - cell_ecef[:,None,None,:]   # (n_cell,n_sat,n_time,3)
    rng = np.linalg.norm(rho, axis=-1)                       # (n_cell,n_sat,n_time)
    dot = np.sum(rho * cell_up[:,None,None,:], axis=-1)      # (n_cell,n_sat,n_time)
    el = np.degrees(np.arcsin(np.clip(dot/rng, -1.0, 1.0)))
    return np.moveaxis(el, 1, 2)                             # (n_cell,n_time,n_sat)
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat: topocentric elevation"`

### Task 7: grids/aor (lat/lon grid + India)

**Files:** Create `ngso_sls/grids/__init__.py` (empty), `aor.py`; Test `tests/test_grids.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grids.py
import numpy as np
from ngso_sls.grids.aor import latlon_grid, INDIA_AOR

def test_latlon_grid_counts_and_bounds():
    lat, lon = latlon_grid(0.0, 2.0, 0.0, 2.0, 1.0)
    assert lat.shape == lon.shape == (9,)   # 3x3
    assert lat.min() == 0.0 and lat.max() == 2.0

def test_india_aor_keys():
    assert set(INDIA_AOR) == {"lat_min","lat_max","lon_min","lon_max"}
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# ngso_sls/grids/aor.py
import numpy as np

INDIA_AOR = {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}

def latlon_grid(lat_min, lat_max, lon_min, lon_max, step_deg):
    lats = np.arange(lat_min, lat_max + 1e-9, step_deg)
    lons = np.arange(lon_min, lon_max + 1e-9, step_deg)
    lon_g, lat_g = np.meshgrid(lons, lats)
    return lat_g.ravel(), lon_g.ravel()
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat: lat/lon AOR grid + India bbox"`

### Task 8: coverage (visibility + availability)

**Files:** Create `ngso_sls/coverage/__init__.py` (empty), `visibility.py`, `availability.py`; Test `tests/test_coverage.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage.py
import numpy as np
from ngso_sls.coverage.visibility import max_elev_and_count
from ngso_sls.coverage.availability import availability

def test_max_and_count():
    # (n_cell=1, n_time=2, n_sat=3)
    el = np.array([[[10., 40., -5.], [-1., -2., 30.]]])
    mx, cnt = max_elev_and_count(el, min_elev_deg=25.0)
    np.testing.assert_allclose(mx, [[40., 30.]])
    np.testing.assert_array_equal(cnt, [[1, 1]])

def test_availability_integer_fraction():
    cnt = np.array([[1, 0, 1, 1]])   # 3 of 4 timesteps serviceable
    np.testing.assert_allclose(availability(cnt, k=1), [0.75])
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement visibility.py**

```python
# ngso_sls/coverage/visibility.py
import numpy as np

def max_elev_and_count(elev_deg: np.ndarray, min_elev_deg: float):
    """elev_deg (n_cell,n_time,n_sat) -> (max_elev (n_cell,n_time), n_in_view (n_cell,n_time))."""
    max_elev = np.nanmax(elev_deg, axis=-1)
    n_in_view = np.sum(elev_deg >= min_elev_deg, axis=-1)
    return max_elev, n_in_view
```

- [ ] **Step 4: Implement availability.py**

```python
# ngso_sls/coverage/availability.py
import numpy as np

def availability(n_in_view: np.ndarray, k: int = 1) -> np.ndarray:
    """Fraction of timesteps with >= k sats in view, per cell. Integer-count form (deterministic)."""
    serviceable = (n_in_view >= k)
    return serviceable.sum(axis=1) / n_in_view.shape[1]
```

- [ ] **Step 5: Run → PASS + Commit** — `git commit -am "feat: coverage visibility + availability"`

### Task 9: Jio preset + pipeline

**Files:** Create `ngso_sls/presets.py`, `ngso_sls/pipeline.py`; Test `tests/test_pipeline.py`.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_pipeline.py
import numpy as np
from datetime import datetime, timezone
from ngso_sls.presets import jio_constellation
from ngso_sls.config import TimeGrid, SimConfig
from ngso_sls.pipeline import run_coverage
from ngso_sls.grids.aor import INDIA_AOR

def test_pipeline_jio_india_smoke():
    cons = jio_constellation()
    assert sum(s.walker_T for s in cons.shells) == 1600
    tg = TimeGrid(datetime(2026,1,1,tzinfo=timezone.utc), duration_s=600.0, step_s=60.0)
    sc = SimConfig(cons, tg)
    res = run_coverage(sc, aor=INDIA_AOR, grid_step_deg=4.0)
    assert res["availability"].shape == res["lat"].shape
    assert np.all((res["availability"] >= 0) & (res["availability"] <= 1))
    # India is well inside both shells' latitude reach -> some coverage somewhere
    assert res["availability"].max() > 0.0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement presets.py**

```python
# ngso_sls/presets.py
from .config import Shell, Constellation

def jio_constellation() -> Constellation:
    primary = Shell("primary", 1200, 40, 1, 650.0, 48.0)
    secondary = Shell("secondary", 400, 20, 7, 650.0, 70.0)
    return Constellation((primary, secondary))
```

- [ ] **Step 4: Implement pipeline.py**

```python
# ngso_sls/pipeline.py
import numpy as np
from .config import SimConfig
from .constellation.walker import walker_elements
from .propagation.kepler_j2 import KeplerJ2Propagator
from .geometry.frames import gmst_rad, eci_to_ecef, geodetic_to_ecef, enu_up
from .geometry.access import elevation_deg
from .grids.aor import latlon_grid
from .coverage.visibility import max_elev_and_count
from .coverage.availability import availability

def run_coverage(sim: SimConfig, aor: dict, grid_step_deg: float, propagator=None) -> dict:
    propagator = propagator or KeplerJ2Propagator()
    elems = np.vstack([walker_elements(s) for s in sim.constellation.shells])
    min_elev = min(s.min_elev_user_deg for s in sim.constellation.shells)
    times = sim.time_grid.times_s()
    r_eci = propagator.propagate(elems, times)                       # (n_sat,n_time,3)
    gmst = gmst_rad(sim.time_grid.epoch_utc, times)                  # (n_time,)
    r_ecef = eci_to_ecef(r_eci, gmst)
    lat, lon = latlon_grid(aor["lat_min"], aor["lat_max"], aor["lon_min"], aor["lon_max"], grid_step_deg)
    cell_ecef = geodetic_to_ecef(lat, lon)                           # (n_cell,3)
    cell_up = enu_up(lat, lon)
    elev = elevation_deg(cell_ecef, cell_up, r_ecef)                 # (n_cell,n_time,n_sat)
    _, n_in_view = max_elev_and_count(elev, min_elev)
    avail = availability(n_in_view, k=sim.k_coverage)
    return {"lat": lat, "lon": lon, "availability": avail, "min_elev_deg": min_elev}
```

- [ ] **Step 5: Run → PASS + Commit** — `git commit -am "feat: Jio preset + run_coverage pipeline"`

### Task 10: io (CSV + manifest)

**Files:** Create `ngso_sls/io/__init__.py` (empty), `csv_io.py`; Test `tests/test_io.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_io.py
import pandas as pd, numpy as np
from ngso_sls.io.csv_io import write_availability_csv

def test_write_availability_csv(tmp_path):
    res = {"lat": np.array([0.,1.]), "lon": np.array([10.,11.]),
           "availability": np.array([0.5, 1.0]), "min_elev_deg": 25.0}
    path = tmp_path/"avail.csv"
    write_availability_csv(res, path, manifest={"seed": 0, "cell_layout": "UNSPEC"})
    df = pd.read_csv(path, comment="#")
    assert list(df.columns) == ["cell_id","lat","lon","availability"]
    assert len(df) == 2
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# ngso_sls/io/csv_io.py
import pandas as pd

def write_availability_csv(res: dict, path, manifest: dict):
    df = pd.DataFrame({
        "cell_id": range(len(res["lat"])),
        "lat": res["lat"], "lon": res["lon"], "availability": res["availability"],
    })
    with open(path, "w") as f:
        for k, v in manifest.items():
            f.write(f"# {k}: {v}\n")
        f.write(f"# min_elev_deg: {res['min_elev_deg']}\n")
        df.to_csv(f, index=False)
```

- [ ] **Step 4: Run → PASS + Commit** — `git commit -am "feat: availability CSV + manifest header"`

### Task 11: viz + Colab notebook + docs sync

**Files:** Create `ngso_sls/viz/__init__.py` (empty), `plots.py`; Test `tests/test_viz.py`; Create `notebooks/01_slice_a_mvp.ipynb`; update `docs/design-docs/progress.md` + `requirements.md`.

- [ ] **Step 1: Write the failing test (headless smoke)**

```python
# tests/test_viz.py
import matplotlib
matplotlib.use("Agg")
import numpy as np
from ngso_sls.viz.plots import plot_availability

def test_plot_returns_figure():
    res = {"lat": np.array([0.,1.,2.]), "lon": np.array([0.,1.,2.]),
           "availability": np.array([0.1,0.5,0.9]), "min_elev_deg": 25.0}
    fig = plot_availability(res)
    assert fig is not None and len(fig.axes) >= 1
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement plots.py**

```python
# ngso_sls/viz/plots.py
import matplotlib.pyplot as plt

def plot_availability(res: dict):
    fig, ax = plt.subplots(figsize=(7,6))
    sc = ax.scatter(res["lon"], res["lat"], c=res["availability"], s=40,
                    cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title(f"Coverage availability (min elev {res['min_elev_deg']}°)")
    fig.colorbar(sc, ax=ax, label="availability")
    return fig
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Create the Colab notebook**

`notebooks/01_slice_a_mvp.ipynb` — cells:
1. (markdown) title + "runs in Colab and locally".
2. (code) `!pip install -q numpy astropy pandas matplotlib` then `import sys; sys.path.append('..')` (Colab: clone/copy `ngso_sls`).
3. (code)
```python
from datetime import datetime, timezone
from ngso_sls.presets import jio_constellation
from ngso_sls.config import TimeGrid, SimConfig
from ngso_sls.pipeline import run_coverage
from ngso_sls.grids.aor import INDIA_AOR
from ngso_sls.viz.plots import plot_availability
from ngso_sls.io.csv_io import write_availability_csv

sim = SimConfig(jio_constellation(),
                TimeGrid(datetime(2026,1,1,tzinfo=timezone.utc), duration_s=3600.0, step_s=60.0))
res = run_coverage(sim, INDIA_AOR, grid_step_deg=2.0)   # MVP unchunked; finer grids await M3
write_availability_csv(res, "coverage_availability.csv", {"seed": sim.seed, "cell_layout": sim.cell_layout})
plot_availability(res)
```

- [ ] **Step 6: Run the notebook headlessly to confirm it executes**

Run: `.venv/bin/python -c "import nbformat; nb=nbformat.read('notebooks/01_slice_a_mvp.ipynb', as_version=4); print('cells', len(nb.cells))"` (sanity), then execute the pipeline cell logic via `.venv/bin/python -m pytest tests/test_pipeline.py -q`.
Expected: pipeline test passes (the notebook uses the same code path).

- [ ] **Step 7: Full test run**

Run: `.venv/bin/pytest -q`
Expected: all tests pass.

- [ ] **Step 8: Docs sync + commit**

Update `docs/design-docs/progress.md` (M1 done) and flip the relevant `requirements.md` rows (N1/N2/SA1 partial-→ implemented for the MVP subset). Then:
```bash
git add -A && git commit -q -m "feat: viz + Colab MVP notebook + docs sync (Slice A M1 complete)"
```

**M1 done = a working coverage map for the Jio constellation over India, CSV + plot, locally and in Colab.**

---

## Milestones 2–8 (roadmap — each gets its own plan when reached)

Each milestone is additive, keeps all M1 tests green, and follows the same TDD cadence. Detailed step-by-step plans are written at the start of each (per the design doc).

- **M2 — Oracle hardening & accuracy.** Independent ECI cross-check vs Skyfield/SGP4 for a synthesized circular orbit; document along/cross/radial error vs propagation time; lock `step_s` accuracy guidance (boolean-agreement metric). (Design §6.)
- **M3 — H3 grid + single-owner `cellToParent` shards + conservative cap pre-filter (λ=9.674°). ✓ DONE (2026-06-30).** `grids/h3_grid.py`, `grids/shards.py`, `coverage/prefilter.py`, `pipeline.run_coverage_h3`; **CI invariant `sharded == monolithic`** holds bit-identical; ~18× sat-axis pruning. Sharding default-off. (Design §3.)
- **M4 — Elevation-threshold sweep + serving-elevation CDF.** `availability_by_elevation(cell,θ)` via broadcast on `max_elev`; monotonicity assert. (Design §4.)
- **M5 — `terminals/` (UT distributions).** `TerminalSet` + seeded generators (uniform/population/hotspot/polygon/CSV); user-weighted availability + %-users-covered. (Design §4, SA4.)
- **M6 — In-view interval family.** Per-(sat,cell/UT) intervals + distributions + count/frequency + in-view fraction; censoring flags; in-view-fraction == availability cross-check. (Design §4, SA7.)
- **M7 — Min-N sweep. ✓ DONE (2026-07-01, %-of-area metric).** `sweep.min_sat_sweep` (thin a Walker shell by sats/plane → total N; per-cell availability → % of AOR cells ≥ target at k), `plot_min_sat_sweep` (coverage-vs-N + min-N marker), `MinSatSweep` UI + notebook section, CSV. Jio primary/India example: min N ≈ 800 for 95% of area @ 99% avail, k=1. **Deferred:** population-weighted %-users (needs public raster loader — D1). (Design §4.)
- **M8 — `cell_layout` inert metadata + layout-independence CI guard + outputs vs lat & global heatmap.** Stamp `cell_layout` into manifest/headers; CI guard (data bit-identical across layout values); finish outputs 1 (sats-in-view vs lat) & 2 (global heatmap). (Design §4, SA8.)

- **M9 — Coarse terrain masking** (mountains). Raise the per-cell effective min-elevation by a
  terrain horizon mask so relief reduces low-elevation visibility. **Tier 1 (simple):** scalar
  per-cell `terrain_mask_deg` — from a coarse DEM (`mask ≈ atan((max-neighbourhood-relief)/dist)`)
  or user-supplied CSV — applied as `elev ≥ min_elev + terrain_mask[cell]` in the visibility test
  (small change to the geometry/coverage contract: min-elev becomes a per-cell vector). **Tier 2
  (better):** azimuth-dependent skyline horizon per cell (compare satellite (elev, az) vs
  mask(az); needs the already-computed azimuth + a DEM skyline). Data: bundle/fetch a coarse DEM
  (e.g. ETOPO downsampled) or accept per-cell masks. (Design §4; SA11.)

**Multi-worker scaling (N7)** enters the testing strategy from M3 onward (shards are embarrassingly parallel; validate 1→n equivalence).

**M4 (elevation sweep), M5 (UT distributions + population-weighted %-users), M6 (in-view intervals),
M2 (oracle hardening)** remain the other open Slice-A pieces.

---

## Self-review notes
- Spec coverage: M1 covers requirements N1/N2/N4/SA1(partial)/SA2(output 3 + foundation); SA5/SA3/SA4/SA7/SA8/D1 and outputs 1/2/4 are explicitly scheduled in M2–M8.
- Types consistent across tasks: `walker_elements`→(n_sat,6); `propagate`→(n_sat,n_time,3); `elevation_deg`→(n_cell,n_time,n_sat); `max_elev_and_count`/`availability` consume those shapes; `run_coverage` returns `{lat,lon,availability,min_elev_deg}` used by io/viz/tests.
- No placeholders: every step has real code/commands/expected outcome.
