import h3


def assign_shards(cells, shard_res):
    """Assign each cell to exactly one parent shard (single-owner) via H3 cell_to_parent.

    Returns (groups: dict[str, list[int]], shard_of: list[str]) where group values are
    indices into `cells`. Requires shard_res <= the cells' resolution (coarser parent)."""
    if cells and shard_res > h3.get_resolution(cells[0]):
        raise ValueError("shard_res must be <= cell resolution (parent is coarser)")
    shard_of = [h3.cell_to_parent(c, shard_res) for c in cells]
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(shard_of):
        groups.setdefault(s, []).append(i)
    return groups, shard_of
