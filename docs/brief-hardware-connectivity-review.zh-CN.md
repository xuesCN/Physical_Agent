# 评估 brief：agent ↔ 硬件连接可行性检查

> 类型：评估 brief（非开工 brief，不解除 R0-R8 冻结，不实施任何 F5 条目）。
> 日期：2026-07-15。范围：transport / driver / watch 防护链路的代码现状核查，对照"电脑端 ↔ 舵机端"参考栈给出缺口与路线建议。

## 0. 结论先行

**连接能否顺利实现取决于走哪条路线**：智能端（WebSocket/MCP）与 vendor SDK 包装两条路线**今天就能通且已有实机验证**；直驱总线舵机（Feetech/Dynamixel 串口）在 F5.1 冻结中但方案已备好；CAN 总线完全未规划，是唯一需要从零新增的面。

## 1. 参考栈 ↔ 仓库现状映射

```
电脑端                          仓库对应                                状态
──────────────────────────────────────────────────────────────────────
控制程序          watch 执行循环 + PhysicalDriver 契约                  ✅ 成熟
                  (connect/observe/execute/health/heartbeat/halt
                   /on_transport_reconnected，drivers/base.py)
SDK 库            三条实现路径：
                  ① xiaozhi_mcp：WS + JSON-RPC(MCP tools/call)         ✅ 已实现+测试
                  ② moce_arm：importlib 加载 vendor SDK(MomoAgent)，    ✅ 已实机回归(D4)
                     SDK 内部走串口舵机总线
                  ③ feetech_arm(F5.1，LeRobot motors 方案)             ⏸ 冻结，仅有 PLAYBOOK 方案
串口/CAN 驱动     SerialTransport(pyserial，读写双超时+重连策略)        ✅ 串口有
                  WebSocketTransport(标准库自研 ws/wss)                 ✅
                  LoopbackTransport(测试)                              ✅
                  CAN                                                  ❌ 不存在
USB 适配器        OS 层；config 的 serial_port 指定(COM3//dev/ttyUSB0)  ✅ 配置面已留

舵机端（固件/协议解析/PID/编码器与电机）
                  刻意不在仓库实现——协议帧编解码留给设备固件或          ✅ 边界决策正确
                  vendor SDK（D2 决策：ServoBus 主动延后，F5.1 接管）
```

## 2. 现有通信协议清单（核实过代码）

| 协议 | 实现 | 载荷 | 用途 |
| --- | --- | --- | --- |
| WebSocket (RFC 6455, ws/wss) | `transport/websocket.py`，标准库 socket+ssl 自研握手/帧 | JSON-RPC 2.0 / MCP `tools/call` | xiaozhi 类智能端设备 |
| 串口 Serial | `transport/serial.py`，pyserial，默认 115200，读/写独立超时 | 由 driver/vendor SDK 决定（moce_arm→总线舵机协议） | 直连串口设备 |
| Loopback | `transport/loopback.py`，内存管道 | 任意 | 测试/mock |

未实现：CAN/CANopen、EtherCAT、Modbus、ROS(rosbridge WS，F5.2 冻结)、Feetech/Dynamixel 直驱 SDK(F5.1 冻结)。

## 3. watch 侧防御纵深（均已核实存在且有专项测试）

- 每类 driver 调用独立超时预算：action 30s / connect 10s / observe 10s / heartbeat 5s / halt 5s（`config.py`，W1）；execute 超时后 best-effort halt 该机器人。
- 心跳看门狗：连续失败阈值 3 → halt（D3.1）；不健康 robot 进 blocked 列表，claim 时跳过。
- 断线重连（W3）：`ReconnectPolicy` 默认关闭；重连中/断开时 execute **fail-fast、不排队、不重放旧动作**（安全语义正确）；重连后 `on_transport_reconnected` 钩子刷新握手/工具缓存。
- 执行权：`driver.execute` 全仓唯一调用点在 watch 循环（runtime.py:307），claim→Gate→执行每步间有 lease 复查（W6.1）。
- 测试覆盖：`test_transport_{serial,websocket,loopback}`、`test_driver_{contract,loader,manifest}`、`test_watch_timeouts`、`test_xiaozhi_mcp_*` 等专项齐全。

## 4. 缺口与风险

1. **F5.1 冻结**：参考栈中"SDK库→串口→总线舵机"直驱路径无 in-repo driver。PLAYBOOK 方案已备：`feetech-servo-sdk` 进 `[servo]` extra，sync write 目标位置，halt 写 Torque_Enable=0，全部总线读写 `to_thread`（W5），标定先行。触发条件=R8 收口+舵机到手。
2. **CAN 缺失**：若目标硬件是 CAN 总线（一体化关节电机等），需新增 `CanTransport`（python-can + SocketCAN/USB-CAN 适配器）+ 排期，工作量为全新 transport 级别。
3. **`my_hardware/` 仍是空 scaffold**：只有 observe 能力，自有硬件 driver 未起步。
4. **高频控制不适配当前模型**：watch tick+逐 action 过 Gate 是离散动作模型；kHz 级力控/遥操作需走 SPEC §0.1 预注册例外（会话粒度 gate+帧流专用通道），尚未实现。
5. **串口路线质量取决于 vendor SDK**：仓库不做协议帧编解码（刻意），阻塞 I/O 纪律（W5）依赖 driver 作者自觉+模板注释，无静态强制。

## 5. 路线建议（按就绪度排序）

- **路线 A｜智能端设备**（设备自带固件+协议栈，暴露 WS/MCP）：零缺口，照 `docs/xiaozhi-driver-tutorial` 走即可。✅ 现在可用
- **路线 B｜vendor SDK 包装**（moce_arm 模式）：为自有硬件写 driver，把厂商 SDK 当"SDK库"层；遵守 W5（to_thread/超时）+ bringup checklist。✅ 现在可用，工作量中等
- **路线 C｜直驱总线舵机**：等 R8 收口后解冻 F5.1；届时按 PLAYBOOK 既有方案实施，不要提前另起炉灶。⏸
- **路线 D｜CAN 设备**：需先在 SPEC §4 立新条目（transport 级），建议 R8 后与 F5.1 一并评审。❌ 未规划

## 6. 验收（本 brief 的核查方式）

- [x] `drivers/base.py` 契约、三个 transport、xiaozhi/moce_arm/my_hardware driver 逐文件读过
- [x] W1/W3/D3/W6.1 防护在 `config.py`/`runtime.py`/`transport/base.py` 中逐项定位
- [x] `driver.execute` 唯一调用点 grep 复核
- [x] PLAYBOOK F5.1/F5.2/W5 条目与冻结状态核对

## 范围外

- 不实施 F5.1/F5.2/CAN；不修改任何生产代码；不解除冻结。
- 高频流式控制的例外通道设计另行立项。
