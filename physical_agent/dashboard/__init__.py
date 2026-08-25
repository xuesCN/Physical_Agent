"""Package-local access to the built React Dashboard assets."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def dashboard_dist_path() -> Path:
    """Return the installed Dashboard dist directory.

    Standard wheel installs unpack package resources onto the filesystem, which
    gives FastAPI/Starlette a stable directory independent of the process cwd.
    """

    return Path(str(files(__package__).joinpath("dist")))


__all__ = ["dashboard_dist_path"]
