"""NMTS model generation from the fss01 template.

The generator clones fss01-demo's per-satellite and per-user-terminal
subtrees into a caller-supplied constellation shape. Gateways, PoPs and
their gear pass through unchanged. The OISL mesh is dropped: its neighbor
wiring belongs to fss01's own grid, and feeder routing serves the regional
use cases.

The template is the fss01 NMTS dump directory (`entities_*.txtpb` +
`relationships_*.txtpb`). The dump is local data, so this module works only
where the dump is present (not in Colab).
"""

import glob
import re
import uuid

import numpy as np

from . import _deps

TEMPLATE_DIR = "/workspace/spacetime-sls/output/fss01-demo-dump"
CIR_BPS = 2_000_000
_SAT_RE = re.compile(r"^satellite-\d+-")
_UT_RE = re.compile(r"^user-terminal-\d+-")
_GRID_RE = re.compile(r"1200\.1\.1(?!\d)")


def _iter_blocks(path):
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


def _block_id(text):
    m = re.search(r'^  id: "([^"]+)"', text, re.M)
    return m.group(1) if m else ""


def _rel_endpoints(text):
    a = re.search(r'a: "([^"]+)"', text)
    z = re.search(r'z: "([^"]+)"', text)
    return (a.group(1) if a else "", z.group(1) if z else "")


def _family(eid):
    if "oisl" in eid or "-to-satellite-" in eid:
        return "drop"
    if _SAT_RE.match(eid):
        return "sat"
    if _UT_RE.match(eid):
        return "ut"
    return None


def _patch_entity(text, patch_fn):
    from google.protobuf import text_format
    pb = _deps.storage_pb2
    e = pb.Entity()
    text_format.Parse(text, e)
    e.ClearField("commit_timestamp")
    e.ClearField("last_modified_by")
    patch_fn(e)
    return text_format.MessageToString(e, indent=2)


def build_model(elems, plane_uid, ut_cells, ref_epoch_s,
                template_dir=TEMPLATE_DIR, pop_route_fn="pop-asia-pop-1-route-fn"):
    """Returns (entity_blocks, relationship_blocks, provisioning_entities).

    `elems` is the (n,6) element array [a_km, e, inc_rad, raan_rad, argp_rad,
    M_rad]; `ut_cells` is a list of (lat_deg, lon_deg) user-terminal sites;
    `ref_epoch_s` is the unix epoch the elements refer to."""
    pb = _deps.storage_pb2
    ents, rels = [], []
    for f in sorted(glob.glob(f"{template_dir}/nmts/entities_*.txtpb")):
        ents += list(_iter_blocks(f))
    for f in sorted(glob.glob(f"{template_dir}/nmts/relationships_*.txtpb")):
        rels += list(_iter_blocks(f))
    if not ents:
        raise FileNotFoundError(f"no template dump under {template_dir}")

    out, sat_tpl, ut_tpl = [], [], []
    for b in ents:
        fam = _family(_block_id(b))
        if fam is None:
            out.append(b)
        elif fam == "sat" and _block_id(b).startswith("satellite-1-"):
            sat_tpl.append(b)
        elif fam == "ut" and _block_id(b).startswith("user-terminal-1-"):
            ut_tpl.append(b)
    out_rels, sat_rtpl, ut_rtpl = [], [], []
    for b in rels:
        a, z = _rel_endpoints(b)
        fa, fz = _family(a), _family(z)
        if fa is None and fz is None:
            out_rels.append(b)
        elif (fa == fz == "sat" and a.startswith("satellite-1-")
              and z.startswith("satellite-1-")):
            sat_rtpl.append(b)
        elif (fa == fz == "ut" and a.startswith("user-terminal-1-")
              and z.startswith("user-terminal-1-")):
            ut_rtpl.append(b)

    n = int(np.asarray(elems).shape[0])
    planes = {p: k for k, p in enumerate(sorted(set(int(x) for x in plane_uid)))}
    slot_count = {}
    for i in range(1, n + 1):
        row = np.asarray(elems)[i - 1]
        p = planes[int(plane_uid[i - 1])]
        s = slot_count[p] = slot_count.get(p, 0) + 1

        def sub(t, i=i, p=p, s=s):
            return _GRID_RE.sub(f"1200.{p + 1}.{s}",
                                t.replace("satellite-1-", f"satellite-{i}-"))

        for t in sat_tpl:
            t2 = sub(t)
            if _block_id(t2) == f"satellite-{i}-platform":
                def patch(e, row=row, i=i, p=p, s=s):
                    kep = (e.nmts_entity.ek_platform.motion.entry[0]
                           .keplerian_elements)
                    kep.semimajor_axis_m = float(row[0]) * 1000.0
                    kep.eccentricity = float(row[1])
                    kep.inclination_deg = float(np.degrees(row[2]))
                    kep.raan_deg = float(np.degrees(row[3])) % 360.0
                    kep.argument_of_periapsis_deg = float(np.degrees(row[4])) % 360.0
                    kep.true_anomaly_deg = float(np.degrees(row[5])) % 360.0
                    kep.epoch.seconds = int(ref_epoch_s)
                    kep.epoch.nanos = 0
                    e.nmts_entity.ek_platform.name = f"SAT-{i} ({p + 1}.{s})"
                t2 = _patch_entity(t2, patch)
            out.append(t2)
        for t in sat_rtpl:
            out_rels.append(sub(t))

    for j, (lat, lon) in enumerate(ut_cells, start=1):
        def sub(t, j=j):
            return (t.replace("user-terminal-1-", f"user-terminal-{j}-")
                    .replace('"UT 1"', f'"UT {j}"'))

        for t in ut_tpl:
            t2 = sub(t)
            if _block_id(t2) == f"user-terminal-{j}-platform":
                def patch(e, lat=lat, lon=lon, j=j):
                    geo = (e.nmts_entity.ek_platform.motion.entry[0]
                           .geodetic_wgs84)
                    geo.latitude_deg = float(lat)
                    geo.longitude_deg = float(lon)
                    geo.height_wgs84_m = 0.0
                    e.nmts_entity.ek_platform.name = f"UT-{j}"
                t2 = _patch_entity(t2, patch)
            out.append(t2)
        for t in ut_rtpl:
            out_rels.append(sub(t))

    prov = []
    for j in range(1, len(ut_cells) + 1):
        for head, end in ((pop_route_fn, f"user-terminal-{j}-route-fn"),
                          (f"user-terminal-{j}-route-fn", pop_route_fn)):
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
    return out, out_rels, prov


def push_model(target, entity_blocks, relationship_blocks, provisioning,
               wipe_first=True, progress=None):
    """Imports a generated model into an ephemeral instance store.

    The writer refuses protected targets (see writer.PROTECTED_TARGETS).
    With `wipe_first`, the current NMTS/provisioning/derived rows are deleted
    before the import so the instance serves exactly one model."""
    import time
    from google.protobuf import text_format
    from .writer import EphemeralStoreWriter
    from .client import StorageEntityStore
    pb = _deps.storage_pb2

    w = EphemeralStoreWriter(target,
                             i_am_writing_to_an_ephemeral_spacebox_instance=True)
    ins = (pb.RowMutation.DESCRIPTOR.fields_by_name["mutation_type"]
           .enum_type.values_by_name["INSERT"].number)
    dele = (pb.RowMutation.DESCRIPTOR.fields_by_name["mutation_type"]
            .enum_type.values_by_name["DELETE"].number)

    def say(msg):
        if progress:
            progress(msg)

    if wipe_first:
        wipe_types = ["NMTS_ENTITY", "NMTS_RELATIONSHIP",
                      "PROVISIONING_REQUEST_P2P_SR_TE_POLICY",
                      "BEAM_CANDIDATE_SEGMENT", "NMTS_POINT_TO_POINT_LINK_REPORT",
                      "PROPAGATION_VECTOR_SEGMENT", "INTENT", "SCHEDULE",
                      "ALLOCATED_DATA_RATE", "TRANSMIT_SIGNAL_CHAIN",
                      "RECEIVE_SIGNAL_CHAIN"]
        with StorageEntityStore(target) as s:
            for t in wipe_types:
                try:
                    ids = [e.id for e in s._get_entities(t)]
                except Exception:
                    continue
                for i in range(0, len(ids), 400):
                    req = pb.WriteRequest()
                    req.ignore_consistency_check = True
                    for sid in ids[i:i + 400]:
                        m = req.row_mutation.add()
                        m.mutation_type = dele
                        m.entity.group.type = pb.EntityType.Value(t)
                        m.entity.id = sid
                    w._store.Write(req, timeout=180)
                if ids:
                    say(f"wiped {t}: {len(ids)}")

    total, t0 = 0, time.time()
    batch = []

    def flush():
        nonlocal total
        if not batch:
            return
        req = pb.WriteRequest()
        req.ignore_consistency_check = True
        for e in batch:
            m = req.row_mutation.add()
            m.mutation_type = ins
            m.entity.CopyFrom(e)
        for attempt in range(6):
            try:
                w._store.Write(req, timeout=180)
                total += len(batch)
                return
            except Exception:
                time.sleep(10)
        raise RuntimeError("Store.Write failed after 6 attempts")

    for text in list(entity_blocks) + list(relationship_blocks):
        e = pb.Entity()
        text_format.Parse(text, e)
        e.ClearField("commit_timestamp")
        e.ClearField("last_modified_by")
        batch.append(e)
        if len(batch) >= 400:
            flush()
            batch.clear()
    flush()
    batch.clear()
    for e in provisioning:
        batch.append(e)
        if len(batch) >= 400:
            flush()
            batch.clear()
    flush()
    say(f"imported {total} rows in {time.time() - t0:.0f}s")
    w.close()
    return total
