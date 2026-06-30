"""Guard the netsolve-core-style invariant: the pure core imports only numpy (+astropy in
geometry) — never pandas/matplotlib/h3/proto/grpc/nmts. This is what lets a future Slice-E
adapter wrap the unchanged core."""
import pathlib
import re

CORE_PKGS = ["constellation", "propagation", "geometry", "coverage"]
FORBIDDEN = {"pandas", "matplotlib", "h3", "shapely", "geopandas", "nmts", "proto", "grpc"}
ALLOWED_TOP = {"numpy", "astropy", "typing", "dataclasses", "datetime", "math", "__future__"}


def _top_imports(path: pathlib.Path):
    for line in path.read_text().splitlines():
        m = re.match(r"\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", line)
        if m and not m.group(1).startswith("."):  # ignore relative intra-package imports
            yield m.group(1).split(".")[0]


def test_core_modules_import_only_numpy_astropy():
    root = pathlib.Path(__file__).resolve().parent.parent / "ngso_sls"
    violations = []
    for pkg in CORE_PKGS:
        for f in (root / pkg).rglob("*.py"):
            for mod in _top_imports(f):
                if mod in FORBIDDEN:
                    violations.append(f"{f.relative_to(root)} imports forbidden '{mod}'")
                elif mod not in ALLOWED_TOP:
                    violations.append(f"{f.relative_to(root)} imports unexpected '{mod}'")
    assert not violations, "core purity violated:\n" + "\n".join(violations)
