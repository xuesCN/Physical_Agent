from pathlib import Path
import shutil

import pytest

from physical_agent.agent.context_builder import build_context
from physical_agent.config import load_config
from physical_agent.drivers.loader import load_driver
from physical_agent.state import open_state_store


CAR_AGENT_DIR = Path("car_agent").resolve()
SAMPLE_CONFIG = CAR_AGENT_DIR / "physical-agent.yaml"
SAFETY_TEMPLATE = CAR_AGENT_DIR / "SAFETY.template.md"


def test_car_agent_bundle_contains_operator_entrypoints():
    assert (CAR_AGENT_DIR / "README.md").is_file()
    assert (CAR_AGENT_DIR / "README.zh-CN.md").is_file()
    assert SAMPLE_CONFIG.is_file()
    assert SAFETY_TEMPLATE.is_file()


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


def test_car_agent_tracked_safety_template_initializes_fresh_workspace(tmp_path):
    clean_bundle = tmp_path / "car_agent"
    clean_bundle.mkdir()
    for name in (
        "physical-agent.yaml",
        "physical_driver.yaml",
        "driver.py",
        "SAFETY.template.md",
    ):
        shutil.copy2(CAR_AGENT_DIR / name, clean_bundle / name)

    config_path = clean_bundle / "physical-agent.yaml"
    store = open_state_store(config_path=config_path)

    assert not store.file("safety").exists()
    store.initialize()
    snapshot = store.read_safety_snapshot()

    assert snapshot.hard.revision == 1
    assert snapshot.agent_guidance is not None
    guidance = snapshot.agent_guidance
    for expected in (
        "wheels-up",
        "disconnect physical power immediately",
        "no local obstacle-avoidance fallback",
        "tof_available",
        "tof_valid",
        "distance is unknown",
        "driver-derived `status`",
        "open-loop PWM command",
        "not obstacle detection",
    ):
        assert expected in guidance

    robot = load_config(config_path).robots["car_1"]
    assert robot.execution_mode == "hardware"
    assert "max_abs_speed" not in robot.config
    assert "max_duration_ms" not in robot.config


@pytest.mark.parametrize("purpose", ["reply", "proposal", "planner", "tool_loop"])
def test_car_agent_fresh_template_reaches_every_context_purpose(tmp_path, purpose):
    clean_bundle = tmp_path / f"car_agent_{purpose}"
    clean_bundle.mkdir()
    for name in ("physical-agent.yaml", "SAFETY.template.md"):
        shutil.copy2(CAR_AGENT_DIR / name, clean_bundle / name)
    store = open_state_store(config_path=clean_bundle / "physical-agent.yaml")
    store.initialize()
    store.write_capabilities(
        {
            "car_1": {
                "kind": "car",
                "driver": ".",
                "execution_mode": "hardware",
                "status": "connected",
                "requires_approval": True,
                "capabilities": [],
            }
        }
    )

    payload = build_context(store, "inspect safely", purpose=purpose).payload

    assert payload["safety"]["guidance"]["present"] is True
    assert "wheels-up" in payload["safety"]["guidance"]["text"]
    assert payload["safety"]["hard"]["rules"][
        "require_human_approval_for_real_hardware"
    ] is True


def test_car_agent_template_is_only_applied_on_fresh_initialize(tmp_path):
    clean_bundle = tmp_path / "car_agent"
    clean_bundle.mkdir()
    for name in ("physical-agent.yaml", "SAFETY.template.md"):
        shutil.copy2(CAR_AGENT_DIR / name, clean_bundle / name)
    store = open_state_store(config_path=clean_bundle / "physical-agent.yaml")
    store.initialize()
    original = store.read_safety_snapshot()

    (clean_bundle / "SAFETY.template.md").write_text(
        SAFETY_TEMPLATE.read_text(encoding="utf-8").replace(
            "wheels-up bench device only",
            "changed project template",
        ),
        encoding="utf-8",
    )
    store.initialize()

    assert store.read_safety_snapshot() == original
