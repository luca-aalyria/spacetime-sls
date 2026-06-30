import numpy as np
from ..config import Shell
from ..constants import RE_EQ


def walker_elements(shell: Shell) -> np.ndarray:
    """Expand a Walker T/P/F shell to (n_sat, 6) classical elements
    [a_km, e, i_rad, raan_rad, argp_rad, M_rad]."""
    T, P, F = shell.walker_T, shell.walker_P, shell.walker_F
    if T % P != 0:
        raise ValueError(f"walker_T ({T}) must be divisible by walker_P ({P})")
    S = T // P
    a = RE_EQ + shell.altitude_km
    inc = np.radians(shell.inclination_deg)
    argp = np.radians(shell.arg_perigee_deg)
    e = shell.ecc
    p_idx = np.repeat(np.arange(P), S)  # plane index per sat
    s_idx = np.tile(np.arange(S), P)    # in-plane index per sat
    raan = np.radians(shell.raan0_deg + p_idx * 360.0 / P) % (2 * np.pi)
    M = np.radians(shell.phase0_deg + s_idx * 360.0 / S + p_idx * F * 360.0 / T) % (2 * np.pi)
    out = np.empty((T, 6))
    out[:, 0] = a
    out[:, 1] = e
    out[:, 2] = inc
    out[:, 3] = raan
    out[:, 4] = argp
    out[:, 5] = M
    return out
