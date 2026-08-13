"""WebSocket 连接冒烟测试（只验连接，不执行任何动作）。

用途：在给公司 ESP32 板子写正式 driver 之前，先单独验证
电脑 → 板子 的 WebSocket 链路是否通。

安全边界：
- 不加载任何 driver，不 import watch runtime；
- 只读探测：最多发送 MCP `initialize` + `tools/list`，永不发送 `tools/call`；
- 不触碰 Action Board / SQLite 状态。

用法（在装好 `pip install -e .` 的环境里运行）：

    # 一档：TCP + WS 握手 + 关闭（零业务字节）
    python scripts/ws_connection_smoke.py ws://192.168.1.50:8080/ws

    # 二档：加 MCP 只读探测（initialize + tools/list，列出板子暴露的能力）
    python scripts/ws_connection_smoke.py ws://192.168.1.50:8080/ws --probe mcp

    # 无板自测：本地起一个假 WS 服务，验证脚本与 transport 本身
    python scripts/ws_connection_smoke.py --selftest
    python scripts/ws_connection_smoke.py --selftest --probe mcp

    # 需要鉴权头时（如固件要 token）
    python scripts/ws_connection_smoke.py ws://... --header "Authorization: Bearer XXX"
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import struct
import sys
import threading
import time
from typing import Any

from physical_agent.drivers.transport import WebSocketTransport
from physical_agent.drivers.transport.base import TransportError

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _step(label: str) -> None:
    print(f"  [*] {label} ...", end="", flush=True)


def _ok(started: float, extra: str = "") -> None:
    ms = (time.perf_counter() - started) * 1000
    suffix = f"  {extra}" if extra else ""
    print(f" ok ({ms:.0f} ms){suffix}")


def _fail(exc: BaseException) -> None:
    print(" FAILED")
    print(f"      -> {type(exc).__name__}: {exc}")


def _hint_for(exc: BaseException) -> str | None:
    text = str(exc).lower()
    if "refused" in text:
        return "端口没人监听：固件 WS 服务没起来，或端口/路径写错。"
    if "timed out" in text or "timeout" in text:
        return "连不上主机：IP 写错、不在同一网段、或防火墙拦截。先 ping 板子 IP。"
    if "getaddrinfo" in text or "name or service" in text or "nodename" in text:
        return "域名解析失败：mDNS(.local) 在本机不可用时改用 IP 直连。"
    if "accept" in text or "101" in text or "handshake" in text:
        return "对端不是 WebSocket 端点：路径不对，或那是普通 HTTP/TCP 服务。"
    if "401" in text or "403" in text:
        return "鉴权失败：用 --header 传固件要求的 token。"
    return None


def _read_until_matching_id(
    transport: WebSocketTransport, request_id: int, timeout_s: float
) -> dict[str, Any]:
    deadline = time.perf_counter() + timeout_s
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError(f"No JSON-RPC response for id={request_id}")
        raw = transport.read(remaining).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # 兼容小智桥格式 {"type": "mcp", "payload": {...}}
        if isinstance(data, dict) and data.get("type") == "mcp":
            data = data.get("payload")
        if isinstance(data, dict) and data.get("id") == request_id:
            return data


def _jsonrpc(
    transport: WebSocketTransport,
    request_id: int,
    method: str,
    params: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    transport.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    response = _read_until_matching_id(transport, request_id, timeout_s)
    if "error" in response:
        raise RuntimeError(f"JSON-RPC error: {response['error']}")
    result = response.get("result")
    return result if isinstance(result, dict) else {"value": result}


def run_smoke(url: str, probe: str, headers: dict[str, str],
              connect_timeout_s: float, timeout_s: float) -> int:
    print(f"目标: {url}")
    transport = WebSocketTransport(
        url,
        connect_timeout_s=connect_timeout_s,
        timeout_s=timeout_s,
        headers=headers or None,
    )

    _step("TCP 连接 + WebSocket 握手")
    started = time.perf_counter()
    try:
        transport.open()
    except (TransportError, ValueError, OSError) as exc:
        _fail(exc)
        hint = _hint_for(exc)
        if hint:
            print(f"      提示: {hint}")
        return 1
    _ok(started)

    exit_code = 0
    try:
        if probe == "mcp":
            _step("MCP initialize（只读）")
            started = time.perf_counter()
            try:
                info = _jsonrpc(
                    transport, 1, "initialize",
                    {"capabilities": {},
                     "clientInfo": {"name": "ws-connection-smoke", "version": "0.1.0"}},
                    timeout_s,
                )
                server = info.get("serverInfo") or {}
                _ok(started, f"server={server.get('name', '?')} {server.get('version', '')}".rstrip())
            except (TransportError, RuntimeError, TimeoutError, OSError) as exc:
                _fail(exc)
                print("      提示: 握手已通，但对端不认识 MCP initialize——固件可能")
                print("            用的是自定义 JSON 协议。连接层没问题，协议层需对齐。")
                exit_code = 2

            if exit_code == 0:
                _step("MCP tools/list（只读，绝不 tools/call）")
                started = time.perf_counter()
                try:
                    result = _jsonrpc(transport, 2, "tools/list", {}, timeout_s)
                    tools = result.get("tools") or []
                    names = [t.get("name", "?") for t in tools if isinstance(t, dict)]
                    _ok(started, f"{len(names)} 个工具: {', '.join(names[:8]) or '(空)'}")
                except (TransportError, RuntimeError, TimeoutError, OSError) as exc:
                    _fail(exc)
                    exit_code = 2
    finally:
        _step("关闭连接")
        started = time.perf_counter()
        transport.close()
        _ok(started)

    health = transport.health()
    print(f"  [i] transport health: ok={health.ok} status={health.status!r}")
    if exit_code == 0:
        print("结论: 连接链路正常 ✔")
    elif exit_code == 2:
        print("结论: WS 连接正常，MCP 协议探测未通过（连接不背锅）")
    return exit_code


# ---------------------------------------------------------------- selftest --

def _selftest_server(listener: socket.socket, ready: threading.Event) -> None:
    """最小假 WS 服务：握手 + 应答 initialize/tools-list。仅供无板自测。"""
    ready.set()
    conn, _ = listener.accept()
    with conn:
        conn.settimeout(5)
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        key = ""
        for line in request.decode("latin-1").split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
        accept = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode()).digest()).decode()
        conn.sendall(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode()
        )
        while True:
            try:
                header = conn.recv(2)
            except TimeoutError:
                return
            if len(header) < 2:
                return
            opcode = header[0] & 0x0F
            length = header[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", conn.recv(2))[0]
            mask = conn.recv(4)
            payload = bytearray()
            while len(payload) < length:
                payload.extend(conn.recv(length - len(payload)))
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:  # close
                conn.sendall(b"\x88\x00")
                return
            if opcode != 0x1:
                continue
            try:
                msg = json.loads(data.decode())
            except json.JSONDecodeError:
                continue
            method = msg.get("method")
            if method == "initialize":
                result: dict[str, Any] = {
                    "serverInfo": {"name": "selftest-board", "version": "0.0.1"}
                }
            elif method == "tools/list":
                result = {"tools": [{"name": "get_state"}, {"name": "say_hello"}]}
            else:
                result = {}
            reply = json.dumps(
                {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
            ).encode()
            conn.sendall(b"\x81" + struct.pack(">B", len(reply)) + reply)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", nargs="?", help="ws:// 或 wss:// 地址")
    parser.add_argument("--probe", choices=["none", "mcp"], default="none",
                        help="none=只握手；mcp=加 initialize+tools/list 只读探测")
    parser.add_argument("--header", action="append", default=[],
                        metavar='"Name: value"', help="附加握手头，可重复")
    parser.add_argument("--connect-timeout", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--selftest", action="store_true",
                        help="本地起假 WS 服务自测（无需板子）")
    args = parser.parse_args()

    headers: dict[str, str] = {}
    for item in args.header:
        name, _, value = item.partition(":")
        if not value:
            parser.error(f"--header 需要 'Name: value' 格式，收到: {item!r}")
        headers[name.strip()] = value.strip()

    if args.selftest:
        listener = socket.create_server(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        ready = threading.Event()
        thread = threading.Thread(
            target=_selftest_server, args=(listener, ready), daemon=True
        )
        thread.start()
        ready.wait(2)
        url = f"ws://127.0.0.1:{port}/ws"
        print("(selftest 模式：连接本地假板子)")
        code = run_smoke(url, args.probe if args.probe != "none" else "mcp",
                         headers, args.connect_timeout, args.timeout)
        listener.close()
        return code

    if not args.url:
        parser.error("需要 ws:// 地址，或使用 --selftest")
    return run_smoke(args.url, args.probe, headers,
                     args.connect_timeout, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
