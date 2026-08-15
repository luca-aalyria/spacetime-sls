#!/usr/bin/env python3
"""Dump a live Spacetime Store (via port-forward, see sandbox_live_setup.sh) to local
textproto files, split into greppable groups:

  <out>/intents/<oneof-arm>.txtpb           e.g. link.txtpb, modem.txtpb, route.txtpb
  <out>/nmts/entities_<ek-kind>.txtpb       e.g. entities_ek_platform.txtpb
  <out>/nmts/relationships_<rk-kind>.txtpb  e.g. relationships_rk_contains.txtpb
  <out>/manifest.json                       counts + instance + snapshot time

Each .txtpb is a `minkowski.proto.TxtpbEntities` holding the FULL storage Entity wrappers
(id, commit_timestamp, value oneof), so dumps stay round-trippable with `storectl import`
and diffable against later snapshots.

Default output: /workspace/<instance>-dump (e.g. /workspace/fss01-demo-dump). Re-running
overwrites group files in place; the manifest records the snapshot time.

Usage:
  .venv/bin/python tools/dump_live_store.py [--target localhost:9999] [--instance fss01-demo] [--out DIR]
"""
import argparse
import collections
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.protobuf import text_format

from ngso_sls.spacetime import _deps
from ngso_sls.spacetime.client import StorageEntityStore


def _write_group(path, entities):
    """Write storage Entity wrappers as one TxtpbEntities textproto."""
    box = _deps.storage_pb2.TxtpbEntities()
    box.entity.extend(entities)
    with open(path, "w") as f:
        f.write(text_format.MessageToString(box))
    return os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="localhost:9999")
    ap.add_argument("--out", default=None, help="output dir (default: /workspace/<instance>-dump)")
    ap.add_argument("--instance", default="fss01-demo",
                    help="instance short name; names the default output dir and the manifest")
    args = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    out = args.out or f"/workspace/{args.instance}-dump"
    os.makedirs(os.path.join(out, "intents"), exist_ok=True)
    os.makedirs(os.path.join(out, "nmts"), exist_ok=True)

    manifest = {"instance": args.instance, "target": args.target,
                "snapshot_utc": now.isoformat(), "groups": {}}

    with StorageEntityStore(args.target) as store:
        # Intents, split by the Intent.value oneof arm (link / modem / route / cell / ...).
        by_arm = collections.defaultdict(list)
        for e in store._get_entities("INTENT"):
            arm = e.intent.WhichOneof("value") if e.HasField("intent") else None
            by_arm[arm or "unset"].append(e)
        for arm, ents in sorted(by_arm.items()):
            p = os.path.join(out, "intents", f"{arm}.txtpb")
            size = _write_group(p, ents)
            manifest["groups"][f"intents/{arm}"] = {"count": len(ents), "bytes": size}
            print(f"intents/{arm}: {len(ents)} ({size/1e6:.1f} MB)")

        # NMTS entities, split by the nmts.v1.Entity kind arm (ek_platform / ek_antenna / ...).
        by_kind = collections.defaultdict(list)
        for e in store._get_entities("NMTS_ENTITY"):
            kind = e.nmts_entity.WhichOneof("kind") if e.HasField("nmts_entity") else None
            by_kind[kind or "unset"].append(e)
        for kind, ents in sorted(by_kind.items()):
            p = os.path.join(out, "nmts", f"entities_{kind}.txtpb")
            size = _write_group(p, ents)
            manifest["groups"][f"nmts/entities_{kind}"] = {"count": len(ents), "bytes": size}
            print(f"nmts/entities_{kind}: {len(ents)} ({size/1e6:.1f} MB)")

        # NMTS relationships, split by the RK enum value.
        rk_name = _deps.nmts_pb2.RK.Name if _deps.HAS_NMTS else (lambda v: f"rk_{v}")
        by_rk = collections.defaultdict(list)
        for e in store._get_entities("NMTS_RELATIONSHIP"):
            rk = rk_name(e.nmts_relationship.kind).lower() if e.HasField("nmts_relationship") else "unset"
            by_rk[rk].append(e)
        for rk, ents in sorted(by_rk.items()):
            p = os.path.join(out, "nmts", f"relationships_{rk}.txtpb")
            size = _write_group(p, ents)
            manifest["groups"][f"nmts/relationships_{rk}"] = {"count": len(ents), "bytes": size}
            print(f"nmts/relationships_{rk}: {len(ents)} ({size/1e6:.1f} MB)")

    manifest["totals"] = {
        "intents": sum(v["count"] for k, v in manifest["groups"].items() if k.startswith("intents/")),
        "nmts_entities": sum(v["count"] for k, v in manifest["groups"].items()
                             if k.startswith("nmts/entities_")),
        "nmts_relationships": sum(v["count"] for k, v in manifest["groups"].items()
                                  if k.startswith("nmts/relationships_")),
        "bytes": sum(v["bytes"] for v in manifest["groups"].values()),
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    t = manifest["totals"]
    print(f"\n{out}\n{t['intents']} intents, {t['nmts_entities']} entities, "
          f"{t['nmts_relationships']} relationships, {t['bytes']/1e6:.1f} MB total")


if __name__ == "__main__":
    main()
