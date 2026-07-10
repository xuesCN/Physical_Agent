from __future__ import annotations

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class CleanDashboardBuild(_build_py):
    """Prevent stale hashed Dashboard assets from leaking into incremental wheels."""

    def run(self) -> None:
        dashboard_dist = Path(self.build_lib) / "physical_agent" / "dashboard" / "dist"
        if dashboard_dist.exists():
            shutil.rmtree(dashboard_dist)
        super().run()


setup(cmdclass={"build_py": CleanDashboardBuild})
