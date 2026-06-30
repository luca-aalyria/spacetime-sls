from .config import Shell, Constellation


def jio_constellation() -> Constellation:
    """Reliance-Jio anchor: 1600-sat dual shell (Primary 1200/40/1 @48°, Secondary 400/20/7 @70°)."""
    primary = Shell("primary", 1200, 40, 1, 650.0, 48.0)
    secondary = Shell("secondary", 400, 20, 7, 650.0, 70.0)
    return Constellation((primary, secondary))
