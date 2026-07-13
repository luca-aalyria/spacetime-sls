"""Guard: every code cell in every shipped notebook must at least COMPILE.

`nbformat.read` only validates the JSON envelope, not the Python inside the cells — that gap let
a notebook ship with unterminated string literals and Colab-incompatible f-strings. This test
compiles each code cell (IPython line-magics / shell escapes stripped, since `!pip`/`%foo` are
valid in Colab but not plain-Python-compilable)."""
import pathlib
import pytest

nbformat = pytest.importorskip("nbformat")

NB_DIR = pathlib.Path(__file__).resolve().parent.parent / "notebooks"


def _strip_magics(src: str) -> str:
    return "\n".join("" if ln.lstrip().startswith(("!", "%")) else ln
                     for ln in src.splitlines())


def test_all_notebook_code_cells_compile():
    nbs = sorted(NB_DIR.glob("*.ipynb"))
    assert nbs, f"no notebooks found under {NB_DIR}"
    errors = []
    for nb_path in nbs:
        nb = nbformat.read(str(nb_path), as_version=4)
        for i, cell in enumerate(nb.cells):
            if cell.cell_type != "code":
                continue
            try:
                compile(_strip_magics(cell.source), f"{nb_path.name}[cell {i}]", "exec")
            except SyntaxError as e:
                errors.append(f"{nb_path.name} cell {i}: {e}")
    assert not errors, "notebook code cells failed to compile:\n" + "\n".join(errors)
