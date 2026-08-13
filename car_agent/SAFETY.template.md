---
schema: physical-agent/safety/v1
owner: human
revision: 1
---

# Safety Policy

## Rules

```yaml
require_human_approval_for_real_hardware: true
allow_autonomous_execution: true
max_action_timeout_s: 30
forbid_duplicate_action_ids: true
```

## Agent Guidance

- Treat this Level 0 car as a wheels-up bench device only. Keep both wheels clear of the ground for every motion test.
- A human operator must remain present, supervise every action, and be able to disconnect physical power immediately.
- The device has no local obstacle-avoidance fallback. Do not interpret Agent reasoning or the watchdog as certified collision avoidance, an emergency stop, or permission for unattended operation.
- Interpret `tof_mm` only when both `tof_available` and `tof_valid` are true. An unavailable or invalid TOF reading means distance is unknown, never that the path is clear.
- Prefer the driver-derived `status`, `moving`, and `motor_cmd` state over the firmware raw `status`, which remains `idle` at Level 0.
- `speed` is an open-loop PWM command, not a physical velocity or a closed-loop speed target; there is no calibrated speed-to-distance correspondence.
- The watchdog only bounds how long an unrefreshed motor command can persist. It is not obstacle detection, a certified interlock, or a substitute for the operator's physical power cutoff.
