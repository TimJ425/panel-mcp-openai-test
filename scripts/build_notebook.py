"""Build notebooks/harness.ipynb (one code cell) from notebooks/harness_cell.py.

Edit harness_cell.py, then run: python3 scripts/build_notebook.py
"""
import json
from pathlib import Path

NOTEBOOKS = Path(__file__).resolve().parent.parent / "notebooks"
SOURCE = NOTEBOOKS / "harness_cell.py"
OUTPUT = NOTEBOOKS / "harness.ipynb"


def build() -> None:
    """Wrap the cell source in a minimal nbformat 4.5 notebook and write it."""
    cell = {"id": "harness", "cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": SOURCE.read_text().rstrip("\n")}
    notebook = {
        "cells": [cell],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    OUTPUT.write_text(json.dumps(notebook, indent=1))
    print("wrote", OUTPUT)


if __name__ == "__main__":
    build()
