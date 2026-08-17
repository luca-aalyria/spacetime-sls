"""Slice A "oracle compare": rebuild notebook-01's coverage outputs from the PRODUCTION
link predictor's beam-candidate segments instead of our geometry engine.

BeamCandidateSegment (proto_internal/storage): one segment per (sat-antenna, time bucket,
ground target) — id `T:<bucket>#<antenna>@<lat>/<lon>` — carrying time-sampled
`accessibilities` booleans over `interval` at `sampling_resolution`. Aggregating segments
per ground point gives n-in-view per time sample -> availability_by_k / sats_in_view_mean
in the SAME result shape as `run_coverage_h3_elements`, so every nb01/viz plot and the
CSV writer work unchanged, and results diff cell-by-cell against the offline engine.

Read via Listen dump (see tools/quantum_sampler.py rationale: interval GetEntities is a
full-history scan) with a `ListenRange` id-prefix time slice, e.g. "T:2026-08-17T09".
"""
import re

import numpy as np

from . import _deps

_ID_RE = re.compile(r"^T:(?P<bucket>[^#]+)#(?P<antenna>[^@]+)@(?P<lat>-?[\d.]+)/(?P<lon>-?[\d.]+)")


def read_beam_candidates(target="localhost:9999", bucket_prefix=None, dump_timeout_s=600.0):
    """Listen-dump BEAM_CANDIDATE_SEGMENT entities (optionally one time-bucket prefix).
    Returns the list of storage Entity protos. Read-only (Listen is a subscription;
    we disconnect after the dump)."""
    _deps.require("HAS_STORAGE", "proto_internal.storage (vendored stubs)")
    import time as _time
    grpc = _deps.grpc
    pb = _deps.storage_pb2
    stub = _deps.storage_pb2_grpc.StoreStub(grpc.insecure_channel(
        target, options=[("grpc.max_receive_message_length", 512 << 20)]))
    req = pb.ListenRequest()
    req.group.add().type = pb.EntityType.Value("BEAM_CANDIDATE_SEGMENT")
    req.dump_only = True
    if bucket_prefix:
        rng = req.ranges.add()
        rng.type = req.group[0].type
        rng.begin = bucket_prefix
        rng.end = bucket_prefix + "\U0010ffff"
    out = []
    t0 = _time.monotonic()
    stream = stub.Listen(req, timeout=dump_timeout_s)
    try:
        for chunk in stream:
            if chunk.HasField("dump_complete"):
                break
            for mut in chunk.updates.mutations:
                out.append(mut.entity)
            if _time.monotonic() - t0 > dump_timeout_s:
                break
    finally:
        stream.cancel()
    return out


def beam_candidates_to_coverage(entities, cell_res=3, k_values=(1, 2), default_k=None,
                                sat_of=None):
    """Aggregate beam-candidate segments -> nb01-shaped coverage result computed from the
    LIVE link predictor's accessibility samples.

    `sat_of(antenna_id) -> sat_id` collapses multiple antennas per satellite (default:
    strip everything from '-platform' on, so all antennas of one platform count once).
    Returns {cells, lat, lon, availability, availability_by_k, sats_in_view_mean,
    min_elev_deg: None, n_samples, n_points} — plottable with ngso_sls.viz.plots.
    """
    import h3
    if sat_of is None:
        sat_of = lambda a: a.split("-platform")[0]              # noqa: E731

    # point -> sample_time -> set of sats accessible
    points = {}                                                 # (lat,lon) -> {t: set(sat)}
    time_grid = set()                # ALL sample times, including fully-inaccessible ones
    for e in entities:
        seg = e.beam_candidate_segment if hasattr(e, "beam_candidate_segment") else e
        m = _ID_RE.match(e.id if hasattr(e, "id") else "")
        if not m:
            continue
        lat, lon = float(m["lat"]), float(m["lon"])
        sat = sat_of(m["antenna"])
        acc = list(seg.accessibilities)
        if not acc:
            continue
        res_s = seg.sampling_resolution.seconds + seg.sampling_resolution.nanos / 1e9
        start = seg.interval.start_time.seconds
        n_plat = max(1, len(seg.platforms))
        # layout: either one series per segment, or platforms x samples (row-major)
        n_samp = len(acc) if len(acc) % n_plat else len(acc) // n_plat
        series = acc[:n_samp] if len(acc) == n_samp else \
            [any(acc[p * n_samp + i] for p in range(n_plat)) for i in range(n_samp)]
        slot = points.setdefault((lat, lon), {})
        for i, ok in enumerate(series):
            time_grid.add(start + i * res_s)
            if ok:
                slot.setdefault(start + i * res_s, set()).add(sat)

    if not points:
        raise ValueError("no parseable beam-candidate segments (id format drift?)")

    all_times = sorted(time_grid)
    n_time = len(all_times)
    latlon = list(points)
    ks = sorted(set(k_values))
    n_cellpts = len(latlon)
    availability_by_k = {k: np.zeros(n_cellpts) for k in ks}
    siv = np.zeros(n_cellpts)
    for i, key in enumerate(latlon):
        counts = np.array([len(points[key].get(t, ())) for t in all_times])
        for k in ks:
            availability_by_k[k][i] = float((counts >= k).mean())
        siv[i] = float(counts.mean())

    lat = np.array([p[0] for p in latlon])
    lon = np.array([p[1] for p in latlon])
    cells = [h3.latlng_to_cell(a, o, cell_res) for a, o in latlon]
    dk = default_k if default_k in availability_by_k else ks[0]
    return {"cells": cells, "lat": lat, "lon": lon,
            "availability": availability_by_k[dk],
            "availability_by_k": availability_by_k,
            "sats_in_view_mean": siv, "min_elev_deg": None,
            "n_samples": n_time, "n_points": n_cellpts}
