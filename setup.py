from __future__ import annotations

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class CleanPackageBuild(_build_py):
    """Rebuild the Python package tree without stale deleted modules or assets."""

    def run(self) -> None:
        package_root = Path(self.build_lib) / "physical_agent"
        if package_root.exists():
            shutil.rmtree(package_root)
        super().run()


setup(cmdclass={"build_py": CleanPackageBuild})
