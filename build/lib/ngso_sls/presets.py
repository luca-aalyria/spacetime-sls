from .config import Shell, Constellation

# Reliance-Jio constellation sizing scenarios (650 km; user min-elev handled per run).
# Named presets for the "minimum subset to begin serving India" study: the full 1600-sat dual
# shell, single shells, and thinned primary-shell subsets (fewer sats/plane, planes preserved
# for longitude coverage). All Walker T/P/F satisfy T % P == 0.
JIO_SCENARIOS = {
    "Full 1600 (dual shell)": Constellation((
        Shell("primary", 1200, 40, 1, 650.0, 48.0),
        Shell("secondary", 400, 20, 7, 650.0, 70.0),
    )),
    "Primary 1200 @48°": Constellation((Shell("primary", 1200, 40, 1, 650.0, 48.0),)),
    "Secondary 400 @70°": Constellation((Shell("secondary", 400, 20, 7, 650.0, 70.0),)),
    "~800 @48° (thinned)": Constellation((Shell("p800", 800, 40, 1, 650.0, 48.0),)),
    "~400 India-initial @48°": Constellation((Shell("p400", 400, 40, 1, 650.0, 48.0),)),
    "~200 @48° (minimal)": Constellation((Shell("p200", 200, 20, 1, 650.0, 48.0),)),
}


def jio_constellation() -> Constellation:
    """The full Reliance-Jio 1600-sat dual shell (Primary 1200/40/1 @48°, Secondary 400/20/7 @70°)."""
    return JIO_SCENARIOS["Full 1600 (dual shell)"]
