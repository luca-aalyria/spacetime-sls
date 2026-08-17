#!/usr/bin/env python3
"""Bump the version marker in a notebook's title cell.

Convention (see CLAUDE.md): every notebook carries '**Notebook version: vX.Y.Z**' in its
first markdown cell; ANY change to the .ipynb bumps it — patch for fixes, minor for
features, major for restructures.

Usage: tools/bump_nb_version.py notebooks/01_*.ipynb [patch|minor|major]   (default patch)
"""
import json
import re
import sys

path, part = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "patch")
nb = json.load(open(path))
cell = nb["cells"][0]
src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
m = re.search(r"\*\*Notebook version: v(\d+)\.(\d+)\.(\d+)\*\*", src)
if not m:
    sys.exit(f"no version marker in first cell of {path}")
maj, mi, pa = (int(g) for g in m.groups())
maj, mi, pa = {"major": (maj + 1, 0, 0), "minor": (maj, mi + 1, 0),
               "patch": (maj, mi, pa + 1)}[part]
new = f"**Notebook version: v{maj}.{mi}.{pa}**"
cell["source"] = src.replace(m.group(0), new).splitlines(keepends=True)
json.dump(nb, open(path, "w"), indent=1)
print(f"{path}: {m.group(0)} -> {new}")
