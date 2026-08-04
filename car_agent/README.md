# car_agent vehicle driver

This is a self-contained Physical Agent hardware bundle for a Moce Level 0 vehicle running the `car_agent` firmware. Only `watch` opens the persistent TCP connection. Chat, the GUI, the API, and the agent remain proposal producers and never call the hardware directly.

> Current verification status: the driver passes a local scripted TCP fake, real asyncio socket tests, and Watch/SafetyGate integration tests. It has **not yet connected to the physical vehicle or passed a physical motion test**.

The execution path remains:

```text
Chat / GUI / agent proposal
  -> SQLite pending action
  -> human approval (mandatory for hardware)
  -> watch
  -> SafetyGate
  -> CarAgentDriver.execute
  -> vehicle firmware
```

## Capabilities

- `observe` reads motion, the shared motor command, watchdog, and TOF state.
- `stop` sends the firmware stop command.
- `drive_for(speed, duration_ms)` renews firmware `drive` commands inside one SafetyGate-approved action, then sends `stop` on completion or failure.

The committed sample deliberately **does not publish `drive_for`**. Motion becomes available only when both `max_abs_speed` and `max_duration_ms` are configured locally and the connected firmware advertises `drive`. Never configure only one limit.

There is currently no `turn`, path planning, closed-loop distance control, automatic obstacle avoidance, or device discovery. `speed` is an open-loop PWM command, not a physical velocity. The firmware `status` field is not treated as motion truth; the driver derives state from `moving` and `motor_cmd`.

## Firmware contract

This version is intentionally strict about device identity:

- Persistent TCP with UTF-8 NDJSON, one request/response per line; default port `8080`.
- `protocol: moce-physical-agent/v1`
- `device: moce-car`
- `project: car_agent`
- Methods: `health`, `capabilities`, `observe`, `execute`, and `stop`.
- The motion watchdog is `800 ms`; the default drive renewal interval is `250 ms`.

Responses are correlated by `id`; unmatched extra responses are ignored. Only the stable remote `error.code` is trusted. The driver does not reconnect or replay actions automatically, avoiding duplicate motion after a connection recovery.

## First connection: observe and stop only

Perform this only with the wheels off the ground, an operator present, and immediate physical power removal available. The vehicle and controller must share the same trusted 2.4GHz network. The firmware provides no authentication or TLS, and only one control client may run at a time.

1. Replace `REPLACE_WITH_CAR_IP` in [physical-agent.yaml](./physical-agent.yaml) with the vehicle's current DHCP address.
2. Leave `max_abs_speed` and `max_duration_ms` commented out.
3. From the repository root, initialize and check the workspace:

```powershell
.\.venv\Scripts\physical-agent.exe init --config car_agent\physical-agent.yaml
.\.venv\Scripts\physical-agent.exe state-check --config car_agent\physical-agent.yaml
.\.venv\Scripts\physical-agent.exe doctor --config car_agent\physical-agent.yaml
```

Open and manually review the generated `car_agent/workspace/SAFETY.md` against the actual bench, power, and personnel conditions. Do not reuse unverified default safety text.

4. After confirming the network and physical setup, start watch in its own terminal:

```powershell
.\.venv\Scripts\physical-agent.exe watch --config car_agent\physical-agent.yaml
```

5. Inspect from another terminal:

```powershell
.\.venv\Scripts\physical-agent.exe inspect --config car_agent\physical-agent.yaml
```

At this stage the capability list must contain only `observe` and `stop`. The connection handshake validates firmware identity and sends `stop` before publishing the connected baseline.

## Enable bounded motion after wheels-up calibration

Use the firmware's native tooling first to determine the minimum stable PWM, direction, left/right consistency, and an operator-approved maximum action duration. Then add both conservative local limits, for example:

```yaml
max_abs_speed: 10
max_duration_ms: 250
```

Restart watch and use `inspect` to confirm that the `drive_for` JSON Schema and `constraints.bounds` match those values. `execution_mode: hardware` requires approval for every hardware action; the driver also declares `drive_for.requires_approval: true`.

Keep the wheels off the ground for the first motion test and approve only one short action at a time. Clamping, an unexpected effective speed, unavailable motors, timeout, disconnect, or cancellation fails the action and triggers a final `stop` attempt. A drive acknowledgement that exceeds the action's absolute deadline also fails and immediately queues a stop. If stop cannot be confirmed, the driver closes the connection and withdraws motion until a fresh handshake. A stalled device task can still make physical motion exceed the requested duration, leaving the 800 ms firmware watchdog or manual power removal as the final fallback; neither software stop nor the watchdog is a hardware emergency stop.

## Chat-proposed actions

The sample selects `agent.planner: llm`. `fake/local` only means that YAML does not override the model; it does not provide a model service. In Dashboard Settings, enter the real provider, model, base URL, and key, save them to the local workspace, and pass the connection test. Do not put the key in this YAML or commit it.

Choose exactly one execution layout; never start two watch executors:

1. Integrated mode: do not run the standalone watch shown above. Start the API with watch, or use the GUI's default embedded watch.

```powershell
.\.venv\Scripts\physical-agent.exe api --config car_agent\physical-agent.yaml --host 127.0.0.1 --port 8766 --watch
```

2. Split mode: keep the standalone watch and start the API **without** `--watch`, or use `gui --no-watch`.

```powershell
.\.venv\Scripts\physical-agent.exe api --config car_agent\physical-agent.yaml --host 127.0.0.1 --port 8766
# or
.\.venv\Scripts\physical-agent.exe gui --config car_agent\physical-agent.yaml --no-watch
```

Chat creates a proposal, not a hardware command. Review its parameters and rationale and approve the hardware action; only watch can pass it through SafetyGate and invoke the driver. With motion limits absent, the model cannot see or validly propose `drive_for`.

## Information still required for physical motion

The code does not need these facts to be completed, but motion does: current IP, power and disconnect method, wheels-up fixture, positive/negative direction, minimum stable PWM, conservative maximum PWM, per-action duration limit, measured TOF validity range, and an operator who can remove power immediately. Once available, the next stage is a physical `health/observe/stop` check before any short wheels-up motion.
