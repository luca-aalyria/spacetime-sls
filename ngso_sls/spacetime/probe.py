"""Staged first-contact diagnostic for a live Spacetime/Minkowski instance.

Exercises the read-only surface ONE RPC at a time with a clear PASS/FAIL per stage, so the first
contact with a real instance is debuggable: capability flags → build the authenticated channel →
proven intents pull → NMTS model (entities, platform motion, relationships). Each stage is
isolated (one failure never aborts the others) and credentials are never logged.

`probe_store` is store-agnostic and offline-testable against MemoryEntityStore/RecordedEntityStore;
`probe_endpoint` additionally builds the live GrpcEntityStore. Run as a CLI:

    SPACETIME_URL=https://<host>:443 SPACETIME_KEY_ID=... SPACETIME_USER_ID=... \\
    SPACETIME_PRIVATE_KEY_FILE=/path/key SPACETIME_MODEL_VERSION=v1 \\
    python -m ngso_sls.spacetime.probe
"""
from . import _deps
from ._access import _get, _motion_entries, _kepler
from .nmts_adapter import EK_PLATFORM, EK_ANTENNA, RK_CONTAINS

_FLAG_NAMES = ("HAS_AUTH", "HAS_NBI", "HAS_PROVISIONING", "HAS_MODEL", "HAS_NMTS")


def _stage(name, fn) -> dict:
    """Run one probe stage, capturing success or a sanitized error (never crashes the probe)."""
    try:
        ok, detail = fn()
        return {"stage": name, "ok": bool(ok), "detail": detail}
    except Exception as e:                       # normalize; never leak creds into the message
        return {"stage": name, "ok": False, "detail": f"{type(e).__name__}: {e}"}


def probe_store(store) -> list:
    """Run the read-only stages against any EntityStore; returns a list of stage-result dicts.
    Store-agnostic → works against Memory/Recorded (offline) or Grpc (live)."""
    results = []
    ents_box = {}

    def _intents():
        n = len(store.list_intents(states=["INSTALLED"]))
        return True, f"{n} INSTALLED intent(s)"
    results.append(_stage("intents (NbiStub.ListIntents)", _intents))

    def _entities():
        ents = store.list_entities()
        ents_box["ents"] = ents
        plats = [e for e in ents if int(_get(e, "kind", -1)) == EK_PLATFORM]
        ants = [e for e in ents if int(_get(e, "kind", -1)) == EK_ANTENNA]
        return True, f"{len(ents)} entit(y/ies): {len(plats)} platform(s), {len(ants)} antenna(s)"
    results.append(_stage("entities (ModelStub.ListEntities)", _entities))

    def _motion():
        ents = ents_box.get("ents")
        if ents is None:
            ents = store.list_entities()
        plats = [e for e in ents if int(_get(e, "kind", -1)) == EK_PLATFORM]
        kep_served = ext = other = 0
        for e in plats:
            plat = _get(e, "platform")
            is_ext = bool(_get(plat, "is_external_system", False))
            entries = _motion_entries(plat)
            is_kep = bool(entries and _kepler(entries[0]) is not None)
            if is_ext:
                ext += 1
            if is_kep and not is_ext:
                kep_served += 1
            elif not is_kep:
                other += 1
        return (kep_served > 0), (f"{len(plats)} platform(s): {kep_served} keplerian served, "
                                  f"{other} TLE/other (skipped), {ext} external-system (skipped)")
    results.append(_stage("platform motion", _motion))

    def _rels():
        rels = store.list_relationships()
        contains = sum(1 for r in rels if int(_get(r, "kind", -1)) == RK_CONTAINS)
        return True, f"{len(rels)} relationship(s), {contains} RK_CONTAINS"
    results.append(_stage("relationships (ModelStub.ListRelationships)", _rels))

    return results


def probe_endpoint(endpoint) -> dict:
    """Full first-contact probe of a live endpoint: capability flags → build live store → staged
    read surface. Degrades gracefully (flags + reason) when the live store can't be built (e.g. in
    the sandbox where spacetime-api is absent, or on an auth/connection failure)."""
    report = {
        "capability_flags": {k: getattr(_deps, k) for k in _FLAG_NAMES},
        "model_root": _deps.MODEL_ROOT,
        "store_built": False,
        "stages": [],
    }
    from .client import GrpcEntityStore     # lazy: importing probe must not require spacetime-api
    try:
        store = GrpcEntityStore(endpoint)
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["store_built"] = True
    report["stages"] = probe_store(store)
    return report


def format_report(report: dict) -> str:
    """Human-readable rendering of a probe report."""
    lines = ["Spacetime first-contact probe", "  capability flags:"]
    for k, v in report["capability_flags"].items():
        lines.append(f"    {k} = {v}")
    if report.get("model_root"):
        lines.append(f"    (Model import root resolved: {report['model_root']})")
    if not report.get("store_built"):
        lines.append(f"  live store: NOT built — {report.get('error', 'n/a')}")
        return "\n".join(lines)
    lines.append("  live store: built OK")
    for s in report["stages"]:
        lines.append(f"  [{'PASS' if s['ok'] else 'FAIL'}] {s['stage']}: {s['detail']}")
    return "\n".join(lines)


def _endpoint_from_env():
    """Build an endpoint from env vars. Key: prefer KEY_DATA_B64 (base64 of the key file);
    else SPACETIME_PRIVATE_KEY_FILE (path)."""
    import os
    from .config import SpacetimeEndpoint
    return SpacetimeEndpoint(
        url=os.environ["SPACETIME_URL"],
        key_id=os.environ["SPACETIME_KEY_ID"],
        user_id=os.environ["SPACETIME_USER_ID"],
        private_key_b64=os.environ.get("KEY_DATA_B64") or None,
        private_key_file=os.environ.get("SPACETIME_PRIVATE_KEY_FILE") or None,
        model_url=os.environ.get("SPACETIME_MODEL_URL") or None,
        model_version=os.environ.get("SPACETIME_MODEL_VERSION", "v1"),
    )


def main():
    print(format_report(probe_endpoint(_endpoint_from_env())))


if __name__ == "__main__":
    main()
