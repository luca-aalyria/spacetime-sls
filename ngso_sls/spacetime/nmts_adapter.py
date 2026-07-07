"""Translate pulled NMTS entities/relationships into the canonical (n_sat,6) element array the
Slice-A engine consumes, plus reporting metadata. Pure Python (numpy only) — reads proto/JSON
fields via duck-typed accessors so it is unit-tested with no proto dependency.

Increment-1 supports KEPLERIAN motion. TLE / state-vector / ephemeris motion is flagged and
skipped (a real Sgp4Propagator/EphemerisInterpolator is a deferred follow-up)."""
import numpy as np
from ..constants import MU_EARTH, RE_EQ
from ..constellation.model import _physical_plane_uid
from ._access import _get, _epoch_s, _motion_entries, _kepler

EK_PLATFORM = 11
EK_ANTENNA = 40
RK_CONTAINS = 4                      # compared as an int, never a proto enum


def _true_to_mean(nu_rad: float, e: float) -> float:
    E = 2.0 * np.arctan2(np.sqrt(1 - e) * np.sin(nu_rad / 2),
                         np.sqrt(1 + e) * np.cos(nu_rad / 2))
    return (E - e * np.sin(E)) % (2 * np.pi)


def _antenna_ids_for(platform_id: str, relationships) -> list:
    return [_get(r, "z") for r in relationships
            if int(_get(r, "kind", -1)) == RK_CONTAINS and _get(r, "a") == platform_id]


def platforms_to_elements(entities, relationships, *, ref_epoch_s: float | None = None,
                          include_external: bool = False) -> dict:
    """Returns {elems (n,6), plane_uid (n,), meta [dict], skipped [dict], ref_epoch_s,
    antennas [dict]}. External-system platforms are excluded unless include_external."""
    platforms = [e for e in entities if int(_get(e, "kind", -1)) == EK_PLATFORM]
    antennas = [e for e in entities if int(_get(e, "kind", -1)) == EK_ANTENNA]

    # collect Keplerian rows first (to pick a reference epoch), skip/flag the rest
    rows, meta, skipped = [], [], []
    for e in platforms:
        pid = _get(e, "id")
        plat = _get(e, "platform")
        is_ext = bool(_get(plat, "is_external_system", False))
        entries = _motion_entries(plat)
        kep = _kepler(entries[0]) if entries else None       # Increment-1: first entry
        if kep is None:
            skipped.append({"sat_id": pid, "reason": "non-Keplerian motion (TLE/ephemeris) "
                                                      "not supported in Increment-1"})
            continue
        if is_ext and not include_external:
            skipped.append({"sat_id": pid, "reason": "external-system platform (interferer)"})
            continue
        rows.append((pid, e, plat, kep))

    if not rows:
        return {"elems": np.empty((0, 6)), "plane_uid": np.empty((0,), dtype=np.int64),
                "meta": [], "skipped": skipped, "ref_epoch_s": ref_epoch_s or 0.0,
                "antennas": [_antenna_meta(a) for a in antennas]}

    epochs = [_epoch_s(kep) for (_pid, _e, _plat, kep) in rows]
    t_ref = float(ref_epoch_s) if ref_epoch_s is not None else float(min(epochs))

    elems = np.empty((len(rows), 6))
    for i, (pid, e, plat, kep) in enumerate(rows):
        a_km = float(_get(kep, "semimajor_axis_m")) / 1000.0
        ecc = float(_get(kep, "eccentricity", 0.0))
        inc = np.radians(float(_get(kep, "inclination_deg")))
        raan = np.radians(float(_get(kep, "raan_deg")))
        argp = np.radians(float(_get(kep, "argument_of_periapsis_deg", 0.0)))
        M = _true_to_mean(np.radians(float(_get(kep, "true_anomaly_deg"))), ecc)
        # epoch reconciliation to the common reference epoch (two-body mean-motion advance).
        # A satellite whose epoch is dt AFTER t_ref has advanced by n0*dt from its t_ref state,
        # so its mean anomaly at t_ref = M_raw - n0*(t_epoch - t_ref) = M_raw + n0*(t_ref - t_epoch).
        # Equivalently: M(t_ref) = M_epoch + n0*(t_epoch - t_ref) where M_epoch is M at t_epoch.
        # The sign here reconciles mean anomaly FORWARD from the element epoch to t_ref.
        n0 = np.sqrt(MU_EARTH / a_km ** 3)
        t_epoch = _epoch_s(kep)
        M = (M + n0 * (t_epoch - t_ref)) % (2 * np.pi)
        elems[i] = [a_km, ecc, inc, raan, argp, M]
        meta.append({"sat_id": pid, "name": _get(plat, "name"),
                     "epoch_utc_s": t_ref, "motion_kind": "keplerian",
                     "antenna_ids": _antenna_ids_for(pid, relationships),
                     "is_external_system": bool(_get(plat, "is_external_system", False))})

    return {"elems": elems, "plane_uid": _physical_plane_uid(elems), "meta": meta,
            "skipped": skipped, "ref_epoch_s": t_ref,
            "antennas": [_antenna_meta(a) for a in antennas]}


def _antenna_meta(a) -> dict:
    an = _get(a, "antenna")
    return {"antenna_id": _get(a, "id"), "type": _get(an, "type"),
            "is_steerable": _get(an, "is_steerable"),
            "max_transmit_power_w": _get(an, "max_transmit_power_w"),
            "g_over_t_db_per_k": _get(an, "g_over_t_db_per_k")}


def routes_from_intents(intents) -> list:
    """Flatten installed PathIntents to a list of hops {src, dst, src_if, dst_if} (the live
    'computed coverage' reference to compare against predicted access)."""
    hops = []
    for i in intents:
        route = _get(i, "route")
        for seg in (_get(route, "path_segments", []) or []):
            hops.append({"src": _get(seg, "src_network_node_id"),
                         "dst": _get(seg, "dst_network_node_id"),
                         "src_if": _get(seg, "src_interface_id"),
                         "dst_if": _get(seg, "dst_interface_id")})
    return hops
