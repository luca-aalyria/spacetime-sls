#!/usr/bin/env python3
"""Compute the remaining Jio-report artifacts: the reference-window oracle
compare (per-bucket streaming, bounded memory) and the capacity figure.

The tool appends its results to docs/reports/figs/jio_report_stats.json.
"""
import glob
import gzip
import json
import pickle
import re
import resource
import sys

resource.setrlimit(resource.RLIMIT_AS, (12 << 30, 12 << 30))

sys.path.insert(0, "/workspace/spacetime-sls")
sys.path.insert(0, "/workspace/spacetime-sls/vendor/spacetime_api_stubs")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from google.protobuf import text_format

from ngso_sls.propagation.kepler_j2 import KeplerJ2Propagator
from ngso_sls.spacetime import _deps
from ngso_sls.spacetime.client import _NmtsEntityView
from ngso_sls.spacetime.nmts_adapter import platforms_to_elements
from ngso_sls.spacetime.oracle import (beam_candidates_to_coverage,
                                       engine_coverage_at_points)

FIGS = "/workspace/spacetime-sls/docs/reports/figs"
DUMP = "/workspace/spacetime-sls/output/fss01-demo-dump"
MIN_ELEV = 25.0
N_BUCKETS = 3
pb = _deps.storage_pb2


def log(msg):
    print(msg, flush=True)


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


def load_model_B():
    views = []
    for block in iter_blocks(f"{DUMP}/nmts/entities_ek_platform.txtpb"):
        e = pb.Entity()
        text_format.Parse(block, e)
        views.append(_NmtsEntityView(e.nmts_entity))
    return platforms_to_elements(views, [])


def main():
    stats = json.load(open(f"{FIGS}/jio_report_stats.json")) \
        if glob.glob(f"{FIGS}/jio_report_stats.json") else {}
    built = load_model_B()

    # Per-bucket compare; weighted merge over the union of points.
    acc = {}          # cell -> [lat, lon, samples, orc_avail_w, eng_avail_w]
    tot_samples = 0
    files = sorted(glob.glob(f"{DUMP}/window-2026-08-20/*.pkl.gz"))[:N_BUCKETS]
    for fn in files:
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
            built["elems"], built["plane_uid"], orc, built["ref_epoch_s"],
            min_elev_deg=MIN_ELEV, k_values=[1, 2], default_k=1,
            propagator=KeplerJ2Propagator(j2=0.0))
        n = int(orc["n_samples"])
        tot_samples += n
        for i, c in enumerate(orc["cells"]):
            a = acc.setdefault(c, [orc["lat"][i], orc["lon"][i], 0, 0.0, 0.0])
            a[2] += n
            a[3] += float(orc["availability"][i]) * n
            a[4] += float(eng["availability"][i]) * n
        log(f"{fn.split('/')[-1]}: {orc['n_points']} points, {n} samples")

    lat = np.array([v[0] for v in acc.values()])
    lon = np.array([v[1] for v in acc.values()])
    # A point missing from a bucket contributes zero availability there.
    orc_av = np.array([v[3] / tot_samples for v in acc.values()])
    eng_av = np.array([v[4] / tot_samples for v in acc.values()])
    d = eng_av - orc_av
    stats["oracle_B"] = {"n_points": int(len(acc)), "n_samples": int(tot_samples),
                         "k1_mean": round(float(orc_av.mean()), 4)}
    stats["delta_B"] = {"propagator": "two-body",
                        "mean_delta": round(float(np.nanmean(d)), 4),
                        "max_abs_delta": round(float(np.nanmax(np.abs(d))), 4)}
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for k, (vals, title, cmap, vmin, vmax) in enumerate((
            (orc_av, "Spacetime link predictor: k=1 availability", "viridis", 0, 1),
            (eng_av, "SLS engine at the same points (two-body)", "viridis", 0, 1),
            (d, f"Delta (engine - Spacetime)\nmean {np.nanmean(d):+.4f}, "
                f"max |d| {np.nanmax(np.abs(d)):.4f}", "coolwarm", -0.2, 0.2))):
        s = ax[k].scatter(lon, lat, c=vals, cmap=cmap, vmin=vmin, vmax=vmax, s=18)
        ax[k].set_title(title)
        ax[k].set_xlabel("lon [deg]")
        ax[k].set_ylabel("lat [deg]")
        plt.colorbar(s, ax=ax[k])
    plt.tight_layout()
    fig.savefig(f"{FIGS}/jio_oracle_delta_B.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    log("fig: jio_oracle_delta_B")

    with open(f"{DUMP}/output_window.pkl", "rb") as f:
        wnd = pickle.load(f)
    adrs = []
    for b in wnd["data"]["ALLOCATED_DATA_RATE"]:
        e = pb.Entity()
        e.ParseFromString(b)
        m = re.search(r"(?:data_)?rate_bps: (\d+)", str(e))
        adrs.append(int(m.group(1)) if m else 0)
    adrs = np.array(adrs, dtype=float)
    served = adrs[adrs > 0]
    stats["capacity_B"] = {
        "n_requests": int(len(adrs)),
        "n_served": int(len(served)),
        "served_pct": round(100.0 * len(served) / max(len(adrs), 1), 1),
        "aggregate_gbps": round(float(adrs.sum()) / 1e9, 2),
        "median_served_mbps": round(float(np.median(served)) / 1e6, 2)
        if len(served) else 0.0,
        "requested_mbps": 2.0,
    }
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(adrs / 1e6, bins=30)
    ax.axvline(2.0, color="red", linestyle="--", label="requested CIR (2 Mbps)")
    ax.set_xlabel("allocated data rate [Mbps]")
    ax.set_ylabel("service requests")
    ax.set_title(f"Reference scenario: allocated data rates ({len(adrs)} requests)")
    ax.legend()
    fig.savefig(f"{FIGS}/jio_capacity_B.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    log("fig: jio_capacity_B")

    with open(f"{FIGS}/jio_report_stats.json", "w") as f:
        json.dump(stats, f, indent=1)
    log("DONE")
    log(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
