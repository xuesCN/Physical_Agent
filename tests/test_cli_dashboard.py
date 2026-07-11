from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from typer.testing import CliRunner

import physical_agent.cli as cli_module
from physical_agent.api.server import MissingServerDependencyError, SERVER_EXTRA_HINT
from physical_agent.dashboard import dashboard_dist_path


ROOT = Path(__file__).parents[1]


def _fake_server(monkeypatch):
    calls: dict[str, object] = {}
    events: list[str] = []
    calls["events"] = events
    app_object = object()

    def fake_create_app(config, *, enable_watch=False, watch_interval_s=None):
        events.append("create_app")
        calls["create_app"] = {
            "config": Path(config),
            "enable_watch": enable_watch,
            "watch_interval_s": watch_interval_s,
        }
        return app_object

    class FakeUvicorn:
        @staticmethod
        def run(app, *, host, port):
            events.append("uvicorn")
            calls["uvicorn"] = {"app": app, "host": host, "port": port}

    monkeypatch.setattr(cli_module, "_load_api_server", lambda: (fake_create_app, FakeUvicorn))
    return calls, app_object


def test_gui_cli_schedules_ready_browser_before_serving_with_embedded_watch(tmp_path, monkeypatch):
    calls, app_object = _fake_server(monkeypatch)
    scheduled: list[str] = []

    def schedule(url: str):
        calls["events"].append("schedule")
        scheduled.append(url)

    monkeypatch.setattr(cli_module, "_schedule_dashboard_browser", schedule)
    config_path = tmp_path / "physical-agent.yaml"

    result = CliRunner().invoke(
        cli_module.app,
        ["gui", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert calls["create_app"] == {
        "config": config_path,
        "enable_watch": True,
        "watch_interval_s": None,
    }
    assert calls["uvicorn"] == {
        "app": app_object,
        "host": "127.0.0.1",
        "port": 8765,
    }
    assert scheduled == ["http://127.0.0.1:8765"]
    assert calls["events"] == ["create_app", "schedule", "uvicorn"]
    assert "Physical Agent Dashboard running at http://127.0.0.1:8765" in result.output


def test_gui_cli_no_watch_no_open_and_binding_flags(tmp_path, monkeypatch):
    calls, app_object = _fake_server(monkeypatch)
    scheduled: list[str] = []
    monkeypatch.setattr(cli_module, "_schedule_dashboard_browser", scheduled.append)
    config_path = tmp_path / "physical-agent.yaml"

    result = CliRunner().invoke(
        cli_module.app,
        [
            "gui",
            "--config",
            str(config_path),
            "--host",
            "0.0.0.0",
            "--port",
            "9812",
            "--no-watch",
            "--no-open",
        ],
    )

    assert result.exit_code == 0
    assert calls["create_app"] == {
        "config": config_path,
        "enable_watch": False,
        "watch_interval_s": None,
    }
    assert calls["uvicorn"] == {
        "app": app_object,
        "host": "0.0.0.0",
        "port": 9812,
    }
    assert scheduled == []
    assert calls["events"] == ["create_app", "uvicorn"]
    assert "Physical Agent Dashboard running at http://127.0.0.1:9812" in result.output


def test_dashboard_browser_url_maps_wildcard_and_ipv6_bind_hosts():
    assert cli_module._dashboard_browser_url("0.0.0.0", 8765) == "http://127.0.0.1:8765"
    assert cli_module._dashboard_browser_url("::", 8765) == "http://[::1]:8765"
    assert cli_module._dashboard_browser_url("::1", 8765) == "http://[::1]:8765"
    assert cli_module._dashboard_browser_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"


def test_dashboard_browser_scheduler_starts_daemon_readiness_waiter(monkeypatch):
    captured = {}

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            captured.update(target=target, args=args, name=name, daemon=daemon)
            captured["thread"] = self

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(cli_module.threading, "Thread", FakeThread)

    thread = cli_module._schedule_dashboard_browser("http://127.0.0.1:8765")

    assert thread is captured["thread"]
    assert captured == {
        "target": cli_module._wait_for_dashboard_and_open,
        "args": ("http://127.0.0.1:8765",),
        "name": "physical-agent-dashboard-opener",
        "daemon": True,
        "thread": thread,
        "started": True,
    }


def test_readiness_waiter_does_not_open_during_failed_polls_then_opens(monkeypatch):
    health_results = iter([False, False, True])
    health_urls: list[str] = []
    opened: list[str] = []
    sleeps: list[float] = []

    def health_ready(url: str) -> bool:
        health_urls.append(url)
        return next(health_results)

    monkeypatch.setattr(cli_module, "_dashboard_health_ready", health_ready)
    monkeypatch.setattr(cli_module.webbrowser, "open", opened.append)
    monkeypatch.setattr(cli_module.time, "sleep", sleeps.append)

    ready = cli_module._wait_for_dashboard_and_open(
        "http://127.0.0.1:8765",
        timeout_s=1.0,
        poll_interval_s=0.01,
    )

    assert ready is True
    assert health_urls == ["http://127.0.0.1:8765/api/health"] * 3
    assert len(sleeps) == 2
    assert opened == ["http://127.0.0.1:8765"]


def test_readiness_waiter_never_opens_when_health_poll_times_out(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(cli_module, "_dashboard_health_ready", lambda _url: False)
    monkeypatch.setattr(cli_module.webbrowser, "open", opened.append)

    ready = cli_module._wait_for_dashboard_and_open(
        "http://127.0.0.1:8765",
        timeout_s=0,
    )

    assert ready is False
    assert opened == []


def test_gui_cli_missing_server_extra_has_actionable_message(tmp_path, monkeypatch):
    def fail_loader():
        raise MissingServerDependencyError(SERVER_EXTRA_HINT)

    monkeypatch.setattr(cli_module, "_load_api_server", fail_loader)

    result = CliRunner().invoke(
        cli_module.app,
        ["gui", "--config", str(tmp_path / "physical-agent.yaml"), "--no-open"],
    )

    assert result.exit_code == 1
    assert "FastAPI backend dependencies are not installed" in result.output
    assert ".[server]" in result.output


def test_dashboard_resource_path_is_package_local():
    assert dashboard_dist_path() == ROOT / "physical_agent" / "dashboard" / "dist"


def test_wheel_contains_dashboard_index_and_hashed_assets(tmp_path):
    dist = dashboard_dist_path()
    assert (dist / "index.html").is_file(), "Run `cd frontend && npm run build` before wheel smoke."
    assert any((dist / "assets").iterdir()), "Dashboard build did not produce assets."

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheel = next(tmp_path.glob("physical_agent-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())

    prefix = "physical_agent/dashboard/dist/"
    packaged_dashboard = {
        member for member in members if member.startswith(prefix) and not member.endswith("/")
    }
    source_dashboard = {
        f"{prefix}{path.relative_to(dist).as_posix()}"
        for path in dist.rglob("*")
        if path.is_file()
    }
    assert packaged_dashboard == source_dashboard
    assert not any(member.startswith("physical_agent/gui/") for member in members)
