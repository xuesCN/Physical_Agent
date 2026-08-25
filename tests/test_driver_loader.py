import asyncio
from pathlib import Path

from physical_agent.drivers.loader import load_driver
from physical_agent.drivers.mock_arm import MockArmDriver
from physical_agent.drivers.templates import create_driver_template


def _driver_paths(tmp_path: Path) -> tuple[Path, Path]:
    workspace_path = tmp_path / "workspace"
    artifacts_path = workspace_path / "artifacts"
    artifacts_path.mkdir(parents=True)
    return workspace_path, artifacts_path


def test_load_builtin_mock_arm(tmp_path):
    workspace_path, artifacts_path = _driver_paths(tmp_path)
    loaded = load_driver(
        robot_id="arm_1",
        driver_ref="mock_arm",
        config={},
        workspace_path=workspace_path,
        artifacts_path=artifacts_path,
    )
    assert isinstance(loaded.driver, MockArmDriver)
    assert loaded.manifest.name == "mock_arm"


def test_load_local_generated_driver(tmp_path):
    workspace_path, artifacts_path = _driver_paths(tmp_path)
    driver_dir = create_driver_template(tmp_path / "my_arm_driver")
    loaded = load_driver(
        robot_id="local_1",
        driver_ref=str(driver_dir),
        config={},
        workspace_path=workspace_path,
        artifacts_path=artifacts_path,
    )
    asyncio.run(loaded.driver.connect())
    health = asyncio.run(loaded.driver.health())
    assert health.ok is True
    assert loaded.driver.capabilities()[0].name == "observe"
