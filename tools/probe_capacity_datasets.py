#!/usr/bin/env python3
"""Probe the capacity-estimation datasets on a live Store using interval/diff time-specs.

BEAM_CANDIDATE_SEGMENT / PROPAGATION_VECTOR_SEGMENT / SCHEDULE are written continuously
and duration-cached — `current` snapshots can be huge or transient, so this probes with
the SMALLEST window that returns data (one solver quantum ~10s, then 60s, 600s).

Usage:  .venv/bin/python tools/probe_capacity_datasets.py [--target localhost:9999]
        (needs a port-forward: tools/sandbox_live_setup.sh, START_JUPYTER=0)
"""
import argparse
import sys
import time

sys.path.insert(0, "/workspace/spacetime-sls/vendor/spacetime_api_stubs")
import grpc
from proto_internal.storage import storage_pb2 as pb, storage_pb2_grpc as pg

TYPES = ("BEAM_CANDIDATE_SEGMENT", "PROPAGATION_VECTOR_SEGMENT", "SCHEDULE",
         "LINK_PERFORMANCE_RATIOS", "TELEMETRY_SINR", "SERVICE_REQUEST", "BAND_PROFILE")
WINDOWS = (10, 60, 600)          # seconds; smallest-first (one quantum ≈ 10s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="localhost:9999")
    args = ap.parse_args()
    st = pg.StoreStub(grpc.insecure_channel(args.target))

    def probe(t, window=None):
        req = pb.GetEntitiesRequest(type=pb.EntityType.Value(t))
        if window is None:
            req.current.SetInParent()
        else:
            now = time.time()
            req.interval.start_time.unix_time_usec = int((now - window) * 1e6)
            req.interval.end_time.unix_time_usec = int(now * 1e6)
        n = 0
        sample = None
        for part in st.GetEntities(req, timeout=60):
            n += 1
            if sample is None:
                sample = part.entity
        return n, sample

    n, _ = probe("INTENT")
    print(f"sanity INTENT current: {n}")
    for t in TYPES:
        for win in WINDOWS:
            try:
                n, sample = probe(t, win)
            except grpc.RpcError as e:
                print(f"{t} @{win}s: {e.code().name}")
                break
            print(f"{t} @{win}s: {n}")
            if n:
                arm = sample.WhichOneof("value") if sample else None
                print(f"   sample id={sample.id!r} arm={arm} bytes={sample.ByteSize()}")
                break


if __name__ == "__main__":
    main()
