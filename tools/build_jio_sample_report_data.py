#!/usr/bin/env python3
"""Compute every figure and statistic for the Reliance Jio sample report.

Inputs:
- luca-sls1 store (localhost:9996): the 200-satellite Jio-shape model and its
  frozen beam-candidate window.
- output/fss01-demo-dump/: the 150-satellite reference model and the archived
  24-bucket candidate window (window-2026-08-20/*.pkl.gz).

Outputs:
- docs/reports/figs/jio_*.png (all report figures)
- docs/reports/figs/jio_report_stats.json (all report numbers)
"""
import glob
import gzip
import resource

# Hard address-space cap: the process dies cleanly instead of exhausting the
# host VM (16 GiB).
resource.setrlimit(resource.RLIMIT_AS, (12 << 30, 12 << 30))
import json
import pickle
import re
import sys

sys.path.insert(0, "/workspace/spacetime-sls")
sys.path.insert(0, "/workspace/spacetime-sls/vendor/spacetime_api_stubs")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from google.protobuf import text_format

from ngso_sls.config import TimeGrid
from ngso_sls.pipeline import run_coverage_h3_elements
from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator
from ngso_sls.spacetime import _deps
from ngso_sls.spacetime.client import StorageEntityStore, _NmtsEntityView
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements
from ngso_sls.spacetime.oracle import (beam_candidates_to_coverage,
                                       engine_coverage_at_points,
                                       read_beam_candidates)
from ngso_sls.viz.plots import plot_coverage_hexmap, plot_sats_in_view_hexmap

FIGS = "/workspace/spacetime-sls/docs/reports/figs"
DUMP = "/workspace/spacetime-sls/output/fss01-demo-dump"
MIN_ELEV = 25.0                       # both models: 65-deg UT field of regard
from ngso_sls.explorer import AORS
AOR_INDIA = AORS["India"]
AOR_GLOBAL = AORS["Global"]
from datetime import datetime, timezone
EPOCH = datetime(2026, 8, 20, tzinfo=timezone.utc)   # engine runs anchor
N_ARCHIVE_BUCKETS = 4                 # 20 min of the reference window
pb = _deps.storage_pb2
stats = {}


def log(msg):
    print(msg, flush=True)


def save_stats():
    with open(f"{FIGS}/jio_report_stats.json", "w") as f:
        json.dump(stats, f, indent=1)


def save(fig, name):
    fig.savefig(f"{FIGS}/{name}.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    log(f"fig: {name}")


def iter_blocks(path):
    buf, depth, inside = [], 0, False
    for line in open(path):
        if not inside:
            if line.rstrip() == "entity {":
                inside, depth, buf = True, 1, []
            continue
        depth += line.count("{") - line.count("}")
        if depth == 0:
            yield "".join(buf)
            inside = False
        else:
            buf.append(line)


def load_model_A():
    """The 200-satellite Jio shape from the cached model dump."""
    views, uts = [], []
    with gzip.open("/workspace/spacetime-sls/output/pinned-instance/"
                   "model_A_entities.pkl.gz", "rb") as f:
        raw = pickle.load(f)
    for b in raw:
        e = pb.Entity()
        e.ParseFromString(b)
        views.append(_NmtsEntityView(e.nmts_entity))
        plat = e.nmts_entity.ek_platform
        if (e.id.startswith("user-terminal-") and e.id.endswith("-platform")
                and plat.motion.entry
                and plat.motion.entry[0].WhichOneof("type") == "geodetic_wgs84"):
            g = plat.motion.entry[0].geodetic_wgs84
            uts.append((g.latitude_deg, g.longitude_deg))
    built = platforms_to_elements(views, [])
    return built, uts


class _Wrap:
    def __init__(self, e):
        self.id = e.id
        self.nmts_entity = e.nmts_entity


def load_model_B():
    """The 150-satellite reference shape from the fss01 dump."""
    views, uts = [], []
    for block in iter_blocks(f"{DUMP}/nmts/entities_ek_platform.txtpb"):
        e = pb.Entity()
        text_format.Parse(block, e)
        views.append(_NmtsEntityView(e.nmts_entity))
        plat = e.nmts_entity.ek_platform
        if (e.id.startswith("user-terminal-")
                and plat.motion.entry
                and plat.motion.entry[0].WhichOneof("type") == "geodetic_wgs84"):
            g = plat.motion.entry[0].geodetic_wgs84
            uts.append((g.latitude_deg, g.longitude_deg))
    built = platforms_to_elements(views, [])
    return built, uts


def load_candidates_A():
    with gzip.open("/workspace/spacetime-sls/output/pinned-instance/"
                   "window_A_2026-08-20.pkl.gz", "rb") as f:
        raw = pickle.load(f)
    out = []
    for b in raw:
        e = pb.Entity()
        e.ParseFromString(b)
        out.append(e)
    return out


def load_candidates_B():
    files = sorted(glob.glob(f"{DUMP}/window-2026-08-20/*.pkl.gz"))[:N_ARCHIVE_BUCKETS]
    ents = []
    for fn in files:
        with gzip.open(fn, "rb") as f:
            raw = pickle.load(f)
        while raw:                       # free each byte string after parsing
            e = pb.Entity()
            e.ParseFromString(raw.pop())
            ents.append(e)
        del raw
        log(f"loaded {fn.split('/')[-1]} (total {len(ents)})")
    return ents


def constellation_fig(built, label):
    e, pu = built["elems"], built["plane_uid"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
    ax[0].scatter(np.degrees(e[:, 3]) % 360, np.degrees(e[:, 5]) % 360,
                  c=pu, cmap="tab20", s=14)
    ax[0].set_xlabel("RAAN [deg]")
    ax[0].set_ylabel("mean anomaly [deg]")
    ax[0].set_title(f"{label}: {e.shape[0]} satellites, "
                    f"{len(np.unique(pu))} planes")
    ax[1].hist(e[:, 0] * (1 + e[:, 1]) - 6378.137, bins=20)
    ax[1].set_xlabel("apoapsis altitude [km]")
    ax[1].set_title("Altitude distribution")
    plt.tight_layout()
    return fig


def ut_fig(uts_a, uts_b):
    a = np.array(uts_a)
    b = np.array(uts_b)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    ax[0].scatter(a[:, 1], a[:, 0], s=10, c="tab:blue")
    ax[0].set_title(f"Jio 200-sat scenario: {len(a)} user terminals\n"
                    "(uniform, India H3 res 3)")
    ax[1].scatter(b[:, 1], b[:, 0], s=10, c="tab:orange")
    ax[1].set_title(f"Reference scenario: {len(b)} user terminals (global)")
    for x in ax:
        x.set_xlabel("longitude [deg]")
        x.set_ylabel("latitude [deg]")
    plt.tight_layout()
    return fig


def run_engine(built, aor, res, label, duration_s=6600, step_s=30.0):
    tg = TimeGrid(EPOCH, duration_s=duration_s, step_s=step_s)
    out = run_coverage_h3_elements(
        built["elems"], built["plane_uid"], MIN_ELEV, tg, aor,
        cell_res=res, shard_res=1, chunk_steps=10, workers=2,
        k_values=[1, 2], default_k=1)
    log(f"engine run done: {label}")
    return out


def lat_profile(res):
    lat = np.asarray(res["lat"])
    av = np.asarray(res["availability"])
    bins = np.arange(-60, 61, 2.0)
    idx = np.digitize(lat, bins)
    xs, ys = [], []
    for i in range(1, len(bins)):
        m = idx == i
        if m.sum():
            xs.append(0.5 * (bins[i - 1] + bins[i]))
            ys.append(float(av[m].mean()))
    return np.array(xs), np.array(ys)


def main():
    import os
    os.makedirs(FIGS, exist_ok=True)

    log("== models ==")
    built_A, uts_A = load_model_A()
    built_B, uts_B = load_model_B()
    for tag, built in (("A", built_A), ("B", built_B)):
        e = built["elems"]
        stats[f"model_{tag}"] = {
            "n_sats": int(e.shape[0]),
            "n_planes": int(len(np.unique(built["plane_uid"]))),
            "alt_km": round(float(e[:, 0].mean()) - 6378.137, 1),
            "inclination_deg": round(float(np.degrees(e[:, 2]).mean()), 1),
            "ref_epoch_s": float(built["ref_epoch_s"]),
        }
    stats["model_A"]["n_uts"] = len(uts_A)
    stats["model_B"]["n_uts"] = len(uts_B)
    save_stats()
    save(constellation_fig(built_A, "Jio layer 1 (Walker 200/20/1)"),
         "jio_constellation_A")
    save(constellation_fig(built_B, "Reference (Walker 150/10/1)"),
         "jio_constellation_B")
    save(ut_fig(uts_A, uts_B), "jio_ut_distribution")

    log("== engine parametric runs ==")
    engA_india = run_engine(built_A, AOR_INDIA, 3, "A India res3")
    engB_india = run_engine(built_B, AOR_INDIA, 3, "B India res3")
    engA_glob = run_engine(built_A, AOR_GLOBAL, 2, "A global res2")
    engB_glob = run_engine(built_B, AOR_GLOBAL, 2, "B global res2")
    for tag, r in (("A_india", engA_india), ("B_india", engB_india),
                   ("A_global", engA_glob), ("B_global", engB_glob)):
        stats[f"engine_{tag}"] = {
            "k1_mean": round(float(np.mean(r["availability"])), 4),
            "k1_full_cells_pct": round(
                100.0 * float(np.mean(np.asarray(r["availability"]) >= 0.999)), 1),
            "sats_in_view_mean": round(float(np.mean(r["sats_in_view_mean"])), 2),
            "n_cells": int(len(r["availability"])),
        }
    save_stats()

    save(plot_coverage_hexmap(engA_india,
         title="Jio 200-sat: availability k=1 (India, engine)"), "jio_avail_A_india")
    save(plot_coverage_hexmap(engB_india,
         title="Reference 150-sat: availability k=1 (India, engine)"), "jio_avail_B_india")
    save(plot_coverage_hexmap(engA_glob,
         title="Jio 200-sat: availability k=1 (global, engine)"), "jio_avail_A_global")
    save(plot_coverage_hexmap(engB_glob,
         title="Reference 150-sat: availability k=1 (global, engine)"), "jio_avail_B_global")
    save(plot_sats_in_view_hexmap(engA_glob,
         title="Jio 200-sat: mean satellites in view (global)"), "jio_sats_A_global")

    fig, ax = plt.subplots(figsize=(8, 4))
    for r, lbl, c in ((engA_glob, "Jio 200 @48°/650 km", "tab:blue"),
                      (engB_glob, "Reference 150 @53°/1157 km", "tab:orange")):
        xs, ys = lat_profile(r)
        ax.plot(xs, ys, label=lbl, color=c)
    ax.axvspan(6, 36, color="green", alpha=0.08, label="India latitude band")
    ax.set_xlabel("latitude [deg]")
    ax.set_ylabel("k=1 availability")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower center")
    ax.set_title(f"Availability vs latitude ({MIN_ELEV:.0f}° mask, engine)")
    save(fig, "jio_lat_profile")

    log("== oracle windows ==")
    bc_A = load_candidates_A()
    orc_A = beam_candidates_to_coverage(bc_A, cell_res=3, k_values=[1, 2], default_k=1)
    del bc_A
    stats["oracle_A"] = {"n_points": int(orc_A["n_points"]),
                         "n_samples": int(orc_A["n_samples"]),
                         "k1_mean": round(float(np.mean(orc_A["availability"])), 4)}
    save_stats()

    log("== oracle vs engine (B: per-bucket streaming) ==")
    acc, tot = {}, 0
    for fn in sorted(glob.glob(f"{DUMP}/window-2026-08-20/*.pkl.gz"))[:N_ARCHIVE_BUCKETS]:
        with gzip.open(fn, "rb") as f:
            raw = pickle.load(f)
        ents = []
        while raw:
            e = pb.Entity()
            e.ParseFromString(raw.pop())
            ents.append(e)
        del raw
        orc = beam_candidates_to_coverage(ents, cell_res=3, k_values=[1, 2],
                                          default_k=1)
        del ents
        eng = engine_coverage_at_points(
            built_B["elems"], built_B["plane_uid"], orc, built_B["ref_epoch_s"],
            min_elev_deg=MIN_ELEV, k_values=[1, 2], default_k=1,
            propagator=KeplerJ2Propagator(j2=0.0))
        n = int(orc["n_samples"])
        tot += n
        for i, c in enumerate(orc["cells"]):
            a = acc.setdefault(c, [orc["lat"][i], orc["lon"][i], 0.0, 0.0])
            a[2] += float(orc["availability"][i]) * n
            a[3] += float(eng["availability"][i]) * n
        log(f"bucket merged: {fn.split('/')[-1]} ({n} samples)")
    latB = np.array([v[0] for v in acc.values()])
    lonB = np.array([v[1] for v in acc.values()])
    orcB_av = np.array([v[2] / tot for v in acc.values()])
    engB_av = np.array([v[3] / tot for v in acc.values()])
    dB = engB_av - orcB_av
    stats["oracle_B"] = {"n_points": int(len(acc)), "n_samples": int(tot),
                         "k1_mean": round(float(orcB_av.mean()), 4)}
    stats["delta_B"] = {"propagator": "two-body",
                        "mean_delta": round(float(np.nanmean(dB)), 4),
                        "max_abs_delta": round(float(np.nanmax(np.abs(dB))), 4)}
    save_stats()
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for k, (vals, title, cmap, vmin, vmax) in enumerate((
            (orcB_av, "Spacetime link predictor: k=1 availability", "viridis", 0, 1),
            (engB_av, "SLS engine at the same points (two-body)", "viridis", 0, 1),
            (dB, f"Delta (engine - Spacetime)\nmean {np.nanmean(dB):+.4f}, "
                 f"max |d| {np.nanmax(np.abs(dB)):.4f}", "coolwarm", -0.2, 0.2))):
        s = ax[k].scatter(lonB, latB, c=vals, cmap=cmap, vmin=vmin, vmax=vmax, s=18)
        ax[k].set_title(title)
        ax[k].set_xlabel("lon [deg]")
        ax[k].set_ylabel("lat [deg]")
        plt.colorbar(s, ax=ax[k])
    plt.tight_layout()
    save(fig, "jio_oracle_delta_B")

    for tag, built, orc in (("A", built_A, orc_A),):
        best = None
        for pname, prop in (("two-body", KeplerJ2Propagator(j2=0.0)),
                            ("kepler-j2", KeplerJ2Propagator())):
            eng = engine_coverage_at_points(
                built["elems"], built["plane_uid"], orc, built["ref_epoch_s"],
                min_elev_deg=MIN_ELEV, k_values=[1, 2], default_k=1,
                propagator=prop)
            d = np.asarray(eng["availability"]) - np.asarray(orc["availability"])
            cand = {"propagator": pname,
                    "mean_delta": round(float(np.nanmean(d)), 4),
                    "max_abs_delta": round(float(np.nanmax(np.abs(d))), 4),
                    "eng": eng, "d": d}
            if best is None or cand["max_abs_delta"] < best["max_abs_delta"]:
                best = cand
        stats[f"delta_{tag}"] = {k: best[k] for k in
                                 ("propagator", "mean_delta", "max_abs_delta")}
        save_stats()
        fig, ax = plt.subplots(1, 3, figsize=(15, 4))
        s0 = ax[0].scatter(orc["lon"], orc["lat"],
                           c=orc["availability"], cmap="viridis",
                           vmin=0, vmax=1, s=18)
        ax[0].set_title("Spacetime link predictor: k=1 availability")
        plt.colorbar(s0, ax=ax[0])
        s1 = ax[1].scatter(orc["lon"], orc["lat"],
                           c=best["eng"]["availability"], cmap="viridis",
                           vmin=0, vmax=1, s=18)
        ax[1].set_title(f"SLS engine at the same points ({best['propagator']})")
        plt.colorbar(s1, ax=ax[1])
        s2 = ax[2].scatter(orc["lon"], orc["lat"], c=best["d"],
                           cmap="coolwarm", vmin=-0.2, vmax=0.2, s=18)
        ax[2].set_title(f"Delta (engine - Spacetime)\nmean {best['mean_delta']:+.4f}, "
                        f"max |d| {best['max_abs_delta']:.4f}")
        plt.colorbar(s2, ax=ax[2])
        for x in ax:
            x.set_xlabel("lon [deg]")
            x.set_ylabel("lat [deg]")
        plt.tight_layout()
        save(fig, f"jio_oracle_delta_{tag}")

    log("== capacity snapshot (reference scenario) ==")
    with open(f"{DUMP}/output_window.pkl", "rb") as f:
        wnd = pickle.load(f)
    adrs = []
    for b in wnd["data"]["ALLOCATED_DATA_RATE"]:
        e = pb.Entity()
        e.ParseFromString(b)
        m = re.search(r"data_rate_bps: (\d+)", str(e)) or \
            re.search(r"rate_bps: (\d+)", str(e))
        adrs.append(int(m.group(1)) if m else 0)
    adrs = np.array(adrs, dtype=float)
    served = adrs[adrs > 0]
    stats["capacity_B"] = {
        "n_requests": int(len(adrs)),
        "n_served": int(len(served)),
        "served_pct": round(100.0 * len(served) / max(len(adrs), 1), 1),
        "aggregate_gbps": round(float(adrs.sum()) / 1e9, 2),
        "median_served_mbps": round(float(np.median(served)) / 1e6, 2) if len(served) else 0.0,
        "requested_mbps": 2.0,
    }
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(adrs / 1e6, bins=30)
    ax.axvline(2.0, color="red", linestyle="--", label="requested CIR (2 Mbps)")
    ax.set_xlabel("allocated data rate [Mbps]")
    ax.set_ylabel("service requests")
    ax.set_title("Reference scenario: satsolver allocated data rates "
                 f"({len(adrs)} requests)")
    ax.legend()
    save(fig, "jio_capacity_B")

    with open(f"{FIGS}/jio_report_stats.json", "w") as f:
        json.dump(stats, f, indent=1)
    log("STATS WRITTEN")
    log(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
