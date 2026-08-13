"""car_agent 真机首连探针（只读 + stop，不发任何运动指令）。

复用 CarAgentDriver 本体（经现有 loader 加载），因此探针通过 = watch 将走的
同一条代码路径通过。定位为现场运维工具，不接入请求/提案路径，不调用
driver.execute。

流程：connect（握手 = health 身份校验 + capabilities + 一次停车基线）
      → health → capabilities → observe → 顶层 stop → observe → disconnect

用法（仓库根目录，Windows）：
    .venv\\Scripts\\python.exe scripts\\car_first_contact.py --host 192.168.66.12

前提：车轮架空、可信 2.4GHz 同网段、同一时刻只有这一个控制客户端。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from physical_agent.drivers.loader import load_driver  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f"  ({detail})"
    print(line)


def show(title: str, payload: object) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


async def run(host: str, port: int) -> int:
    workdir = REPO_ROOT / ".tmp" / "car-first-contact"
    loaded = load_driver(
        robot_id="car_1",
        driver_ref=str(REPO_ROOT / "car_agent"),
        config={"host": host, "port": port},
        workspace_path=workdir / "workspace",
        artifacts_path=workdir / "workspace" / "artifacts",
    )
    driver = loaded.driver

    print(f"connecting to {host}:{port} ...")
    await driver.connect()
    # connect() 内部已完成：health 身份三元组校验 + wifi/service 健康校验
    # + capabilities 拉取（必须含 observe/stop）+ 一次停车基线。
    check("connect: TCP + 身份握手(protocol/device/project) + 停车基线", True)

    try:
        status = await driver.health()
        show("health", status.details)
        check("health: wifi_connected 且 service_running", status.ok, status.message)

        caps = [cap.name for cap in driver.capabilities()]
        show("agent 侧发布的能力", caps)
        check("能力含 observe/stop", {"observe", "stop"} <= set(caps))
        check(
            "首连阶段未发布 drive_for（运动限值未配置，符合预期）",
            "drive_for" not in caps,
        )

        observation = await driver.observe()
        state = dict(observation.robots["car_1"])
        show("observe", state)
        check("运动真源使用 moving 字段（非 status）", "moving" in state)
        check(
            "停车基线生效：moving=false",
            state.get("moving") is False,
            f"motor_cmd={state.get('motor_cmd')}",
        )
        if state.get("tof_available"):
            check(
                "TOF 可用",
                True,
                f"tof_valid={state.get('tof_valid')} tof_mm={state.get('tof_mm')}",
            )
        else:
            check("TOF 不可用 -> 读数按契约忽略", True, "tof_available=false")
        check(
            "watchdog_tripped 可读",
            "watchdog_tripped" in state,
            f"watchdog_tripped={state.get('watchdog_tripped')}",
        )

        await driver.halt()  # 顶层 stop；driver 要求设备确认 status=completed
        check("显式 stop 已被设备确认", True)

        observation2 = await driver.observe()
        state2 = dict(observation2.robots["car_1"])
        check("stop 后仍为 moving=false", state2.get("moving") is False)
    finally:
        await driver.disconnect()
        print("\ndisconnected.")

    failed = [item for item in CHECKS if not item[1]]
    print()
    if failed:
        print(f"==== RESULT: {len(failed)} FAILED / {len(CHECKS)} ====")
        return 1
    print(f"==== RESULT: ALL PASS ({len(CHECKS)}/{len(CHECKS)}) ====")
    return 0


HINTS = {
    "ConnectionRefusedError": "该 IP 上没有 8080 服务：核对 OLED 上的 IP、固件是否已启动。",
    "TimeoutError": (
        "TCP 通了但请求超时：多半是已有另一个客户端占用连接（固件为单客户端"
        "串行模型，F-6），或不在同一 2.4GHz 网段。关掉其他客户端后重试。"
    ),
    "CarAgentProtocolError": (
        "固件响应与 driver 预期不符（身份三元组 / service_running / 响应结构）。"
        "把上面的完整输出发回来做差异校对。"
    ),
    "OSError": "网络不可达：确认上位机与小车在同一 2.4GHz 网段。",
}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="192.168.66.12", help="小车当前 DHCP 地址")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        rc = asyncio.run(run(args.host, args.port))
    except Exception as exc:  # noqa: BLE001 - 现场探针需要兜底展示一切异常
        print(f"\n[FAIL] {type(exc).__name__}: {exc}")
        for cls in type(exc).__mro__:
            hint = HINTS.get(cls.__name__)
            if hint:
                print(f"提示: {hint}")
                break
        rc = 2
    sys.exit(rc)


if __name__ == "__main__":
    main()
