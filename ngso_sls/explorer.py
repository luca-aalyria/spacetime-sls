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
import traceback

import matplotlib.pyplot as plt
import ipywidgets as w
from IPython.display import display, clear_output

from .presets import JIO_SCENARIOS
from .config import Shell, Constellation, TimeGrid, SimConfig
from .pipeline import run_coverage_h3
from .grids.aor import AORS
from .viz.plots import (
    plot_coverage_hexmap,
    plot_sats_in_view_hexmap,
    plot_sats_in_view_vs_latitude,
    plot_availability_hist,
)
from .io.csv_io import write_availability_csv

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _lbl(text):
    return w.HTML(f"<b>{text}</b>")


def _titled(title, box):
    return w.VBox([_lbl(title), box])


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
        self.step_s = w.FloatSlider(value=60, min=10, max=120, step=10, description="Time step s", style=s, layout=L)
        self.k_cov = w.IntSlider(value=2, min=1, max=30, description="k (min sats in view)",
                                 style=wide, layout=w.Layout(width="360px"))
        self.use_shard = w.Checkbox(value=True, description="Use sharding (faster, identical result)")
        self.terrain_on = w.Checkbox(value=False, description="Account for terrain (raises horizon)")
        self.terrain_source = w.Dropdown(options=["ETOPO fetch (Colab)", "Demo ridge (offline)"],
                                         value="ETOPO fetch (Colab)", description="Terrain source",
                                         style=s, layout=L)
        self.hex_alpha = w.FloatSlider(value=0.80, min=0.1, max=1.0, step=0.05,
                                       description="Cell opacity", style=s, layout=L)
        self.run_btn = w.Button(description="Run simulation", button_style="primary", icon="play")
        self.progress = w.IntProgress(value=0, min=0, max=1, bar_style="info",
                                      layout=w.Layout(width="260px"))
        self.status = w.HTML("<i>idle</i>")

    def _build_layout(self):
        box = w.Layout(border="1px solid #ccc", padding="6px", margin="2px", min_height="60px")
        self.out_log = w.Output(layout=w.Layout(min_height="40px"))
        self.out_avail = w.Output(layout=box)
        self.out_siv = w.Output(layout=box)
        self.out_lat = w.Output(layout=box)
        self.out_hist = w.Output(layout=box)
        self.tabs = w.Tab(children=[self.out_avail, self.out_siv, self.out_lat, self.out_hist])
        for i, t in enumerate(["Availability map", "Sats-in-view map", "Sats vs latitude", "Histogram"]):
            self.tabs.set_title(i, t)
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
            w.HBox([self.hex_alpha, self.terrain_on]),
            w.HBox([self.terrain_source]),
            self.run_btn,
            w.HBox([self.progress, self.status]),
        ])
        self.results = w.VBox([_lbl("Run log"), self.out_log, self.tabs])

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

    def compute(self, progress=None) -> dict:
        cons = self.build_constellation()
        sim = SimConfig(cons,
                        TimeGrid(_EPOCH, duration_s=self.duration_min.value * 60.0, step_s=self.step_s.value),
                        k_coverage=self.k_cov.value)
        terrain = None
        if self.terrain_on.value:
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
                terrain = lambda clat, clon, d=dem: horizon_mask_from_dem(  # noqa: E731
                    *d, clat, clon, n_bins=36, radius_km=400)
            else:
                terrain = lambda clat, clon: cell_horizon_masks(clat, clon, bbox)  # noqa: E731
        res = run_coverage_h3(sim, AORS[self.aor.value], cell_res=self.cell_res.value,
                              shard_res=(1 if self.use_shard.value else None), chunk_steps=10,
                              progress=progress, terrain=terrain)
        res["_sim"] = sim
        res["_total_sats"] = sum(s.walker_T for s in cons.shells)
        res["_shape"] = "; ".join(
            f"{s.walker_T}/{s.walker_P}/{s.walker_F} @{s.inclination_deg:g}°/{s.altitude_km:g}km"
            for s in cons.shells)
        return res

    # -- rendering ------------------------------------------------------------
    @staticmethod
    def _draw(box, make_fig):
        with box:
            clear_output(wait=True)
            try:
                make_fig()
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
                print("Running simulation…")
                res = self.compute(progress=_progress)
                self.last_result = res
                a = res["availability"]
                print(f"Constellation: {self.scenario.value}  |  {res['_total_sats']} sats  |  {res['_shape']}")
                print(f"Over {self.aor.value} (H3 res {self.cell_res.value}, {self.duration_min.value:.0f} min "
                      f"@ {self.step_s.value:.0f}s, k={self.k_cov.value}):")
                print(f"  cells={len(res['cells'])}  availability mean={a.mean():.3f} min={a.min():.3f} "
                      f"max={a.max():.3f}  mean sats-in-view(time-avg)={res['sats_in_view_mean'].mean():.1f} "
                      f"(max {res['sats_in_view_mean'].max():.0f})")
                write_availability_csv(
                    res, self.csv_path,
                    {"scenario": self.scenario.value, "aor": self.aor.value, "total_sats": res["_total_sats"],
                     "k_coverage": self.k_cov.value, "seed": res["_sim"].seed,
                     "step_s": res["_sim"].time_grid.step_s, "propagator": "KeplerJ2"})
                print(f"  wrote {self.csv_path}")
            self.status.value = "🖼️ rendering plots…"
            ak = self.k_cov.value
            alpha = self.hex_alpha.value
            self._draw(self.out_avail, lambda: plot_coverage_hexmap(res, title=f"Coverage availability (k={ak}) - {self.aor.value}", alpha=alpha))
            self._draw(self.out_siv, lambda: plot_sats_in_view_hexmap(res, title=f"Mean satellites in view (time-avg) - {self.aor.value}", alpha=alpha))
            self._draw(self.out_lat, lambda: plot_sats_in_view_vs_latitude(res))
            self._draw(self.out_hist, lambda: plot_availability_hist(res))
            self.status.value = (f"✅ done — {len(res['cells'])} cells, availability mean "
                                 f"{a.mean():.3f}, mean sats-in-view {res['sats_in_view_mean'].mean():.1f}")
            self.progress.bar_style = "success"
        except Exception:
            with self.out_log:
                traceback.print_exc()
            self.status.value = "❌ error — see Run log"
            self.progress.bar_style = "danger"
        finally:
            self.run_btn.disabled = False
            self.run_btn.description = "Run simulation"

    def display(self):
        """Show controls + results together and run once (single-cell convenience)."""
        display(self.controls, self.results)
        self.run()


class MinSatSweep:
    """Minimum-satellite sweep UI: vary a single Walker shell's size (planes x sats/plane) and
    plot coverage vs N over the AOR, marking the smallest constellation meeting a coverage grade."""

    def __init__(self, csv_path: str = "min_sat_sweep.csv"):
        self.csv_path = csv_path
        self.last_result = None
        s = {"description_width": "150px"}
        L = w.Layout(width="340px")
        self.aor = w.Dropdown(options=list(AORS), value="India", description="Service area", style=s, layout=L)
        self.planes = w.IntSlider(value=40, min=1, max=60, description="Planes", style=s, layout=L)
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
        self.step_s = w.FloatSlider(value=60, min=10, max=120, step=10, description="Time step s", style=s, layout=L)
        self.use_shard = w.Checkbox(value=True, description="Use sharding")
        self.run_btn = w.Button(description="Run sweep", button_style="primary", icon="play")
        self.progress = w.IntProgress(value=0, min=0, max=1, bar_style="info", layout=w.Layout(width="260px"))
        self.status = w.HTML("<i>idle</i>")
        box = w.Layout(border="1px solid #ccc", padding="6px", margin="2px", min_height="60px")
        self.out_plot = w.Output(layout=box)
        self.out_log = w.Output(layout=w.Layout(min_height="40px"))
        self.run_btn.on_click(self.run)
        self.controls = w.VBox([
            _lbl("Minimum-satellite sweep — base shell (single Walker shell, thinned by sats/plane)"),
            w.HBox([self.aor, self.planes]),
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
            self.use_shard,
            self.run_btn,
            w.HBox([self.progress, self.status]),
        ])
        self.results = w.VBox([_lbl("Sweep log"), self.out_log,
                               _titled("Coverage vs constellation size", self.out_plot)])

    def compute(self, progress=None):
        """Returns (mode, result, inclinations). mode is 'coverage_vs_N' for a single inclination,
        or 'min_N_vs_incl' for an inclination range."""
        from .sweep import min_sat_sweep, inclination_sweep, incl_values
        spp = list(range(self.spp_min.value, self.spp_max.value + 1, self.spp_step.value))
        ks = tuple(self.k_values.value) or (2,)
        incs = incl_values(self.incl_min.value, self.incl_max.value, self.incl_step.value)
        common = dict(min_elev_deg=self.min_elev.value, k_values=ks,
                      target_availability=self.target_avail.value, area_grade=self.area_grade.value,
                      cell_res=self.cell_res.value, duration_s=self.duration_min.value * 60.0,
                      step_s=self.step_s.value, phasing=self.phasing.value,
                      use_sharding=self.use_shard.value, progress=progress)
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
                mode, res, incs = self.compute(progress=_progress)
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
                _write_sweep_csv(res, mode, self.csv_path)
                print(f"wrote {self.csv_path}")
            self.status.value = "🖼️ rendering…"
            with self.out_plot:
                clear_output(wait=True)
                try:
                    from .viz.plots import plot_min_sat_sweep, plot_inclination_sweep
                    (plot_min_sat_sweep if mode == "coverage_vs_N" else plot_inclination_sweep)(res)
                    plt.show()
                except Exception:
                    traceback.print_exc()
            self.status.value = "✅ done"
            self.progress.bar_style = "success"
        except Exception:
            with self.out_log:
                traceback.print_exc()
            self.status.value = "❌ error — see Sweep log"
            self.progress.bar_style = "danger"
        finally:
            self.run_btn.disabled = False
            self.run_btn.description = "Run sweep"


def _write_sweep_csv(res: dict, mode: str, path: str):
    import csv
    ks = res["k_values"]
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        if mode == "coverage_vs_N":
            f.write(f"# min_N_by_k: {res['min_N_by_k']}  target_availability: {res['target_availability']}"
                    f"  area_grade: {res['area_grade']}  inclination: {res['inclination_deg']}\n")
            wr.writerow(["N", "planes", "sats_per_plane", "mean_sats_in_view"]
                        + [f"pct_k{k}" for k in ks] + [f"mean_avail_k{k}" for k in ks])
            for r in res["sweep"]:
                wr.writerow([r["N"], r["planes"], r["sats_per_plane"], f"{r['mean_sats_in_view']:.6f}"]
                            + [f"{r['pct_by_k'][k]:.6f}" for k in ks]
                            + [f"{r['mean_avail_by_k'][k]:.6f}" for k in ks])
        else:  # min_N_vs_incl
            f.write(f"# target_availability: {res['target_availability']}  area_grade: {res['area_grade']}"
                    f"  planes: {res['planes']}  altitude_km: {res['altitude_km']}\n")
            wr.writerow(["inclination_deg"] + [f"min_N_k{k}" for k in ks])
            for b in res["by_inclination"]:
                wr.writerow([b["inclination"]] + [b["min_N_by_k"][k] for k in ks])

