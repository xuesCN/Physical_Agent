# MomoAgent Physical Agent Driver

This is the current watch-side adapter for the MomoAgent arm. It supports a
deterministic mock profile and full or partial serial-hardware profiles while
keeping every physical command behind the normal Action Board, SafetyGate, and
watch execution path.

## Driver Contract

Two files are enough to connect a device to Physical Agent:

```text
physical_driver.yaml
driver.py
```

The manifest declares the adapter and validates configuration.
The driver implements `PhysicalDriver` and stays on the watch side.

## Capabilities in This Scaffold

- `observe`
- `home`
- `stop`
- `move_joint`
- `move_joints`
- `set_gripper`
- `open_gripper`
- `close_gripper`

## Suggested Config

```yaml
robots:
  momo_1:
    driver: ./examples/moce_arm
    execution_mode: simulation
    config:
      mode: mock
      timeout_s: 5

```

## How to Finish the Integration

1. Start with `physical-agent.yaml` in mock mode.
2. For a real partial arm, copy and calibrate `physical-agent.partial-hardware.yaml`.
3. Keep the driver on the watch side and retain bounded call timeouts.
4. Verify `observe` before enabling motion or gripper commands.
5. Review every Draft, add it to the Action Board, approve it when required,
   and let watch run SafetyGate before execution.

## Suggested Run Order

```bash
physical-agent watch --config examples/moce_arm/physical-agent.yaml
physical-agent run --config examples/moce_arm/physical-agent.yaml --task "observe"
physical-agent run --config examples/moce_arm/physical-agent.yaml --task "open gripper"
```
