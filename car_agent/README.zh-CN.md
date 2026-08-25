# car_agent 小车 driver

这是一个自包含的 Physical Agent 硬件包，用于连接运行 `car_agent` 固件的 Moce Level 0 小车。它只在 `watch` 侧建立 TCP 长连接；Chat、GUI、API 和 agent 仍然只生成动作提案，不能直接调用硬件。

> 当前验证状态：driver 已通过本机 scripted TCP fake、真实 asyncio socket 和 Watch/SafetyGate 集成测试；**尚未连接真实小车，也未完成真实运动验收**。

执行链路保持为：

```text
Chat / GUI / agent 提案
  -> SQLite pending action
  -> 人工审批（实机强制）
  -> watch
  -> SafetyGate
  -> CarAgentDriver.execute
  -> 小车固件
```

## 当前能力

- `observe`：读取运动、电机命令、watchdog 和 TOF 状态。
- `stop`：向固件发送停车命令。
- `drive_for(speed, duration_ms)`：在一个已经通过 SafetyGate 的动作内，按固定间隔续发 `drive`，到时或发生异常后发送 `stop`。

提交到仓库的样例配置**默认不发布 `drive_for`**。只有本地同时配置 `max_abs_speed` 与 `max_duration_ms`，并且已连接固件确实声明 `drive`，driver 才会发布运动能力。不要只填其中一项。

当前没有 `turn`、路径规划、闭环距离控制、自动避障或自动发现设备 IP。`speed` 是开环 PWM 命令，不是厘米每秒。固件的 `status` 字段不能作为运动真源；driver 使用 `moving` 和 `motor_cmd` 生成观察状态。

## 固件协议假设

这个版本严格绑定以下身份：

- TCP 长连接、UTF-8 NDJSON，一行一个请求/响应；默认端口 `8080`。
- `protocol: moce-physical-agent/v1`
- `device: moce-car`
- `project: car_agent`
- 方法：`health`、`capabilities`、`observe`、`execute`、`stop`。
- 运动 watchdog 为 `800 ms`；默认每 `250 ms` 续发一次 `drive`。

driver 会按响应 `id` 关联请求，忽略不匹配的额外响应；远端错误只信任稳定的 `error.code`。它不会自动重连或重放动作，以免在连接恢复后重复运动。

## 第一次连接：只观察和停车

仅在轮子离地、现场有人值守、物理断电手段可立即触达时进行。小车与上位机必须位于同一个可信 2.4GHz 网络。固件没有鉴权或 TLS；同一时刻只运行一个控制客户端。

1. 把 [physical-agent.yaml](./physical-agent.yaml) 中的 `REPLACE_WITH_CAR_IP` 换成小车当前 DHCP 地址。
2. 保持 `max_abs_speed` 和 `max_duration_ms` 注释状态。
3. 在仓库根目录初始化并检查 workspace：

```powershell
.\.venv\Scripts\physical-agent.exe init --config car_agent\physical-agent.yaml
.\.venv\Scripts\physical-agent.exe state-check --config car_agent\physical-agent.yaml
.\.venv\Scripts\physical-agent.exe doctor --config car_agent\physical-agent.yaml
```

打开并人工核对新建的 `car_agent/workspace/SAFETY.md`，确保它符合当前台架、电源和人员条件。不要沿用未经确认的默认安全文本。

4. 确认网络和现场条件后，单独启动 watch：

```powershell
.\.venv\Scripts\physical-agent.exe watch --config car_agent\physical-agent.yaml
```

5. 另开终端检查：

```powershell
.\.venv\Scripts\physical-agent.exe inspect --config car_agent\physical-agent.yaml
```

此阶段能力列表必须只有 `observe` 和 `stop`。连接握手会检查固件身份，并先发一次 `stop` 建立已停车基线。

## 轮空标定后启用有限运动

先用固件原生工具完成轮空标定，确定最低可用 PWM、方向、左右轮一致性和现场认可的单次最长时间。然后在本地配置中同时加入保守值，例如：

```yaml
max_abs_speed: 10
max_duration_ms: 250
```

重启 watch，再用 `inspect` 确认 `drive_for` 的 JSON Schema 和 `constraints.bounds` 与配置一致。`execution_mode: hardware` 会使每个实机动作都必须审批；driver 自身也将 `drive_for.requires_approval` 设为 `true`。

第一次运动仍应轮子离地，每次只批准一个很短的动作。任何返回夹限、有效速度不符、电机不可用、超时、断连或取消都会使动作失败，并触发一次最终 `stop` 尝试。drive 响应若超过动作的绝对截止时间，动作也会失败并立即排队停车；若停车结果无法确认，driver 会关闭连接并撤销运动能力，必须重新握手后才能再动。设备任务卡死时，物理运动仍可能超过请求时长，最终只能依靠 800 ms 固件 watchdog 或人工断电；软件停车和 watchdog 都不是硬件急停。

## 通过 Chat 提议动作

样例使用 `agent.planner: llm`；`fake/local` 只是“YAML 不覆盖模型”的占位值，本身不提供模型服务。先在 Dashboard 的 Settings 中填写实际 provider、model、base URL 与 key，保存到本地 workspace，并通过页面里的连接测试；不要把 key 写进这份 YAML 或提交到 Git。

只能选择下面一种运行方式，不能同时启动两个 watch：

1. 一体模式：不要运行前文的独立 watch，只启动带 watch 的 API，或使用默认内嵌 watch 的 GUI。

```powershell
.\.venv\Scripts\physical-agent.exe api --config car_agent\physical-agent.yaml --host 127.0.0.1 --port 8766 --watch
```

2. 分离模式：保留前文的独立 watch，再启动**不带** `--watch` 的 API，或使用 `gui --no-watch`。

```powershell
.\.venv\Scripts\physical-agent.exe api --config car_agent\physical-agent.yaml --host 127.0.0.1 --port 8766
# 或
.\.venv\Scripts\physical-agent.exe gui --config car_agent\physical-agent.yaml --no-watch
```

Chat 生成的是 proposal，不是硬件命令。检查参数和理由、完成实机审批后，只有 watch 才能经过 SafetyGate 调用 driver。未配置运动限值时，LLM 看不到 `drive_for`，因此不能合法提议运动。

## 还需要现场确认的信息

代码接入不依赖这些信息，但真机运动前仍需要：当前 IP、供电与断电方式、轮子离地固定方式、速度正负方向、最小稳定 PWM、保守最大 PWM、单动作时长上限、TOF 实测有效范围，以及一位能随时断电的现场值守人员。拿到这些信息后，下一阶段才是先连实机只测 `health/observe/stop`，再做轮空短时运动。
