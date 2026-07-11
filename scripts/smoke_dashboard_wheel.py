from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATTERN = re.compile(
    r'(?:src|href)="(?P<path>/assets/[^"?]+-[A-Za-z0-9_-]{6,}\.(?:js|css))"'
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and smoke-test the packaged Physical Agent Dashboard."
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the temporary wheel and virtual environments for debugging.",
    )
    args = parser.parse_args()

    if args.keep_workdir:
        workdir = Path(tempfile.mkdtemp(prefix="physical-agent-wheel-smoke-"))
        _run_smoke(workdir)
        print(f"Dashboard wheel smoke passed. Workdir: {workdir}")
        return 0

    with tempfile.TemporaryDirectory(prefix="physical-agent-wheel-smoke-") as raw:
        _run_smoke(Path(raw))
    print("Dashboard wheel smoke passed.")
    return 0


def _run_smoke(workdir: Path) -> None:
    wheel_dir = workdir / "wheel"
    wheel_dir.mkdir(parents=True)
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheel_dir),
        ],
        cwd=ROOT,
    )
    wheel = next(wheel_dir.glob("physical_agent-*.whl"))
    _assert_no_retired_gui(wheel)

    base_env = workdir / "base-env"
    _create_venv(base_env)
    base_python = _venv_python(base_env)
    _run(
        [str(base_python), "-m", "pip", "install", str(wheel)],
        clean_python_env=True,
    )
    base_cli = _venv_cli(base_env)
    missing = subprocess.run(
        [str(base_cli), "gui", "--no-open", "--no-watch"],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
        env=_clean_python_env(),
    )
    missing_output = missing.stdout + missing.stderr
    if missing.returncode != 1 or "physical-agent[server]" not in missing_output:
        raise RuntimeError(
            "Base-wheel GUI did not provide the server-extra installation hint:\n"
            + missing_output
        )

    server_env = workdir / "server-env"
    _create_venv(server_env)
    server_python = _venv_python(server_env)
    _run(
        [str(server_python), "-m", "pip", "install", f"{wheel}[server]"],
        clean_python_env=True,
    )
    server_cli = _venv_cli(server_env)
    config_path = workdir / "missing-project" / "physical-agent.yaml"

    gui_health = _smoke_server(
        [
            str(server_cli),
            "gui",
            "--no-open",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
            "--config",
            str(config_path),
        ],
        cwd=workdir,
    )
    if (gui_health.get("executor") or {}).get("mode") != "waiting_for_init":
        raise RuntimeError(f"GUI did not report waiting_for_init: {gui_health}")

    api_health = _smoke_server(
        [
            str(server_cli),
            "api",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
            "--config",
            str(config_path),
        ],
        cwd=workdir,
    )
    if (api_health.get("executor") or {}).get("mode") != "none":
        raise RuntimeError(f"API without --watch did not report executor none: {api_health}")


def _assert_no_retired_gui(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        retired = [
            name
            for name in archive.namelist()
            if name.startswith("physical_agent/gui/")
        ]
    if retired:
        raise RuntimeError(
            "Packaged wheel contains retired physical_agent/gui files: "
            + ", ".join(retired)
        )


def _smoke_server(command: list[str], *, cwd: Path) -> dict:
    port = _free_port()
    rendered = [part.format(port=port) for part in command]
    process = subprocess.Popen(
        rendered,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_clean_python_env(),
    )
    try:
        health = _wait_json(f"http://127.0.0.1:{port}/api/health", process)
        html = _read(f"http://127.0.0.1:{port}/").decode("utf-8")
        asset_match = ASSET_PATTERN.search(html)
        if asset_match is None:
            raise RuntimeError("Packaged index did not reference a hashed JS/CSS asset.")
        asset = _read(f"http://127.0.0.1:{port}{asset_match.group('path')}")
        if not asset:
            raise RuntimeError("Packaged Dashboard asset was empty.")
        return health
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_json(url: str, process: subprocess.Popen[str]) -> dict:
    deadline = time.monotonic() + 30
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"Dashboard server exited early:\n{output}")
        try:
            return json.loads(_read(url).decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Dashboard server did not become ready: {last_error}")


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pa-wheel-smoke"})
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP {response.status} for {url}")
        return response.read()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _create_venv(path: Path) -> None:
    venv.EnvBuilder(with_pip=True, clear=True).create(path)


def _venv_python(path: Path) -> Path:
    if os.name == "nt":
        return path / "Scripts" / "python.exe"
    return path / "bin" / "python"


def _venv_cli(path: Path) -> Path:
    if os.name == "nt":
        return path / "Scripts" / "physical-agent.exe"
    return path / "bin" / "physical-agent"


def _clean_python_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    clean_python_env: bool = False,
) -> None:
    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        env=_clean_python_env() if clean_python_env else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
