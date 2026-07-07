"""Increment-1 orchestration: pull NMTS model + installed intents from a store, build the SLS
raw-element constellation, run Slice-A coverage on it, and return the routes for comparison.
Store-agnostic: works with MemoryEntityStore/RecordedEntityStore (offline) or GrpcEntityStore
(live). Reuses the shipped run_coverage_h3_elements seam."""
from datetime import datetime, timezone
from ..config import TimeGrid
from ..pipeline import run_coverage_h3_elements
from .nmts_adapter import platforms_to_elements, routes_from_intents

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def pull_and_cover(store, aor, cell_res=3, min_elev_user_deg=25.0, duration_s=3600.0,
                   step_s=60.0, epoch_utc=None, k_values=(1, 2), shard_res=1,
                   chunk_steps=10, continuity_overlap_s=None):
    """Pull -> build elements -> run coverage -> collect installed routes. Returns a dict with
    the coverage result, served-satellite count, routes, and the skipped/flagged platforms."""
    entities = store.list_entities()
    rels = store.list_relationships()
    built = platforms_to_elements(entities, rels)
    elems, plane_uid = built["elems"], built["plane_uid"]
    if elems.shape[0] == 0:
        raise ValueError("no served Keplerian platforms pulled — check the instance/probe "
                         f"(skipped: {built['skipped']})")
    tg = TimeGrid(epoch_utc or _EPOCH, duration_s=duration_s, step_s=step_s)
    coverage = run_coverage_h3_elements(
        elems, plane_uid, min_elev_user_deg, tg, aor, cell_res, shard_res=shard_res,
        chunk_steps=chunk_steps, k_values=list(k_values), continuity_overlap_s=continuity_overlap_s)
    routes = routes_from_intents(store.list_intents(states=["INSTALLED"]))
    return {"coverage": coverage, "n_served": int(elems.shape[0]), "routes": routes,
            "meta": built["meta"], "antennas": built["antennas"], "skipped": built["skipped"],
            "ref_epoch_s": built["ref_epoch_s"]}
