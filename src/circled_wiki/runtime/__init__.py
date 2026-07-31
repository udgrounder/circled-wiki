"""Deployable Circled Wiki Runtime package."""

from importlib import import_module
import sys


__version__ = "0.1.0"

# The installer copies this directory directly into ``circled_wiki``. These
# aliases keep Runtime-internal imports stable in both the source tree and an
# installed Wiki without exposing Engineering-only modules.
for _package in ("config", "core", "cli", "integrations", "mcp", "worker"):
    _module = import_module(f".{_package}", __name__)
    sys.modules[f"{__name__}.{_package}"] = _module
    globals()[_package] = _module
