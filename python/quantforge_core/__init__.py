"""QuantForge core: stage A foundations, written from specifications/01-core."""

try:  # the installed package's version (python/pyproject.toml), so the CLI cannot drift from the release
    from importlib.metadata import version as _version
    __version__ = _version("quantforge-core")
except Exception:  # noqa: BLE001 (not installed: running from a source tree)
    __version__ = "0.8.3"
