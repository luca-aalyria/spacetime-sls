#!/usr/bin/env python3
"""Listen-based one-quantum sampler for transient Store datasets.

Why: GetEntities interval/diff windows select on COMMIT time (when rows were written,
not the forecast time they describe); an end_time at/after the commit watermark BLOCKS
until real time passes it, and the reply carries last-version-before-start for every
entity — so 'now'-anchored windows hang on big datasets. Listen is the intended reader: it streams a chunked dump of current state, a
dump_complete delimiter, then live mutations. We count the dump as it streams (dataset
size for free), then collect live mutations for ~one solver quantum, then disconnect.

Usage:
  .venv/bin/python tools/quantum_sampler.py [--target localhost:9999] [--window 12]
      [--types BEAM_CANDIDATE_SEGMENT,PROPAGATION_VECTOR_SEGMENT,SCHEDULE]
      [--dump-timeout 300] [--id-prefix <begin>]      # ranges slice, optional
"""
import argparse
import collections
import sys
import time

sys.path.insert(0, "/workspace/spacetime-sls/vendor/spacetime_api_stubs")
import grpc
from proto_internal.storage import storage_pb2 as pb, storage_pb2_grpc as pg

DEFAULT_TYPES = "BEAM_CANDIDATE_SEGMENT,PROPAGATION_VECTOR_SEGMENT,SCHEDULE"


def sample(stub, type_name, window_s, dump_timeout_s, id_prefix=None):
    req = pb.ListenRequest()
    req.group.add().type = pb.EntityType.Value(type_name)   # repeated: one group per type
    if id_prefix:
        rng = req.ranges.add()
        rng.type = req.group[0].type
        rng.begin = id_prefix
        rng.end = id_prefix + "\U0010ffff"
    stream = stub.Listen(req, timeout=dump_timeout_s + window_s + 30)

    dump_n = dump_bytes = 0
    first = None
    dump_done_at = None
    live = collections.Counter()          # mutation_type -> count
    live_n = live_bytes = 0
    live_ids = []
    t0 = time.monotonic()
    try:
        for chunk in stream:
            now = time.monotonic()
            if chunk.HasField("dump_complete"):
                dump_done_at = now
                continue
            for mut in chunk.updates.mutations:
                e = mut.entity
                if dump_done_at is None:
                    dump_n += 1
                    dump_bytes += e.ByteSize()
                    if first is None:
                        first = (e.id[:70], e.WhichOneof("value"), e.ByteSize())
                    if now - t0 > dump_timeout_s:
                        raise TimeoutError(f"dump still streaming after {dump_timeout_s}s "
                                           f"({dump_n} entities so far)")
                else:
                    live_n += 1
                    live_bytes += e.ByteSize()
                    live[mut.mutation_type] += 1
                    if len(live_ids) < 3:
                        live_ids.append(e.id[:70])
            if dump_done_at is not None and now - dump_done_at >= window_s:
                break
    finally:
        stream.cancel()                    # disconnect: sampling, not subscribing

    return {"dump_n": dump_n, "dump_mb": dump_bytes / 1e6,
            "dump_s": (dump_done_at - t0) if dump_done_at else None,
            "first": first, "live_n": live_n, "live_mb": live_bytes / 1e6,
            "live_ids": live_ids, "window_s": window_s,
            "mutations": dict(live)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="localhost:9999")
    ap.add_argument("--window", type=float, default=12.0, help="live-sample seconds (~quantum)")
    ap.add_argument("--types", default=DEFAULT_TYPES)
    ap.add_argument("--dump-timeout", type=float, default=300.0)
    ap.add_argument("--id-prefix", default=None)
    args = ap.parse_args()
    stub = pg.StoreStub(grpc.insecure_channel(
        args.target, options=[("grpc.max_receive_message_length", 512 << 20)]))

    for t in args.types.split(","):
        t = t.strip()
        try:
            r = sample(stub, t, args.window, args.dump_timeout, args.id_prefix)
        except (grpc.RpcError, TimeoutError) as e:
            code = e.code().name if isinstance(e, grpc.RpcError) else "TIMEOUT"
            print(f"{t}: FAILED {code}: {str(e)[:120]}")
            continue
        rate = r["live_n"] / r["window_s"]
        print(f"{t}: dump={r['dump_n']} entities ({r['dump_mb']:.1f} MB in "
              f"{r['dump_s']:.1f}s)" if r["dump_s"] is not None else
              f"{t}: dump={r['dump_n']} (no dump_complete seen)")
        if r["first"]:
            print(f"   sample: id={r['first'][0]!r} arm={r['first'][1]} bytes={r['first'][2]}")
        print(f"   live window {r['window_s']:.0f}s: {r['live_n']} mutations "
              f"({rate:.1f}/s, {r['live_mb']:.2f} MB) types={r['mutations']}")
        for i in r["live_ids"]:
            print(f"     live id: {i!r}")
        time.sleep(2)                      # pace between types


if __name__ == "__main__":
    main()
