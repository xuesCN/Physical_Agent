from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

import yaml

from physical_agent.config import default_config_dict, load_config, write_default_config


def test_write_default_config_never_replaces_existing_bytes(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    original = b"project:\n  name: existing-project\n"
    config_path.write_bytes(original)

    write_default_config(config_path, overwrite=False)

    assert config_path.read_bytes() == original
    assert load_config(config_path).project.name == "existing-project"


def test_write_default_config_exclusively_publishes_complete_file_under_race(tmp_path):
    default_text = yaml.safe_dump(default_config_dict(), sort_keys=False)
    custom_text = "project:\n  name: concurrent-user-config\n"

    for attempt in range(10):
        config_path = tmp_path / f"physical-agent-{attempt}.yaml"
        barrier = threading.Barrier(8)

        def publish_default() -> None:
            barrier.wait()
            write_default_config(config_path, overwrite=False)

        def publish_custom() -> None:
            barrier.wait()
            try:
                with config_path.open("x", encoding="utf-8") as handle:
                    handle.write(custom_text)
            except FileExistsError:
                pass

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(publish_default) for _ in range(4)]
            futures.extend(executor.submit(publish_custom) for _ in range(4))
            for future in futures:
                future.result()

        final_text = config_path.read_text(encoding="utf-8")
        assert final_text in {default_text, custom_text}
        assert load_config(config_path).project.name in {
            "quickstart",
            "concurrent-user-config",
        }
