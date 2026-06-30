import numpy as np
from ..constants import MU_EARTH, RE_EQ, J2


class KeplerJ2Propagator:
    """Vectorized analytic two-body + J2 secular propagator (ECI position only)."""

    def __init__(self, mu: float = MU_EARTH, re: float = RE_EQ, j2: float = J2):
        self.mu, self.re, self.j2 = mu, re, j2

    def _rates(self, elements):
        a = elements[:, 0]
        e = elements[:, 1]
        inc = elements[:, 2]
        n0 = np.sqrt(self.mu / a**3)
        p = a * (1 - e**2)
        f = (self.re / p) ** 2
        cosi = np.cos(inc)
        sin2i = np.sin(inc) ** 2
        raan_dot = -1.5 * n0 * self.j2 * f * cosi
        argp_dot = 0.75 * n0 * self.j2 * f * (5 * cosi**2 - 1)
        m_dot = n0 * (1 + 1.5 * self.j2 * f * np.sqrt(1 - e**2) * (1 - 1.5 * sin2i))
        return raan_dot, argp_dot, m_dot

    def raan_dot(self, elements):  # exposed for tests / SSO validation
        return self._rates(elements)[0]

    def propagate(self, elements: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        a = elements[:, 0][:, None]
        e = elements[:, 1][:, None]
        inc = elements[:, 2][:, None]
        raan0 = elements[:, 3][:, None]
        argp0 = elements[:, 4][:, None]
        M0 = elements[:, 5][:, None]
        raan_dot, argp_dot, m_dot = (r[:, None] for r in self._rates(elements))
        t = np.asarray(times_s)[None, :]
        raan = raan0 + raan_dot * t
        argp = argp0 + argp_dot * t
        M = M0 + m_dot * t
        E = _kepler_E(M, e)
        nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
        r = a * (1 - e * np.cos(E))
        xp = r * np.cos(nu)
        yp = r * np.sin(nu)
        cO, sO = np.cos(raan), np.sin(raan)
        ci, si = np.cos(inc), np.sin(inc)
        cw, sw = np.cos(argp), np.sin(argp)
        x = (cO * cw - sO * sw * ci) * xp + (-cO * sw - sO * cw * ci) * yp
        y = (sO * cw + cO * sw * ci) * xp + (-sO * sw + cO * cw * ci) * yp
        z = (sw * si) * xp + (cw * si) * yp
        return np.stack([x, y, z], axis=-1)


def _kepler_E(M, e, tol=1e-12, itmax=60):
    E = np.array(M, dtype=float)
    for _ in range(itmax):
        dE = (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        E -= dE
        if np.max(np.abs(dE)) < tol:
            break
    return E
