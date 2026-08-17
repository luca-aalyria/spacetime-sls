"""Interactive Coverage Explorer UI for notebooks (Colab / Jupyter).

Encapsulates the ipywidgets control panel, the simulation callback, and the tabbed result
plots so the notebook stays thin:

    from ngso_sls.explorer import CoverageExplorer
    explorer = CoverageExplorer()
    display(explorer.controls)   # in the Controls cell
    ...
    display(explorer.results); explorer.run()   # in the Results cell

This module is UI-tier (imports ipywidgets/matplotlib/plotly); the numerical core stays
dependency-light and is untouched.
"""
from dataclasses import replace
from datetime import datetime, timezone
import os
import traceback

import matplotlib.pyplot as plt
import numpy as np
import ipywidgets as w
from IPython.display import display, clear_output

from .presets import JIO_SCENARIOS
from .config import Shell, Constellation, TimeGrid, SimConfig, constellation_model
from .pipeline import run_coverage_h3, run_coverage_h3_elements
from .grids.aor import AORS
from .viz.plots import (
    plot_coverage_hexmap,
    plot_sats_in_view_hexmap,
    plot_mbb_feasible_hexmap,
    plot_sats_in_view_vs_latitude,
    plot_availability_hist,
)
from .io.csv_io import write_availability_csv

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _n_workers() -> int:
    """Parallel shard workers: all-but-two cores (measured 8.5x on Global res2)."""
    return max(1, (os.cpu_count() or 4) - 2)


def _lbl(text):
    return w.HTML(f"<b>{text}</b>")


def _titled(title, box):
    return w.VBox([_lbl(title), box])


def _run_csv_path(base: str, n: int) -> str:
    """Per-run CSV filename: 'coverage_availability.csv' -> 'coverage_availability_run3.csv'.
    Each run persists its own file so a closed tab never loses its data."""
    stem, ext = os.path.splitext(base)
    return f"{stem}_run{n}{ext}"


class CoverageExplorer:
    """Builds the control panel + tabbed results and wires the run callback."""

    def __init__(self, csv_path: str = "coverage_availability.csv"):
        self.csv_path = csv_path
        self.last_result = None
        self._build_widgets()
        self._build_layout()
        self.run_btn.on_click(self.run)

    # -- widgets --------------------------------------------------------------
    def _build_widgets(self):
        s = {"description_width": "130px"}
        wide = {"description_width": "initial"}
        L = w.Layout(width="330px")
        self.scenario = w.Dropdown(options=list(JIO_SCENARIOS) + ["Custom (Walker)"],
                                   value="Full 1600 (dual shell)", description="Scenario", style=s, layout=L)
        self.aor = w.Dropdown(options=list(AORS), value="India", description="Service area", style=s, layout=L)
        self.planes1 = w.IntSlider(value=40, min=1, max=60, description="S1 planes", style=s, layout=L)
        self.spp1 = w.IntSlider(value=30, min=1, max=40, description="S1 sats/plane", style=s, layout=L)
        self.phase1 = w.IntSlider(value=1, min=0, max=59, description="S1 phasing F", style=s, layout=L)
        self.alt1 = w.FloatSlider(value=650, min=300, max=1500, step=10, description="S1 altitude km", style=s, layout=L)
        self.inc1 = w.FloatSlider(value=48, min=0, max=90, step=1, description="S1 inclination", style=s, layout=L)
        self.shell2_on = w.Checkbox(value=False, description="Add second shell")
        self.planes2 = w.IntSlider(value=20, min=1, max=60, description="S2 planes", style=s, layout=L)
        self.spp2 = w.IntSlider(value=20, min=1, max=40, description="S2 sats/plane", style=s, layout=L)
        self.phase2 = w.IntSlider(value=7, min=0, max=59, description="S2 phasing F", style=s, layout=L)
        self.alt2 = w.FloatSlider(value=650, min=300, max=1500, step=10, description="S2 altitude km", style=s, layout=L)
        self.inc2 = w.FloatSlider(value=70, min=0, max=90, step=1, description="S2 inclination", style=s, layout=L)
        self.min_elev = w.FloatSlider(value=25, min=5, max=45, step=1, description="Min elev deg", style=s, layout=L)
        self.cell_res = w.IntSlider(value=3, min=1, max=5, description="H3 resolution", style=s, layout=L)
        self.duration_min = w.FloatSlider(value=60, min=10, max=240, step=10, description="Duration min", style=s, layout=L)
        self.step_s = w.FloatSlider(value=60, min=1, max=120, step=1, description="Time step s", style=s, layout=L)
        self.k_cov = w.IntSlider(value=2, min=1, max=30, description="k (min sats in view)",
                                 style=wide, layout=w.Layout(width="360px"))
        self.use_shard = w.Checkbox(value=True, description="Use sharding (faster, identical result)")
        self.terrain_on = w.Checkbox(value=False, description="Account for terrain (raises horizon)")
        self.terrain_source = w.Dropdown(options=["ETOPO fetch (Colab)", "Demo ridge (offline)"],
                                         value="ETOPO fetch (Colab)", description="Terrain source",
                                         style=s, layout=L)
        self.hex_alpha = w.FloatSlider(value=0.80, min=0.1, max=1.0, step=0.05,
                                       description="Cell opacity", style=s, layout=L)
        self.handover_gate = w.Checkbox(value=False,
                                        description="k=1 make-before-break gate (min 2-sat overlap)")
        self.overlap_s = w.FloatSlider(value=20, min=0, max=180, step=5,
                                       description="Min 2-sat overlap s", style=s, layout=L)
        self.require_diff_plane = w.Checkbox(value=False,
                                             description="Require different plane at handover")
        self.run_btn = w.Button(description="Run simulation", button_style="primary", icon="play")
        self.progress = w.IntProgress(value=0, min=0, max=1, bar_style="info",
                                      layout=w.Layout(width="260px"))
        self.status = w.HTML("<i>idle</i>")

    def _build_layout(self):
        self.out_log = w.Output(layout=w.Layout(min_height="40px"))
        self.runs_tab = w.Tab(children=[])          # one child tab per run (history kept)
        self._run_count = 0
        self.tab_titles = ["Availability map", "Sats-in-view map", "MBB feasibility",
                           "Sats vs latitude", "Histogram"]
        self.controls = w.VBox([
            _lbl("Scenario & service area"),
            w.HBox([self.scenario, self.aor]),
            _lbl("Custom Walker (used only when Scenario = 'Custom (Walker)')"),
            w.HBox([self.planes1, self.spp1, self.phase1]),
            w.HBox([self.alt1, self.inc1]),
            self.shell2_on,
            w.HBox([self.planes2, self.spp2, self.phase2]),
            w.HBox([self.alt2, self.inc2]),
            _lbl("Analysis  (k = min # satellites in view for a cell to count as covered)"),
            w.HBox([self.min_elev, self.cell_res]),
            w.HBox([self.duration_min, self.step_s]),
            w.HBox([self.k_cov, self.use_shard]),
            _lbl("Handover continuity (k=1 make-before-break: continuous single coverage "
                 "+ a ≥ overlap 2-sat window at every handover)"),
            w.HBox([self.handover_gate, self.overlap_s]),
            w.HBox([self.require_diff_plane]),
            w.HBox([self.hex_alpha, self.terrain_on]),
            w.HBox([self.terrain_source]),
            self.run_btn,
            w.HBox([self.progress, self.status]),
        ])
        self.results = w.VBox([_lbl("Runs (each run appends a new tab — previous runs are kept)"),
                               self.out_log, self.runs_tab])

    # -- model ----------------------------------------------------------------
    def build_constellation(self) -> Constellation:
        if self.scenario.value == "Custom (Walker)":
            shells = [Shell("s1", self.planes1.value * self.spp1.value, self.planes1.value,
                            min(self.phase1.value, self.planes1.value - 1), self.alt1.value,
                            self.inc1.value, min_elev_user_deg=self.min_elev.value)]
            if self.shell2_on.value:
                shells.append(Shell("s2", self.planes2.value * self.spp2.value, self.planes2.value,
                                    min(self.phase2.value, self.planes2.value - 1), self.alt2.value,
                                    self.inc2.value, min_elev_user_deg=self.min_elev.value))
            return Constellation(tuple(shells))
        return Constellation(tuple(replace(s, min_elev_user_deg=self.min_elev.value)
                                   for s in JIO_SCENARIOS[self.scenario.value].shells))

    def _workload_sats(self) -> int:
        return sum(sh.walker_T for sh in self.build_constellation().shells)

    def _terrain(self):
        """Optional per-cell horizon-mask callable from the terrain widgets (None = off)."""
        if not self.terrain_on.value:
            return None
        from .grids.aor import aor_bbox
        from .terrain import cell_horizon_masks, fetch_dem_erddap, horizon_mask_from_dem
        bbox = aor_bbox(AORS[self.aor.value])
        dem = None
        if self.terrain_source.value.startswith("ETOPO"):
            try:
                dem = fetch_dem_erddap(bbox)   # real DEM (Colab has internet)
            except Exception:
                dem = None                     # fall back to the offline demo ridge
        if dem is not None:
            return lambda clat, clon, d=dem: horizon_mask_from_dem(  # noqa: E731
                *d, clat, clon, n_bins=36, radius_km=400)
        return lambda clat, clon: cell_horizon_masks(clat, clon, bbox)  # noqa: E731

    def compute(self, progress=None) -> dict:
        cons = self.build_constellation()
        sim = SimConfig(cons,
                        TimeGrid(_EPOCH, duration_s=self.duration_min.value * 60.0, step_s=self.step_s.value),
                        k_coverage=self.k_cov.value)
        terrain = self._terrain()
        overlap = self.overlap_s.value if self.handover_gate.value else None
        res = run_coverage_h3(sim, AORS[self.aor.value], cell_res=self.cell_res.value,
                              shard_res=(1 if self.use_shard.value else None), chunk_steps=10,
                              workers=(_n_workers() if self.use_shard.value else None),
                              progress=progress, terrain=terrain, continuity_overlap_s=overlap,
                              require_different_plane=self.require_diff_plane.value)
        res["_sim"] = sim
        res["_total_sats"] = sum(s.walker_T for s in cons.shells)
        res["_shape"] = "; ".join(
            f"{s.walker_T}/{s.walker_P}/{s.walker_F} @{s.inclination_deg:g}°/{s.altitude_km:g}km"
            for s in cons.shells)
        res["_params"] = self._params()
        return res

    def _params(self) -> dict:
        """The full input parameter set for this run (saved into the output CSV + shown in the
        run panel), so every result is self-describing and reproducible."""
        p = {
            "scenario": self.scenario.value, "service_area": self.aor.value,
            "min_elev_deg": self.min_elev.value, "h3_res": self.cell_res.value,
            "duration_min": self.duration_min.value, "step_s": self.step_s.value,
            "k_coverage": self.k_cov.value, "sharding": self.use_shard.value,
            "handover_gate": self.handover_gate.value,
            "min_overlap_s": (self.overlap_s.value if self.handover_gate.value else None),
            "require_different_plane": self.require_diff_plane.value,
            "terrain": (self.terrain_source.value if self.terrain_on.value else "off"),
            "epoch_utc": _EPOCH.isoformat(), "propagator": "KeplerJ2", "seed": 0,
        }
        if self.scenario.value == "Custom (Walker)":
            p["shell1"] = (f"{self.planes1.value}p×{self.spp1.value}s/p F{self.phase1.value} "
                           f"@{self.inc1.value:g}°/{self.alt1.value:g}km")
            if self.shell2_on.value:
                p["shell2"] = (f"{self.planes2.value}p×{self.spp2.value}s/p F{self.phase2.value} "
                               f"@{self.inc2.value:g}°/{self.alt2.value:g}km")
        return p

    # -- rendering ------------------------------------------------------------
    @staticmethod
    def _draw(box, make_fig):
        with box:
            clear_output(wait=True)
            try:
                fig = make_fig()
                if fig is not None:
                    display(fig)            # explicit display: plt.show() inside Output
                    plt.close(fig)          # widgets renders blank on some frontends
                else:
                    plt.show()
            except Exception:
                traceback.print_exc()

    def run(self, _=None):
        self.run_btn.disabled = True
        self.run_btn.description = "Running…"
        self.status.value = "⏳ running simulation…"
        self.progress.bar_style = "info"
        self.progress.value = 0

        def _progress(done, total):
            self.progress.max = max(total, 1)
            self.progress.value = done

        try:
            with self.out_log:
                clear_output(wait=True)
                try:
                    from .grids.h3_grid import h3_cells_for_aor
                    n_cells = len(h3_cells_for_aor(AORS[self.aor.value],
                                                   self.cell_res.value)[0])
                    n_steps = int(self.duration_min.value * 60.0 / self.step_s.value) + 1
                    n_sats = self._workload_sats()
                    work = n_cells * n_steps * n_sats
                    eta = work / 10e6 * (2.0 if self.handover_gate.value else 1.0)
                    print(f"Running simulation… workload: {n_cells} cells × {n_sats} sats × "
                          f"{n_steps} steps ≈ {work/1e6:.0f}M ops, rough ETA {max(eta, 1):.0f}s")
                except Exception:
                    print("Running simulation…")
            # NOTE: compute() runs OUTSIDE the Output context on purpose — ipywidgets'
            # Output.__exit__ renders AND SWALLOWS exceptions, which previously let run()
            # fall through to the panel code with `res` unbound.
            res = self.compute(progress=_progress)
            with self.out_log:
                self.last_result = res
                a = res["availability"]
                params = res["_params"]
                n = self._run_count + 1
                print(f"Constellation: {self.scenario.value}  |  {res['_total_sats']} sats  |  {res['_shape']}")
                print("Parameters: " + ", ".join(f"{k}={v}" for k, v in params.items()))
                print(f"  cells={len(res['cells'])}  availability mean={a.mean():.3f} min={a.min():.3f} "
                      f"max={a.max():.3f}  mean sats-in-view(time-avg)={res['sats_in_view_mean'].mean():.1f} "
                      f"(max {res['sats_in_view_mean'].max():.0f})")
                if "mbb_feasible" in res:
                    print(f"  make-before-break (≥{res['continuity_overlap_s']:g}s overlap): "
                          f"{res['mbb_feasible'].mean():.1%} of cells feasible (k=1)")
                manifest = {**params, "total_sats": res["_total_sats"], "shape": res["_shape"]}
                run_csv = _run_csv_path(self.csv_path, n)
                write_availability_csv(res, self.csv_path, manifest)   # latest (stable name)
                write_availability_csv(res, run_csv, manifest)         # per-run (survives tab close)
                print(f"  wrote {self.csv_path} and {run_csv}")
            self.status.value = "🖼️ rendering plots…"
            self._append_run_panel(res, n)
            self.status.value = (f"✅ done — run {self._run_count}: {len(res['cells'])} cells, "
                                 f"availability mean {a.mean():.3f}, mean sats-in-view "
                                 f"{res['sats_in_view_mean'].mean():.1f}")
            self.progress.bar_style = "success"
        except Exception as e:
            with self.out_log:
                traceback.print_exc()
            self.status.value = f"❌ {type(e).__name__}: {str(e)[:140]}"
            self.progress.bar_style = "danger"
        finally:
            self.run_btn.disabled = False
            self.run_btn.description = "Run simulation"

    @staticmethod
    def _fig_widget(make_fig, empty_text=None):
        """A tab child holding the rendered figure as PNG widget state (no output
        streaming — deterministic across frontends, persists across page reloads)."""
        import io as _io
        if make_fig is None:
            return w.HTML(f"<i>{empty_text}</i>")
        try:
            fig = make_fig()
            if fig is None:
                return w.HTML(f"<i>{empty_text or 'nothing to plot'}</i>")
            buf = _io.BytesIO()
            fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
            plt.close(fig)
            return w.Image(value=buf.getvalue(), format="png",
                           layout=w.Layout(max_width="98%"))
        except Exception:
            return w.HTML("<pre style='color:#a00'>" + traceback.format_exc()[-2000:] + "</pre>")

    def _append_run_panel(self, res, n):
        """Render this run's plots into a fresh tab appended to the runs history (previous runs
        stay visible), with a header echoing the input parameters and a ✕ Close button."""
        self._run_count = n
        alpha, ak, aor = self.hex_alpha.value, self.k_cov.value, self.aor.value
        children = [
            self._fig_widget(lambda: plot_coverage_hexmap(
                res, title=f"Coverage availability (k={ak}) - {aor}", alpha=alpha)),
            self._fig_widget(lambda: plot_sats_in_view_hexmap(
                res, title=f"Mean satellites in view (time-avg) - {aor}", alpha=alpha)),
            self._fig_widget(
                (lambda: plot_mbb_feasible_hexmap(
                    res, title=f"Make-before-break feasible - {aor}", alpha=alpha))
                if "mbb_feasible" in res else None,
                empty_text="Enable the 'k=1 make-before-break gate' control to "
                           "compute handover feasibility."),
            self._fig_widget(lambda: plot_sats_in_view_vs_latitude(res)),
            self._fig_widget(lambda: plot_availability_hist(res)),
        ]
        titles = list(self.tab_titles)
        if hasattr(self, "_elems"):          # Live explorer: record the constellation used
            children.append(self._fig_widget(self._constellation_fig))
            titles.append("Constellation")
            if getattr(self, "_oracle_pair", None):
                from .spacetime.oracle import plot_oracle_delta
                eng, orc = self._oracle_pair
                children.append(self._fig_widget(lambda: plot_oracle_delta(eng, orc, k=1)))
                titles.append("Spacetime Δ")
        inner = w.Tab(children=children)
        base = os.path.splitext(self.csv_path)[0]
        saved = []
        for t, ch in zip(titles, children):
            if isinstance(ch, w.Image):      # also save to disk for slides/reports
                fn = f"{base}_run{n}_{t.lower().replace(' ', '_').replace('-', '_')}.png"
                with open(fn, "wb") as fh:
                    fh.write(ch.value)
                saved.append(fn)
        if saved:
            with self.out_log:
                print("  PNGs: " + ", ".join(saved))
        for i, t in enumerate(titles):
            inner.set_title(i, t)
        params = res["_params"]
        hdr = w.HTML(f"<b>Run {n}</b> — {res['_total_sats']} sats · {res['_shape']}<br>"
                     f"<span style='font-size:90%;color:#555'>"
                     + " · ".join(f"{k}={v}" for k, v in params.items())
                     + " · (CSV kept on disk)</span>")
        close_btn = w.Button(description="✕ Close run", button_style="danger",
                             tooltip="Remove this run's tab (its CSV stays on disk)",
                             layout=w.Layout(width="120px"))
        panel = w.VBox([w.HBox([close_btn, hdr]), inner])
        close_btn.on_click(lambda _b, p=panel: self._close_run(p))
        self.runs_tab.children = self.runs_tab.children + (panel,)
        idx = len(self.runs_tab.children) - 1
        self.runs_tab.set_title(idx, f"Run {n}: k{ak}{' MBB' if 'mbb_feasible' in res else ''}")
        self.runs_tab.selected_index = idx

    def _close_run(self, panel):
        """Remove a run's tab (data stays in its per-run CSV). Reindexes the remaining tab titles."""
        kids = list(self.runs_tab.children)
        if panel not in kids:
            return
        titles = [self.runs_tab.get_title(i) for i in range(len(kids))]
        i = kids.index(panel)
        kids.pop(i)
        titles.pop(i)
        self.runs_tab.children = tuple(kids)
        for j, t in enumerate(titles):
            self.runs_tab.set_title(j, t or "")
        if kids:
            self.runs_tab.selected_index = min(i, len(kids) - 1)

    def display(self):
        """Show controls + results together (no auto-run — press 'Run simulation')."""
        display(self.controls, self.results)




class WalkerConstellationBuilder:
    """The constellation section of notebook 01 as a standalone panel. `elements()` reads
    the CURRENT widget values and returns (elems, plane_uid, label) — the same shape the
    live-NMTS pull produces — so the analysis cell can be the same LiveCoverageExplorer in
    both notebooks. No build button: pass `builder.elements` (the callable) to the explorer
    and every Run picks up the latest slider values."""

    def __init__(self):
        st = {"description_width": "130px"}
        L = w.Layout(width="330px")
        self.scenario = w.Dropdown(options=list(JIO_SCENARIOS) + ["Custom (Walker)"],
                                   value="Full 1600 (dual shell)", description="Scenario",
                                   style=st, layout=L)
        self.planes1 = w.IntSlider(value=40, min=1, max=60, description="S1 planes", style=st, layout=L)
        self.spp1 = w.IntSlider(value=30, min=1, max=40, description="S1 sats/plane", style=st, layout=L)
        self.phase1 = w.IntSlider(value=1, min=0, max=59, description="S1 phasing F", style=st, layout=L)
        self.alt1 = w.FloatSlider(value=650, min=300, max=1500, step=10, description="S1 altitude km", style=st, layout=L)
        self.inc1 = w.FloatSlider(value=48, min=0, max=90, step=1, description="S1 inclination", style=st, layout=L)
        self.shell2_on = w.Checkbox(value=False, description="Add second shell")
        self.planes2 = w.IntSlider(value=20, min=1, max=60, description="S2 planes", style=st, layout=L)
        self.spp2 = w.IntSlider(value=20, min=1, max=40, description="S2 sats/plane", style=st, layout=L)
        self.phase2 = w.IntSlider(value=7, min=0, max=59, description="S2 phasing F", style=st, layout=L)
        self.alt2 = w.FloatSlider(value=650, min=300, max=1500, step=10, description="S2 altitude km", style=st, layout=L)
        self.inc2 = w.FloatSlider(value=70, min=0, max=90, step=1, description="S2 inclination", style=st, layout=L)
        self.panel = w.VBox([
            _lbl("Constellation (used by the analysis cell below at every Run)"),
            w.HBox([self.scenario]),
            _lbl("Custom Walker (used only when Scenario = 'Custom (Walker)')"),
            w.HBox([self.planes1, self.spp1, self.phase1]),
            w.HBox([self.alt1, self.inc1]),
            self.shell2_on,
            w.HBox([self.planes2, self.spp2, self.phase2]),
            w.HBox([self.alt2, self.inc2]),
        ])

    def constellation(self) -> Constellation:
        if self.scenario.value == "Custom (Walker)":
            shells = [Shell("s1", self.planes1.value * self.spp1.value, self.planes1.value,
                            min(self.phase1.value, self.planes1.value - 1), self.alt1.value,
                            self.inc1.value, min_elev_user_deg=25.0)]
            if self.shell2_on.value:
                shells.append(Shell("s2", self.planes2.value * self.spp2.value, self.planes2.value,
                                    min(self.phase2.value, self.planes2.value - 1), self.alt2.value,
                                    self.inc2.value, min_elev_user_deg=25.0))
            return Constellation(tuple(shells))
        return Constellation(JIO_SCENARIOS[self.scenario.value].shells)

    def elements(self):
        """(elems, plane_uid, label) from the current widget values."""
        cons = self.constellation()
        model = constellation_model(cons)
        label = self.scenario.value if self.scenario.value != "Custom (Walker)" else \
            "; ".join(f"{sh.walker_T}/{sh.walker_P}/{sh.walker_F} "
                      f"@{sh.inclination_deg:g}°/{sh.altitude_km:g}km" for sh in cons.shells)
        return model.elems, model.plane_uid, label

    def display(self):
        display(self.panel)



def _pull_spacetime_elements(target="localhost:9999", dump_dir=None):
    """Pull the constellation from a live Store (textproto-dump fallback) and return
    (elems, plane_uid, label, model_min_elev_deg). Spacetime imports are LAZY so the core
    explorer module stays proto-free unless this source is actually used."""
    import os
    from .spacetime.nmts_adapter import platforms_to_elements
    EK_ANTENNA = 40
    try:
        from .spacetime.client import StorageEntityStore
        with StorageEntityStore(target) as store:
            entities = store.list_entities()
            rels = store.list_relationships()
        label = f"live {target}"
    except Exception as live_exc:
        import glob, pathlib
        from google.protobuf import text_format
        from .spacetime import _deps
        from .spacetime.client import _NmtsEntityView
        dump = dump_dir or os.environ.get("SLS_DUMP_DIR") or next(
            (str(d) for d in (pathlib.Path("/workspace/fss01-demo-dump"),)
             if d.is_dir()), None)
        if not dump or _deps.storage_pb2 is None:
            raise RuntimeError(f"live pull failed ({live_exc}) and no dump available "
                               f"(set SLS_DUMP_DIR)") from live_exc
        def _load(pattern):
            out = []
            for path in sorted(glob.glob(f"{dump}/{pattern}")):
                box = _deps.storage_pb2.TxtpbEntities()
                with open(path) as f:
                    text_format.Parse(f.read(), box)
                out.extend(box.entity)
            return out
        entities = [_NmtsEntityView(e.nmts_entity) for e in _load("nmts/entities_ek_*.txtpb")]
        rels = [e.nmts_relationship for e in _load("nmts/relationships_rk_contains.txtpb")]
        label = f"dump {dump}"
    built = platforms_to_elements(entities, rels)
    if built["elems"].shape[0] == 0:
        raise RuntimeError(f"no Keplerian platforms in {label} (skipped: {len(built['skipped'])})")
    angles = [e.antenna.field_of_regard.conic.outer_half_angle_deg
              for e in entities if getattr(e, "kind", -1) == EK_ANTENNA
              and str(e.id).startswith("user-terminal")
              and e.antenna.HasField("field_of_regard")]
    min_elev = (90.0 - float(np.median(angles))) if angles else None
    return built["elems"], built["plane_uid"], label, min_elev, built["ref_epoch_s"]


class ConstellationSource:
    """Constellation step for the merged explorer notebook: Walker presets/custom OR a live
    Spacetime NMTS pull (with textproto-dump fallback). `elements` matches the
    LiveCoverageExplorer source contract: Walker values are re-read at every Run; the
    Spacetime pull is cached until 'Pull' is pressed again."""

    def __init__(self, target="localhost:9999", dump_dir=None):
        self.walker = WalkerConstellationBuilder()
        self.mode = w.ToggleButtons(options=["Walker (presets/custom)", "Spacetime (live NMTS)"],
                                    value="Walker (presets/custom)", description="Source")
        self.target = w.Text(value=target, description="Store target",
                             style={"description_width": "130px"}, layout=w.Layout(width="330px"))
        self.pull_btn = w.Button(description="Pull from Spacetime", icon="download")
        self.pull_status = w.HTML("<i>not pulled yet — Pull, or first Run pulls automatically</i>")
        self.pull_btn.on_click(self._pull)
        self._pulled = None
        self.model_min_elev = None
        self._dump_dir = dump_dir
        self.panel = w.VBox([
            _lbl("Constellation source (analysis cell re-reads this at every Run)"),
            self.mode,
            self.walker.panel,
            _lbl("Spacetime (used when Source = live NMTS; falls back to a local dump)"),
            w.HBox([self.target, self.pull_btn]),
            self.pull_status,
        ])

    def _pull(self, _=None):
        self.pull_status.value = "⏳ pulling…"
        try:
            elems, pu, label, min_elev, ref_epoch = _pull_spacetime_elements(
                self.target.value, self._dump_dir)
            self._pulled = (elems, pu, label)
            self.ref_epoch_s = ref_epoch
            self.model_min_elev = min_elev
            hint = (f"; model min-elev (user links): {min_elev:g}° — set the slider to match"
                    if min_elev is not None else "")
            self.pull_status.value = (f"✅ {label}: {elems.shape[0]} sats, "
                                      f"{len(np.unique(pu))} planes{hint}")
        except Exception as e:
            self._pulled = None
            self.pull_status.value = f"❌ {type(e).__name__}: {str(e)[:160]}"

    def elements(self):
        if self.mode.value.startswith("Walker"):
            return self.walker.elements()
        if self._pulled is None:
            self._pull()
        if self._pulled is None:
            raise RuntimeError("Spacetime pull failed — see the constellation panel status")
        return self._pulled

    def display(self):
        display(self.panel)


class LiveCoverageExplorer(CoverageExplorer):
    """Notebook-01's Coverage Explorer with the constellation FIXED to externally supplied
    element arrays (e.g. pulled from a live Spacetime NMTS model). The constellation-shape
    controls are removed; every analysis control (service area, min elev, H3 res, duration,
    step, k, sharding, make-before-break gate, terrain, opacity) and the run-tab/CSV
    machinery are inherited unchanged."""

    def __init__(self, elems, plane_uid=None, label="live NMTS constellation",
                 csv_path="live_coverage_availability.csv", min_elev_deg=None):
        if callable(elems):                     # elements source (e.g. builder.elements):
            self._source = elems                # re-evaluated at every Run
            e, pu, label = elems()
        else:
            self._source = None
            e, pu = elems, plane_uid
        self._elems = np.asarray(e, dtype=float)
        self._plane_uid = np.asarray(pu)
        self._label = label
        self.compare_spacetime = w.Checkbox(
            value=False, description="Compare vs Spacetime prediction (pull beam candidates)")
        self._oracle_pair = None
        super().__init__(csv_path=csv_path)
        # the scenario widget only feeds run-log text here (compute() ignores it)
        self.scenario = w.Dropdown(options=[label], value=label, description="Scenario")
        if min_elev_deg is not None:
            self.min_elev.value = float(min_elev_deg)

    def _build_layout(self):
        super()._build_layout()
        n_planes = len(np.unique(self._plane_uid))
        self.controls = w.VBox([
            _lbl(f"Constellation (fixed, from NMTS): {self._label} — "
                 f"{self._elems.shape[0]} sats, {n_planes} planes"),
            _lbl("Service area"),
            w.HBox([self.aor]),
            _lbl("Analysis  (k = min # satellites in view for a cell to count as covered)"),
            w.HBox([self.min_elev, self.cell_res]),
            w.HBox([self.duration_min, self.step_s]),
            w.HBox([self.k_cov, self.use_shard]),
            _lbl("Handover continuity (k=1 make-before-break: continuous single coverage "
                 "+ a ≥ overlap 2-sat window at every handover)"),
            w.HBox([self.handover_gate, self.overlap_s]),
            w.HBox([self.require_diff_plane]),
            w.HBox([self.hex_alpha, self.terrain_on]),
            w.HBox([self.terrain_source]),
            w.HBox([self.compare_spacetime]),
            self.run_btn,
            w.HBox([self.progress, self.status]),
        ])

    def compute(self, progress=None) -> dict:
        if self._source is not None:            # refresh from the builder's current widgets
            e, pu, label = self._source()
            self._elems = np.asarray(e, dtype=float)
            self._plane_uid = np.asarray(pu)
            self._label = label
            self.scenario.options = [label]
            self.scenario.value = label
        tg = TimeGrid(_EPOCH, duration_s=self.duration_min.value * 60.0,
                      step_s=self.step_s.value)
        overlap = self.overlap_s.value if self.handover_gate.value else None
        res = run_coverage_h3_elements(
            self._elems, self._plane_uid, self.min_elev.value, tg, AORS[self.aor.value],
            cell_res=self.cell_res.value, shard_res=(1 if self.use_shard.value else None),
            chunk_steps=10, workers=(_n_workers() if self.use_shard.value else None),
            progress=progress, terrain=self._terrain(),
            continuity_overlap_s=overlap,
            require_different_plane=self.require_diff_plane.value,
            k_values=[self.k_cov.value], default_k=self.k_cov.value)
        alt_km = float((self._elems[:, 0] * (1 + self._elems[:, 1])).mean()) - 6378.137
        inc = float(np.degrees(self._elems[:, 2]).mean())
        self._oracle_pair = None
        if self.compare_spacetime.value:
            from datetime import datetime, timezone
            from .spacetime.oracle import (read_beam_candidates, beam_candidates_to_coverage,
                                           engine_coverage_at_points)
            prefix = "T:" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
            ents = read_beam_candidates(bucket_prefix=prefix)
            if ents:
                orc = beam_candidates_to_coverage(ents, cell_res=self.cell_res.value,
                                                  k_values=[1, self.k_cov.value])
                owner = getattr(self._source, "__self__", None)
                ref = getattr(owner, "ref_epoch_s", None) or 0.0
                eng = engine_coverage_at_points(
                    self._elems, self._plane_uid, orc, ref,
                    min_elev_deg=self.min_elev.value, k_values=[1, self.k_cov.value])
                self._oracle_pair = (eng, orc)
        res["_total_sats"] = int(self._elems.shape[0])
        res["_shape"] = (f"{self._label}: {res['_total_sats']} sats / "
                         f"{len(np.unique(self._plane_uid))} planes "
                         f"@{inc:.1f}°/{alt_km:.0f}km")
        res["_params"] = self._params()
        return res

    def _workload_sats(self) -> int:
        if self._source is not None:        # cheap: Walker maths / cached pull; no compute
            try:
                e, _, _ = self._source()
                return int(e.shape[0])
            except Exception:
                return int(self._elems.shape[0])
        return int(self._elems.shape[0])

    def _constellation_fig(self):
        """Lattice + altitude snapshot of the elements THIS run used (source re-read at Run)."""
        e, pu = self._elems, self._plane_uid
        fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
        ax[0].scatter(np.degrees(e[:, 3]), np.degrees(e[:, 5]), c=pu, cmap="tab20", s=12)
        ax[0].set_xlabel("RAAN [deg]"); ax[0].set_ylabel("mean anomaly [deg]")
        ax[0].set_title(f"{self._label}: {e.shape[0]} sats, {len(np.unique(pu))} planes")
        ax[1].hist(e[:, 0] * (1 + e[:, 1]) - 6378.137, bins=20)
        ax[1].set_xlabel("apoapsis altitude [km]"); ax[1].set_title("Altitude distribution")
        plt.tight_layout()
        return fig

    def _params(self) -> dict:
        p = super()._params()
        p["scenario"] = self._label
        p["constellation_source"] = ("builder (re-read at Run)" if self._source
                                     else "external elements (e.g. live NMTS)")
        p["n_sats"] = int(self._elems.shape[0])
        for key in ("shell1", "shell2"):
            p.pop(key, None)
        return p


class MinSatSweep:
    """Minimum-satellite sweep UI: vary a single Walker shell's size (planes x sats/plane) and
    plot coverage vs N over the AOR, marking the smallest constellation meeting a coverage grade."""

    def __init__(self, csv_path: str = "min_sat_sweep.csv"):
        self.csv_path = csv_path
        self.last_result = None
        s = {"description_width": "150px"}
        L = w.Layout(width="340px")
        self.aor = w.Dropdown(options=list(AORS), value="India", description="Service area", style=s, layout=L)
        self.planes = w.IntSlider(value=40, min=1, max=60, description="Planes (min)", style=s, layout=L)
        self.planes_max = w.IntSlider(value=40, min=1, max=60, description="Planes max", style=s, layout=L)
        self.planes_step = w.IntSlider(value=1, min=1, max=20, description="Planes step", style=s, layout=L)
        self.altitude = w.FloatSlider(value=650, min=300, max=1500, step=10, description="Altitude km", style=s, layout=L)
        self.incl_min = w.FloatSlider(value=48, min=0, max=90, step=0.1, description="Inclination min °", style=s, layout=L)
        self.incl_max = w.FloatSlider(value=48, min=0, max=90, step=0.1, description="Inclination max °", style=s, layout=L)
        self.incl_step = w.FloatSlider(value=5.0, min=0.1, max=30.0, step=0.1, description="Inclination step °", style=s, layout=L)
        self.phasing = w.IntSlider(value=1, min=0, max=59, description="Phasing F", style=s, layout=L)
        self.spp_min = w.IntSlider(value=5, min=1, max=40, description="sats/plane min", style=s, layout=L)
        self.spp_max = w.IntSlider(value=30, min=1, max=40, description="sats/plane max", style=s, layout=L)
        self.spp_step = w.IntSlider(value=5, min=1, max=10, description="sats/plane step", style=s, layout=L)
        self.min_elev = w.FloatSlider(value=25, min=5, max=45, step=1, description="Min elev deg", style=s, layout=L)
        self.k_values = w.SelectMultiple(options=[1, 2, 3, 4], value=(1, 2), rows=4,
                                         description="k values (min sats in view)", style=s, layout=L)
        self.target_avail = w.FloatSlider(value=0.99, min=0.5, max=1.0, step=0.01, description="Availability target", style=s, layout=L)
        self.area_grade = w.FloatSlider(value=0.95, min=0.5, max=1.0, step=0.01, description="Area grade", style=s, layout=L)
        self.cell_res = w.IntSlider(value=3, min=1, max=5, description="H3 resolution", style=s, layout=L)
        self.duration_min = w.FloatSlider(value=30, min=10, max=240, step=10, description="Duration min", style=s, layout=L)
        self.step_s = w.FloatSlider(value=60, min=1, max=120, step=1, description="Time step s", style=s, layout=L)
        self.use_shard = w.Checkbox(value=True, description="Use sharding")
        self.handover_gate = w.Checkbox(value=False, description="k=1 make-before-break gate")
        self.overlap_s = w.FloatSlider(value=20, min=0, max=180, step=5,
                                       description="Min 2-sat overlap s", style=s, layout=L)
        self.run_btn = w.Button(description="Run sweep", button_style="primary", icon="play")
        self.progress = w.IntProgress(value=0, min=0, max=1, bar_style="info", layout=w.Layout(width="260px"))
        self.status = w.HTML("<i>idle</i>")
        self.out_log = w.Output(layout=w.Layout(min_height="40px"))
        self.runs_box = w.VBox([])          # history of sweep run panels (kept across runs)
        self._run_count = 0
        self.run_btn.on_click(self.run)
        self.controls = w.VBox([
            _lbl("Minimum-satellite sweep — base shell (single Walker shell, thinned by sats/plane)"),
            w.HBox([self.aor, self.planes]),
            w.HBox([self.planes_max, self.planes_step]),
            w.HBox([self.altitude, self.phasing]),
            _lbl("Inclination range (min, max, step ≥ 0.1°; a range compares inclinations)"),
            w.HBox([self.incl_min, self.incl_max, self.incl_step]),
            _lbl("Coverage levels & sweep range (total N = planes x sats/plane)"),
            w.HBox([self.k_values]),
            _lbl("Sweep range (sats/plane)"),
            w.HBox([self.spp_min, self.spp_max, self.spp_step]),
            _lbl("Coverage grade & analysis"),
            w.HBox([self.target_avail, self.area_grade]),
            w.HBox([self.min_elev, self.cell_res]),
            w.HBox([self.duration_min, self.step_s]),
            _lbl("Handover continuity (k=1 make-before-break gate; failing sizes flagged red)"),
            w.HBox([self.handover_gate, self.overlap_s]),
            self.use_shard,
            self.run_btn,
            w.HBox([self.progress, self.status]),
        ])
        self.results = w.VBox([_lbl("Sweep runs (each run appends a panel below — previous kept)"),
                               self.out_log, self.runs_box])

    def compute(self, progress=None):
        """Returns (mode, result, inclinations). mode is 'coverage_vs_N' for a single inclination,
        'min_N_vs_incl' for an inclination range, or 'multi_shape' when planes range has >1 value."""
        from .sweep import min_sat_sweep, inclination_sweep, incl_values, multi_shape_sweep
        spp = list(range(self.spp_min.value, self.spp_max.value + 1, self.spp_step.value))
        ks = tuple(self.k_values.value) or (2,)
        incs = incl_values(self.incl_min.value, self.incl_max.value, self.incl_step.value)
        overlap = self.overlap_s.value if self.handover_gate.value else None
        Pv = list(range(self.planes.value, self.planes_max.value + 1, self.planes_step.value))
        if len(Pv) > 1:
            res = multi_shape_sweep(AORS[self.aor.value], Pv, spp, self.altitude.value,
                                    incs[0], min_elev_deg=self.min_elev.value, k_values=ks,
                                    target_availability=self.target_avail.value,
                                    area_grade=self.area_grade.value, cell_res=self.cell_res.value,
                                    duration_s=self.duration_min.value * 60.0, step_s=self.step_s.value,
                                    phasing=self.phasing.value, use_sharding=self.use_shard.value,
                                    handover_gate=self.handover_gate.value,
                                    continuity_overlap_s=overlap, progress=progress)
            return "multi_shape", res, incs
        common = dict(min_elev_deg=self.min_elev.value, k_values=ks,
                      target_availability=self.target_avail.value, area_grade=self.area_grade.value,
                      cell_res=self.cell_res.value, duration_s=self.duration_min.value * 60.0,
                      step_s=self.step_s.value, phasing=self.phasing.value,
                      use_sharding=self.use_shard.value, progress=progress,
                      continuity_overlap_s=overlap)
        if len(incs) <= 1:
            res = min_sat_sweep(AORS[self.aor.value], self.planes.value, self.altitude.value,
                                incs[0], spp, **common)
            return "coverage_vs_N", res, incs
        res = inclination_sweep(AORS[self.aor.value], self.planes.value, self.altitude.value,
                                incs, spp, **common)
        return "min_N_vs_incl", res, incs

    def run(self, _=None):
        self.run_btn.disabled = True
        self.run_btn.description = "Running…"
        self.status.value = "⏳ running sweep…"
        self.progress.bar_style = "info"
        self.progress.value = 0

        def _progress(done, total):
            self.progress.max = max(total, 1)
            self.progress.value = done

        try:
            with self.out_log:
                clear_output(wait=True)
                from .sweep import incl_values
                ks = tuple(self.k_values.value) or (2,)
                incs = incl_values(self.incl_min.value, self.incl_max.value, self.incl_step.value)
                n_spp = len(range(self.spp_min.value, self.spp_max.value + 1, self.spp_step.value))
                print(f"Sweeping {len(incs)} inclination(s) x {n_spp} sizes over {self.aor.value} "
                      f"({self.planes.value} planes @ {self.altitude.value:g}km, k={list(ks)})…")
                print("Parameters: " + ", ".join(f"{k}={v}" for k, v in self._params().items()))
            # outside the Output context: Output.__exit__ swallows exceptions (see run() above)
            mode, res, incs = self.compute(progress=_progress)
            with self.out_log:
                self.last_result, self.last_mode = res, mode
                if mode == "coverage_vs_N":
                    for r in res["sweep"]:
                        parts = "  ".join(f"k{k}={r['pct_by_k'][k]:.0%}" for k in res["k_values"])
                        print(f"  N={r['N']:>5} ({r['sats_per_plane']:>2}/plane)  "
                              f"cells≥{res['target_availability']:.0%}avail:[{parts}]  siv={r['mean_sats_in_view']:.1f}")
                    print(f"\nMin N for {res['area_grade']:.0%} of {self.aor.value} @ "
                          f"{res['target_availability']:.0%} avail (incl {res['inclination_deg']:g}°):")
                    for k in res["k_values"]:
                        mn = res["min_N_by_k"][k]
                        tag = "single" if k == 1 else ("dual/handover" if k == 2 else f"{k}-fold")
                        print(f"  k={k} ({tag}): " + (f"{mn} satellites" if mn is not None else "not reached"))
                    if res.get("continuity_overlap_s") is not None:
                        mn = res["min_N_mbb"]
                        print(f"  k=1 make-before-break (≥{res['continuity_overlap_s']:g}s overlap): "
                              + (f"{mn} satellites" if mn is not None else "not reached"))
                elif mode == "multi_shape":
                    print(f"  {len(res['candidates'])} candidates "
                          f"(P={res['planes_values']}, spp={res['spp_values']}):")
                    for c in res["candidates"]:
                        parts = "  ".join(f"k{k}={c['pct_by_k'][k]:.0%}" for k in res["k_values"])
                        print(f"  N={c['N']:>5} ({c['planes']}P×{c['sats_per_plane']}spp)  "
                              f"[{parts}]  pareto={c['is_pareto']}")
                    for k in res["k_values"]:
                        mn = res["min_N_by_k"][k]
                        print(f"  min N k={k}: " + (f"{mn}" if mn is not None else "not reached"))
                else:
                    print("min N by inclination:")
                    for b in res["by_inclination"]:
                        parts = "  ".join(f"k{k}={b['min_N_by_k'][k] if b['min_N_by_k'][k] is not None else '—'}"
                                          for k in res["k_values"])
                        print(f"  {b['inclination']:>5.1f}°:  {parts}")
                    for k in res["k_values"]:
                        cand = [(b["inclination"], b["min_N_by_k"][k]) for b in res["by_inclination"]
                                if b["min_N_by_k"][k] is not None]
                        if cand:
                            bi = min(cand, key=lambda x: x[1])
                            print(f"  best for k={k}: {bi[1]} satellites at {bi[0]:g}°")
                    if res.get("continuity_overlap_s") is not None:
                        cand = [(b["inclination"], b["min_N_mbb"]) for b in res["by_inclination"]
                                if b.get("min_N_mbb") is not None]
                        if cand:
                            bi = min(cand, key=lambda x: x[1])
                            print(f"  best MBB (≥{res['continuity_overlap_s']:g}s): {bi[1]} sats at {bi[0]:g}°")
                n = self._run_count + 1
                _write_sweep_csv(res, mode, self.csv_path, manifest=self._params())   # latest
                run_csv = _run_csv_path(self.csv_path, n)
                _write_sweep_csv(res, mode, run_csv, manifest=self._params())          # per-run
                print(f"wrote {self.csv_path} and {run_csv}")
            self.status.value = "🖼️ rendering…"
            self._append_sweep_panel(mode, res, n)
            self.status.value = "✅ done"
            self.progress.bar_style = "success"
        except Exception as e:
            with self.out_log:
                traceback.print_exc()
            self.status.value = f"❌ {type(e).__name__}: {str(e)[:140]}"
            self.progress.bar_style = "danger"
        finally:
            self.run_btn.disabled = False
            self.run_btn.description = "Run sweep"

    def _params(self) -> dict:
        """Full input parameter set for this sweep (saved into the CSV + shown per run)."""
        gate = self.handover_gate.value
        return {
            "service_area": self.aor.value, "planes": self.planes.value,
            "altitude_km": self.altitude.value, "phasing_F": self.phasing.value,
            "incl_min": self.incl_min.value, "incl_max": self.incl_max.value,
            "incl_step": self.incl_step.value, "spp_min": self.spp_min.value,
            "spp_max": self.spp_max.value, "spp_step": self.spp_step.value,
            "k_values": list(self.k_values.value), "target_availability": self.target_avail.value,
            "area_grade": self.area_grade.value, "min_elev_deg": self.min_elev.value,
            "h3_res": self.cell_res.value, "duration_min": self.duration_min.value,
            "step_s": self.step_s.value, "sharding": self.use_shard.value,
            "handover_gate": gate, "min_overlap_s": (self.overlap_s.value if gate else None),
            "propagator": "KeplerJ2",
        }

    def _append_sweep_panel(self, mode, res, n):
        """Render this sweep's plot(s) into a fresh panel appended below previous runs, with a
        header echoing the input parameters and a ✕ Close button (previous runs are kept)."""
        self._run_count = n
        from .viz.plots import (plot_min_sat_sweep, plot_inclination_sweep,
                                plot_inclination_coverage_curves,
                                plot_multi_shape_scatter, plot_multi_shape_heatmap)
        # PNG Image-widget state, same rationale as the coverage run tabs: Output-widget
        # streaming drops plots on some frontends and is lost on page reload.
        if mode == "coverage_vs_N":
            figs = [lambda: plot_min_sat_sweep(res)]
        elif mode == "multi_shape":
            k0 = res["k_values"][0]
            figs = [lambda: plot_multi_shape_scatter(res, k=k0),
                    lambda: plot_multi_shape_heatmap(res, k=k0)]
        else:
            figs = [lambda: plot_inclination_coverage_curves(res),
                    lambda: plot_inclination_sweep(res)]
        out = w.VBox([CoverageExplorer._fig_widget(f) for f in figs])
        base = os.path.splitext(self.csv_path)[0]
        saved = []
        for i, ch in enumerate(out.children):
            if isinstance(ch, w.Image):      # persist for slides/reports (like run tabs)
                fn = f"{base}_run{n}_plot{i + 1}.png"
                with open(fn, "wb") as fh:
                    fh.write(ch.value)
                saved.append(fn)
        if saved:
            with self.out_log:
                print("  PNGs: " + ", ".join(saved))
        hdr = w.HTML(f"<b>Run {n}</b> ({mode}) — <span style='font-size:90%;color:#555'>"
                     + " · ".join(f"{k}={v}" for k, v in self._params().items())
                     + " · (CSV kept on disk)</span>")
        close_btn = w.Button(description="✕ Close", button_style="danger",
                             tooltip="Remove this run's panel (its CSV stays on disk)",
                             layout=w.Layout(width="90px"))
        panel = w.VBox([w.HBox([close_btn, hdr]), out])
        close_btn.on_click(lambda _b, p=panel: self._close_run(p))
        self.runs_box.children = self.runs_box.children + (panel,)

    def _close_run(self, panel):
        """Remove a sweep run's panel (its per-run CSV stays on disk)."""
        self.runs_box.children = tuple(p for p in self.runs_box.children if p is not panel)


def _write_sweep_csv(res: dict, mode: str, path: str, manifest: dict | None = None):
    import csv
    ks = res["k_values"]
    mbb = res.get("continuity_overlap_s") is not None
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        if manifest:
            for k, v in manifest.items():
                f.write(f"# {k}: {v}\n")
        if mode == "coverage_vs_N":
            f.write(f"# min_N_by_k: {res['min_N_by_k']}  min_N_mbb: {res.get('min_N_mbb')}"
                    f"  target_availability: {res['target_availability']}"
                    f"  area_grade: {res['area_grade']}  inclination: {res['inclination_deg']}\n")
            wr.writerow(["N", "planes", "sats_per_plane", "mean_sats_in_view"]
                        + [f"pct_k{k}" for k in ks] + [f"mean_avail_k{k}" for k in ks]
                        + (["pct_mbb", "mbb_pass"] if mbb else []))
            for r in res["sweep"]:
                wr.writerow([r["N"], r["planes"], r["sats_per_plane"], f"{r['mean_sats_in_view']:.6f}"]
                            + [f"{r['pct_by_k'][k]:.6f}" for k in ks]
                            + [f"{r['mean_avail_by_k'][k]:.6f}" for k in ks]
                            + ([f"{r['pct_mbb']:.6f}", int(r['mbb_pass'])] if mbb else []))
        elif mode == "multi_shape":
            mbb = res.get("continuity_overlap_s") is not None
            f.write(f"# min_N_by_k: {res['min_N_by_k']}  min_N_mbb: {res.get('min_N_mbb')}"
                    f"  area_grade: {res['area_grade']}  inclination: {res['inclination_deg']}\n")
            wr.writerow(["N", "planes", "sats_per_plane"] + [f"pct_k{k}" for k in ks]
                        + (["pct_mbb", "mbb_pass"] if mbb else []) + ["is_pareto"])
            for c in res["candidates"]:
                wr.writerow([c["N"], c["planes"], c["sats_per_plane"]]
                            + [f"{c['pct_by_k'][k]:.6f}" for k in ks]
                            + ([f"{c['pct_mbb']:.6f}", int(c['mbb_pass'])] if mbb else [])
                            + [int(c["is_pareto"])])
        else:  # min_N_vs_incl
            f.write(f"# target_availability: {res['target_availability']}  area_grade: {res['area_grade']}"
                    f"  planes: {res['planes']}  altitude_km: {res['altitude_km']}\n")
            wr.writerow(["inclination_deg"] + [f"min_N_k{k}" for k in ks]
                        + (["min_N_mbb"] if mbb else []))
            for b in res["by_inclination"]:
                wr.writerow([b["inclination"]] + [b["min_N_by_k"][k] for k in ks]
                            + ([b.get("min_N_mbb")] if mbb else []))

