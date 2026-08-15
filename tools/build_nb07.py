#!/usr/bin/env python3
"""Generate notebooks/07_live_coverage_explorer.ipynb — the notebook-01 (Slice A) coverage
analysis, but with the constellation pulled from a LIVE Spacetime instance instead of a
Walker preset. Read-only: only Store.Get/GetEntities are wired in StorageEntityStore."""
import json

CELLS = []


def md(src):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": src})


def code(src):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": src})


md("""# NGSO SLS — Live Coverage Explorer (Slice A analysis on a live constellation)

The notebook-01 coverage analysis (n-in-view, max-elevation, availability curves, latitude
profile, elevation sweep) computed on the **live constellation pulled from Spacetime**
(fss01-demo: 150-sat, 10×15, 53°, ~1157 km) instead of a Walker preset.

**Read-only guarantee:** the pull uses `StorageEntityStore`, which wires only
`Store.Get` / `Store.GetEntities` — no write RPC exists on the client. Nothing in this
notebook alters the instance model or provisioning.

**Data source:** live raw Store (default `localhost:9999`, override `SLS_STORE_TARGET`)
with automatic fallback to the textproto dump (`SLS_DUMP_DIR`).
""")

code("""# === Setup & live pull ===
import os, sys, pathlib, datetime
_REPO = pathlib.Path.cwd().resolve()
while _REPO != _REPO.parent and not (_REPO / "ngso_sls").is_dir():
    _REPO = _REPO.parent
for p in (str(_REPO), str(_REPO / "vendor" / "spacetime_api_stubs")):
    if p not in sys.path:
        sys.path.insert(0, p)
import numpy as np
import matplotlib.pyplot as plt
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements

TARGET = os.environ.get("SLS_STORE_TARGET", "localhost:9999")
try:
    from ngso_sls.spacetime.client import StorageEntityStore
    _store = StorageEntityStore(TARGET)
    entities, rels = _store.list_entities(), _store.list_relationships()
    SOURCE = f"live {TARGET}"
except Exception as exc:
    print(f"live store unavailable ({type(exc).__name__}) -> loading dump")
    import glob
    from google.protobuf import text_format
    from ngso_sls.spacetime import _deps
    from ngso_sls.spacetime.client import _NmtsEntityView
    DUMP_DIR = os.environ.get("SLS_DUMP_DIR") or next(
        (str(d) for d in (_REPO.parent / "fss01-demo-dump",
                          pathlib.Path("/workspace/fss01-demo-dump")) if d.is_dir()), None)
    def _load(pattern):
        out = []
        for path in sorted(glob.glob(f"{DUMP_DIR}/{pattern}")):
            box = _deps.storage_pb2.TxtpbEntities()
            with open(path) as f:
                text_format.Parse(f.read(), box)
            out.extend(box.entity)
        return out
    entities = [_NmtsEntityView(e.nmts_entity) for e in _load("nmts/entities_ek_platform.txtpb")]
    rels = [e.nmts_relationship for e in _load("nmts/relationships_rk_contains.txtpb")]
    SOURCE = f"dump {DUMP_DIR}"

built = platforms_to_elements(entities, rels)
elems, plane_uid = built["elems"], built["plane_uid"]
print(f"source: {SOURCE}")
print(f"served Keplerian satellites: {elems.shape[0]} "
      f"(skipped {len(built['skipped'])} ground/non-Keplerian platforms)")
""")

code("""# === What constellation is this? (derived from the live elements) ===
from ngso_sls.constants import RE_EQ
alt_km = elems[:, 0] * (1 + elems[:, 1]) - RE_EQ
inc_deg = np.degrees(elems[:, 2])
raan_deg = np.degrees(elems[:, 3])
M_deg = np.degrees(elems[:, 5])
n_planes = len(np.unique(plane_uid))
print(f"altitude: {alt_km.min():.0f}-{alt_km.max():.0f} km | inclination: "
      f"{inc_deg.min():.1f}-{inc_deg.max():.1f} deg | {n_planes} planes x "
      f"{elems.shape[0] // max(n_planes,1)} sats")

fig, ax = plt.subplots(1, 2, figsize=(13, 4))
sc = ax[0].scatter(raan_deg, M_deg, c=plane_uid, cmap="tab10", s=18)
ax[0].set_xlabel("RAAN [deg]"); ax[0].set_ylabel("mean anomaly [deg]")
ax[0].set_title("Live constellation lattice (color = plane)")
ax[1].hist(alt_km, bins=20, color="tab:blue")
ax[1].set_xlabel("apoapsis altitude [km]"); ax[1].set_title("Altitude distribution")
plt.tight_layout(); plt.show()
""")

code("""# === Global coverage run (the nb01 headline analysis, live constellation) ===
from datetime import datetime, timezone
from ngso_sls.pipeline import run_coverage_h3_elements
from ngso_sls.config import TimeGrid
from ngso_sls.grids.aor import AORS

EPOCH_UTC  = datetime(2026, 1, 1, tzinfo=timezone.utc)
MIN_ELEV   = 25.0
DURATION_S = 3600.0
STEP_S     = 60.0

tg = TimeGrid(EPOCH_UTC, duration_s=DURATION_S, step_s=STEP_S)
res_global = run_coverage_h3_elements(
    elems, plane_uid, MIN_ELEV, tg, AORS["Global"], cell_res=2,
    shard_res=1, chunk_steps=10, k_values=[1, 2])
av = res_global["availability_by_k"][1]
print(f"Global grid: {len(res_global['cells'])} cells | k=1 availability "
      f"mean={av.mean():.3f}, fully-covered cells={float((av >= 1.0).mean()):.1%}")
""")

code("""# === Global maps & latitude profile ===
from ngso_sls.viz.plots import (plot_availability_map, plot_sats_in_view_hexmap,
                                plot_sats_in_view_vs_latitude, plot_availability,
                                plot_availability_hist)
plot_availability_map(res_global); plt.show()
plot_sats_in_view_hexmap(res_global); plt.show()
plot_sats_in_view_vs_latitude(res_global); plt.show()
""")

code("""# === Availability curves & distribution (k=1,2) ===
plot_availability(res_global); plt.show()
plot_availability_hist(res_global); plt.show()
""")

code("""# === Regional zoom + min-elevation sweep (Europe, H3 res 3) ===
sweep = {}
for elev in (10.0, 25.0, 40.0):
    sweep[elev] = run_coverage_h3_elements(
        elems, plane_uid, elev, tg, AORS["Europe"], cell_res=3,
        shard_res=1, chunk_steps=10, k_values=[1])
fig, ax = plt.subplots(figsize=(8, 4))
for elev, r in sweep.items():
    av = np.sort(r["availability_by_k"][1])[::-1]
    ax.plot(np.linspace(0, 100, len(av)), av * 100, label=f"min elev {elev:.0f} deg")
ax.set_xlabel("% of Europe cells (sorted)"); ax.set_ylabel("k=1 availability [%]")
ax.set_title(f"Europe (res 3, {len(sweep[25.0]['cells'])} cells) — elevation-mask sensitivity, "
             "live constellation"); ax.legend(); ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()
for elev, r in sweep.items():
    print(f"  min_elev {elev:4.0f} deg -> mean k=1 availability {r['availability_by_k'][1].mean():.3f}")
""")

code("""# === CSV export (CSV-out convention) ===
from ngso_sls.io.csv_io import write_availability_csv, write_elements_csv
out_dir = _REPO / "outputs"; out_dir.mkdir(exist_ok=True)
manifest = {"source": SOURCE, "epoch_utc": str(EPOCH_UTC), "min_elev_deg": MIN_ELEV,
            "duration_s": DURATION_S, "step_s": STEP_S, "n_sats": int(elems.shape[0]),
            "snapshot_utc": datetime.now(timezone.utc).isoformat()}
write_availability_csv(res_global, out_dir / "live_global_availability.csv", manifest)
write_elements_csv(elems, [m["sat_id"] for m in built["meta"]],
                   out_dir / "live_constellation_elements.csv", manifest)
print("wrote:", *[p.name for p in out_dir.glob('live_*.csv')])
""")

md("""**Reading the results** — this is the Slice-A analysis of notebook 01, but the
constellation under test is whatever the live instance is actually flying. The 53°
inclination shows as the availability band in the global map and the sats-in-view
latitude profile (peak near ±53°, zero at the poles). The elevation sweep quantifies how
much margin the scenario has against stricter masks. Elements + availability are exported
to `outputs/` for downstream comparison against Walker presets (e.g. notebook 01 with
matched parameters).""")

nb = {"cells": CELLS,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                  "name": "python3"},
                   "language_info": {"name": "python", "version": "3.14"}},
      "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"cell-{i}"
with open("notebooks/07_live_coverage_explorer.ipynb", "w") as f:
    json.dump(nb, f, indent=1)
print("notebooks/07_live_coverage_explorer.ipynb written")
