import numpy as np
import pytest
from ngso_sls.constellation.model import ConstellationModel
from ngso_sls.constellation.model import walker_model, OrbitTemplate
from ngso_sls.constellation.walker import walker_elements
from ngso_sls.config import Shell
from ngso_sls.constants import RE_EQ


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


def _walker_golden(shell):
    """The exact original walker.py:16-27 expression, pinned here as the byte-identity oracle."""
    T, P, F = shell.walker_T, shell.walker_P, shell.walker_F
    S = T // P
    a = RE_EQ + shell.altitude_km
    inc = np.radians(shell.inclination_deg)
    argp = np.radians(shell.arg_perigee_deg)
    p_idx = np.repeat(np.arange(P), S)
    s_idx = np.tile(np.arange(S), P)
    raan = np.radians(shell.raan0_deg + p_idx * 360.0 / P) % (2 * np.pi)
    M = np.radians(shell.phase0_deg + s_idx * 360.0 / S + p_idx * F * 360.0 / T) % (2 * np.pi)
    out = np.empty((T, 6))
    out[:, 0], out[:, 1], out[:, 2] = a, shell.ecc, inc
    out[:, 3], out[:, 4], out[:, 5] = raan, argp, M
    return out


def test_walker_elements_byte_identical_after_refactor():
    shell = Shell("s", 48, 6, 1, 550.0, 53.0, raan0_deg=10.0, phase0_deg=5.0)
    assert np.array_equal(walker_elements(shell), _walker_golden(shell))


def test_walker_model_plane_uid_is_physical_plane():
    m = walker_model(OrbitTemplate(a_km=RE_EQ + 550.0, ecc=0.0, inc_rad=np.radians(53.0)),
                     total_sats=48, planes=6, phasing=1)
    assert m.n_sat == 48
    # 6 physical planes, 8 sats each
    uids, counts = np.unique(m.plane_uid, return_counts=True)
    assert len(uids) == 6 and set(counts.tolist()) == {8}
