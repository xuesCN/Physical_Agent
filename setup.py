from __future__ import annotations

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class CleanPackageBuild(_build_py):
    """Prevent stale Dashboard assets or retired GUI files from leaking into wheels."""

    def run(self) -> None:
        dashboard_dist = Path(self.build_lib) / "physical_agent" / "dashboard" / "dist"
        retired_gui = Path(self.build_lib) / "physical_agent" / "gui"
        if dashboard_dist.exists():
            shutil.rmtree(dashboard_dist)
        if retired_gui.exists():
            shutil.rmtree(retired_gui)
        super().run()


setup(cmdclass={"build_py": CleanPackageBuild})
