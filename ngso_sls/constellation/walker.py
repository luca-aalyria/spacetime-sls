import numpy as np
from ..config import Shell
from ..constants import RE_EQ
from .model import walker_model, OrbitTemplate


def walker_elements(shell: Shell) -> np.ndarray:
    """Expand a Walker T/P/F shell to (n_sat, 6) classical elements
    [a_km, e, i_rad, raan_rad, argp_rad, M_rad]. Byte-identical shim over `walker_model`."""
    tmpl = OrbitTemplate(a_km=RE_EQ + shell.altitude_km, ecc=shell.ecc,
                         inc_rad=np.radians(shell.inclination_deg),
                         argp_rad=np.radians(shell.arg_perigee_deg))
    return walker_model(tmpl, shell.walker_T, shell.walker_P, shell.walker_F,
                        raan0_deg=shell.raan0_deg, phase0_deg=shell.phase0_deg,
                        shell_name=shell.shell_id).elems
