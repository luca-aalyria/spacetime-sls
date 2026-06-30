import h3
import pytest
from ngso_sls.grids.h3_grid import h3_cells_for_bbox
from ngso_sls.grids.shards import assign_shards
from ngso_sls.grids.aor import INDIA_AOR


def test_single_owner_partition():
    cells, _, _ = h3_cells_for_bbox(**INDIA_AOR, res=4)
    groups, shard_of = assign_shards(cells, shard_res=2)
    assert len(shard_of) == len(cells)
    # every cell belongs to exactly one shard; groups partition the index set
    all_idx = sorted(i for idxs in groups.values() for i in idxs)
    assert all_idx == list(range(len(cells)))
    # shard ids are resolution-2 parents
    assert all(h3.get_resolution(s) == 2 for s in groups)
    # each owned cell's parent equals its shard id
    for s, idxs in groups.items():
        for i in idxs:
            assert h3.cell_to_parent(cells[i], 2) == s


def test_shard_res_must_be_coarser():
    cells, _, _ = h3_cells_for_bbox(**INDIA_AOR, res=3)
    with pytest.raises(ValueError):
        assign_shards(cells, shard_res=5)
