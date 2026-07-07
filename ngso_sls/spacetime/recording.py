"""Record a store's read surface to a proto-free JSON projection, and replay it offline.

Only the fields the adapter consumes are projected (so replay needs NO proto). A separate
proto-native .pb format for Colab round-trip parity is out of scope for the offline default
(would be gated behind @pytest.mark.integration)."""
import json
from ._access import _get
from .memory_store import MemoryEntityStore


def _project_entity(e):
    kind = int(_get(e, "kind", -1))
    out = {"id": _get(e, "id"), "kind": kind}
    if kind == 11:                     # ek_platform: keep name/is_external + motion entries
        plat = _get(e, "platform")
        entries = []
        for en in (_get(_get(plat, "motion"), "entry", []) or []):
            kep = _get(en, "keplerian_elements")
            if kep is not None:
                entries.append({"keplerian_elements": {
                    k: _get(kep, k) for k in ("semimajor_axis_m", "eccentricity",
                    "inclination_deg", "raan_deg", "argument_of_periapsis_deg",
                    "true_anomaly_deg")} | {"epoch": {"seconds": int(
                        _get(_get(kep, "epoch"), "seconds", 0) or 0)}}})
            else:
                entries.append({"motion_kind": "non_keplerian"})   # flagged, not propagatable
        out["platform"] = {"name": _get(plat, "name"),
                           "is_external_system": bool(_get(plat, "is_external_system", False)),
                           "motion": {"entry": entries}}
    elif kind == 40:                   # ek_antenna
        an = _get(e, "antenna")
        out["antenna"] = {k: _get(an, k) for k in ("type", "is_steerable",
                          "max_transmit_power_w", "g_over_t_db_per_k")}
    return out


def _project_rel(r):
    return {"kind": int(_get(r, "kind", -1)), "a": _get(r, "a"), "z": _get(r, "z")}


def _project_intent(i):
    route = _get(i, "route")
    segs = [{"src_network_node_id": _get(s, "src_network_node_id"),
             "dst_network_node_id": _get(s, "dst_network_node_id"),
             "src_interface_id": _get(s, "src_interface_id"),
             "dst_interface_id": _get(s, "dst_interface_id")}
            for s in (_get(route, "path_segments", []) or [])]
    return {"id": _get(i, "id"), "state": _get(i, "state"), "route": {"path_segments": segs}}


def record(store, path: str, intent_states=None) -> None:
    """Serialize a store's read surface to a proto-free JSON snapshot at `path`."""
    data = {
        "entities": [_project_entity(e) for e in store.list_entities()],
        "relationships": [_project_rel(r) for r in store.list_relationships()],
        "intents": [_project_intent(i) for i in store.list_intents(states=intent_states)],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class RecordedEntityStore(MemoryEntityStore):
    """Replays a JSON snapshot produced by `record()` — identical read surface, offline."""
    def __init__(self, path: str):
        data = json.loads(open(path).read())
        super().__init__(data.get("entities"), data.get("relationships"), data.get("intents"))
