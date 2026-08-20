#!/usr/bin/env python3
"""Build a constellation variant from the fss01-demo NMTS dump.

The tool clones fss01's per-satellite and per-user-terminal subtrees into a
new shape and keeps gateways, PoPs and their gear unchanged. v1 drops the
OISL mesh: its neighbor wiring belongs to fss01's 10x15 grid, and the India
use case routes traffic through feeder links.

Inputs:  output/fss01-demo-dump/nmts/*.txtpb (+ provisioning sample)
Output:  a list of storage-entity text blocks, imported into a target store.

Shape parameters sit in the CONSTANTS block below. Satellite i (1-based)
maps to plane p = (i-1)//SATS_PER_PLANE, slot s = (i-1)%SATS_PER_PLANE.
"""
import glob
import re
import sys
import time
import uuid

sys.path.insert(0, "/workspace/spacetime-sls")
sys.path.insert(0, "/workspace/spacetime-sls/vendor/spacetime_api_stubs")
sys.path.insert(0, "/workspace/spacetime-sls/scenarios/pybuilder-jio")

from google.protobuf import text_format          # noqa: E402
from india_cells import INDIA_RES3_CENTERS       # noqa: E402
from ngso_sls.spacetime import _deps             # noqa: E402
from ngso_sls.spacetime.writer import EphemeralStoreWriter  # noqa: E402

DUMP = "/workspace/spacetime-sls/output/fss01-demo-dump"
TARGET = "localhost:9996"

N_PLANES, SATS_PER_PLANE = 20, 10                # Walker 200/20/1
N_SATS = N_PLANES * SATS_PER_PLANE
SEMIMAJOR_AXIS_M = 6_378_137 + 650_000
INCLINATION_DEG = 48.0
PHASING_F = 1
EPOCH_SECONDS = 1_787_011_200                    # 2026-08-18T00:00:00Z
N_UTS = len(INDIA_RES3_CENTERS)                  # 251 India H3 res-3 cells
POP_ROUTE_FN = "pop-asia-pop-1-route-fn"
CIR_BPS = 2_000_000

pb = _deps.storage_pb2


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


def block_id(text):
    m = re.search(r'^  id: "([^"]+)"', text, re.M)
    return m.group(1) if m else ""


def rel_endpoints(text):
    a = re.search(r'a: "([^"]+)"', text)
    z = re.search(r'z: "([^"]+)"', text)
    return (a.group(1) if a else "", z.group(1) if z else "")


SAT_RE = re.compile(r"^satellite-\d+-")
UT_RE = re.compile(r"^user-terminal-\d+-")


def owned(eid):
    """The clone family an id belongs to: 'sat', 'ut', or None (global)."""
    if "oisl" in eid or "-to-satellite-" in eid:
        return "drop"
    if SAT_RE.match(eid):
        return "sat"
    if UT_RE.match(eid):
        return "ut"
    return None


def patch_platform(text, patch_fn):
    """Parse a storage-entity block, let patch_fn edit it, re-serialize."""
    e = pb.Entity()
    text_format.Parse(text, e)
    e.ClearField("commit_timestamp")
    e.ClearField("last_modified_by")
    patch_fn(e)
    return text_format.MessageToString(e, indent=2)


def main():
    ent_blocks, rel_blocks = [], []
    for f in sorted(glob.glob(f"{DUMP}/nmts/entities_*.txtpb")):
        ent_blocks += list(iter_blocks(f))
    for f in sorted(glob.glob(f"{DUMP}/nmts/relationships_*.txtpb")):
        rel_blocks += list(iter_blocks(f))

    out = []
    sat_tpl, ut_tpl = [], []
    for b in ent_blocks:
        fam = owned(block_id(b))
        if fam is None:
            out.append(b)
        elif fam == "sat" and block_id(b).startswith("satellite-1-"):
            sat_tpl.append(b)
        elif fam == "ut" and block_id(b).startswith("user-terminal-1-"):
            ut_tpl.append(b)
    sat_rel_tpl, ut_rel_tpl, kept_rels = [], [], []
    for b in rel_blocks:
        a, z = rel_endpoints(b)
        fa, fz = owned(a), owned(z)
        if fa is None and fz is None:
            kept_rels.append(b)
        elif (fa == fz == "sat" and a.startswith("satellite-1-")
              and z.startswith("satellite-1-")):
            sat_rel_tpl.append(b)
        elif (fa == fz == "ut" and a.startswith("user-terminal-1-")
              and z.startswith("user-terminal-1-")):
            ut_rel_tpl.append(b)
    print(f"global entities kept: {len(out)}, sat template: {len(sat_tpl)} "
          f"(+{len(sat_rel_tpl)} rels), ut template: {len(ut_tpl)} "
          f"(+{len(ut_rel_tpl)} rels), global rels: {len(kept_rels)}")

    grid_re = re.compile(r"1200\.1\.1(?!\d)")
    new_rels = list(kept_rels)
    for i in range(1, N_SATS + 1):
        p, s = (i - 1) // SATS_PER_PLANE, (i - 1) % SATS_PER_PLANE
        raan = p * (360.0 / N_PLANES)
        ta = (s * (360.0 / SATS_PER_PLANE)
              + p * PHASING_F * (360.0 / N_SATS)) % 360.0

        def sub(t):
            return grid_re.sub(f"1200.{p + 1}.{s + 1}",
                               t.replace("satellite-1-", f"satellite-{i}-"))

        for t in sat_tpl:
            t2 = sub(t)
            if block_id(t2) == f"satellite-{i}-platform":
                def patch(e, raan=raan, ta=ta, i=i, p=p, s=s):
                    kep = (e.nmts_entity.ek_platform.motion.entry[0]
                           .keplerian_elements)
                    kep.semimajor_axis_m = SEMIMAJOR_AXIS_M
                    kep.eccentricity = 0.0
                    kep.inclination_deg = INCLINATION_DEG
                    kep.raan_deg = raan
                    kep.argument_of_periapsis_deg = 0.0
                    kep.true_anomaly_deg = ta
                    kep.epoch.seconds = EPOCH_SECONDS
                    kep.epoch.nanos = 0
                    e.nmts_entity.ek_platform.name = f"SAT-{i} ({p + 1}.{s + 1})"
                t2 = patch_platform(t2, patch)
            out.append(t2)
        for t in sat_rel_tpl:
            new_rels.append(sub(t))

    for j in range(1, N_UTS + 1):
        lat, lon = INDIA_RES3_CENTERS[j - 1]

        def sub(t):
            return (t.replace("user-terminal-1-", f"user-terminal-{j}-")
                    .replace('"UT 1"', f'"UT {j}"'))

        for t in ut_tpl:
            t2 = sub(t)
            if block_id(t2) == f"user-terminal-{j}-platform":
                def patch(e, lat=lat, lon=lon, j=j):
                    geo = (e.nmts_entity.ek_platform.motion.entry[0]
                           .geodetic_wgs84)
                    geo.latitude_deg = lat
                    geo.longitude_deg = lon
                    geo.height_wgs84_m = 0.0
                    e.nmts_entity.ek_platform.name = f"UT-{j}"
                t2 = patch_platform(t2, patch)
            out.append(t2)
        for t in ut_rel_tpl:
            new_rels.append(sub(t))

    prov = []
    for j in range(1, N_UTS + 1):
        for head, end in ((POP_ROUTE_FN, f"user-terminal-{j}-route-fn"),
                          (f"user-terminal-{j}-route-fn", POP_ROUTE_FN)):
            sym = f"{head}--1--{end}"
            pid = f"p2pSrTePolicies/{uuid.uuid5(uuid.NAMESPACE_URL, sym)}"
            e = pb.Entity()
            e.group.type = pb.EntityType.Value(
                "PROVISIONING_REQUEST_P2P_SR_TE_POLICY")
            e.group.app_id = "provisioningfe"
            e.id = pid
            r = e.provisioning_request_p2p_sr_te_policy_resource
            r.p2p_sr_te_policy.name = pid
            r.p2p_sr_te_policy.headend = head
            r.p2p_sr_te_policy.color = 1
            r.p2p_sr_te_policy.endpoint = end
            r.p2p_sr_te_policy.symbolic_name = sym
            cp = r.p2p_sr_te_policy_candidate_paths.add()
            cp.name = f"{pid}/candidatePaths/1"
            cp.discriminator = 1
            cp.symbolic_name = "primary"
            cp.metrics.cir_bps = CIR_BPS
            prov.append(e)
    print(f"built: {len(out)} entities, {len(new_rels)} relationships, "
          f"{len(prov)} provisioning requests")

    w = EphemeralStoreWriter(TARGET,
                             i_am_writing_to_an_ephemeral_spacebox_instance=True)
    INS = (pb.RowMutation.DESCRIPTOR.fields_by_name["mutation_type"]
           .enum_type.values_by_name["INSERT"].number)
    total, t0 = 0, time.time()

    def flush(entities):
        nonlocal total, w
        req = pb.WriteRequest()
        req.ignore_consistency_check = True
        for e in entities:
            m = req.row_mutation.add()
            m.mutation_type = INS
            m.entity.CopyFrom(e)
        for attempt in range(10):
            try:
                w._store.Write(req, timeout=180)
                total += len(entities)
                return
            except Exception as ex:
                print(f"write err ({attempt}): {str(ex)[:70]}", flush=True)
                time.sleep(15)
                try:
                    w.close()
                except Exception:
                    pass
                w = EphemeralStoreWriter(
                    TARGET, i_am_writing_to_an_ephemeral_spacebox_instance=True)
        raise RuntimeError("write failed after 10 attempts")

    batch = []
    for text in out + new_rels:
        e = pb.Entity()
        text_format.Parse(text, e)
        e.ClearField("commit_timestamp")
        e.ClearField("last_modified_by")
        batch.append(e)
        if len(batch) >= 400:
            flush(batch)
            batch = []
    if batch:
        flush(batch)
    for i in range(0, len(prov), 400):
        flush(prov[i:i + 400])
    print(f"IMPORT DONE: {total} rows in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
