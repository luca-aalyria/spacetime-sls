"""GUARDED write path for EPHEMERAL spacebox instances only.

Policy (slice-de-ephemeral-instances.md, owner-approved for spacebox scenario testing):
the SLS never mutates shared/demo instances. This writer refuses to construct unless the
caller passes the ephemeral acknowledgement, and it is meant to be pointed ONLY at a
port-forward into a spacebox namespace you created. Everything else in the package stays
read-only.
"""
import numpy as np

from . import _deps
from .store import StoreError


class EphemeralStoreWriter:
    """Writes NMTS entities into an ephemeral instance's Store (Store.Write, one
    RowMutation per call). Deliberately minimal: platforms (Keplerian) now; antennas /
    UTs / carriers arrive with the full scenario template."""

    def __init__(self, target, *, i_am_writing_to_an_ephemeral_spacebox_instance=False):
        if not i_am_writing_to_an_ephemeral_spacebox_instance:
            raise StoreError.rpc(
                "write path refused: pass i_am_writing_to_an_ephemeral_spacebox_instance="
                "True and point target ONLY at a spacebox namespace you created "
                "(policy: slice-de-ephemeral-instances.md)")
        _deps.require("HAS_STORAGE", "proto_internal.storage (vendored stubs)")
        self._pb = _deps.storage_pb2
        self._channel = _deps.grpc.insecure_channel(
            target, options=[("grpc.max_receive_message_length", 256 << 20)])
        self._store = _deps.storage_pb2_grpc.StoreStub(self._channel)

    def close(self):
        self._channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _write(self, entity, mutation="INSERT"):
        pb = self._pb
        req = pb.WriteRequest()
        m = req.row_mutation.add()                        # repeated RowMutation
        m.mutation_type = (pb.RowMutation.DESCRIPTOR.fields_by_name["mutation_type"]
                           .enum_type.values_by_name[mutation].number)
        m.entity.CopyFrom(entity)
        req.ignore_consistency_check = True       # ephemeral scratch instance: no OCC
        try:
            resp = self._store.Write(req, timeout=30)
        except Exception as e:
            raise StoreError.rpc(f"Store.Write({entity.id}) failed: {type(e).__name__}")
        if not resp.committed:                    # e.g. INSERT of an existing id
            raise StoreError.rpc(f"Store.Write({entity.id}): not committed "
                                 f"(INSERT of existing id, or precondition failed)")

    def write_constellation(self, elems, sat_ids=None, name_prefix="jio", epoch_s=None,
                            category_tag="LEO"):
        """Write (n,6) Keplerian elements [a_km, e, inc_rad, raan_rad, argp_rad, M_rad]
        as ek_platform entities (true anomaly approximated by M for near-circular
        orbits). Returns the written entity ids."""
        import time as _time
        pb = self._pb
        elems = np.asarray(elems, dtype=float)
        epoch = int(epoch_s if epoch_s is not None else _time.time())
        ids = []
        for i, row in enumerate(elems):
            sid = sat_ids[i] if sat_ids else f"{name_prefix}-sat-{i + 1}-platform"
            e = pb.Entity()
            e.group.type = pb.EntityType.Value("NMTS_ENTITY")
            e.id = sid
            ne = e.nmts_entity
            ne.id = sid
            p = ne.ek_platform
            p.name = f"{name_prefix}-sat-{i + 1}"
            p.category_tag = category_tag
            kep = p.motion.entry.add().keplerian_elements
            kep.semimajor_axis_m = float(row[0]) * 1000.0
            kep.eccentricity = float(row[1])
            kep.inclination_deg = float(np.degrees(row[2]))
            kep.raan_deg = float(np.degrees(row[3]))
            kep.argument_of_periapsis_deg = float(np.degrees(row[4]))
            kep.true_anomaly_deg = float(np.degrees(row[5]))   # ~M for e≈0
            kep.epoch.seconds = epoch
            self._write(e)
            ids.append(sid)
        return ids

    def delete_ids(self, ids):
        """Unload: delete previously-written NMTS entities by id."""
        pb = self._pb
        for sid in ids:
            e = pb.Entity()
            e.group.type = pb.EntityType.Value("NMTS_ENTITY")
            e.id = sid
            self._write(e, mutation="DELETE")
