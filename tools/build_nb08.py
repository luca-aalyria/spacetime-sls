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

**Notebook version: v1.0.0** — bumped on every notebook change (`tools/bump_nb_version.py`)

Loads the smallest Reliance Jio preset (**~200 @48° (minimal)**: 200 sats, 20 planes,
650 km) into an EPHEMERAL spacebox instance (`luca-sls1` on e2e-internal, 6h TTL), reads
it back via the live-NMTS path, and runs the Slice-A analysis on **India, H3 res 3**.

Prereq (this machine): port-forward into the instance's Store:
```
kubectl --context e2e-internal port-forward svc/spacetime-storage -n luca-sls1 9997:9999
```
Instance lifecycle: see `docs/design-docs/spacebox-smoke-report.md`. The write path is
the GUARDED `EphemeralStoreWriter` — spacebox namespaces only, never shared instances.
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

TARGET = os.environ.get("SLS_EPHEMERAL_TARGET", "localhost:9997")
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

md("""**Next steps** — this instance carries platforms only, enough for the geometry
round-trip above. The full scenario template (antennas with fields-of-regard, carriers,
H3-res-3 user terminals over India, gateways, demand as service requests) activates the
instance's link predictor and satsolver, after which the oracle/capacity readout
(notebooks 06/07 machinery) applies to THIS constellation. Unload:
`EphemeralStoreWriter(target, ...).delete_ids(ids)`; the instance itself expires on TTL.
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
