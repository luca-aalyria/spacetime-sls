#!/usr/bin/env python3
"""Generate notebooks/08_ephemeral_instance_jio.ipynb — load the smallest Reliance Jio
constellation into an ephemeral spacebox instance, read it back through the live-NMTS
path, and run the India res-3 coverage analysis on the round-tripped data."""
import json

CELLS = []


def md(src):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": src})


def code(src):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": src})


md("""# NGSO SLS — Ephemeral Spacetime Instance: Jio Minimal Constellation

**Notebook version: v2.1.0 — DEPRECATED.** Use **notebook 01** instead: select
Source = "Spacetime (live NMTS)" and Instance = "ephemeral/pinned (:9996)". Notebook 01
runs the same analysis and the "Spacetime Δ" compare against the selected instance.
This notebook remains only as the runbook for LOADING a constellation into an empty
ephemeral instance (guarded write path).

This notebook targets the VERSION-PINNED ephemeral instance (Spacetime
`20.2.1771980430-ff066dc`, the fss01-demo release). The instance runs the full Jio
200-satellite NMTS model (9,834 entities): Walker 200/20/1 at 48 deg / 650 km, 251
India H3 res-3 user terminals, 3 gateways, 502 SR-TE path requests. Scenario sources:
`scenarios/pybuilder-jio/`.

Prereq (this machine): port-forward into the instance's Store:
```
kubectl --context e2e-internal port-forward svc/storage-sqlite -n spacetime 9996:9999
```
Instance lifecycle and build fixes: `docs/design-docs/spacebox-smoke-report.md`. The
write path is the GUARDED `EphemeralStoreWriter` — spacebox namespaces only, never
shared instances.
""")

code("""# === Setup ===
import os, sys, pathlib
_REPO = pathlib.Path.cwd().resolve()
while _REPO != _REPO.parent and not (_REPO / "ngso_sls").is_dir():
    _REPO = _REPO.parent
if not (_REPO / "ngso_sls").is_dir():
    _anchor = pathlib.Path("/workspace/spacetime-sls")
    if (_anchor / "ngso_sls").is_dir():
        _REPO = _anchor
for p in (str(_REPO), str(_REPO / "vendor" / "spacetime_api_stubs")):
    if p not in sys.path:
        sys.path.insert(0, p)
import numpy as np
import ngso_sls
print("ngso_sls", ngso_sls.__version__)

TARGET = os.environ.get("SLS_EPHEMERAL_TARGET", "localhost:9996")
PRESET = "~200 @48° (minimal)"        # smallest Jio constellation
""")

code("""# === Load the Jio minimal constellation into the instance (idempotent) ===
from ngso_sls.explorer import WalkerConstellationBuilder
from ngso_sls.spacetime.client import StorageEntityStore
from ngso_sls.spacetime.writer import EphemeralStoreWriter

b = WalkerConstellationBuilder()
b.scenario.value = PRESET
elems, plane_uid, label = b.elements()
print(f"preset: {label} -> {elems.shape[0]} sats, {len(np.unique(plane_uid))} planes")

with StorageEntityStore(TARGET) as s:
    existing = [e for e in s.list_entities() if e.kind == 11
                and str(e.id).startswith("jio-min-")]
if len(existing) == elems.shape[0]:
    print(f"instance already loaded ({len(existing)} platforms) — skipping write")
else:
    with EphemeralStoreWriter(TARGET,
                              i_am_writing_to_an_ephemeral_spacebox_instance=True) as w:
        if existing:                                   # partial load: clean and reload
            w.delete_ids([e.id for e in existing])
        ids = w.write_constellation(elems, name_prefix="jio-min")
    print(f"wrote {len(ids)} platforms into {TARGET}")
""")

code("""# === Read back through the live-NMTS path & verify round-trip ===
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements
with StorageEntityStore(TARGET) as s:
    ents = s.list_entities()
built = platforms_to_elements(ents, [])
rt, rt_pu = built["elems"], built["plane_uid"]
print(f"instance serves {rt.shape[0]} Keplerian platforms, "
      f"{len(np.unique(rt_pu))} planes")
print(f"round-trip element check: max |a_km delta| = "
      f"{abs(np.sort(rt[:, 0]) - np.sort(elems[:, 0])).max():.6f} km")
""")

code("""# === Coverage analysis on the INSTANCE data — India, H3 res 3 ===
from ngso_sls.explorer import LiveCoverageExplorer
explorer = LiveCoverageExplorer(
    rt, rt_pu, label=f"{label} (from ephemeral instance)",
    csv_path="jio_min_instance_coverage.csv", min_elev_deg=25.0)
explorer.aor.value = "India"
explorer.cell_res.value = 3
explorer.display()
""")

code("""from IPython.display import display
display(explorer.results)
""")

code("""explorer.run()      # India res-3 run so Run-All yields a result tab + CSV + PNGs
""")

md("""## Full-model pipeline readout

The instance runs the production pipeline on the loaded model. The cells below count
the solver outputs and compare the instance's beam-candidate coverage against the
`ngso_sls` engine at the model's accessibility mask.

Model facts that set the mask: the user-terminal antennas carry an 80-deg conic field
of regard (minimum elevation 10 deg). The satellite user antennas carry a 75-deg conic
field of regard, which exceeds the Earth limb at 650 km (65.1 deg) and does not bind.
The NMTS Keplerian elements carry no epoch; Spacetime propagates them two-body from
unix 0. Match both in the engine: `KeplerJ2Propagator(j2=0.0)`, `ref_epoch_s=0.0`.
""")

code("""# === Solver output counts (production pipeline, this instance) ===
with StorageEntityStore(TARGET) as s:
    for t in ["NMTS_ENTITY", "NMTS_RELATIONSHIP", "BEAM_CANDIDATE_SEGMENT",
              "NMTS_POINT_TO_POINT_LINK_REPORT", "PROPAGATION_VECTOR_SEGMENT",
              "SCHEDULE", "ALLOCATED_DATA_RATE", "INTENT"]:
        try:
            print(f"{t}: {len(s._get_entities(t))}")
        except Exception as e:
            print(f"{t}: read failed ({type(e).__name__})")
""")

code("""# === Oracle compare: instance beam candidates vs ngso_sls engine ===
from ngso_sls.spacetime.oracle import (read_beam_candidates,
                                       beam_candidates_to_coverage,
                                       engine_coverage_at_points)
from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator

ents_bc = read_beam_candidates(TARGET, dump_timeout_s=400)
orc = beam_candidates_to_coverage(ents_bc, cell_res=3, k_values=[1, 2])
eng = engine_coverage_at_points(rt, rt_pu, orc, 0.0, min_elev_deg=10.0,
                                k_values=[1, 2],
                                propagator=KeplerJ2Propagator(j2=0.0))
d = eng["availability"] - orc["availability"]
print(f"beam candidates: {len(ents_bc)}  cells: {orc['n_points']}  "
      f"samples: {orc['n_samples']}")
print(f"availability delta (engine - instance): mean {np.nanmean(d):+.4f}, "
      f"max |d| {np.nanmax(np.abs(d)):.4f}")
print(f"sats in view: engine {np.nanmean(eng['sats_in_view_mean']):.2f}, "
      f"instance {np.nanmean(orc['sats_in_view_mean'])/2:.2f} "
      f"(two user antennas per satellite)")
""")

md("""### Reference results (2026-08-18, window 11:30-13:39Z, 210 samples, 253 cells)

- Store after load: 9,834 NMTS entities, 18,740 relationships.
- Pipeline output: 20,974 beam-candidate segments, 29,682 point-to-point link
  reports, 8,305 propagation-vector segments, 455 schedules, 502 allocated data
  rates. 157 intents observed live when candidate coverage reached the solve
  quantum; the feeder layer assigned all 3 gateway-satellite links.
- Oracle compare at the 10-deg mask: availability delta mean +0.0000,
  max |delta| 0.0000 over all 253 India res-3 cells. Mean satellites in view:
  engine 4.59-4.61, instance 5.61 (bucket-level candidates count partial
  visibility for a full 300-s bucket, so the instance reads high).
- Figure: `output/pinned-instance/oracle_compare_india.png`.

**Next steps** — read the intent/schedule stream during a covered window for the
capacity readout (Slice B), and age out stale candidates before long reads. Unload:
`EphemeralStoreWriter(target, ...).delete_ids(ids)`; the instance expires on TTL.
""")

nb = {"cells": CELLS,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                  "name": "python3"},
                   "language_info": {"name": "python", "version": "3.12"}},
      "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]):
    c["id"] = f"cell-{i}"
with open("notebooks/08_ephemeral_instance_jio.ipynb", "w") as f:
    json.dump(nb, f, indent=1)
print("notebooks/08_ephemeral_instance_jio.ipynb written")
