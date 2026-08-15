"""Duck-typed field access so the adapter runs identically on real protobuf messages AND on
plain JSON dicts (fixtures). Never import proto here."""


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _epoch_s(kep) -> float:
    """Seconds-since-epoch of a KeplerianElements' `epoch` (proto Timestamp or JSON {seconds})."""
    ep = _get(kep, "epoch")
    return float(_get(ep, "seconds", 0.0) or 0.0)


def _motion_entries(platform):
    """The list of MotionDescription entries for a platform (Motion.entry is REPEATED)."""
    motion = _get(platform, "motion")
    return list(_get(motion, "entry", []) or [])


def _kepler(entry):
    """The KeplerianElements of a MotionDescription entry, or None if this entry is not
    Keplerian. On real protos the motion arms live in a oneof and reading an unset message
    field returns a DEFAULT INSTANCE (never None) — e.g. a gateway's geodetic entry would
    read back as all-zero Keplerian elements — so the set arm must be checked explicitly."""
    if hasattr(entry, "DESCRIPTOR") and hasattr(entry, "WhichOneof"):
        f = entry.DESCRIPTOR.fields_by_name.get("keplerian_elements")
        if f is None:
            return None
        if f.containing_oneof is not None and \
                entry.WhichOneof(f.containing_oneof.name) != "keplerian_elements":
            return None
    return _get(entry, "keplerian_elements")


def _is_external(platform) -> bool:
    """Whether a platform is an external-system (interferer) platform. In the real NMTS proto
    `is_external_system` is a MESSAGE field (an empty message is truthy in python-protobuf!),
    so presence must be checked with HasField; JSON fixtures carry a plain bool."""
    if hasattr(platform, "HasField"):
        try:
            return platform.HasField("is_external_system")
        except Exception:                # field not in this schema variant
            return False
    return bool(_get(platform, "is_external_system", False))
