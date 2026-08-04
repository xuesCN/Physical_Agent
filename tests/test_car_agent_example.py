from pathlib import Path

from physical_agent.config import load_config
from physical_agent.drivers.loader import load_driver


CAR_AGENT_DIR = Path("car_agent").resolve()
SAMPLE_CONFIG = CAR_AGENT_DIR / "physical-agent.yaml"


def test_car_agent_bundle_contains_operator_entrypoints():
    assert (CAR_AGENT_DIR / "README.md").is_file()
    assert (CAR_AGENT_DIR / "README.zh-CN.md").is_file()
    assert SAMPLE_CONFIG.is_file()


def test_car_agent_sample_is_hardware_mode_with_motion_disabled(tmp_path):
    config = load_config(SAMPLE_CONFIG)
    robot = config.robots["car_1"]

    assert robot.driver == "."
    assert robot.execution_mode == "hardware"
    assert robot.config["host"] == "REPLACE_WITH_CAR_IP"
    assert "max_abs_speed" not in robot.config
    assert "max_duration_ms" not in robot.config

    loaded = load_driver(
        robot_id="car_1",
        driver_ref=robot.driver,
        config=robot.config,
        workspace_path=tmp_path / "workspace",
        artifacts_path=tmp_path / "workspace" / "artifacts",
        base_dir=SAMPLE_CONFIG.parent,
    )
    assert [capability.name for capability in loaded.driver.capabilities()] == [
        "observe",
        "stop",
    ]
