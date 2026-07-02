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
        self.k_cov = w.IntSlider(value=1, min=1, max=30, description="k (min sats in view)",
                                 style=wide, layout=w.Layout(width="360px"))
        self.use_shard = w.Checkbox(value=True, description="Use sharding (faster, identical result)")
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
        res = run_coverage_h3(sim, AORS[self.aor.value], cell_res=self.cell_res.value,
                              shard_res=(1 if self.use_shard.value else None), chunk_steps=10,
                              progress=progress)
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
            self._draw(self.out_avail, lambda: plot_coverage_hexmap(res, title=f"Coverage availability (k={ak}) - {self.aor.value}"))
            self._draw(self.out_siv, lambda: plot_sats_in_view_hexmap(res, title=f"Mean satellites in view (time-avg) - {self.aor.value}"))
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
