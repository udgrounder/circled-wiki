"""Circled Wiki source package with explicit Runtime/Engineering boundaries."""

from importlib import import_module
import sys


__version__ = "0.1.0"

# Keep source imports stable while the deployable implementation lives under
# ``runtime/``. The installer copies that directory's contents directly into
# an installed ``circled_wiki`` package, where runtime/__init__.py installs the
# same aliases without bringing Engineering tooling along.
for _package in ("config", "core", "cli", "integrations", "mcp", "worker"):
    _module = import_module(
        f".{_package}", f"{__name__}.runtime"
    )
    sys.modules[f"{__name__}.{_package}"] = _module
    globals()[_package] = _module
