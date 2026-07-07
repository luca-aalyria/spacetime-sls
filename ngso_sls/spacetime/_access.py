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
    """The KeplerianElements of a MotionDescription entry, or None if this entry is not Keplerian."""
    return _get(entry, "keplerian_elements")
