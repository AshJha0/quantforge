"""R6-26: both branches of the package version lookup, checked against pyproject.toml."""
import importlib
import importlib.metadata
import re
from pathlib import Path

import pytest

import quantforge_core

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _declared() -> str:
    found = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    assert found is not None
    return found.group(1)


def test_installed_version_is_read_from_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "9.9.9" if name == "quantforge-core" else "")
    assert importlib.reload(quantforge_core).__version__ == "9.9.9"
    monkeypatch.undo()
    importlib.reload(quantforge_core)


def test_source_tree_version_matches_pyproject(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert importlib.reload(quantforge_core).__version__ == _declared()
    monkeypatch.undo()
    importlib.reload(quantforge_core)
