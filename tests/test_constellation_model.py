import numpy as np
import pytest
from ngso_sls.constellation.model import ConstellationModel


def _model(n, shell_id=0, plane_uid=None):
    elems = np.tile([7000.0, 0.0, 0.9, 0.1, 0.0, 0.2], (n, 1))
    pu = np.zeros(n, dtype=np.int64) if plane_uid is None else np.asarray(plane_uid, np.int64)
    return ConstellationModel(
        elems=elems, plane_uid=pu, slot_id=np.arange(n, dtype=np.int64),
        shell_id=np.full(n, shell_id, dtype=np.int64), epoch_s=np.zeros(n),
        sat_id=tuple(f"s{shell_id}-{i}" for i in range(n)))


def test_model_shape_and_n_sat():
    m = _model(3)
    assert m.n_sat == 3 and m.elems.shape == (3, 6)


def test_model_rejects_mismatched_metadata():
    with pytest.raises((ValueError, AssertionError)):
        ConstellationModel(elems=np.zeros((2, 6)), plane_uid=np.zeros(3, np.int64),
                           slot_id=np.zeros(2, np.int64), shell_id=np.zeros(2, np.int64),
                           epoch_s=np.zeros(2), sat_id=("a", "b"))


def test_concat_stacks_and_renumbers():
    a = _model(2, shell_id=0, plane_uid=[0, 1])
    b = _model(3, shell_id=0, plane_uid=[0, 0, 2])   # its own uid space, shell_id will renumber
    c = ConstellationModel.concat([a, b])
    assert c.n_sat == 5
    assert c.shell_id.tolist() == [0, 0, 1, 1, 1]           # renumbered by position
    # b's non-(-1) uids offset past a's max (1) -> +2
    assert c.plane_uid.tolist() == [0, 1, 2, 2, 4]
    assert c.sat_id == a.sat_id + b.sat_id


def test_concat_preserves_unknown_plane_sentinel():
    a = _model(1, plane_uid=[-1])
    b = _model(1, plane_uid=[-1])
    c = ConstellationModel.concat([a, b])
    assert c.plane_uid.tolist() == [-1, -1]                 # -1 stays -1 across shells
